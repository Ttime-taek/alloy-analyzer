"""Compatibility package for the project's historical ``test7`` imports.

The source files live at the repository root, while older entry points import
them through ``test7``.  Extending this package path keeps those imports valid
regardless of the directory name used by GitHub Actions or a local clone.
"""

from pathlib import Path

__path__ = [str(Path(__file__).resolve().parent.parent)]
