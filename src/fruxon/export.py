"""Export a multi-file Python agent project into a single consolidated file.

Uses Python's ast module to trace local imports from an entry point,
then inlines all discovered local modules into one readable file.
"""

import ast
import sys
from pathlib import Path


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


def export_agent(entry_path: str, output_path: str | None = None) -> str:
    """Main export function. Returns the consolidated source and optionally writes to file."""
    entry_file = Path(entry_path).resolve()

    if not entry_file.exists():
        print(f"Error: File not found: {entry_file}", file=sys.stderr)
        raise SystemExit(1)

    if not entry_file.suffix == ".py":
        print(f"Error: Entry point must be a .py file, got: {entry_file.suffix}", file=sys.stderr)
        raise SystemExit(1)

    project_root = find_project_root(entry_file)
    result = build_export(entry_file, project_root)

    if output_path:
        out = Path(output_path)
        out.write_text(result, encoding="utf-8")
        print(f"Exported to {out}")

    return result
