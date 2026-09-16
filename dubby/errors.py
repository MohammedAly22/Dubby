"""Turn raw exceptions into messages people can act on.

Workers and the studio run everything through :func:`explain` before an error reaches
the UI, so "CUDA out of memory. Tried to allocate 112.00 MiB…" becomes
"The GPU ran out of memory" plus a concrete next step.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, Union


class InsufficientVRAM(RuntimeError):
    """Raised *before* loading a model that cannot fit, so nothing half-loads onto the GPU."""


@dataclass
class Explained:
    message: str
    hint: str = ""
    kind: str = "error"  # vram | oom | cuda_fatal | gated | not_found | network | missing_package | disk | numeric | needs_gpu | killed | error

    def text(self) -> str:
        return f"{self.message} 💡 {self.hint}" if self.hint else self.message


_REPO = re.compile(r"huggingface\.co/(?:api/models/)?([\w.-]+/[\w.-]+)")
_GIB = re.compile(r"total capacity of ([\d.]+) GiB")
_MODULE = re.compile(r"No module named '([\w.]+)'")

# import name → pip name, where they differ
_PIP = {"sklearn": "scikit-learn", "cv2": "opencv-python", "yaml": "pyyaml", "google": "protobuf"}


def is_oom(error: Union[BaseException, str]) -> bool:
    text = error if isinstance(error, str) else f"{type(error).__name__}: {error}"
    low = text.lower()
    return "outofmemoryerror" in low or "cuda out of memory" in low or "cublas_status_alloc_failed" in low


def _first_line(text: str, limit: int = 300) -> str:
    line = next((ln.strip() for ln in text.strip().splitlines() if ln.strip()), text.strip())
    return line if len(line) <= limit else line[: limit - 1] + "…"


def explain(error: Union[BaseException, str], family: Optional[str] = None) -> Explained:
    if isinstance(error, InsufficientVRAM):
        return Explained(str(error), kind="vram")
    text = error if isinstance(error, str) else f"{type(error).__name__}: {error}"
    low = text.lower()
    repo_match = _REPO.search(text)
    repo = f" ({repo_match.group(1)})" if repo_match else ""
    env = f"the {family} environment" if family else "this environment"

    if "insufficientvram" in low:
        return Explained(_first_line(text.split(":", 1)[-1]), kind="vram")

    if is_oom(low):
        cap = _GIB.search(text)
        where = f" ({float(cap.group(1)):.1f} GB total)" if cap else ""
        return Explained(
            f"The GPU ran out of memory{where}.",
            "Pick a smaller model or set Quantization to 4-bit, lower the batch size, or free VRAM with ⚙️ Settings → Stop workers.",
            "oom",
        )

    if "cuda error" in low or "device-side assert" in low or "cudnn_status" in low:
        return Explained(
            "The GPU hit a fatal CUDA error, so the worker was restarted.",
            "Retry the step. If it keeps happening, switch the engine or restart the runtime.",
            "cuda_fatal",
        )

    if "gatedrepoerror" in low or "cannot access gated repo" in low or ("access to model" in low and "restricted" in low):
        return Explained(
            f"This model is gated on Hugging Face{repo}.",
            "Open the model page, accept its terms, then add a read token in ⚙️ Settings → Hugging Face token.",
            "gated",
        )

    if "401 client error" in low or "invalid user token" in low or "invalid credentials" in low:
        return Explained(
            f"Hugging Face rejected the request{repo} (401).",
            "Check the token in ⚙️ Settings, and accept the model's terms on its page if it is gated.",
            "gated",
        )

    if "repositorynotfounderror" in low or "404 client error" in low or "is not a valid model identifier" in low:
        return Explained(
            f"Model not found on Hugging Face{repo}.",
            "Check the model id for typos; private repositories also need a token in ⚙️ Settings.",
            "not_found",
        )

    module = _MODULE.search(text)
    if module:
        name = module.group(1).split(".")[0]
        return Explained(
            f"{env[0].upper() + env[1:]} is missing the Python package '{name}'.",
            f"Install it there: pip install {_PIP.get(name, name)}",
            "missing_package",
        )

    if "no space left on device" in low:
        return Explained("The disk is full.", "Delete old projects or clear the Hugging Face cache (~/.cache/huggingface), then retry.", "disk")

    if "probability tensor contains either" in low or ("nan" in low and "inf" in low and "tensor" in low):
        return Explained(
            "The model produced invalid numbers (NaN/inf) — usually a float16 overflow.",
            "Set Quantization to 4-bit, lower the temperature, or turn sampling off.",
            "numeric",
        )

    if "bitsandbytes" in low and ("cuda" in low or "gpu" in low) or "a gpu is needed for quantization" in low:
        return Explained(
            "8-bit and 4-bit quantization need an NVIDIA GPU.",
            "Set Quantization to 'None' or choose a full-precision model when running on CPU.",
            "needs_gpu",
        )

    if (
        "localentrynotfounderror" in low
        or "connectionerror" in low
        or "max retries exceeded" in low
        or "temporary failure in name resolution" in low
        or "name or service not known" in low
        or "read timed out" in low
        or "connection reset" in low
    ):
        return Explained(
            "Could not reach Hugging Face to download the model.",
            "Check the internet connection and retry — files that already downloaded are reused.",
            "network",
        )

    if re.search(r"code (-9|137)\b", low) or "killed" == low.strip():
        return Explained(
            "The worker was killed by the operating system — almost always because it ran out of RAM.",
            "Use a smaller model or 4-bit quantization. On Colab, a High-RAM runtime helps.",
            "killed",
        )

    return Explained(_first_line(text))
