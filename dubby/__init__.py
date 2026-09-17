"""Dubby 🐨 — YouTube dubbing studio for Egyptian Arabic and MSA."""

import os
import sys

__version__ = "0.1.0"
__all__ = ["__version__"]

# Pillow's text shaping (raqm: Arabic joining, bidi, Devanagari) loads fribidi from PATH on Windows.
# A conda env ships it in Library/bin, which is only on PATH when the env is activated.
if os.name == "nt":
    _conda_bin = os.path.join(sys.prefix, "Library", "bin")
    if os.path.isfile(os.path.join(_conda_bin, "fribidi-0.dll")) and _conda_bin.lower() not in os.environ.get("PATH", "").lower():
        os.environ["PATH"] = _conda_bin + os.pathsep + os.environ.get("PATH", "")
