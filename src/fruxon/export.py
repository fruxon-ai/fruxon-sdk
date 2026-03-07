"""Export a multi-file Python agent project into a single consolidated file.

Uses Python's ast module to trace local imports from an entry point,
then inlines all discovered local modules into one readable file.
Supports auto-detection of agent entry points by scanning for framework imports.
"""

import ast
import sys
from pathlib import Path

from fruxon.exceptions import MultipleAgentsError as MultipleAgentsError

# Known agent framework module prefixes. A file that imports any of these
# is considered an agent-related file.
AGENT_FRAMEWORKS = [
    "langgraph",
    "langchain",
    "langchain_core",
    "langchain_community",
    "langchain_openai",
    "langchain_anthropic",
    "langchain_google",
    "crewai",
    "autogen",
    "google.adk",
    "google.genai",
    "smolagents",
    "llama_index",
    "haystack",
    "semantic_kernel",
    "pydantic_ai",
    "agno",
    "openai_agents",
]

# Directories to skip when scanning for .py files
SKIP_DIRS = {
    "venv",
    ".venv",
    "env",
    ".env",
    "node_modules",
    "__pycache__",
    ".git",
    ".tox",
    ".nox",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
    "tests",
    "test",
    "build",
    "dist",
    ".eggs",
}


def find_project_root(entry_file: Path) -> Path:
    """Find the project root by looking for common markers."""
    current = entry_file.parent.resolve()
    markers = {"pyproject.toml", "setup.py", "setup.cfg", ".git"}
    while current != current.parent:
        if any((current / m).exists() for m in markers):
            return current
        current = current.parent
    return entry_file.parent.resolve()


def resolve_import(module_name: str, project_root: Path, source_file: Path) -> Path | None:
    """Resolve an import name to a local file path, or None if it's third-party."""
    parts = module_name.split(".")

    # Try as a module file relative to project root
    for base in [project_root, project_root / "src"]:
        # Try direct file: foo.bar -> foo/bar.py
        candidate = base / Path(*parts).with_suffix(".py")
        if candidate.exists():
            return candidate.resolve()

        # Try package __init__: foo.bar -> foo/bar/__init__.py
        candidate = base / Path(*parts) / "__init__.py"
        if candidate.exists():
            return candidate.resolve()

    # Try relative to source file's directory
    source_dir = source_file.parent
    candidate = source_dir / Path(*parts).with_suffix(".py")
    if candidate.exists():
        return candidate.resolve()

    return None


def extract_imports(source: str, filepath: Path, project_root: Path) -> list[Path]:
    """Parse a Python file and return paths of local imports."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    local_paths = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                resolved = resolve_import(alias.name, project_root, filepath)
                if resolved:
                    local_paths.append(resolved)

        elif isinstance(node, ast.ImportFrom):
            if node.module:
                resolved = resolve_import(node.module, project_root, filepath)
                if resolved:
                    local_paths.append(resolved)

    return local_paths


def collect_files(entry_file: Path, project_root: Path) -> list[Path]:
    """Trace all local dependencies from the entry file using BFS."""
    entry_resolved = entry_file.resolve()
    visited: set[Path] = set()
    order: list[Path] = []
    queue = [entry_resolved]

    while queue:
        current = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)

        try:
            source = current.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        deps = extract_imports(source, current, project_root)
        for dep in deps:
            if dep not in visited:
                queue.append(dep)

        order.append(current)

    return order


def build_export(entry_file: Path, project_root: Path) -> str:
    """Build a single consolidated file from the entry point and its local deps."""
    files = collect_files(entry_file, project_root)

    if not files:
        return entry_file.read_text(encoding="utf-8")

    parts: list[str] = []
    parts.append(f"# Fruxon Export - consolidated from {len(files)} file(s)")
    parts.append(f"# Entry point: {entry_file.name}")
    parts.append(f"# Project root: {project_root}")
    parts.append("")

    # Dependencies first, entry file last
    deps = [f for f in files if f != files[0]]
    entry = files[0]

    for filepath in deps:
        try:
            source = filepath.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        relative = filepath.relative_to(project_root) if filepath.is_relative_to(project_root) else filepath
        parts.append(f"# {'=' * 60}")
        parts.append(f"# Source: {relative}")
        parts.append(f"# {'=' * 60}")
        parts.append("")
        parts.append(source.rstrip())
        parts.append("")

    # Entry file last
    try:
        source = entry.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        source = ""

    relative = entry.relative_to(project_root) if entry.is_relative_to(project_root) else entry
    parts.append(f"# {'=' * 60}")
    parts.append(f"# Entry point: {relative}")
    parts.append(f"# {'=' * 60}")
    parts.append("")
    parts.append(source.rstrip())
    parts.append("")

    return "\n".join(parts)


def scan_py_files(directory: Path) -> list[Path]:
    """Recursively find all .py files in directory, skipping irrelevant dirs."""
    py_files = []
    for item in sorted(directory.iterdir()):
        if item.is_dir():
            if item.name in SKIP_DIRS or item.name.startswith("."):
                continue
            py_files.extend(scan_py_files(item))
        elif item.is_file() and item.suffix == ".py" and item.name != "__init__.py":
            py_files.append(item.resolve())
    return py_files


def get_all_imports(source: str) -> list[str]:
    """Extract all import module names from source code."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return modules


def has_framework_import(source: str) -> str | None:
    """Check if source imports a known agent framework. Returns framework name or None."""
    modules = get_all_imports(source)
    for module in modules:
        for framework in AGENT_FRAMEWORKS:
            if module == framework or module.startswith(framework + "."):
                return framework
    return None


def find_agent_entry_points(project_root: Path) -> list[tuple[Path, str]]:
    """Scan project for files that import agent frameworks and find entry points.

    Returns list of (file_path, framework_name) for detected entry points.
    An entry point is a framework-importing file that is NOT imported by
    other framework-importing files in the project.
    """
    py_files = scan_py_files(project_root)
    # Also check src/ if it exists
    src_dir = project_root / "src"
    if src_dir.is_dir() and src_dir not in [project_root]:
        py_files.extend(scan_py_files(src_dir))

    # Find all files that import a framework
    framework_files: list[tuple[Path, str, str]] = []  # (path, framework, source)
    for filepath in py_files:
        try:
            source = filepath.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        framework = has_framework_import(source)
        if framework:
            framework_files.append((filepath, framework, source))

    if not framework_files:
        return []

    # Build a set of files that are imported by other framework files
    imported_by_others: set[Path] = set()
    for filepath, _, source in framework_files:
        local_deps = extract_imports(source, filepath, project_root)
        for dep in local_deps:
            if any(dep == fw_file for fw_file, _, _ in framework_files):
                imported_by_others.add(dep)

    # Entry points = framework files NOT imported by other framework files
    entry_points = [(fp, fw) for fp, fw, _ in framework_files if fp not in imported_by_others]

    # If all framework files import each other (cycle), return all of them
    if not entry_points:
        entry_points = [(fp, fw) for fp, fw, _ in framework_files]

    return entry_points


def export_agent(entry_path: str | None = None, output_path: str | None = None) -> str:
    """Main export function. Returns the consolidated source and optionally writes to file.

    If entry_path is None, auto-detects the agent entry point by scanning
    for framework imports. Raises SystemExit on errors.
    """
    if entry_path:
        entry_file = Path(entry_path).resolve()

        if not entry_file.exists():
            print(f"Error: File not found: {entry_file}", file=sys.stderr)
            raise SystemExit(1)

        if not entry_file.suffix == ".py":
            print(f"Error: Entry point must be a .py file, got: {entry_file.suffix}", file=sys.stderr)
            raise SystemExit(1)

        project_root = find_project_root(entry_file)
    else:
        # Auto-detect mode
        project_root = find_project_root(Path.cwd() / "dummy.py")
        entry_points = find_agent_entry_points(project_root)

        if not entry_points:
            print(
                "Error: No agent framework detected. "
                "Make sure you're in a directory with Python agent files, "
                "or specify the entry point: fruxon export <file.py>",
                file=sys.stderr,
            )
            raise SystemExit(1)

        if len(entry_points) == 1:
            entry_file = entry_points[0][0]
            framework = entry_points[0][1]
            print(f"Detected {framework} agent in {entry_file.relative_to(project_root)}", file=sys.stderr)
        else:
            # Multiple entry points found — let caller handle selection
            print("Multiple agents detected:", file=sys.stderr)
            for i, (fp, fw) in enumerate(entry_points, 1):
                relative = fp.relative_to(project_root) if fp.is_relative_to(project_root) else fp
                print(f"  {i}. {relative} ({fw})", file=sys.stderr)
            raise MultipleAgentsError(entry_points)

    result = build_export(entry_file, project_root)

    if output_path:
        out = Path(output_path)
        out.write_text(result, encoding="utf-8")
        print(f"Exported to {out}", file=sys.stderr)

    return result
