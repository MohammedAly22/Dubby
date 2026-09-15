"""Report which engines are importable in *this* interpreter.

``python -m dubby.workers.doctor --family qwen`` prints one JSON object.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import platform
import sys


def check(family: str) -> dict:
    from dubby.engines.registry import all_infos

    report = {
        "family": family,
        "python": sys.executable,
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "torch": None,
        "engines": {},
    }
    if importlib.util.find_spec("torch") is not None:
        try:
            import torch

            report["torch"] = {
                "version": torch.__version__,
                "cuda": bool(torch.cuda.is_available()),
                "device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu",
                "vram_gb": round(torch.cuda.get_device_properties(0).total_memory / 1024**3, 1) if torch.cuda.is_available() else None,
            }
        except Exception as exc:
            report["torch"] = {"error": str(exc)}
    for info in all_infos():
        if info.family != family:
            continue
        missing = [m for m in info.requires if importlib.util.find_spec(m) is None]
        report["engines"][info.id] = {"available": not missing, "missing": missing}
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--family", default="core")
    args = parser.parse_args()
    sys.stdout.write(json.dumps(check(args.family)) + "\n")


if __name__ == "__main__":
    main()
