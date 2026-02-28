# Changelog

All notable changes to scry will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.4] - 2026-02-28

## Improved
- Changed versioning automation with GitHub Actions to point to commit SHA instead of mutable version tag

## Added
- Multi-language handling using `--include-ext` flag (per run - can be configured permanently in `.scry.toml`) 

## Changed
- Minor aesthetic and typographical fixes to README and source code

## [0.1.3] - 2026-02-23

### Improved
- Secret detection now uses Shannon entropy analysis with alphanumeric
  ratio checks, significantly reducing false positives (~400 → 3 on
  large codebases)
- `--changed` now exports only git-changed files without prepending
  core files
- Output format is auto-detected from `-o` filename (e.g. `-o export.xml`
  automatically selects XML format)
- `--ext` arguments are normalised (both `--ext yaml` and `--ext .yaml`
  now work)

### Added
- Additional secret patterns: PyPI, npm, Google, Azure, Twilio,
  Mailgun, and Square tokens
- High-entropy string fallback detector for unknown secret formats
- Sensitive `.txt` filename detection (e.g. `api_token.txt`,
  `credentials.txt`)
- Warning when `--ext` is used without `--list-files`
- Early exit with helpful message when no files are selected for export
- Robustness for `--changed` in new repos with no commits

## [0.1.2] - 2026-02-23

### Added
- XML output format (`--format xml`) with CDATA-wrapped file contents,
  optimised for LLM parsing
- Secret detection scanning before every export (API keys, tokens,
  private keys, database credentials, JWTs, and more)
- `--no-scan` flag to skip secret detection
- `--list-files` with `--ext` filtering for full project file discovery
- `--init-config` to generate `.scry.toml` configuration templates
- `--root` flag to specify a different project directory
- `--tree-depth` flag to control directory tree depth
- Syntax-highlighted code fences via language detection (`LANG_MAP`)
- File size display in `--list-files` output with per-extension summary

### Changed
- `--files` is now additive (can be combined with `--module`,
  `--changed`, etc.)
- `--module` accepts multiple arguments (`--module models training`)
- `--module`, `--changed`, and `--all` are now mutually exclusive
  (clear error on conflict)

## [0.1.1] - 2026-02-23 - Initial Public Release

### Changed
- Renamed from `export_codebase` to `scry`
- Configuration file renamed to `.scry.toml` with `[scry]` section

## [0.1.0] - NOT RELEASED PUBLICLY

### Added
- Initial release
- Auto-discovery of Python project structure (flat and src layouts)
- Module-aware selective export (`--module`)
- Specific file export (`--files`)
- Git-changed file export (`--changed`)
- Full export (`--all`)
- Directory tree generation
- `--list-modules` for project introspection
- Optional `.scry.toml` configuration
- Project name auto-detection from `pyproject.toml` / `setup.cfg`
- Zero dependencies — stdlib only

[Unreleased]: https://github.com/amdouek/scry/compare/v0.1.4...HEAD
[0.1.4]: https://github.com/amdouek/scry/compare/v0.1.3...v0.1.4
[0.1.3]: https://github.com/amdouek/scry/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/amdouek/scry/compare/0.1.1...v0.1.2