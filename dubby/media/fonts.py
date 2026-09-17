"""The studio UI's web fonts as local TTF files, so exported captions use the exact same typefaces.

Files come from the Google Fonts CSS API (static TTF per weight) and are cached under
``<cache>/fonts``. When the network is unavailable, close system fonts are used instead.
"""

from __future__ import annotations

import os
import re
import urllib.request
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple

# family -> weights the UI loads (styles.css @import); CJK and Devanagari only download when needed
FAMILIES: Dict[str, Tuple[int, ...]] = {
    "Inter": (400, 500, 600, 700, 800),
    "IBM Plex Sans Arabic": (400, 500, 600),
    "Noto Sans Devanagari": (400, 500, 600, 700, 800),
    "Noto Sans SC": (400, 500, 600, 700, 800),
    "Noto Sans JP": (400, 500, 600, 700, 800),
}
CSS_API = "https://fonts.googleapis.com/css2?family={family}:wght@{weights}"

SYSTEM_FALLBACKS = {
    "nt": {
        "latin": {400: "segoeui.ttf", 500: "segoeui.ttf", 600: "seguisb.ttf", 700: "segoeuib.ttf", 800: "segoeuib.ttf"},
        "arabic": {400: "segoeui.ttf", 500: "segoeui.ttf", 600: "seguisb.ttf", 700: "segoeuib.ttf", 800: "segoeuib.ttf"},
        "devanagari": {400: "Nirmala.ttc", 600: "NirmalaB.ttc", 700: "NirmalaB.ttc", 800: "NirmalaB.ttc"},
        "han": {400: "msyh.ttc", 600: "msyhbd.ttc", 700: "msyhbd.ttc", 800: "msyhbd.ttc"},
        "kana": {400: "YuGothR.ttc", 600: "YuGothB.ttc", 700: "YuGothB.ttc", 800: "YuGothB.ttc"},
    },
    "posix": {
        "latin": {400: "NotoSans-Regular.ttf", 600: "NotoSans-SemiBold.ttf", 700: "NotoSans-Bold.ttf", 800: "NotoSans-ExtraBold.ttf"},
        "arabic": {400: "NotoSansArabic-Regular.ttf", 600: "NotoSansArabic-SemiBold.ttf", 700: "NotoSansArabic-Bold.ttf"},
        "devanagari": {400: "NotoSansDevanagari-Regular.ttf", 700: "NotoSansDevanagari-Bold.ttf"},
        "han": {400: "NotoSansCJK-Regular.ttc", 700: "NotoSansCJK-Bold.ttc"},
        "kana": {400: "NotoSansCJK-Regular.ttc", 700: "NotoSansCJK-Bold.ttc"},
    },
}
SCRIPT_FAMILY = {"latin": "Inter", "arabic": "IBM Plex Sans Arabic", "devanagari": "Noto Sans Devanagari", "han": "Noto Sans SC", "kana": "Noto Sans JP"}


def slug(family: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "", family)


def nearest_weight(family: str, weight: int) -> int:
    """CSS font matching: the requested weight, else the closest heavier one (for bold), else lighter."""
    available = FAMILIES[family]
    if weight in available:
        return weight
    if weight >= 500:
        heavier = [w for w in available if w >= weight]
        return min(heavier) if heavier else max(available)
    lighter = [w for w in available if w <= weight]
    return max(lighter) if lighter else min(available)


def download_family(family: str, directory: Path, timeout: float = 60.0) -> List[Path]:
    """Fetch every weight of a Google Fonts family as TTF (the plain user agent gets TTF URLs)."""
    directory.mkdir(parents=True, exist_ok=True)
    url = CSS_API.format(family=family.replace(" ", "+"), weights=";".join(str(w) for w in FAMILIES[family]))
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "dubby"}), timeout=timeout) as response:
        css = response.read().decode("utf-8")
    saved = []
    for weight, src in re.findall(r"font-weight:\s*(\d+);.*?src:\s*url\((https://[^)]+\.ttf)\)", css, re.S):
        target = directory / f"{slug(family)}-{weight}.ttf"
        if not target.exists():
            tmp = target.with_suffix(".part")
            with urllib.request.urlopen(src, timeout=timeout) as response, open(tmp, "wb") as out:
                out.write(response.read())
            os.replace(tmp, target)
        saved.append(target)
    return saved


def _system_font(script: str, weight: int) -> Optional[Path]:
    table = SYSTEM_FALLBACKS["nt" if os.name == "nt" else "posix"][script]
    names = [table[w] for w in sorted(table, key=lambda w: (abs(w - weight), -w))]
    roots = [Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"] if os.name == "nt" else [Path("/usr/share/fonts"), Path("/usr/local/share/fonts"), Path.home() / ".fonts"]
    for name in names:
        for root in roots:
            if (root / name).is_file():
                return root / name
            if os.name != "nt" and root.is_dir():
                found = next(root.rglob(name), None)
                if found:
                    return found
    return None


class FontSet:
    """Resolves (script, weight) to a font file, downloading the UI's web fonts on first use."""

    def __init__(self, directory: Path, log: Callable[[str], None] = lambda message: None):
        self.directory = directory
        self.log = log
        self.failed: set = set()
        self.cache: Dict[Tuple[str, int], Optional[Path]] = {}

    def ensure(self, scripts: Iterable[str]) -> None:
        for script in set(scripts):
            family = SCRIPT_FAMILY[script]
            if family in self.failed or all((self.directory / f"{slug(family)}-{w}.ttf").exists() for w in FAMILIES[family]):
                continue
            try:
                self.log(f"Downloading the {family} font for captions…")
                download_family(family, self.directory)
            except Exception as exc:  # offline: fall back to system fonts
                self.failed.add(family)
                self.log(f"Couldn't download {family} ({exc}); using a system font instead.")

    def path(self, script: str, weight: int) -> Optional[Path]:
        key = (script, weight)
        if key not in self.cache:
            family = SCRIPT_FAMILY[script]
            local = self.directory / f"{slug(family)}-{nearest_weight(family, weight)}.ttf"
            self.cache[key] = local if local.exists() else _system_font(script, weight)
        return self.cache[key]
