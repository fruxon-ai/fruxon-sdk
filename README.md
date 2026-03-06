# fruxon

![PyPI version](https://img.shields.io/pypi/v/fruxon.svg)

The Fruxon SDK is a lightweight Python client for integrating with the [Fruxon](https://fruxon.com) platform.

* PyPI package: https://pypi.org/project/fruxon/
* Free software: MIT License

## Installation

```bash
pip install fruxon
```

## Features

### `fruxon export` — Consolidate multi-file agents

Export a multi-file Python agent project into a single file for importing into Fruxon.

Works with any Python framework: LangChain, LangGraph, CrewAI, Google ADK, AutoGen, and more.

```bash
# Print consolidated output to stdout
fruxon export graph.py

# Copy to clipboard
fruxon export graph.py --copy

# Write to file
fruxon export my_agent/main.py -o export.py
```

**How it works:**
1. Parses the entry point file using Python's AST
2. Traces all local imports (skips third-party packages like `langchain`, `crewai`, etc.)
3. Recursively collects all local dependency files
4. Outputs a single consolidated file with all local code and source markers

## Credits

Built by [Fruxon](https://fruxon.com).
