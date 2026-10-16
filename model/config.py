"""Load and expose `config.yaml`."""

from __future__ import annotations

import copy
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config.yaml"


@lru_cache(maxsize=4)
def _load(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_config(path: str | Path | None = None, *, fresh: bool = False) -> dict[str, Any]:
    """Return the parsed configuration.

    The cached dict is shared: callers must not mutate it. Pass ``fresh=True``
    to get a private deep copy (used by tests that tweak values).
    """
    cfg = _load(str(path or CONFIG_PATH))
    return copy.deepcopy(cfg) if fresh else cfg


def param_keys(cfg: dict[str, Any] | None = None) -> list[str]:
    cfg = cfg or load_config()
    return [p["key"] for p in cfg["parameters"]]


def param_labels(cfg: dict[str, Any] | None = None) -> dict[str, str]:
    cfg = cfg or load_config()
    return {p["key"]: p["label"] for p in cfg["parameters"]}


def resolve(path: str | Path) -> Path:
    """Resolve a config path relative to the project root."""
    p = Path(path)
    return p if p.is_absolute() else ROOT / p
