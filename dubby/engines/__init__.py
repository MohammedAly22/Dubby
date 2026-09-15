"""Pluggable ASR, translation and TTS engines."""

from dubby.engines.registry import all_infos, engine_class, get_info

__all__ = ["all_infos", "engine_class", "get_info"]
