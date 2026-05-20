"""Re-export module name used in the plan; actual entry point lives in __main__.py."""

from . import create_app

__all__ = ["create_app"]
