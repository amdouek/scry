# scry

> *Peer into any Python codebase. Discover structure, extract files, export for LLM parsing.*

**scry** is a zero-dependency, single-file CLI tool that auto-discovers
your Python project structure and lets you selectively export files for
sharing -- in LLM chat sessions, code reviews, documentation, or
anywhere else you need a clean, readable snapshot of your codebase.

### Via pip
```bash
pip install cli-scry
```

### Via pipx
```bash
pipx install cli-scry
```

### Direct download
```bash
curl -O https://raw.githubusercontent.com/amdouek/scry/main/scry/cli.py
python cli.py --help
```

> Note: The PyPI package is `cli-scry` (the name `scry` was
> already taken by an unrelated package). The CLI command is simply
> `scry`.

## Why?
Modern coding increasingly involves pasting code into LLM
conversations, sharing project subsets with collaborators, or
extracting specific modules for targeted code review. 
The typical workflow (manually copying files, remembering paths, 
stitching things together) is tedious and can be error-prone.

`scry` simplifies this! Point to any Python project and it
will automatically discover packages, modules, config files, and project 
structure. Then export exactly the slice you need, in a format optimised for
the recipient (be it human or machine).

> **Due credit** -- this tool was heavily inspired by the excellent [repomix](https://github.com/yamadashy/repomix) tool. Where `repomix` is a feature-rich, 
> comprehensive solution, `scry` is deliberately minimal: No dependencies, 
> single-file, Python-native and designed for quick, selective 
> exports as well as full-repo dumps.

## Quick Start
```bash
# See what scry discovers in your project
scry --list-modules

# List every file (not just Python)
scry --list-files

# View core files + project overview in terminal
scry

# Export core files + project overview
scry -o core.txt

# Export a specific module
scry --module models

# Export only files you've changed since last commit
scry --changed

# Export everything as LLM-optimised XML
scry --all --format xml -o codebase.xml
# or
scry --all -o codebase.xml    # Auto-detects extension 

# Export specific files
scry --files src/core.py config/defaults.yaml tests/test_core.py
```

## Features

### Auto-Discovery
`scry` understands Python project conventions out of the box:

- Flat layout (`mypackage/` in project root)
- Src layout (`src/mypackage/`)
- Subpackages (automatically grouped as modules)
- Special directories (`tests/`, `scripts/`, `examples/`, etc.)
- Core project files (`pyproject.toml`, `README.md`, `requirements.txt`, etc.)

You don't have to configure anything - just run it for your project!

### Selective Export
```bash
scry --module models          # One module
scry --module models training # Multiple modules
scry --files src/config.yaml  # Specific files
scry --changed                # Git-changed files only
scry --all                    # Everything
```

### Secret Detection
Before every export, scry scans for potential secrets (API keys,
tokens, private keys, database credentials, and other sensitive
patterns). Warnings are displayed before any output is written.

**IMPORTANTLY**, `scry` does NOT automatically prevent secrets
from appearing in the output. The output warnings require acknowledgement,
but users MUST take care to ensure that sensitive info is not shared.

An example warning:

```
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  POTENTIAL SECRETS DETECTED
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

  config/settings.py:
    Line   42: Generic API Key — Generic API key assignment detected
    Line   67: Database URL — Database connection string with credentials

  Found 2 potential secret(s) across 1 file(s).
  Review the above before sharing this export.
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
```

Detected patterns include:
- AWS access keys and secret keys
- GitHub, GitLab, and Slack tokens
- Stripe, SendGrid, and Heroku API keys
- Private key blocks (RSA, EC, DSA, etc.)
- Database connection strings with embedded credentials
- Generic `password=`, `secret=`, `api_key=` assignments
- JWT tokens
- Sensitive filenames (`.env`, `.pem`, `.key`, `credentials.*`)

Use --no-scan to skip if needed (but **use with caution!**).

## Output Formats
**Text** (default) - Markdown-style with fenced code blocks:
```bash
scry --module models -o export.txt
```

**XML** - Structured, `CDATA`-wrapped, and optimised for LLM parsing:
```bash
scry --all --format xml -o codebase.xml
# or
scry --all -o codebase.xml
```

The XML format uses `<file path="..." language="..." size="...">`
elements with CDATA sections, which avoids the nested-backtick
problems that can occur when LLMs parse markdown.

## Full Project Listing
Discover every file in your project, not just Python modules:
```bash
# List all files with sizes, grouped by directory
scry --list-files

# Filter to specific extensions
scry --list-files --ext .yaml .yml .toml .json
```

The output includes a per-extension summary table, which is
particularly helpful to spot any parts of your repo that are too chunky!

```
Extension         Count   Total Size
───────────────   ──────   ────────────
.py                  31       42.3 KB
.yaml                 3        2.8 KB
.toml                 1        1.3 KB
───────────────   ──────   ────────────
TOTAL                35       46.2 KB
```

## Optional Configuration
`scry` is designed to work without any configuration. However,
if you want fine-grained control, you can generate a config file:
```bash
scry --init-config
```

This creates `.scry.toml` in your project root, which is pre-populated
with your project structure (as discovered by `scry`). You can use this
to customise core files, ignore patterns, default modules, etc.

```toml
[scry]
project_name = "myproject"
core_files = ["pyproject.toml", "README.md"]
default_module = "utils"
tree_depth = 4

ignore_dirs = [".git", "__pycache__", "venv", "node_modules"]
ignore_patterns = ["*.egg-info", "*.pyc"]
extensions = [".py"]
```

## Common workflows

### Starting an LLM chat session
```bash
# Give the LLM your project overview and the module you're working on
scry --module embeddings -o context.txt
# Then paste or upload context.txt into your chat
```

### Debugging with an LLM
```bash
# Export only what you've changed (minimal, focused context)
scry --changed
```

### Full codebase export for deep refactoring
```bash
# XML format for best LLM parsing
scry --all --format xml -o codebase.xml
```

### Exploring an unfamiliar project
```bash
# What modules exist?
scry --list-modules

# What non-Python files are there?
scry --list-files --ext .yaml .json .toml .cfg

# Export the module you want to understand
scry --module data_processing
```

## How does `scry` work?
`scry` performs the following steps:
1. **Detect project root** and load `.scry.toml` if present;
2. **Discover source packages** by checking `src/` layout, then flat layout;
3. **Map subpackages to module names** (each subdirectory with .py files becomes a selectable module);
4. **Detect core files** (`pyproject.toml`, `README.md`, etc.);
5. **Scan for secrets** before any export;
6. **Format and output** in the requested format (currently supports txt and xml).

## Requirements
- Python 3.10+
- **Zero dependencies** - `scry` is deliberately lightweight; we use only the standard Python library
- Optional: `tomli` for `.scry.toml` support on Python <3.11