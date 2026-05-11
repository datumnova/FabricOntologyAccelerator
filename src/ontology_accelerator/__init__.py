"""Fabric Ontology Accelerator — CLI for creating Microsoft Fabric ontology payloads."""

__all__ = ["main"]

try:
    from importlib.metadata import version

    __version__ = version("ontology-accelerator")
except Exception:
    __version__ = "0.0.0-dev"

from .cli import main
