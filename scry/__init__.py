"""scry: Peer into any Python codebase."""

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("cli-scry")
except PackageNotFoundError:
    __version__ = "dev"

from scry.cli import main

__all__ = ["main", "__version__"]