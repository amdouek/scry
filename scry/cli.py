#!/usr/bin/env python
"""
scry - Generic convenient python project file exporter.

Auto-discovers your project structure and exports source files for easy
sharing. Works with any Python project with zero configuration required.

Usage:
    # First pip install scry, then cd to your project root
    # Auto-discover and export core files + project overview
        scry

    # Export a discovered module/subpackage
         scry --module utils

    # Export specific files
        scry --files src/main.py src/config.py

    # Export git-changed files only
        scry --changed

    # Export as XML (good for LLM parsing)
        scry --format xml --all -o codebase.xml

    # List discovered modules
        scry --list-modules

    # List all project files
        scry --list-files

    # List only YAML and JSON files
        scry --list-files --ext .yaml .json

    # Generate a config file for customisation
        scry --init-config

Examples/Quick Reference:

    # Export core files
        scry

    # Export a specific module you're working on
        scry --module models

    # Export only files you've changed (good for debugging)
        scry --changed

    # Export specific files
        scry --files mypackage/models.py mypackage/utils.py

    # Export everything (for major refactoring discussions)
        scry --all

    # Export as XML for LLM consumption
        scry --all --format xml -o codebase.xml

    # Save to file instead of printing
        scry --module models --output codebase_export.txt

    # Specify a different project root
        scry --root /path/to/project

    # List all auto-discovered modules
        scry --list-modules

    # List all project files (discover configs, data files, etc.)
        scry --list-files

    # List only config files
        scry --list-files --ext .yaml .yml .toml .json .cfg .ini

Configuration (optional):
    Create a `.scry.toml` in your project root for customisation,
    or run `scry --init-config` to generate one
    pre-populated with your discovered project structure.
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path
from datetime import datetime
from fnmatch import fnmatch
from collections import defaultdict

try:
    import tomllib  # Python 3.11+
except ImportError:
    try:
        import tomli as tomllib  # Fallback for older Python
    except ImportError:
        tomllib = None


# ── Default Configuration ────────────────────────────────────────────

DEFAULT_CONFIG = {
    "project_name": None,       # Auto-detected if not set
    "core_files": None,         # Auto-detected if not set
    "source_dirs": None,        # Auto-detected if not set
    "ignore_dirs": [
        ".git", "__pycache__", ".pytest_cache", "venv", ".venv",
        "env", ".env", "node_modules", ".mypy_cache", ".ruff_cache",
        "dist", "build", ".tox", ".nox", ".eggs", "htmlcov",
        ".coverage", ".ipynb_checkpoints", ".idea", ".vscode",
    ],
    "ignore_patterns": ["*.egg-info", "*.pyc", "*.pyo"],
    "extensions": [".py"],
    "tree_depth": 3,
    "default_module": None,     # Module exported when no args given
}

# Files considered "core" project files (checked in order of priority)
CORE_FILE_CANDIDATES = [
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "README.md",
    "README.rst",
    "requirements.txt",
    "Makefile",
    "Dockerfile",
    "docker-compose.yml",
    ".env.example",
]


# ── Configuration Loading ────────────────────────────────────────────

def load_config(root: Path) -> dict:
    """Load configuration from .scry.toml if present; otherwise use defaults."""
    config = dict(DEFAULT_CONFIG)
    config_path = root / ".scry.toml"

    if config_path.exists() and tomllib is not None:
        try:
            with open(config_path, "rb") as f:
                data = tomllib.load(f)
            if "scry" in data:
                user_config = data["scry"]
                config.update({k: v for k, v in user_config.items() if v is not None})
        except Exception as e:
            print(f"Warning: Failed to parse {config_path}: {e}", file=sys.stderr)
    elif config_path.exists() and tomllib is None:
        print(
            "Warning: .scry.toml found but tomllib/tomli not available. "
            "Using defaults. Install tomli for Python < 3.11: pip install tomli",
            file=sys.stderr,
        )

    return config


# ── Project Auto-Detection ───────────────────────────────────────────

def detect_project_name(root: Path) -> str:
    """Auto-detect project name from pyproject.toml, setup.cfg, or directory name."""
    pyproject = root / "pyproject.toml"
    if pyproject.exists() and tomllib is not None:
        try:
            with open(pyproject, "rb") as f:
                data = tomllib.load(f)
            name = data.get("project", {}).get("name")
            if name:
                return name
        except Exception:
            pass

    if pyproject.exists():
        try:
            text = pyproject.read_text(encoding="utf-8")
            for line in text.splitlines():
                stripped = line.strip()
                if stripped.startswith("name") and "=" in stripped:
                    _, _, value = stripped.partition("=")
                    name = value.strip().strip('"').strip("'")
                    if name:
                        return name
        except Exception:
            pass

    setup_cfg = root / "setup.cfg"
    if setup_cfg.exists():
        try:
            text = setup_cfg.read_text(encoding="utf-8")
            in_metadata = False
            for line in text.splitlines():
                if line.strip() == "[metadata]":
                    in_metadata = True
                elif line.strip().startswith("["):
                    in_metadata = False
                elif in_metadata and line.strip().startswith("name"):
                    _, _, value = line.partition("=")
                    name = value.strip()
                    if name:
                        return name
        except Exception:
            pass

    return root.resolve().name


def _should_ignore(name: str, config: dict) -> bool:
    """Check if a file/directory name matches ignore rules."""
    if name in set(config["ignore_dirs"]):
        return True
    if any(fnmatch(name, p) for p in config["ignore_patterns"]):
        return True
    if name.startswith("."):
        return True
    return False


def discover_source_dirs(root: Path, config: dict) -> list[Path]:
    """Discover Python source directories/packages in the project."""
    if config.get("source_dirs"):
        return [root / d for d in config["source_dirs"] if (root / d).is_dir()]

    source_dirs = []

    src_dir = root / "src"
    if src_dir.is_dir():
        for item in sorted(src_dir.iterdir()):
            if item.is_dir() and (item / "__init__.py").exists():
                source_dirs.append(item)

    for item in sorted(root.iterdir()):
        if (
            item.is_dir()
            and not _should_ignore(item.name, config)
            and (item / "__init__.py").exists()
            and item not in source_dirs
        ):
            source_dirs.append(item)

    return source_dirs


def discover_modules(source_dir: Path, root: Path, config: dict) -> dict[str, list[str]]:
    """Discover submodules/subpackages within a source directory."""
    modules = {}
    extensions = set(config["extensions"])

    top_level_files = []
    for f in sorted(source_dir.iterdir()):
        if f.is_file() and f.suffix in extensions:
            top_level_files.append(str(f.relative_to(root)))

    if top_level_files:
        pkg_name = source_dir.name
        modules[pkg_name] = top_level_files

    for item in sorted(source_dir.iterdir()):
        if item.is_dir() and not _should_ignore(item.name, config):
            module_files = []
            for f in sorted(item.rglob("*")):
                if f.is_file() and f.suffix in extensions and not _should_ignore(f.name, config):
                    module_files.append(str(f.relative_to(root)))
            if module_files:
                modules[item.name] = module_files

    return modules


def discover_all_modules(root: Path, config: dict) -> dict[str, list[str]]:
    """Discover all modules across all source directories and special directories."""
    all_modules = {}
    source_dirs = discover_source_dirs(root, config)

    for source_dir in source_dirs:
        sub_modules = discover_modules(source_dir, root, config)
        all_modules.update(sub_modules)

    special_dirs = ["tests", "test", "scripts", "examples", "benchmarks", "notebooks"]
    for dir_name in special_dirs:
        dir_path = root / dir_name
        if dir_path.is_dir() and not _should_ignore(dir_name, config):
            py_files = []
            for f in sorted(dir_path.rglob("*")):
                if f.is_file() and f.suffix in set(config["extensions"]):
                    py_files.append(str(f.relative_to(root)))
            if py_files:
                all_modules[dir_name] = py_files

    if not all_modules:
        top_py = []
        for f in sorted(root.iterdir()):
            if f.is_file() and f.suffix in set(config["extensions"]) and not _should_ignore(f.name, config):
                top_py.append(str(f.relative_to(root)))
        if top_py:
            all_modules["root"] = top_py

    return all_modules


def detect_core_files(root: Path, source_dirs: list[Path], config: dict) -> list[str]:
    """Auto-detect core project files."""
    if config.get("core_files"):
        return list(config["core_files"])

    core = []

    for candidate in CORE_FILE_CANDIDATES:
        if (root / candidate).exists():
            core.append(candidate)

    for source_dir in source_dirs:
        init_file = source_dir / "__init__.py"
        if init_file.exists():
            rel = str(init_file.relative_to(root))
            if rel not in core:
                core.append(rel)

    return core


# ── File Discovery ───────────────────────────────────────────────────

def discover_all_files(
    root: Path,
    config: dict,
    extension_filter: list[str] | None = None,
) -> dict[str, list[Path]]:
    """
    Walk the entire project tree and collect all files, grouped by
    their parent directory (relative to root).
    """
    ignore_dirs = set(config["ignore_dirs"])
    ignore_patterns = config["ignore_patterns"]
    files_by_dir: dict[str, list[Path]] = defaultdict(list)

    if extension_filter is not None:
        extension_filter = set(extension_filter)

    def _walk(directory: Path) -> None:
        try:
            entries = sorted(directory.iterdir(), key=lambda x: (x.is_file(), x.name))
        except PermissionError:
            return

        for entry in entries:
            if entry.name in ignore_dirs:
                continue
            if any(fnmatch(entry.name, p) for p in ignore_patterns):
                continue
            if entry.name.startswith("."):
                continue

            if entry.is_dir():
                _walk(entry)
            elif entry.is_file():
                if extension_filter is not None and entry.suffix not in extension_filter:
                    continue
                rel_dir = str(entry.parent.relative_to(root))
                if rel_dir == ".":
                    rel_dir = "."
                files_by_dir[rel_dir].append(entry)

    _walk(root)
    return dict(files_by_dir)


def format_file_size(size_bytes: int) -> str:
    """Format a file size into a human-readable string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


def print_file_listing(
    root: Path,
    config: dict,
    project_name: str,
    extension_filter: list[str] | None = None,
) -> None:
    """Print a comprehensive listing of all project files."""
    files_by_dir = discover_all_files(root, config, extension_filter)

    if not files_by_dir:
        filter_msg = f" matching {extension_filter}" if extension_filter else ""
        print(f"No files found{filter_msg}.")
        return

    total_files = sum(len(fs) for fs in files_by_dir.values())
    filter_label = ""
    if extension_filter:
        filter_label = f"  (filter: {', '.join(sorted(extension_filter))})"

    print(f"Project : {project_name}")
    print(f"Root    : {root}")
    print(f"Files   : {total_files}{filter_label}")
    print("─" * 60)

    ext_counts: dict[str, int] = defaultdict(int)
    ext_sizes: dict[str, int] = defaultdict(int)

    for dir_rel in sorted(files_by_dir.keys()):
        file_list = files_by_dir[dir_rel]
        dir_label = dir_rel if dir_rel != "." else "(project root)"
        print(f"\n  {dir_label}/  ({len(file_list)} file{'s' if len(file_list) != 1 else ''})")

        for fpath in sorted(file_list, key=lambda p: p.name):
            size = fpath.stat().st_size
            ext = fpath.suffix if fpath.suffix else "(no ext)"
            ext_counts[ext] += 1
            ext_sizes[ext] += size

            rel_path = str(fpath.relative_to(root))
            print(f"    • {rel_path:<55s} {format_file_size(size):>8s}")

    print("\n" + "─" * 60)
    print("Extension summary:")
    print(f"  {'Extension':<15s} {'Count':>6s} {'Total Size':>12s}")
    print(f"  {'─' * 15:<15s} {'─' * 6:>6s} {'─' * 12:>12s}")
    for ext in sorted(ext_counts.keys()):
        print(f"  {ext:<15s} {ext_counts[ext]:>6d} {format_file_size(ext_sizes[ext]):>12s}")

    total_size = sum(ext_sizes.values())
    print(f"  {'─' * 15:<15s} {'─' * 6:>6s} {'─' * 12:>12s}")
    print(f"  {'TOTAL':<15s} {total_files:>6d} {format_file_size(total_size):>12s}")


# ── File & Git Utilities ─────────────────────────────────────────────

def get_file_content(filepath: Path) -> str:
    """Read file content; return error message if file doesn't exist."""
    if filepath.exists():
        return filepath.read_text(encoding="utf-8")
    return f"# FILE NOT FOUND: {filepath}"


def get_git_changed_files(root: Path, extensions: set[str] | None = None) -> list[str]:
    """Get list of files changed since last commit (staged, unstaged, untracked)."""
    if extensions is None:
        extensions = {".py"}
        
    changed = []

    try:
        # Staged an unstaged changes versus HEAD
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            capture_output=True, text=True, check=True, cwd=root,
        )
        changed.extend(result.stdout.strip().split("\n"))
    except subprocess.CalledProcessError:
        # If HEAD doesn't exist (e.g. new repo, no commits), get staged files instead
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", "--cached"],
                capture_output=True, text=True, check=True, cwd=root,
            )
            changed.extend(result.stdout.strip().split("\n"))
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass
        
    try:
        # Untracked files
        result = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
                capture_output=True, text=True, check=True, cwd=root,
        )
        changed.extend(result.stdout.strip().split("\n"))
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    
    # Filter by extension and remove empty strings
    filtered = [f for f in changed if f and any(f.endswith(e) for e in extensions)]
    
    # Remove dups while preserving order
    seen = set()
    unique = []
    for f in filtered:
        if f not in seen:
            seen.add(f)
            unique.append(f)
            
    return unique


# ── Directory Tree ───────────────────────────────────────────────────

def get_directory_tree(
    root: Path,
    prefix: str = "",
    max_depth: int = 3,
    ignore_dirs: set[str] | None = None,
    ignore_patterns: list[str] | None = None,
) -> str:
    """Generate a directory tree string."""
    if max_depth == 0:
        return ""
    if ignore_dirs is None:
        ignore_dirs = set()
    if ignore_patterns is None:
        ignore_patterns = []

    try:
        items = sorted(root.iterdir(), key=lambda x: (x.is_file(), x.name))
    except PermissionError:
        return ""

    items = [
        i for i in items
        if i.name not in ignore_dirs
        and not any(fnmatch(i.name, p) for p in ignore_patterns)
        and not i.name.startswith(".")
    ]

    lines = []
    for i, item in enumerate(items):
        is_last = i == len(items) - 1
        connector = "└── " if is_last else "├── "
        lines.append(f"{prefix}{connector}{item.name}")

        if item.is_dir():
            extension = "    " if is_last else "│   "
            subtree = get_directory_tree(
                item, prefix + extension, max_depth - 1, ignore_dirs, ignore_patterns
            )
            if subtree:
                lines.append(subtree)

    return "\n".join(lines)


# ── Output Formatting ────────────────────────────────────────────────

LANG_MAP = {
    ".py": "python", ".toml": "toml", ".yaml": "yaml", ".yml": "yaml",
    ".json": "json", ".md": "markdown", ".rst": "rst", ".txt": "",
    ".cfg": "ini", ".ini": "ini", ".sh": "bash", ".bash": "bash",
    ".js": "javascript", ".ts": "typescript", ".html": "html",
    ".css": "css", ".sql": "sql", ".r": "r", ".R": "r",
    ".java": "java", ".cpp": "cpp", ".c": "c", ".rs": "rust",
    ".go": "go", ".rb": "ruby", ".dockerfile": "dockerfile",
}


def format_output_txt(
    files: list[str],
    root: Path,
    project_name: str,
    config: dict,
    include_tree: bool = True,
) -> str:
    """Format the output as plain text with markdown-style fences."""
    parts = []

    parts.append("=" * 70)
    parts.append(
        f"{project_name.upper()} CODE EXPORT — "
        f"{datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )
    parts.append("=" * 70)

    if include_tree:
        parts.append("\n## PROJECT STRUCTURE\n")
        parts.append("```")
        parts.append(f"{root.resolve().name}/")
        parts.append(
            get_directory_tree(
                root,
                max_depth=config.get("tree_depth", 3),
                ignore_dirs=set(config["ignore_dirs"]),
                ignore_patterns=config["ignore_patterns"],
            )
        )
        parts.append("```")

    parts.append("\n## FILE CONTENTS\n")

    for filepath in files:
        path = root / filepath if not Path(filepath).is_absolute() else Path(filepath)
        lang = LANG_MAP.get(path.suffix, "")

        parts.append(f"### {filepath}")
        if path.exists():
            content = get_file_content(path)
            parts.append(f"```{lang}")
            parts.append(content)
            parts.append("```")
        else:
            parts.append("```")
            parts.append(f"# FILE NOT FOUND: {filepath}")
            parts.append("```")
        parts.append("")

    parts.append("=" * 70)
    parts.append("END OF EXPORT")
    parts.append("=" * 70)

    return "\n".join(parts)


# ── XML Output Formatting ───────────────────────────────────────────

def xml_escape(text: str) -> str:
    """Escape text for use in XML attribute values."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def cdata_wrap(content: str) -> str:
    """
    Wrap content in a CDATA section, safely handling the edge case
    where the content itself contains ']]>'.

    The sequence ]]> is the only thing that can break CDATA. We handle
    it by splitting into multiple CDATA sections:
        "code]]>more" → "<![CDATA[code]]]]><![CDATA[>more]]>"
    """
    if "]]>" in content:
        parts = content.split("]]>")
        escaped = "]]]]><![CDATA[>".join(parts)
        return f"<![CDATA[{escaped}]]>"
    return f"<![CDATA[{content}]]>"


def format_output_xml(
    files: list[str],
    root: Path,
    project_name: str,
    config: dict,
    include_tree: bool = True,
) -> str:
    """
    Format the output as structured XML, optimised for LLM parsing.

    Produces a structure like:

        <?xml version="1.0" encoding="UTF-8"?>
        <codebase project="myproject" exported="2024-01-15 14:30"
                  total_files="12">

          <project_structure>
            <![CDATA[
              myproject/
              ├── src/
              │   ├── __init__.py
              ...
            ]]>
          </project_structure>

          <files>
            <file path="pyproject.toml" extension=".toml"
                  language="toml" size="1234">
              <![CDATA[
                [project]
                name = "myproject"
                ...
              ]]>
            </file>
            ...
          </files>

          <export_metadata>
            <tool>scry</tool>
            <format_version>1.0</format_version>
            <file_count>12</file_count>
          </export_metadata>

        </codebase>
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    parts = []

    # XML declaration
    parts.append('<?xml version="1.0" encoding="UTF-8"?>')

    # Root element
    parts.append(
        f'<codebase project="{xml_escape(project_name)}" '
        f'exported="{timestamp}" '
        f'total_files="{len(files)}">'
    )

    # Preamble instruction for the LLM
    parts.append("  <export_notes>")
    note_text = (
        f"This is an export of the {project_name} codebase. "
        f"Each <file> element contains the full contents of one source file "
        f"wrapped in CDATA. Use the 'path' attribute to identify files."
    )
    parts.append(f"    {cdata_wrap(note_text)}")
    parts.append("  </export_notes>")

    # Project structure (directory tree)
    if include_tree:
        tree = get_directory_tree(
            root,
            max_depth=config.get("tree_depth", 3),
            ignore_dirs=set(config["ignore_dirs"]),
            ignore_patterns=config["ignore_patterns"],
        )
        tree_text = f"{root.resolve().name}/\n{tree}"
        parts.append("")
        parts.append("  <project_structure>")
        parts.append(f"    {cdata_wrap(tree_text)}")
        parts.append("  </project_structure>")

    # File contents
    parts.append("")
    parts.append("  <files>")

    for filepath in files:
        path = root / filepath if not Path(filepath).is_absolute() else Path(filepath)
        lang = LANG_MAP.get(path.suffix, "unknown")
        ext = path.suffix or "(none)"

        if path.exists():
            content = get_file_content(path)
            size = path.stat().st_size

            parts.append(
                f'    <file path="{xml_escape(filepath)}" '
                f'extension="{xml_escape(ext)}" '
                f'language="{xml_escape(lang)}" '
                f'size="{size}">'
            )
            parts.append(f"      {cdata_wrap(content)}")
            parts.append("    </file>")
        else:
            parts.append(
                f'    <file path="{xml_escape(filepath)}" '
                f'status="not_found">'
            )
            parts.append(f"      {cdata_wrap(f'FILE NOT FOUND: {filepath}')}")
            parts.append("    </file>")

    parts.append("  </files>")

    # Export metadata
    parts.append("")
    parts.append("  <export_metadata>")
    parts.append("    <tool>scry</tool>")
    parts.append("    <format_version>1.0</format_version>")
    parts.append(f"    <file_count>{len(files)}</file_count>")
    parts.append(f"    <timestamp>{timestamp}</timestamp>")
    parts.append("  </export_metadata>")

    # Close root
    parts.append("")
    parts.append("</codebase>")

    return "\n".join(parts)


# ── Unified Format Dispatcher ────────────────────────────────────────

def format_output(
    files: list[str],
    root: Path,
    project_name: str,
    config: dict,
    include_tree: bool = True,
    output_format: str = "txt",
) -> str:
    """Dispatch to the appropriate formatter based on output_format."""
    if output_format == "xml":
        return format_output_xml(files, root, project_name, config, include_tree)
    else:
        return format_output_txt(files, root, project_name, config, include_tree)


# ── Config File Generation ───────────────────────────────────────────

def generate_config_template(root: Path, config: dict) -> str:
    """Generate a .scry.toml configuration template."""
    project_name = config.get("project_name") or detect_project_name(root)
    source_dirs = discover_source_dirs(root, config)
    core_files = detect_core_files(root, source_dirs, config)
    modules = discover_all_modules(root, config)

    lines = [
        "# ─── Export — Configuration ─────────────────────────────────",
        "# Auto-generated. Customise as needed.",
        "# Any value set here overrides the auto-detected default.",
        "",
        "[scry]",
        f'project_name = "{project_name}"',
        "",
        "# Files to always include when exporting (core files)",
        "core_files = [",
    ]
    for f in core_files:
        lines.append(f'    "{f}",')
    lines.append("]")
    lines.append("")

    lines.append("# Directories to ignore during auto-discovery")
    lines.append("ignore_dirs = [")
    for d in config["ignore_dirs"]:
        lines.append(f'    "{d}",')
    lines.append("]")
    lines.append("")

    lines.append("# File name patterns to ignore")
    lines.append("ignore_patterns = [")
    for p in config["ignore_patterns"]:
        lines.append(f'    "{p}",')
    lines.append("]")
    lines.append("")

    lines.append("# File extensions to include in discovery")
    lines.append('extensions = [".py"]')
    lines.append("")

    lines.append("# Max depth for the directory tree")
    lines.append(f"tree_depth = {config.get('tree_depth', 3)}")
    lines.append("")

    lines.append("# Default module to export when no arguments are given")
    lines.append("# Uncomment and set to a module name from the list below:")
    lines.append('# default_module = "utils"')
    lines.append("")

    lines.append("# ─── Auto-Discovered Modules (for reference) ──────────────────────")
    for mod_name, mod_files in sorted(modules.items()):
        lines.append(f"# {mod_name} ({len(mod_files)} files):")
        for f in mod_files:
            lines.append(f"#     {f}")
    lines.append("")

    return "\n".join(lines)

# ── Secret Detection ─────────────────────────────────────────────────

# Patterns that indicate potential secrets in file contents.
# Each entry: (name, compiled regex, description)
SECRET_PATTERNS: list[tuple[str, re.Pattern, str]] = [
    (
        "AWS Access Key",
        re.compile(r"(?:^|[^A-Z0-9])AKIA[0-9A-Z]{16}(?:[^A-Z0-9]|$)"),
        "AWS access key ID detected",
    ),
    (
        "AWS Secret Key",
        re.compile(
            r"""(?i)aws[_\-\s]*secret[_\-\s]*(?:access)?[_\-\s]*key\s*[=:]\s*['"]?[A-Za-z0-9/+=]{40}"""
        ),
        "AWS secret access key assignment detected",
    ),
    (
        "Private Key",
        re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"),
        "Private key block detected",
    ),
    (
        "GitHub Token",
        re.compile(r"(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{36,255}"),
        "GitHub personal access token detected",
    ),
    (
        "GitLab Token",
        re.compile(r"glpat-[A-Za-z0-9\-]{20,}"),
        "GitLab personal access token detected",
    ),
    (
        "Slack Token",
        re.compile(r"xox[bporas]-[A-Za-z0-9\-]{10,}"),
        "Slack API token detected",
    ),
    (
        "Generic API Key",
        re.compile(
            r"""(?i)(?:api[_\-\s]*key|apikey|api[_\-\s]*secret|api[_\-\s]*token)\s*[=:]\s*['"]?[A-Za-z0-9_\-]{20,}['"]?"""
        ),
        "Generic API key assignment detected",
    ),
    (
        "Generic Secret",
        re.compile(
            r"""(?i)(?:secret|password|passwd|pwd|token|auth[_\-\s]*token|access[_\-\s]*token)\s*[=:]\s*['"]?[^\s'"]{8,}['"]?"""
        ),
        "Potential secret/password assignment detected",
    ),
    (
        "Database URL",
        re.compile(
            r"""(?i)(?:postgres|mysql|mongodb|redis|amqp|sqlite):\/\/[^\s'"]+:[^\s'"]+@"""
        ),
        "Database connection string with credentials detected",
    ),
    (
        "JWT",
        re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_\-]{10,}"),
        "JSON Web Token detected",
    ),
    (
        "Heroku API Key",
        re.compile(
            r"""(?i)heroku[_\-\s]*(?:api)?[_\-\s]*key\s*[=:]\s*['"]?[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}['"]?"""
        ),
        "Heroku API key detected",
    ),
    (
        "Stripe Key",
        re.compile(r"(?:sk|pk)_(?:live|test)_[A-Za-z0-9]{20,}"),
        "Stripe API key detected",
    ),
    (
        "SendGrid Key",
        re.compile(r"SG\.[A-Za-z0-9_\-]{22}\.[A-Za-z0-9_\-]{43}"),
        "SendGrid API key detected",
    ),
    (
        "PyPI Token",
        re.compile(r"pypi-[A-Za-z0-9_\-]{20,}"),
        "PyPI API token detected",
    ),
    (
        "npm Token",
        re.compile(r"npm_[A-Za-z0-9]{36,}"),
        "npm access token detected",
    ),
    (
        "Azure Key",
        re.compile(r"(?i)azure[_\-\s]*(?:key|secret|token|password)\s*[=:]\s*['\"]?[A-Za-z0-9+/=]{20,}['\"]?"),
        "Azure credential detected",
    ),
    (
        "Google API Key",
        re.compile(r"AIza[0-9A-Za-z_\-]{35}"),
        "Google API key detected",
    ),
    (
        "Google OAuth",
        re.compile(r"[0-9]+-[a-z0-9_]{32}\.apps\.googleusercontent\.com"),
        "Google OAuth client ID detected",
    ),
    (
        "Twilio Key",
        re.compile(r"SK[0-9a-fA-F]{32}"),
        "Twilio API key detected",
    ),
    (
        "Mailgun Key",
        re.compile(r"key-[0-9a-zA-Z]{32}"),
        "Mailgun API key detected",
    ),
    (
        "Square Token",
        re.compile(r"sq0[a-z]{3}-[0-9A-Za-z_\-]{22,}"),
        "Square access token detected",
    ),
]

# File-level patterns (the filename itself suggests secrets)
SENSITIVE_FILE_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("Private key file", re.compile(r"(?i).*\.pem$")),
    ("Private key file", re.compile(r"(?i).*\.key$")),
    ("Environment file", re.compile(r"^\.env(?:\..+)?$")),
    ("Credentials file", re.compile(r"(?i).*credentials.*")),
    ("Secret config", re.compile(r"(?i).*secrets?\.(?:ya?ml|json|toml|cfg|ini)$")),
    ("Key file", re.compile(r"(?i).*id_(?:rsa|dsa|ecdsa|ed25519)$")),
    ("Certificate", re.compile(r"(?i).*\.p12$")),
    ("Keystore", re.compile(r"(?i).*\.keystore$")),
    ("htpasswd", re.compile(r"(?i).*\.htpasswd$")),
    ("Token/credential file", re.compile(r"(?i).*(?:token|key|secret|cred|auth|password).*\.txt$")),
]

def _line_entropy(line: str) -> float:
    """Calculate Shannon entropy of a string (bits per char)."""
    if not line:
        return 0.0
    from math import log2
    freq: dict[str,int] = {}
    for ch in line:
        freq[ch] = freq.get(ch, 0) + 1
    length = len(line)
    return -sum((c / length) * log2(c / length) for c in freq.values())

# Minimum length and entropy thresholds for bare secret detection
_MIN_SECRET_LENGTH = 20
_MIN_SECRET_ENTROPY = 4.0   # Random strings generally have entropy > 4.5


def scan_content_for_secrets(content: str, filepath: str) -> list[dict]:
    """
    Scan file content for potential secrets.

    Returns a list of findings, each a dict with keys:
        - pattern_name: str
        - description: str
        - filepath: str
        - line_number: int
        - line_preview: str (truncated line showing the match vicinity)
    """
    findings = []

    for line_num, line in enumerate(content.splitlines(), start=1):
        stripped = line.strip()
        
        # Skip empty lines
        if not stripped:
            continue
        
        # Skip comment lines (rough heuristic; covers Python, YAML, TOML, shell)
        if stripped.startswith("#") and "=" not in stripped and ":" not in stripped:
            continue
        
        matched = False

        for pattern_name, regex, description in SECRET_PATTERNS:
            if regex.search(line):
                # Truncate the line for preview to avoid showing the secret
                preview = stripped
                if len(preview) > 80:
                    preview = preview[:77] + "..."

                findings.append({
                    "pattern_name": pattern_name,
                    "description": description,
                    "filepath": filepath,
                    "line_number": line_num,
                    "line_preview": preview,
                })
                matched = True
                
        # Fallback: Detect high-entropy strings that look like bare tokens
        if not matched:
            # Check each whitespace-delimited token on the line
            for token in stripped.split():
                # Strip quotes and common delims
                clean = token.strip("\"'`,;:=()[]{}< >")
                if (
                    len(clean) >= _MIN_SECRET_LENGTH
                    and _line_entropy(clean) >= _MIN_SECRET_ENTROPY
                    and any(c.isdigit() for c in clean)
                    and any(c.isalpha() for c in clean)
                ):
                    preview = stripped
                    if len(preview) > 80:
                        preview = preview[:77] + "..."
                        
                    findings.append({
                        "pattern_name": "High-Entropy String",
                        "description": "Possible secret or token (high entropy)",
                        "filepath": filepath,
                        "line_number": line_num,
                        "line_preview": preview,
                    })
                    break   # One finding per line

    return findings


def scan_filename_for_secrets(filepath: str) -> list[dict]:
    """Check if a filename matches patterns associated with sensitive files."""
    findings = []
    name = Path(filepath).name

    for pattern_name, regex in SENSITIVE_FILE_PATTERNS:
        if regex.match(name):
            findings.append({
                "pattern_name": pattern_name,
                "description": f"Sensitive file type: {name}",
                "filepath": filepath,
                "line_number": 0,
                "line_preview": "(filename match)",
            })

    return findings


def scan_files_for_secrets(files: list[str], root: Path) -> list[dict]:
    """Scan a list of files for potential secrets (both filename and content)."""
    all_findings = []

    for filepath in files:
        # Check filename
        all_findings.extend(scan_filename_for_secrets(filepath))

        # Check content
        path = root / filepath if not Path(filepath).is_absolute() else Path(filepath)
        if path.exists():
            try:
                content = path.read_text(encoding="utf-8")
                all_findings.extend(scan_content_for_secrets(content, filepath))
            except (UnicodeDecodeError, PermissionError):
                pass  # Skip binary/unreadable files

    return all_findings


def print_secret_warnings(findings: list[dict]) -> None:
    """Print formatted secret warnings to stderr."""
    print("\n" + "!" * 60, file=sys.stderr)
    print("  POTENTIAL SECRETS DETECTED", file=sys.stderr)
    print("!" * 60, file=sys.stderr)

    # Group by file
    by_file: dict[str, list[dict]] = defaultdict(list)
    for f in findings:
        by_file[f["filepath"]].append(f)

    for filepath, file_findings in sorted(by_file.items()):
        print(f"\n  {filepath}:", file=sys.stderr)
        for finding in file_findings:
            if finding["line_number"] > 0:
                print(
                    f"    Line {finding['line_number']:>4d}: "
                    f"{finding['pattern_name']} — {finding['description']}",
                    file=sys.stderr,
                )
            else:
                print(
                    f"    {finding['pattern_name']} — {finding['description']}",
                    file=sys.stderr,
                )

    print(f"\n  Found {len(findings)} potential secret(s) across "
          f"{len(by_file)} file(s).", file=sys.stderr)
    print("  Review the above before sharing this export.", file=sys.stderr)
    print("!" * 60 + "\n", file=sys.stderr)


# ── Main ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Convenient exporter for project files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                            Export core files + project overview
  %(prog)s --module models            Export a specific module
  %(prog)s --files src/main.py        Export specific files
  %(prog)s --changed                  Export git-changed files
  %(prog)s --all                      Export all discovered files
  %(prog)s --all --format xml         Export everything as XML
  %(prog)s --list-modules             List auto-discovered modules
  %(prog)s --list-files               List all project files
  %(prog)s --list-files --ext .yaml   List only YAML files
  %(prog)s --init-config              Generate .scry.toml config
        """,
    )

    # Selection mode (mutually exclusive)
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--module", "-m", nargs="+",
        help="Export one or more modules (use --list-modules to see available)",
    )
    mode_group.add_argument(
        "--changed", "-c", action="store_true",
        help="Export git-changed files only",
    )
    mode_group.add_argument(
        "--all", "-a", action="store_true",
        help="Export all discovered Python files",
    )

    # Additive (combinable with any selection mode)
    parser.add_argument(
        "--files", "-f", nargs="+",
        help="Export specific files (can be combined with --module, --changed, etc.)",
    )
    parser.add_argument(
        "--output", "-o", help="Output file path (default: print to stdout)"
    )
    parser.add_argument(
        "--format", choices=["txt", "xml"], default="txt",
        help="Output format: txt (markdown-style) or xml (default: txt)",
    )
    parser.add_argument(
        "--no-tree", action="store_true", help="Omit directory tree from output"
    )
    parser.add_argument(
        "--root", "-r", type=Path, default=Path("."),
        help="Project root directory (default: current directory)",
    )
    parser.add_argument(
        "--list-modules", "-l", action="store_true",
        help="List all auto-discovered modules and exit",
    )
    parser.add_argument(
        "--list-files", action="store_true",
        help="List all project files (grouped by directory) and exit",
    )
    parser.add_argument(
        "--ext", nargs="+",
        help="Filter --list-files by extension (e.g. --ext .yaml .json)",
    )
    parser.add_argument(
        "--init-config", action="store_true",
        help="Generate a .scry.toml configuration file and exit",
    )
    parser.add_argument(
        "--tree-depth", type=int, help="Override directory tree depth"
    )
    parser.add_argument(
        "--no-scan", action="store_true",
        help="Skip secret detection scanning",
    )

    args = parser.parse_args()
    root = args.root.resolve()
    
    # Normalise --ext (e.g. allows "yaml" as well as ".yaml")
    if args.ext:
        args.ext = [e if e.startswith(".") else f".{e}" for e in args.ext]
        
    # Auto-detect format from output filename if --format not explicitly set
    if args.output and args.format == "txt":
        out_suffix = Path(args.output).suffix.lower()
        if out_suffix == ".xml":
            args.format = "xml"

    # ── Load config ──────────────────────────────────────────────────
    config = load_config(root)
    if args.tree_depth is not None:
        config["tree_depth"] = args.tree_depth

    # ── Detect project structure ─────────────────────────────────────
    project_name = config.get("project_name") or detect_project_name(root)
    source_dirs = discover_source_dirs(root, config)
    modules = discover_all_modules(root, config)
    core_files = detect_core_files(root, source_dirs, config)

    # ── Handle --init-config ─────────────────────────────────────────
    if args.init_config:
        config_content = generate_config_template(root, config)
        config_path = root / ".scry.toml"
        if config_path.exists():
            answer = input(f"{config_path} already exists. Overwrite? [y/N] ")
            if answer.lower() not in ("y", "yes"):
                print("Aborted.")
                return
        config_path.write_text(config_content, encoding="utf-8")
        print(f"  Generated configuration: {config_path}")
        print(f"  Discovered {len(modules)} module(s): {', '.join(sorted(modules))}")
        return

    # ── Handle --list-files ──────────────────────────────────────────
    if args.ext and not args.list_files:
        print(
            "Warning: --ext has no effect without --list-files.",
            file=sys.stderr,
        )
    
    if args.list_files:
        print_file_listing(root, config, project_name, extension_filter=args.ext)
        return

    # ── Handle --list-modules ────────────────────────────────────────
    if args.list_modules:
        print(f"Project : {project_name}")
        src_labels = ", ".join(str(s.relative_to(root)) for s in source_dirs) or "(none)"
        print(f"Sources : {src_labels}")
        print(f"Core    : {', '.join(core_files) or '(none)'}")
        print(f"\nDiscovered modules ({len(modules)}):")
        print("─" * 50)
        for mod_name, mod_files in sorted(modules.items()):
            print(f"\n  {mod_name}  ({len(mod_files)} file{'s' if len(mod_files) != 1 else ''})")
            for f in mod_files:
                marker = "•" if (root / f).exists() else "✖"
                print(f"    {marker} {f}")
        return

    # ── Determine files to export ────────────────────────────────────
    if args.changed:
        files_to_export = []
        changed = get_git_changed_files(root, set(config["extensions"]))
        files_to_export.extend(changed)
        if not changed:
            print("No changed files detected.", file=sys.stderr)
    else:
        files_to_export = list(core_files)

        if args.module:
            for mod in args.module:
                if mod in modules:
                    files_to_export.extend(modules[mod])
                else:
                    print(f"Error: Module '{mod}' not found.", file=sys.stderr)
                    print(
                        f"Available: {', '.join(sorted(modules))}",
                        file=sys.stderr,
                    )
                    sys.exit(1)
        elif args.all:
            for module_files in modules.values():
                files_to_export.extend(module_files)
        else:
            default_mod = config.get("default_module")
            if default_mod and default_mod in modules:
                files_to_export.extend(modules[default_mod])

    # --files is always additive, regardless of selection mode
    if args.files:
        files_to_export.extend(args.files)

    # Deduplicate, preserving order
    seen = set()
    unique_files = []
    for f in files_to_export:
        if f not in seen:
            seen.add(f)
            unique_files.append(f)
            
    if not unique_files:
        print(
            "No files to export. Use --list-modules to see available modules, "
            "or --all to export everything.",
            file=sys.stderr,
        )
        return
            
    # ── Secret scanning ──────────────────────────────────────────────
    if not args.no_scan:
        findings = scan_files_for_secrets(unique_files, root)
        if findings:
            print_secret_warnings(findings)
            if args.output:
                answer = input("Secrets detected. Continue with export? [y/N] ")
                if answer.lower() not in ("y", "yes"):
                    print("Export aborted.")
                    sys.exit(1)
            else:
                print(
                    "Hint: Use --no-scan to suppress this check, or review "
                    "the files above before sharing.",
                    file=sys.stderr,
                )

    # ── Generate & emit output ───────────────────────────────────────
    output = format_output(
        unique_files, root, project_name, config,
        include_tree=not args.no_tree,
        output_format=args.format,
    )

    if args.output:
        out_path = Path(args.output)
        out_path.write_text(output, encoding="utf-8")
        print(f"Exported {len(unique_files)} file(s) to {out_path}")
    else:
        print(output)


if __name__ == "__main__":
    main()