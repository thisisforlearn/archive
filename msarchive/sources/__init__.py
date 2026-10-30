# sources/__init__.py — source adapter registry.
# Author: Vaibhav (Vaibhav Agarwal) — the archiver
# Contact: nekomeowpurr@proton.me | GitHub: https://github.com/thisisforlearn/archive
# Project authority: Vaibhav holds final decision power over this project.
# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from .fma_hf import FmaHfSource, slugify, shard_id  # noqa: F401


def get_source(cfg, ledger, name: str | None = None):
    """Return the configured source adapter. Default: FMA full HF mirror."""
    name = (name or "fma_hf").lower()
    if name in ("fma", "fma_hf", "fma-hf", "default"):
        return FmaHfSource(cfg)
    if name in ("jamendo",):
        from .jamendo import JamendoSource
        return JamendoSource(cfg)
    raise ValueError(f"unknown source '{name}' — use fma_hf or jamendo")
