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
# Auto-detect agent and copy to clipboard
fruxon export --copy

# Auto-detect and print to stdout
fruxon export

# Write to file
fruxon export -o export.py

# Explicit entry point (if auto-detect picks the wrong file)
fruxon export graph.py --copy
```

**How it works:**
1. Scans your project for agent framework imports (LangGraph, CrewAI, etc.)
2. Auto-detects the entry point — if multiple agents exist, prompts you to choose
3. Traces all local imports using Python's AST (skips third-party packages)
4. Outputs a single consolidated file with all local code and source markers

## Credits

Built by [Fruxon](https://fruxon.com).
