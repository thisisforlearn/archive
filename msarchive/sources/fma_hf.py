# sources/fma_hf.py — FMA full dataset (HF mirror, @benjamin-paine) source adapter.
#
#   SCAN   — reads ONLY the tiny metadata columns of each parquet shard via ranged
#            HTTP reads, so scanning all 972 shards costs a few MB of bandwidth,
#            never the ~520 GB of embedded audio.
#   EXTRACT— downloads a shard once, streams only the row groups containing still-
#            pending permissive tracks, writes each mp3 while hashing md5+sha256 in
#            one pass (AVX2 OpenSSL), then deletes the shard to bound disk usage.
#
# Everything is resumable through the ledger; Kaggle sessions can die at any second.
# Author: Vaibhav (Vaibhav Agarwal) — the archiver
# Contact: nekomeowpurr@proton.me | GitHub: https://github.com/thisisforlearn/archive
# Project authority: Vaibhav holds final decision power over this project.
# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import hashlib
import os
import re
import threading
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import TYPE_CHECKING

import orjson
import pyarrow.parquet as pq
from huggingface_hub import HfApi, HfFileSystem, hf_hub_download
from tqdm import tqdm

from msarchive.licenses import license_name, license_url

if TYPE_CHECKING:
    from msarchive.state import Ledger
    from msarchive.licenses import PermitPolicy

AUDIO_DIRNAME = "audio"
DATA_DIRNAME = "data"
META_COLS = (
    "title", "url", "artist", "composer", "album_title", "album_url", "license",
    "tags", "genres", "released", "language", "listens",
    "artist_url", "artist_website", "explicit", "instrumental",
    "allow_commercial_use", "allow_derivatives", "require_attribution", "require_share_alike",
)

_slug_re = re.compile(r"[^-a-z0-9_.]+")


def slugify(text, maxlen: int = 70) -> str:
    if not text:
        return "unknown"
    s = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode("ascii")
    s = _slug_re.sub("-", s.lower()).strip("-.")
    return s[:maxlen] or "unknown"


def shard_id(repo_path: str) -> str:
    return Path(repo_path).name.removesuffix(".parquet")


def dual_hash(data: bytes, buf: int) -> tuple[str, str]:
    """md5 (IA checksum-skip) + sha256 (HF mirror gate) in one read pass.
    hashlib uses OpenSSL, which is AVX2/hardware-accelerated here."""
    m5, s2 = hashlib.md5(), hashlib.sha256()
    for i in range(0, len(data), buf):
        c = data[i:i + buf]
        m5.update(c)
        s2.update(c)
    return m5.hexdigest(), s2.hexdigest()


class FmaHfSource:
    def __init__(self, cfg) -> None:
        self.cfg = cfg
        self.api = HfApi(token=cfg.hf_token)
        self.repo = cfg.hf_source_repo
        self.fs = HfFileSystem(token=cfg.hf_token)
        self._sizes: dict[str, int] = {}

    # ------------------------------------------------------------ listing/scan
    def list_shards(self, limit: int | None = None) -> list[str]:
        shards: list[tuple[str, int]] = []
        for f in self.api.list_repo_tree(self.repo, path_in_repo=DATA_DIRNAME, repo_type="dataset", recursive=False):
            name = getattr(f, "path", "")
            if not name.endswith(".parquet"):
                continue
            size = int(getattr(f, "size", 0) or 0)
            lfs = getattr(f, "lfs", None)
            if lfs is not None and getattr(lfs, "size", None):
                size = int(lfs.size)
            if size:
                shards.append((name, size))
        shards.sort()
        paths = [p for p, _ in shards]
        self._sizes = dict(shards)
        return paths[:limit] if limit else paths

    def scan(self, ledger: "Ledger", policy: "PermitPolicy", limit_shards=None, limit_tracks=None) -> None:
        shards = self.list_shards(limit_shards)
        if not shards:
            print("[FMA] no shards found — check network/token/source repo")
            return

        print(f"[FMA] scanning metadata of {len(shards)} shards ({self.cfg.scan_workers} workers, ranged reads only)")
        lock = threading.Lock()
        kept = [0]

        def worker(repo_path: str) -> int:
            sid = shard_id(repo_path)
            tuples = []
            for track_key, sid_, ridx, code, v in self._decode_scan(repo_path, policy):
                if limit_tracks and kept[0] >= limit_tracks:
                    break
                tuples.append(self._row_tuple(track_key, sid_, ridx, code, v))
            if not tuples:
                return 0
            with lock:
                if limit_tracks:
                    tuples = tuples[: max(0, limit_tracks - kept[0])]
                if not tuples:
                    return 0
                kept[0] += len(tuples)
                ledger.insert_tracks(tuples)
                ledger.upsert_shards([(sid, 0, len(tuples), self._sizes.get(repo_path, 0))])
            return len(tuples)

        with ThreadPoolExecutor(max_workers=self.cfg.scan_workers) as ex, \
             tqdm(total=len(shards), desc="SCAN", unit="shard") as bar:
            pfmap = {ex.submit(worker, s): shard_id(s) for s in shards}
            for fut in as_completed(pfmap):
                try:
                    fut.result()
                except Exception as e:  # noqa: BLE001
                    print(f"[FMA] scan warn {pfmap[fut]}: {e!r}")
                bar.update(1)
        print(f"[FMA] scan done — {kept[0]} permissive tracks registered in ledger")

    def _decode_scan(self, repo_path: str, policy: "PermitPolicy"):
        sid = shard_id(repo_path)
        out = []
        with self.fs.open(f"datasets/{self.repo}/{repo_path}", "rb") as h:
            pf = pq.ParquetFile(h)
            cols = [c for c in META_COLS if c in pf.schema_arrow.names]
            roff = 0
            for batch in pf.iter_batches(columns=cols, use_threads=False, batch_size=8192):
                out.extend(self._scan_batch(batch, policy, sid, roff))
                roff += batch.num_rows
        return out

    def _scan_batch(self, batch, policy, sid, roff: int):
        def col(name: str):
            return batch.column(name) if name in batch.schema.names else None

        lic = col("license")
        if lic is None:
            return []
        c_col, d_col, a_col, s_col = (
            col("allow_commercial_use"), col("allow_derivatives"),
            col("require_attribution"), col("require_share_alike"),
        )
        others = {n: col(n) for n in META_COLS if n != "license"}
        out = []
        for i in range(batch.num_rows):
            code = lic[i].as_py()
            if code is None:
                continue
            flags = (
                c_col[i].as_py() if c_col is not None else 1,
                d_col[i].as_py() if d_col is not None else 1,
                a_col[i].as_py() if a_col is not None else 1,
                s_col[i].as_py() if s_col is not None else 0,
            )
            code = int(code)
            if not policy.check(code, flags):
                continue
            vals = {n: (c[i].as_py() if c is not None else None) for n, c in others.items()}
            out.append((f"{sid}:{roff + i}", sid, roff + i, code, vals))
        return out

    def _row_tuple(self, track_key: str, sid: str, ridx: int, code: int, v: dict) -> tuple:
        aslug = slugify(v.get("artist") or "unknown")
        fname = f"{slugify(v.get('title'))}_{sid}-{ridx}.mp3"
        return (
            track_key, sid, ridx,
            v.get("title") or "unknown", v.get("artist") or "unknown", v.get("album_title"),
            v.get("composer"),
            code, license_name(code), license_url(code),
            v.get("url"), v.get("artist_url"), v.get("album_url"),
            orjson.dumps(v.get("tags") or []).decode() if v.get("tags") is not None else None,
            orjson.dumps(v.get("genres") or []).decode() if v.get("genres") is not None else None,
            str(v.get("released") or ""), int(v.get("listens") or 0),
            int(v.get("explicit") or 0), int(v.get("instrumental") or 0),
            f"{AUDIO_DIRNAME}/{aslug}/{fname}",
            None,  # dl_url: FMA rows decode from shards, not direct URLs
        )

    # -------------------------------------------------------------- extraction
    def extract_all(self, ledger: "Ledger", limit_tracks=None, stop=None, guard=None) -> None:
        pending = ledger.pending_tracks_by_shard()
        if limit_tracks:
            left = int(limit_tracks)
            for sid in sorted(pending):
                if left <= 0:
                    pending[sid] = []
                else:
                    pending[sid] = pending[sid][:left]
                    left -= len(pending[sid])
        pending = {k: v for k, v in pending.items() if v}
        total = sum(len(v) for v in pending.values())
        if not total:
            print("[EXTRACT] nothing pending")
            return

        print(f"[EXTRACT] {total} tracks across {len(pending)} shards | {self.cfg.extract_workers} workers | AVX2={'on' if self.cfg.avx2 else 'off'}")
        bar = tqdm(total=total, desc="EXTRACT", unit="track", dynamic_ncols=True)
        done = [0]
        dlock = threading.Lock()

        with ThreadPoolExecutor(max_workers=self.cfg.extract_workers) as ex:
            futures = []
            for sid in sorted(pending):
                if stop is not None and stop.is_set():
                    break
                    # no further shard starts after a stop signal
                if guard is not None:
                    guard.admit(self._sizes.get(f"{DATA_DIRNAME}/{sid}.parquet", 500 << 20))
                claimed = []
                for ridx, track_key in pending[sid]:
                    if stop is not None and stop.is_set():
                        break
                    if ledger.claim_track(track_key):
                        claimed.append((ridx, track_key))
                if claimed:
                    futures.append(ex.submit(self._extract_shard, sid, claimed, bar, done, dlock, ledger))
            for fut in as_completed(futures):
                try:
                    fut.result()
                except Exception as e:  # noqa: BLE001
                    print(f"[EXTRACT] shard error: {e!r}")
        bar.close()
        st = ledger.stats()
        print(f"[EXTRACT] ledger now: {st}")

    def _fetch_shard_local(self, sid: str) -> Path:
        """Download one shard into tmp/ (returns the local file path)."""
        from huggingface_hub import hf_hub_download
        tmp = self.cfg.data_dir / "tmp"
        tmp.mkdir(parents=True, exist_ok=True)
        return Path(hf_hub_download(
            repo_id=self.repo, repo_type="dataset",
            filename=f"{DATA_DIRNAME}/{sid}.parquet",
            local_dir=str(tmp), token=self.cfg.hf_token,
        ))

    def _extract_shard(self, sid: str, rows: list, bar, done, dlock, ledger) -> None:
        local = self._fetch_shard_local(sid)
        pf = pq.ParquetFile(local)
        md = pf.metadata
        offs, acc = {}, 0
        for rg in range(md.num_row_groups):
            offs[rg] = acc
            acc += md.row_group(rg).num_rows

        row_to_key = {ridx: tk for ridx, tk in rows}
        key_to_rel = {}
        for _, tk in rows:
            key_to_rel[tk] = ledger.get_track_field(tk, "audio_path") or f"{AUDIO_DIRNAME}/{slugify('unknown')}/{tk}.mp3"

        rg_wanted: dict[int, set[int]] = {}
        for absrow, tk in rows:
            for rg, off in offs.items():
                if off <= absrow < off + md.row_group(rg).num_rows:
                    rg_wanted.setdefault(rg, set()).add(absrow)
                    break

        buf = self.cfg.hash_buffer
        try:
            for rg in sorted(rg_wanted):
                obs = offs[rg]
                boff = 0
                for batch in pf.iter_batches(columns=["audio"], row_groups=[rg], batch_size=32):
                    struct_arr = batch.column("audio")
                    bytes_arr = struct_arr.field("bytes") if hasattr(struct_arr, "field") else None
                    for i in range(batch.num_rows):
                        absrow = obs + boff + i
                        tk = row_to_key.get(absrow)
                        if tk is None:
                            continue
                        data = bytes_arr[i].as_py() if bytes_arr is not None else struct_arr[i].as_py()["bytes"]
                        if not data:
                            ledger.mark_failed(tk, "empty audio bytes")
                            bar.update(1)
                            continue
                        rel = key_to_rel[tk]
                        dst = self.cfg.data_dir / rel
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        part = dst.with_name(dst.name + ".part")
                        m5, s2 = dual_hash(data, buf)
                        with open(part, "wb") as fh:
                            fh.write(data)
                        os.replace(part, dst)
                        ledger.mark_downloaded(tk, rel, len(data), m5, s2)
                        with dlock:
                            done[0] += 1
                            bar.update(1)
                    boff += batch.num_rows
            if not ledger.pending_tracks_by_shard().get(sid):
                ledger.mark_shard_extracted(sid)
        finally:
            try:
                local.unlink()
            except OSError:
                pass



