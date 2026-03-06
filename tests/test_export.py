"""Tests for the fruxon export module."""

import textwrap

import pytest

from fruxon.export import (
    MultipleAgentsError,
    build_export,
    collect_files,
    export_agent,
    extract_imports,
    find_agent_entry_points,
    find_project_root,
    get_all_imports,
    has_framework_import,
    resolve_import,
    scan_py_files,
)


@pytest.fixture
def tmp_project(tmp_path):
    """Create a minimal multi-file Python project."""
    # Project root marker
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'\n")

    # Entry point
    (tmp_path / "graph.py").write_text(
        textwrap.dedent("""\
            from langgraph.graph import StateGraph
            from tools import search_tool
            from agents.researcher import ResearchAgent

            graph = StateGraph()
            graph.add_node("search", search_tool)
            graph.add_node("research", ResearchAgent)
            graph.add_edge("search", "research")
        """)
    )

    # Local module
    (tmp_path / "tools.py").write_text(
        textwrap.dedent("""\
            from utils.helpers import format_result

            def search_tool(query):
                return format_result(query)
        """)
    )

    # Nested local module
    (tmp_path / "utils").mkdir()
    (tmp_path / "utils" / "__init__.py").write_text("")
    (tmp_path / "utils" / "helpers.py").write_text(
        textwrap.dedent("""\
            def format_result(text):
                return text.strip()
        """)
    )

    # Sub-package
    (tmp_path / "agents").mkdir()
    (tmp_path / "agents" / "__init__.py").write_text("")
    (tmp_path / "agents" / "researcher.py").write_text(
        textwrap.dedent("""\
            class ResearchAgent:
                def run(self):
                    return "research"
        """)
    )

    return tmp_path


class TestFindProjectRoot:
    def test_finds_pyproject_toml(self, tmp_project):
        entry = tmp_project / "graph.py"
        root = find_project_root(entry)
        assert root == tmp_project

    def test_finds_git_marker(self, tmp_path):
        (tmp_path / ".git").mkdir()
        sub = tmp_path / "src"
        sub.mkdir()
        entry = sub / "main.py"
        entry.write_text("x = 1")
        root = find_project_root(entry)
        assert root == tmp_path

    def test_falls_back_to_parent_dir(self, tmp_path):
        entry = tmp_path / "script.py"
        entry.write_text("x = 1")
        root = find_project_root(entry)
        assert root == tmp_path


class TestResolveImport:
    def test_resolves_local_module(self, tmp_project):
        result = resolve_import("tools", tmp_project, tmp_project / "graph.py")
        assert result == (tmp_project / "tools.py").resolve()

    def test_resolves_nested_module(self, tmp_project):
        result = resolve_import("utils.helpers", tmp_project, tmp_project / "graph.py")
        assert result == (tmp_project / "utils" / "helpers.py").resolve()

    def test_resolves_package_init(self, tmp_project):
        result = resolve_import("utils", tmp_project, tmp_project / "graph.py")
        assert result == (tmp_project / "utils" / "__init__.py").resolve()

    def test_returns_none_for_third_party(self, tmp_project):
        result = resolve_import("langgraph.graph", tmp_project, tmp_project / "graph.py")
        assert result is None

    def test_returns_none_for_nonexistent(self, tmp_project):
        result = resolve_import("nonexistent", tmp_project, tmp_project / "graph.py")
        assert result is None


class TestExtractImports:
    def test_extracts_local_imports(self, tmp_project):
        source = (tmp_project / "graph.py").read_text()
        paths = extract_imports(source, tmp_project / "graph.py", tmp_project)
        filenames = {p.name for p in paths}
        assert "tools.py" in filenames
        assert "researcher.py" in filenames

    def test_skips_third_party(self, tmp_project):
        source = (tmp_project / "graph.py").read_text()
        paths = extract_imports(source, tmp_project / "graph.py", tmp_project)
        # langgraph is third-party, should not appear
        for p in paths:
            assert "langgraph" not in str(p)

    def test_handles_syntax_error(self, tmp_project):
        paths = extract_imports("def broken(", tmp_project / "bad.py", tmp_project)
        assert paths == []

    def test_extracts_from_nested_file(self, tmp_project):
        source = (tmp_project / "tools.py").read_text()
        paths = extract_imports(source, tmp_project / "tools.py", tmp_project)
        filenames = {p.name for p in paths}
        assert "helpers.py" in filenames


class TestCollectFiles:
    def test_collects_all_local_files(self, tmp_project):
        entry = tmp_project / "graph.py"
        files = collect_files(entry, tmp_project)
        filenames = {f.name for f in files}
        assert "graph.py" in filenames
        assert "tools.py" in filenames
        assert "researcher.py" in filenames
        assert "helpers.py" in filenames

    def test_entry_is_first(self, tmp_project):
        entry = tmp_project / "graph.py"
        files = collect_files(entry, tmp_project)
        assert files[0] == entry.resolve()

    def test_no_duplicates(self, tmp_project):
        entry = tmp_project / "graph.py"
        files = collect_files(entry, tmp_project)
        assert len(files) == len(set(files))

    def test_single_file_no_local_imports(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("")
        entry = tmp_path / "simple.py"
        entry.write_text("import os\nprint('hello')\n")
        files = collect_files(entry, tmp_path)
        assert len(files) == 1
        assert files[0] == entry.resolve()


class TestBuildExport:
    def test_output_contains_all_sources(self, tmp_project):
        entry = tmp_project / "graph.py"
        result = build_export(entry, tmp_project)
        assert "search_tool" in result
        assert "ResearchAgent" in result
        assert "format_result" in result
        assert "StateGraph" in result

    def test_output_has_header(self, tmp_project):
        entry = tmp_project / "graph.py"
        result = build_export(entry, tmp_project)
        assert "Fruxon Export" in result

    def test_output_has_source_markers(self, tmp_project):
        entry = tmp_project / "graph.py"
        result = build_export(entry, tmp_project)
        assert "Source:" in result
        assert "Entry point:" in result

    def test_entry_point_is_last(self, tmp_project):
        entry = tmp_project / "graph.py"
        result = build_export(entry, tmp_project)
        lines = result.strip().split("\n")
        # Find the last "Entry point:" marker
        entry_markers = [i for i, line in enumerate(lines) if "Entry point:" in line]
        source_markers = [i for i, line in enumerate(lines) if "Source:" in line]
        if source_markers:
            assert entry_markers[-1] > source_markers[-1]

    def test_single_file_export(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("")
        entry = tmp_path / "agent.py"
        entry.write_text("import langchain\nprint('agent')\n")
        result = build_export(entry, tmp_path)
        assert "print('agent')" in result
        assert "Fruxon Export" in result


class TestScanPyFiles:
    def test_finds_py_files(self, tmp_project):
        files = scan_py_files(tmp_project)
        filenames = {f.name for f in files}
        assert "graph.py" in filenames
        assert "tools.py" in filenames
        assert "researcher.py" in filenames
        assert "helpers.py" in filenames

    def test_skips_init_files(self, tmp_project):
        files = scan_py_files(tmp_project)
        filenames = {f.name for f in files}
        assert "__init__.py" not in filenames

    def test_skips_test_dirs(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("")
        (tmp_path / "agent.py").write_text("x = 1")
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_agent.py").write_text("x = 1")
        files = scan_py_files(tmp_path)
        filenames = {f.name for f in files}
        assert "agent.py" in filenames
        assert "test_agent.py" not in filenames

    def test_skips_venv(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("")
        (tmp_path / "agent.py").write_text("x = 1")
        (tmp_path / ".venv").mkdir()
        (tmp_path / ".venv" / "lib.py").write_text("x = 1")
        files = scan_py_files(tmp_path)
        filenames = {f.name for f in files}
        assert "agent.py" in filenames
        assert "lib.py" not in filenames


class TestGetAllImports:
    def test_extracts_imports(self):
        source = "import os\nfrom pathlib import Path\nfrom langgraph.graph import StateGraph"
        modules = get_all_imports(source)
        assert "os" in modules
        assert "pathlib" in modules
        assert "langgraph.graph" in modules

    def test_handles_syntax_error(self):
        assert get_all_imports("def broken(") == []


class TestHasFrameworkImport:
    def test_detects_langgraph(self):
        assert has_framework_import("from langgraph.graph import StateGraph") == "langgraph"

    def test_detects_langchain(self):
        assert has_framework_import("from langchain_openai import ChatOpenAI") == "langchain_openai"

    def test_detects_crewai(self):
        assert has_framework_import("from crewai import Crew, Agent") == "crewai"

    def test_detects_google_adk(self):
        assert has_framework_import("from google.adk import Agent") == "google.adk"

    def test_returns_none_for_no_framework(self):
        assert has_framework_import("import os\nimport json") is None

    def test_returns_none_for_empty(self):
        assert has_framework_import("") is None


class TestFindAgentEntryPoints:
    def test_finds_single_entry_point(self, tmp_project):
        """graph.py imports langgraph, tools.py does not — graph.py is the entry point."""
        entry_points = find_agent_entry_points(tmp_project)
        assert len(entry_points) == 1
        assert entry_points[0][0].name == "graph.py"
        assert entry_points[0][1] == "langgraph"

    def test_finds_no_entry_points_in_empty_project(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("")
        (tmp_path / "utils.py").write_text("import os\ndef helper(): pass")
        entry_points = find_agent_entry_points(tmp_path)
        assert entry_points == []

    def test_finds_multiple_entry_points(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("")
        (tmp_path / "agent_a.py").write_text("from langgraph.graph import StateGraph\ngraph_a = StateGraph()")
        (tmp_path / "agent_b.py").write_text("from crewai import Crew\ncrew = Crew()")
        entry_points = find_agent_entry_points(tmp_path)
        assert len(entry_points) == 2
        names = {ep[0].name for ep in entry_points}
        assert "agent_a.py" in names
        assert "agent_b.py" in names

    def test_framework_file_imported_by_another_is_not_entry(self, tmp_path):
        """If agent.py imports tools.py and both use langchain, only agent.py is entry."""
        (tmp_path / "pyproject.toml").write_text("")
        (tmp_path / "agent.py").write_text(
            "from langchain_openai import ChatOpenAI\nfrom tools import my_tool\nllm = ChatOpenAI()"
        )
        (tmp_path / "tools.py").write_text(
            "from langchain_community.tools import TavilySearch\nmy_tool = TavilySearch()"
        )
        entry_points = find_agent_entry_points(tmp_path)
        assert len(entry_points) == 1
        assert entry_points[0][0].name == "agent.py"

    def test_excludes_test_directory(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("")
        (tmp_path / "agent.py").write_text("from langgraph.graph import StateGraph")
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_agent.py").write_text("from langgraph.graph import StateGraph")
        entry_points = find_agent_entry_points(tmp_path)
        assert len(entry_points) == 1
        assert entry_points[0][0].name == "agent.py"


class TestExportAgentAutoDetect:
    def test_auto_detect_single_agent(self, tmp_project, monkeypatch):
        """Auto-detect should find and export the langgraph agent."""
        monkeypatch.chdir(tmp_project)
        result = export_agent()
        assert "Fruxon Export" in result
        assert "StateGraph" in result
        assert "search_tool" in result

    def test_auto_detect_no_agent_raises(self, tmp_path, monkeypatch):
        (tmp_path / "pyproject.toml").write_text("")
        (tmp_path / "utils.py").write_text("import os")
        monkeypatch.chdir(tmp_path)
        with pytest.raises(SystemExit):
            export_agent()

    def test_auto_detect_multiple_agents_raises(self, tmp_path, monkeypatch):
        (tmp_path / "pyproject.toml").write_text("")
        (tmp_path / "agent_a.py").write_text("from langgraph.graph import StateGraph")
        (tmp_path / "agent_b.py").write_text("from crewai import Crew")
        monkeypatch.chdir(tmp_path)
        with pytest.raises(MultipleAgentsError) as exc_info:
            export_agent()
        assert len(exc_info.value.entry_points) == 2

    def test_explicit_entry_still_works(self, tmp_project):
        result = export_agent(str(tmp_project / "graph.py"))
        assert "Fruxon Export" in result
        assert "StateGraph" in result
