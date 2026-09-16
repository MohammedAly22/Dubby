"""Does an engine fit the GPU? Shared by the studio (UI warnings, run guard) and workers.

Engines describe their memory needs through ``Engine.required_vram_gb(params, vram)``
and ``Engine.needs_cuda(params)``. This module turns those numbers into a verdict,
a readable explanation and the per-option fits the UI uses to disable choices.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from dubby.engines.registry import engine_class

TOLERANCE_GB = 0.1


@dataclass
class GPU:
    cuda: bool
    name: str = "CPU"
    vram_gb: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {"cuda": self.cuda, "name": self.name, "vram_gb": self.vram_gb}


def from_status(status: Dict[str, Any]) -> Optional[GPU]:
    """GPU as seen by the doctor reports (``None`` while they are unknown)."""
    if not status:
        return None
    for family in ("core", *sorted(status)):
        torch = (status.get(family) or {}).get("torch") or {}
        if torch.get("cuda") and torch.get("vram_gb"):
            return GPU(True, str(torch.get("device") or "GPU"), float(torch["vram_gb"]))
    if any(((status.get(f) or {}).get("torch") or {}).get("version") for f in status):
        return GPU(False)
    return None


def current() -> Optional[GPU]:
    """GPU seen by *this* process (workers)."""
    try:
        import torch

        if not torch.cuda.is_available():
            return GPU(False)
        props = torch.cuda.get_device_properties(0)
        return GPU(True, props.name, round(props.total_memory / 1024**3, 1))
    except Exception:
        return None


def _fits(required: Optional[float], needs_cuda: bool, gpu: Optional[GPU]) -> bool:
    if gpu is None:
        return True  # unknown hardware: never block
    if needs_cuda and not gpu.cuda:
        return False
    if not gpu.cuda or required is None or gpu.vram_gb is None:
        return True  # CPU runs anything that doesn't need CUDA, just slower
    return required <= gpu.vram_gb + TOLERANCE_GB


def _gb(value: Optional[float]) -> str:
    return f"{value:g} GB" if value is not None else "?"


def _label(spec, value: Any) -> str:
    for opt in spec.options or []:
        if str(opt["value"]) == str(value):
            return opt["label"]
    return str(value)


def check(engine_id: str, params: Optional[Dict[str, Any]], gpu: Optional[GPU], source: Optional[str] = None, target: Optional[str] = None) -> Dict[str, Any]:
    cls = engine_class(engine_id)
    info = cls.info
    merged = {**info.defaults(), **(params or {})}
    vram = gpu.vram_gb if gpu and gpu.cuda else None
    required = cls.required_vram_gb(merged, vram)
    needs_cuda = cls.needs_cuda(merged, vram)
    fits = _fits(required, needs_cuda, gpu)

    selects = [s for s in info.params if s.type == "select" and s.options]
    options: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for spec in selects:
        per = {}
        for opt in spec.options:
            trial = {**merged, spec.key: opt["value"]}
            req = cls.required_vram_gb(trial, vram)
            per[str(opt["value"])] = {"required_gb": req, "fits": _fits(req, cls.needs_cuda(trial, vram), gpu)}
        if len({(v["required_gb"], v["fits"]) for v in per.values()}) > 1:
            options[spec.key] = per

    message = None
    suggestion = None
    fix = None
    if not fits and gpu is not None:
        if needs_cuda and not gpu.cuda:
            message = f"{info.name} with these settings needs an NVIDIA GPU, and none was detected."
        else:
            message = f"{info.name} needs about {_gb(required)} of VRAM and cannot run on {gpu.name} ({_gb(gpu.vram_gb)})."
        # Best single change that fits: "auto" when available (it picks the fastest precision that
        # fits); on CPU the lightest option (speed); on a GPU the most capable option that fits.
        candidates = [
            (spec, value, verdict["required_gb"])
            for spec in selects
            for value, verdict in (options.get(spec.key) or {}).items()
            if verdict["fits"]
        ]
        best = next((c for c in candidates if c[1] == "auto"), None)
        if best is None and candidates:
            if not gpu.cuda:
                best = min(candidates, key=lambda c: c[2] if c[2] is not None else float("inf"))
            else:
                best = max(candidates, key=lambda c: c[2] or 0)
        if best:
            spec, value, req = best
            fix = {"key": spec.key, "value": next(o["value"] for o in spec.options if str(o["value"]) == value)}
            short = _label(spec, value).split(" — ")[0]
            suggestion = f"Set {spec.label} to “{short}”" + (f" (≈{_gb(req)})" if req and gpu.cuda else "") + " to run it here."

    return {
        "engine": engine_id,
        "gpu": gpu.to_dict() if gpu else None,
        "required_gb": required,
        "needs_cuda": needs_cuda,
        "fits": fits,
        "message": message,
        "suggestion": suggestion,
        "fix": fix,
        "options": options,
        "preview": cls.preview(merged, source, target) if source and target else {},
    }


def minimum_vram(engine_id: str, gpu: Optional[GPU]) -> Dict[str, Any]:
    """Cheapest configuration of an engine, for the engine cards."""
    cls = engine_class(engine_id)
    info = cls.info
    base = info.defaults()
    vram = gpu.vram_gb if gpu and gpu.cuda else None
    selects: List = [s for s in info.params if s.type == "select" and s.options]
    combos = itertools.islice(itertools.product(*[[o["value"] for o in s.options] for s in selects]), 256)
    best_req: Optional[float] = None
    any_fits = False
    for combo in combos:
        trial = {**base, **{s.key: v for s, v in zip(selects, combo)}}
        req = cls.required_vram_gb(trial, vram)
        if _fits(req, cls.needs_cuda(trial, vram), gpu):
            any_fits = True
        if req is not None and (best_req is None or req < best_req):
            best_req = req
    default_req = cls.required_vram_gb(base, vram)
    return {"vram_min_gb": best_req, "vram_default_gb": default_req, "fits_any": any_fits or not selects and _fits(default_req, cls.needs_cuda(base, vram), gpu)}
