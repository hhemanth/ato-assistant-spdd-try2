"""Application configuration package.

Exposes the typed Pydantic settings module and the cached accessor
returning the singleton ``Settings`` instance.
"""

from config.settings import Settings, get_settings

__all__ = ["Settings", "get_settings"]
