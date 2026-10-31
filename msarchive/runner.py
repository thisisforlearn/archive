# runner.py — orchestrates the full archive pipeline with hourly HF checkpoints,
# machine-adaptive tuning, resource guarding, and parallel extract+IA.
# Layout: restore -> scan -> [EXTRACT thread ∥ IA-upload loop on the main thread]
#         until nothing pending or time budget out -> final HF checkpoint.
# The Guard thread watches RAM/disk; workers pause before a spike instead of
# being OOM-killed (Katana rule: keep the session alive at all costs).
# Author: Vaibhav (Vaibhav Agarwal) — the archiver
# Contact: nekomeowpurr@proton.me | GitHub: https://github.com/thisisforlearn/archive
# Project authority: Vaibhav holds final decision power over this project.
# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import os
import shutil
import signal
import threading
import time
from contextlib import suppress

from msarchive import GREETING
from msarchive.config import Config, wipe_tmp
from msarchive.hf_sync import HfMirror
from msarchive.ia_upload import IaUploader
from msarchive.licenses import PermitPolicy
from msarchive.sources import get_source
from msarchive.sources.fma_hf import FmaHfSource
from msarchive.state import STATUS_FAILED, STATUS_PENDING, Ledger


HIGH_MEM_FRAC = 0.90     # pause admissions when RSS > 90% of total
LOW_MEM_FRAC = 0.78      # resume admissions when RSS < 78%
MIN_FREE_GB = 8.0        # disk headroom guard (Kaggle working + scratch)
WATCHDOG_SECS = 20.0


class Guard(threading.Thread):
    """RAM/disk watchdog + admission gate.

    `admit(bytes_needed)` blocks the caller while memory pressure is high or
    disk headroom is low — so the pipeline self-paces before a crash instead of
    being OOM-killed mid-shard. Also wipes stale tmp shards when disk runs out.
    """

    def __init__(self, cfg: Config) -> None:
        super().__init__(daemon=True, name="msarchive-guard")
        self.cfg = cfg
        self._stop = threading.Event()
        self._gate = threading.Event()
        self._gate.set()                      # gate open = workers may proceed
        self.events: list[str] = []

    def _note(self, msg: str) -> None:
        self.events.append(msg)
        print(f"[guard] {msg}", flush=True)

    def run(self) -> None:
        try:
            import psutil
        except ImportError:
            return
        while not self._stop.wait(WATCHDOG_SECS):
            try:
                vm = psutil.virtual_memory()
                frac = vm.percent / 100.0
                du = shutil.disk_usage(str(self.cfg.data_dir))
                free_gb = du.free / (1 << 30)
                if frac >= HIGH_MEM_FRAC:
                    self._gate.clear()
                    self._note(f"mem {vm.percent:.0f}% — pausing new shard downloads")
                elif frac < LOW_MEM_FRAC:
                    if not self._gate.is_set():
                        self._note(f"mem recovered ({vm.percent:.0f}%) — resuming")
                    self._gate.set()
                if free_gb < MIN_FREE_GB:
                    t = self.cfg.data_dir / "tmp"
                    stale = sum(1 for _ in t.glob("**/*.parquet")) if t.is_dir() else 0
                    if stale:
                        size0 = sum(p.stat().st_size for p in t.glob("**/*.parquet"))
                        wipe_tmp(self.cfg)
                        du = shutil.disk_usage(str(self.cfg.data_dir))
                        free_gb = du.free / (1 << 30)
                        self._note(
                            f"disk low ({free_gb:.1f} GB free) — wiped {stale} tmp shard(s), "
                            f"recovered {size0 / (1 << 30):.1f} GiB")
                    if free_gb < MIN_FREE_GB:
                        self._gate.clear()
                        self._note(f"disk still low ({free_gb:.1f} GB) — downloads paused")
                    elif not self._gate.is_set():
                        self._gate.set()
                        self._note(f"disk recovered ({free_gb:.1f} GB) — resuming")
                if self._gate.is_set():
                    bal = vm.available / (1 << 30)
                    print(f"[guard] ok — mem {vm.percent:.0f}% ({bal:.1f} GB free) | disk {free_gb:.1f} GB free", flush=True)
            except Exception:  # noqa: BLE001 — guard must never crash the run
                continue

    def admit(self, bytes_needed: int = 0) -> None:
        self._gate.wait()

    def pause_flips(self) -> int:
        return len(self.events)

    def stop(self) -> None:
        self._stop.set()
        self._gate.set()                      # release any waiting worker


class CheckpointThread(threading.Thread):
    """Commits the archive progress to HF every `interval` seconds, no skips."""

    def __init__(self, hf: HfMirror, interval: int, reason: str = "hourly") -> None:
        super().__init__(daemon=True, name="msarchive-checkpoint")
        self.hf, self.interval, self.reason = hf, max(600, interval), reason
        self._stop = threading.Event()
        self.lock = threading.Lock()          # serializes synchronous + thread checkpoints

    def run(self) -> None:
        while not self._stop.wait(self.interval):
            self.flush("hourly-timer")
        self.flush("final-flush")

    def flush(self, why: str) -> None:
        with self.lock:
            try:
                self.hf.sync(why if why != self.reason else self.reason)
            except Exception as e:  # noqa: BLE001 — never silent:
                print(f"[HF] checkpoint {why} FAILED: {e!r}", flush=True)  # a dead checkpoint thread must be loud

    def stop(self) -> None:
        self._stop.set()


def print_banner(cfg: Config) -> None:
    from msarchive import __author__, __contact__, __github__, __version__
    print(GREETING.format(v=__version__, a=__author__, c=__contact__, g=__github__))
    if cfg.avx2:
        print("[architecture] AVX2 detected — OpenSSL-backed md5/sha256 hashing is hardware-accelerated")


def build(cfg: Config) -> tuple[Ledger, FmaHfSource | None, HfMirror, IaUploader, PermitPolicy]:
    ledger = Ledger(cfg.db_path)
    src = get_source(cfg, ledger)
    hf = HfMirror(cfg, ledger)
    ia = IaUploader(cfg, ledger)
    policy = PermitPolicy(cfg.policy, cfg.include_sampling)
    return ledger, src, hf, ia, policy


def _run_scan(src, ledger: Ledger, policy: PermitPolicy, limit_shards, limit_tracks) -> None:
    if not isinstance(src, FmaHfSource):
        src.scan(ledger, policy, limit_tracks=limit_tracks)
        return
    src.scan(ledger, policy, limit_shards=limit_shards, limit_tracks=limit_tracks)


def run_all(cfg, source_name: str | None = None, max_hours: float | None = None,
            limit_shards=None, limit_tracks=None, limit_items=None) -> int:
    ledger, src, hf, ia, policy = build(cfg)
    print_banner(cfg)
    wipe_tmp(cfg)
    os.environ.setdefault("HF_XET_HIGH_PERFORMANCE", "1")

    deadline = time.time() + (max_hours * 3600 if max_hours else 999 * 3600)

    ck = CheckpointThread(hf, cfg.checkpoint_every_secs)
    guard = Guard(cfg)
    stop_flag = threading.Event()

    def _sig(signum, _frame):
        print(f"\n[signal] {signum} received — flushing checkpoint, stopping cleanly…", flush=True)
        stop_flag.set()

    with suppress(ValueError):
        signal.signal(signal.SIGTERM, _sig)
        signal.signal(signal.SIGINT, _sig)

    hf.restore()  # resume progress + fetch pre-archived audio from the mirror

    # IMMEDIATE first commit: proves the JWT/creds/repo are writable in the first
    # minutes (probe + folder upload), instead of discovering a broken checkpoint
    # thread one hour into a Kaggle session. Future sessions can then restore().
    try:
        hf.sync("startup")
    except Exception as e:  # noqa: BLE001 — loud, then keep going; hourly will retry
        print(f"[HF] startup checkpoint FAILED (hourly will retry): {e!r}", flush=True)

    def extract_loop() -> None:
        """Cycles: scan → extract pass, until stopped or out of budget."""
        while not stop_flag.is_set() and time.time() < deadline:
            try:
                _run_scan(src, ledger, policy, limit_shards, limit_tracks)
                src.extract_all(ledger, limit_tracks, stop=stop_flag, guard=guard)
            except Exception as e:  # noqa: BLE001
                print(f"[runner] extract pass error: {e!r}")
            if stop_flag.is_set() or time.time() >= deadline:
                break
            stop_flag.wait(5)

    guard.start()
    try:
        ck.start()
        ex_thread = threading.Thread(target=extract_loop, name="msarchive-extract", daemon=True)
        ex_thread.start()
        ia_enabled = _ia_keys_ok(cfg)
        passes = 0
        while (not stop_flag.is_set()
               and time.time() < deadline
               and (ex_thread.is_alive() or passes == 0)):
            if not ia_enabled:
                print("[runner] IA keys missing — running extract+HF phases only")
                break
            passes += 1
            print(f"\n===== IA pass {passes} — uploading finished artists =====", flush=True)
            try:
                ia.upload(limit_items=limit_items)
            except Exception as e:  # noqa: BLE001
                print(f"[runner] IA pass error: {e!r}")
            st = ledger.stats()
            pending = sum(st.get(s, 0) for s in (STATUS_PENDING, STATUS_FAILED))
            print(f"[runner] pass {passes}: pending={pending} | {st}", flush=True)
            if pending == 0 and not ex_thread.is_alive():
                break
            stop_flag.wait(15)
        # final flush: extractor is done/stopped
        ex_thread.join(timeout=120)
        ck.flush("final")
        if hf.repo_ok():
            ck.lock.acquire()
            try:
                hf.sync("final-complete", final=True)
            finally:
                ck.lock.release()
    finally:
        guard.stop()
        ck.stop()
        ck.join(timeout=cfg.checkpoint_every_secs // 2 + 30)
        with suppress(Exception):
            ledger.close()
    print(f"=== done — archived by {cfg.archivist_name} "
          f"<{cfg.archivist_email}>, {cfg.archivist_github} ===", flush=True)
    return 0


def _ia_keys_ok(cfg: Config) -> bool:
    return bool(cfg.ia_access_key and cfg.ia_secret_key)
