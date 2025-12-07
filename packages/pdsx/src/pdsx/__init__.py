"""pdsx - general-purpose cli for atproto record operations."""

from __future__ import annotations

import importlib.metadata

try:
    __version__ = importlib.metadata.version("pdsx")
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"  # fallback for development mode

__all__ = ["__version__"]
