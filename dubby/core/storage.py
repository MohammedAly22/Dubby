"""File-backed project store.

Every project lives in ``<home>/projects/<id>/`` with a ``project.json`` and the
media it produces. The server process is the single writer of ``project.json``;
workers only produce media files and report results as events.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Iterator, List

from dubby.schemas import Project


def _slug(text: str, limit: int = 32) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "-", text or "").strip("-").lower()
    return text[:limit].strip("-") or "project"


class ProjectStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, Project] = {}
        self._locks: Dict[str, threading.RLock] = {}
        self._global = threading.Lock()
        self._dirty: set = set()

    # ------------------------------------------------------------------ paths
    def dir(self, project_id: str) -> Path:
        return self.root / project_id

    def path(self, project_id: str, rel: str) -> Path:
        base = self.dir(project_id).resolve()
        target = (base / rel).resolve()
        if base != target and base not in target.parents:
            raise ValueError("path escapes project directory")
        return target

    def rel(self, project_id: str, absolute: Path | str) -> str:
        return Path(absolute).resolve().relative_to(self.dir(project_id).resolve()).as_posix()

    def lock(self, project_id: str) -> threading.RLock:
        with self._global:
            return self._locks.setdefault(project_id, threading.RLock())

    # ------------------------------------------------------------------ CRUD
    def create(self, title: str = "Untitled") -> Project:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        project_id = f"{stamp}-{_slug(title, 20)}-{uuid.uuid4().hex[:4]}"
        project = Project(id=project_id, title=title)
        d = self.dir(project_id)
        for sub in ("source", "tts", "refs", "render", "exports", "cache"):
            (d / sub).mkdir(parents=True, exist_ok=True)
        self.save(project)
        return project

    def get(self, project_id: str) -> Project:
        with self.lock(project_id):
            if project_id not in self._cache:
                f = self.dir(project_id) / "project.json"
                if not f.exists():
                    raise KeyError(project_id)
                self._cache[project_id] = Project.model_validate_json(f.read_text(encoding="utf-8"))
            return self._cache[project_id]

    def save(self, project: Project) -> Project:
        with self.lock(project.id):
            project.updated_at = time.time()
            d = self.dir(project.id)
            d.mkdir(parents=True, exist_ok=True)
            tmp = d / f"project.json.{uuid.uuid4().hex}.tmp"
            tmp.write_text(project.model_dump_json(indent=2), encoding="utf-8")
            os.replace(tmp, d / "project.json")
            self._cache[project.id] = project
            return project

    @contextmanager
    def mutate(self, project_id: str, persist: bool = True) -> Iterator[Project]:
        """Lock, yield the live project, then persist it (or mark it dirty for the debounced saver)."""
        with self.lock(project_id):
            project = self.get(project_id)
            yield project
            if persist:
                self.save(project)
            else:
                with self._global:
                    self._dirty.add(project_id)

    def flush_dirty(self) -> None:
        with self._global:
            dirty, self._dirty = self._dirty, set()
        for project_id in dirty:
            try:
                self.save(self.get(project_id))
            except KeyError:
                continue

    def list(self) -> List[Project]:
        projects = []
        for d in sorted(self.root.iterdir(), reverse=True):
            if (d / "project.json").exists():
                try:
                    projects.append(self.get(d.name))
                except Exception:  # corrupted project.json should not break the list
                    continue
        return projects

    def delete(self, project_id: str) -> None:
        with self.lock(project_id):
            self._cache.pop(project_id, None)
            shutil.rmtree(self.dir(project_id), ignore_errors=True)

    @staticmethod
    def dump_json(path: Path, data) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
