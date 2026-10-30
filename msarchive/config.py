# config.py — environment, paths, and machine-adaptive tuning.
# Author: Vaibhav (Vaibhav Agarwal) — the archiver
# Contact: nekomeowpurr@proton.me | GitHub: https://github.com/thisisforlearn/archive
# Project authority: Vaibhav holds final decision power over this project.
# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import os
import platform
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent

# Load .env from CWD or repo root, never overriding real environment.
load_dotenv(str(REPO_ROOT / ".env"), override=False)
load_dotenv(str(Path.cwd() / ".env"), override=False)

DEFAULT_HF_SOURCE = "benjamin-paine/free-music-archive-full"


def _lscpu_threads() -> int:
    try:
        out = os.popen("nproc").read().strip()
        return max(1, int(out))
    except Exception:
        return max(1, os.cpu_count() or 4)


def _ram_gib() -> float:
    try:
        import psutil
        return psutil.virtual_memory().total / (1 << 30)
    except Exception:
        return 8.0


def has_avx2() -> bool:
    """This deploy machine (i5-1335U) has AVX2; OpenSSL sha/md5 auto-vectorize."""
    try:
        return "avx2" in Path("/proc/cpuinfo").read_text()
    except Exception:
        return False


def is_kaggle() -> bool:
    return os.path.isdir("/kaggle/working") or os.environ.get("KAGGLE_KERNEL_RUN_TYPE") is not None


@dataclass(frozen=True)
class Config:
    # Where audio / state / manifest live. Kaggle scratch for bulk; /kaggle/working only for small artifacts.
    data_dir: Path
    # HF repo that mirrors the archive and acts as the hourly progress ledger.
    hf_repo_id: str
    hf_source_repo: str
    hf_token: str | None
    checkpoint_every_secs: int
    # Internet Archive
    ia_access_key: str | None
    ia_secret_key: str | None
    ia_collection: str
    ia_item_prefix: str
    ia_max_files_per_item: int
    # Archiver credit burned into every uploaded item/file/card.
    archivist_name: str
    archivist_email: str
    archivist_github: str
    # Policy
    policy: str
    include_sampling: bool
    # Tuning
    scan_workers: int
    extract_workers: int
    ia_workers: int
    hash_buffer: int
    avx2: bool
    platform: str
    dry_run: bool
    max_shards: int | None
    max_tracks: int | None
    limit: int | None

    @staticmethod
    def from_env(**overrides) -> "Config":
        ov = {k: v for k, v in overrides.items() if v is not None}

        def env(k: str, d: str | None = None) -> str | None:
            return ov.get(k.lower(), os.environ.get(k, d))

        kaggle = is_kaggle()
        threads = _lscpu_threads()
        ram = _ram_gib()

        if kaggle:
            data_dir = ov.get("data_dir") or env("MSARCHIVE_DATA_DIR") or "/kaggle/tmp/msarchive"
        else:
            data_dir = ov.get("data_dir") or env("MSARCHIVE_DATA_DIR") or str(REPO_ROOT / "data")

        # Worker sizing tuned to cores AND RAM (row-group streaming ~100MB/worker).
        extract_workers = max(2, min(6, int(ram // 6)))
        scan_workers = min(12, threads * 2 if threads <= 8 else threads)
        ia_workers = env("MSARCHIA_WORKERS")
        ia_workers = int(ia_workers) if ia_workers else (4 if ram >= 24 else 2)

        dr = ov["dry_run"] if "dry_run" in ov else env("MSARCHIVE_DRY_RUN", "0")
        pol = ov.get("policy") or env("MSARCHIVE_POLICY", "permissive")

        cfg = Config(
            data_dir=Path(data_dir).expanduser(),
            hf_repo_id=env("MSARCHIVE_HF_REPO_ID") or env("HF_REPO_ID") or "thisisforlearn/vaibhav-music-archive",
            hf_source_repo=env("MSARCHIVE_HF_SOURCE") or DEFAULT_HF_SOURCE,
            hf_token=env("HF_TOKEN") or env("HUGGING_FACE_HUB_TOKEN") or None,
            checkpoint_every_secs=int(env("MSARCHIVE_CHECKPOINT_EVERY", "3600")),
            ia_access_key=env("IA_S3_ACCESS_KEY") or env("IA_ACCESS_KEY"),
            ia_secret_key=env("IA_S3_SECRET_KEY") or env("IA_SECRET_KEY"),
            ia_collection=env("MSARCHIVE_IA_COLLECTION", "opensource_audio"),
            ia_item_prefix=re.sub(r"[^0-9a-z-]", "-", (env("MSARCHIVE_IA_ITEM_PREFIX", "vaibhav-archive-music")).lower())[:60],
            ia_max_files_per_item=int(env("MSARCHIVE_IA_MAX_FILES", "1000")),
            archivist_name=env("MSARCHIVE_ARCHIVIST_NAME", "Vaibhav Agarwal (archiver)") or "Vaibhav Agarwal (archiver)",
            archivist_email=env("MSARCHIVE_ARCHIVIST_EMAIL", "nekomeowpurr@proton.me") or "nekomeowpurr@proton.me",
            archivist_github=env("MSARCHIVE_ARCHIVIST_GITHUB", "https://github.com/thisisforlearn/archive") or "https://github.com/thisisforlearn/archive",
            policy=(pol or "permissive").lower(),
            include_sampling=str(env("MSARCHIVE_INCLUDE_SAMPLING", "0")).lower() in ("1", "true", "yes"),
            scan_workers=scan_workers,
            extract_workers=extract_workers,
            ia_workers=ia_workers,
            hash_buffer=int(env("MSARCHIVE_HASH_BUFFER", str(1 << 20))),
            avx2=has_avx2(),
            platform=("kaggle" if kaggle else platform.node() or "local"),
            dry_run=str(dr).lower() in ("1", "true", "yes"),
            max_shards=int(ov["max_shards"]) if "max_shards" in ov else (int(env("MSARCHIVE_MAX_SHARDS")) if env("MSARCHIVE_MAX_SHARDS") else None),
            max_tracks=int(ov["max_tracks"]) if "max_tracks" in ov else (int(env("MSARCHIVE_MAX_TRACKS")) if env("MSARCHIVE_MAX_TRACKS") else None),
            limit=int(ov["limit"]) if "limit" in ov else None,
        )
        cfg.data_dir.mkdir(parents=True, exist_ok=True)
        for sub in ("audio", "state", "manifest", "tmp"):
            (cfg.data_dir / sub).mkdir(parents=True, exist_ok=True)
        return cfg

    # Layout helpers -------------------------------------------------------
    @property
    def db_path(self) -> Path:
        return (self.data_dir / "state" / "msarchive.db").resolve()

    @property
    def manifest_dir(self) -> Path:
        return self.data_dir / "manifest"

    def audio_rel(self, artist_slug: str, filename: str) -> str:
        return f"audio/{artist_slug}/{filename}"

    @property
    def description_alt(self) -> str:
        return (
            f"Archived by {self.archivist_name} <{self.archivist_email}> "
            f"— {self.archivist_github}"
        )


def wipe_tmp(cfg: Config) -> None:
    t = cfg.data_dir / "tmp"
    shutil.rmtree(t, ignore_errors=True)
    t.mkdir(parents=True, exist_ok=True)
