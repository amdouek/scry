# scry

> *Peer into any codebase. Discover structure, extract files, export for code review and LLM parsing.*

**scry** is a zero-dependency, single-file CLI tool that auto-discovers
project structure and lets you selectively export files for sharing:
In LLM chat sessions, code reviews, documentation, or
anywhere else you need a clean, readable snapshot of your codebase.

> [!NOTE]
> As of v0.1.4, the `--include-ext` flag allows you to export codebases that
> contain multiple languages. This can be performed on a per-run 
> basis (`scry --list-modules --include-ext .R .sql`), or configured to 
> permanently detect other extensions in the `.scry.toml` file 
> created by `--init-config`:
>
> ```toml
> [scry]
> extensions = [".py", ".R", ".sql", ".sh"]
> ```


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

`scry` simplifies this! Point to any project root (Python, R, multi-language
codebases, etc.) and it will automatically discover packages, modules,
config files, and project structure. Then export exactly the slice you
need, in a format optimised for the recipient (be it human or machine).

> [!TIP]
> This tool was heavily inspired by the excellent [repomix](https://github.com/yamadashy/repomix) tool. 
> Where `repomix` is a feature-rich, comprehensive solution, `scry` is deliberately minimal: 
> No dependencies, single-file, Python-native and designed for quick, selective 
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

# Include non-Python files in discovery
scry --list-modules --include-ext .R .sql

# Perform an export dry-run
scry --all --dry-run
```

## CLI Reference

> [!NOTE]
> Single-letter short flags can be chained (e.g., `-a -f core.py` or `-cf core.py`), but multi-letter short flags (e.g., `-lm`, `-nt`) must be provided separately. 

### Selection Modes (Mutually exclusive)

| Flag | Short | Description |
|------|-------|-------------|
| `--module MODULE [...]` | `-m` | Export one or more modules (use `--list-modules` to see available) |
| `--changed` | `-c` | Export git-changed files only (staged, unstaged, and untracked) |
| `--all` | `-a` | Export all discovered files |

### Modifiers (Combinable with any selection mode)

| Flag | Short | Description |
|------|-------|-------------|
| `--files FILE [...]` | `-f` | Add specific files to the export |
| `--exclude PATTERN [...]` | `-x` | Exclude files matching names or glob patterns (e.g. `"*.lock"`, `"tests/*"`) |
| `--include-ext EXT [...]` | `-i` | Include additional file extensions in discovery (e.g. `.R`, `.sql`) |

### Output Options

| Flag | Short | Description |
|------|-------|-------------|
| `--output FILE` | `-o` | Write output to a file (default: print to stdout) |
| `--format {txt,xml}` | | Output format: `txt` (markdown-style) or `xml` (default: `txt`). Auto-detected from `-o` filename. |
| `--no-tree` | `-nt` | Omit the directory tree from output |
| `--tree-depth N` | | Override the directory tree depth (default: 3) |

### Discovery & Inspection

| Flag | Short | Description |
|------|-------|-------------|
| `--list-modules` | `-lm` | List all auto-discovered modules and exit |
| `--list-files` | `-lf` | List all project files grouped by directory and exit |
| `--ext EXT [...]` | `-e` | Filter `--list-files` output by extension (e.g. `.yaml`, `.json`) |
| `--dry-run` | `-dr` | Show what would be exported without exporting |

### Configuration & Security

| Flag | Short | Description |
|------|-------|-------------|
| `--init-config` | | Generate a `.scry.toml` configuration file and exit |
| `--root DIR` | `-r` | Set the project root directory (default: current directory) |
| `--no-scan` | | Skip secret detection scanning |

## Features

### Auto-Discovery
`scry` understands common project conventions out of the box:

- Flat layout (`mypackage/` in project root)
- Src layout (`src/mypackage/`)
- Subpackages (automatically grouped as modules)
- Special directories (`tests/`, `scripts/`, `examples/`, `R/`, 
  `vignettes/`, etc.)
- Core project files (`pyproject.toml`, `DESCRIPTION`, `README.md`, 
  `package.json`, etc.)

For Python-only projects, you don't have to configure anything.
For other languages, use `--include-ext` or set `extensions` in `.scry.toml` 
to include the relevant file types.

### Selective Export
```bash
scry --module models                     # One module
scry --module models training            # Multiple modules
scry --files src/config.yaml             # Specific files
scry --changed                           # Git-changed files only
scry --all                               # Everything
scry --all --exclude "*.lock" "tests/*"  # Everything except lock files and tests
```

### Dry Run
Preview what would be exported before committing:
```bash
scry --all --dry-run                    # How big is everything?
scry --all --exclude "*.lock" --dry-run # Without lock files?
scry --module models training --dry-run # Just these modules?
```

### Secret Detection
Before every export, scry scans for potential secrets (API keys,
tokens, private keys, database credentials, and other sensitive
patterns). Warnings are displayed before any output is written.

> [!IMPORTANT]
> `scry` does NOT automatically prevent secrets from appearing in the output. 
> The output warnings require acknowledgement before the export can proceed,
> but users MUST take care to ensure that sensitive info is not shared.

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
- GitHub, GitLab, Slack, PyPI, npm, Google, Azure, Twilio, Mailgun, and Square tokens
- Stripe, SendGrid, and Heroku API keys
- Private key blocks (RSA, EC, DSA, etc.)
- Database connection strings with embedded credentials
- Generic `password=`, `secret=`, `api_key=` assignments
- JWT tokens
- Sensitive filenames (`.env`, `.pem`, `.key`, `credentials.*`) or those containing `token`, `key`, `secret`, `cred`, or `password` (e.g. `api_token.txt`)
- High-entropy strings that resemble tokens or keys

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

# How big is the entire codebase?
scry --all --dry-run

# How big is the codebase excluding markdown files?
scry --all --exclude "*.md" --dry-run
```

### Working with a project that uses multiple languages
```bash
# Export R and SQL files in addition to Python
scry --list-modules --include-ext .R .sql

# Permanently configure scry to export Python, R and SQL files. Set in .scry.toml:
# extensions = [".py", ".R", ".sql"]
```

## How does `scry` work?
`scry` performs the following steps:
1. **Detect project root** and load `.scry.toml` if present;
2. **Discover source packages** by checking `src/` layout, then flat layout;
3. **Map subpackages to module names** (each subdirectory with matching files becomes a selectable module);
4. **Detect core files** (`pyproject.toml`, `README.md`, etc.);
5. **Scan for secrets** before any export;
6. **Format and output** in the requested format (currently supports txt and xml).

## Requirements
- Python 3.10+
- **Zero dependencies** - `scry` is deliberately lightweight; we use only the standard Python library
- Optional: `tomli` for `.scry.toml` support on Python <3.11