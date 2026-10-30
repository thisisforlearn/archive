# sources/jamendo.py — Jamendo API source (optional secondary permissively-licensed source).
#
# Discovers CC-BY / CC-BY-SA (never NC/ND) tracks via api.jamendo.com, registers them
# in the ledger with direct `dl_url` download links + full attribution, and extracts
# them through the same single-pass dual-hash pipeline used for FMA.
# Set JAMENDO_CLIENT_ID (free at https://devportal.jamendo.com) to enable.
# Author: Vaibhav (Vaibhav Agarwal) — the archiver
# Contact: nekomeowpurr@proton.me | GitHub: https://github.com/thisisforlearn/archive
# Project authority: Vaibhav holds final decision power over this project.
# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import json
import os
import threading
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import orjson
from tqdm import tqdm

from .fma_hf import dual_hash, slugify

API = "https://api.jamendo.com/v3.0/tracks"
UA = "msarchive/0.1 (by Vaibhav; +https://github.com/thisisforlearn/archive)"

# license_cc filter values accepted by Jamendo + our URL → license-code mapping.
CC_FILTER = "+cc_publicdomain,+cc_by,+cc_by-sa"
CCURL2CODE = {
    "publicdomain": 33,   # CC0 1.0
    "zero": 33,
    "by": 3,              # CC-BY 3.0 (approx; full url kept too)
    "by-sa": 26,          # CC-BY-SA 3.0
}


def _code_from_ccurl(ccurl: str) -> int:
    for k, v in CCURL2CODE.items():
        if k in (ccurl or "").lower():
            return v
    return -1


class JamendoSource:
    def __init__(self, cfg) -> None:
        self.cfg = cfg
        self.client_id = os.environ.get("JAMENDO_CLIENT_ID", "")
        self.per_page = 100
        self.enabled = bool(self.client_id)
        if not self.enabled:
            print("[Jamendo] disabled — JAMENDO_CLIENT_ID not set")

    # ------------------------------------------------------------ scan/ingest
    def scan(self, ledger, policy=None, limit_tracks=None) -> None:
        """Discover permissive Jamendo tracks and register them as PENDING rows."""
        if not self.enabled:
            return
        # 1) total count
        q = urllib.parse.urlencode({
            "client_id": self.client_id, "format": "json", "limit": "1",
            "audioformat": "mp32", "audiodownload_allowed": "1", "license_cc": CC_FILTER,
        })
        try:
            with urllib.request.urlopen(f"{API}?{q}", timeout=30) as r:
                headers = json.loads(r.read().decode()).get("headers", {})
        except Exception as e:  # noqa: BLE001
            print(f"[Jamendo] api probe failed: {e!r}")
            return
        results_total = int(headers.get("resultsCount", "0") or 0)
        pages = results_total // self.per_page + 1
        n = [0]
        nlock = threading.Lock()

        def worker(page: int) -> int:
            q = urllib.parse.urlencode({
                "client_id": self.client_id, "format": "json", "limit": str(self.per_page),
                "page": str(page), "audioformat": "mp32", "audiodownload_allowed": "1",
                "include": "musicinfo licenses artists albums", "groupby": "artist_id",
                "license_cc": CC_FILTER,
            })
            req = urllib.request.Request(f"{API}?{q}", headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.loads(r.read().decode())
            tuples = []
            for rank, t in enumerate((data.get("results") or [])):
                lic = ((t.get("musicinfo") or {}).get("licenses") or {}).get("license_ccurl", "") or ""
                dl = t.get("audiodownload") or ""
                low = lic.lower()
                if not lic or "nc" in low or "nd" in low or not dl:
                    continue
                artist = t.get("artist_name") or "unknown"
                aslug = slugify(artist)
                if "publicdomain" in low or "zero" in low:
                    code = CCURL2CODE["publicdomain"]
                elif "sa" in low:
                    code = CCURL2CODE["by-sa"]
                else:
                    code = CCURL2CODE["by"]
                from msarchive.licenses import license_name
                tuples.append((
                    f"jamendo-p{page}:{rank}", f"jamendo-p{page}", rank,
                    t.get("name") or "unknown", artist, t.get("album_name") or None,
                    code, license_name(code), lic,
                    f"https://www.jamendo.com/track/{t.get('id')}", "", "",
                    orjson.dumps(t.get("tags") or []).decode() if t.get("tags") is not None else None,
                    None, "", 0, 0, 0,
                    f"audio/{aslug}/{slugify(t.get('name'))}_j{page}-{rank}.mp3",
                    dl,
                ))
            if not tuples:
                return 0
            with nlock:
                if limit_tracks:
                    tuples = tuples[: max(0, limit_tracks - n[0])]
                if not tuples:
                    return 0
                n[0] += len(tuples)
                ledger.insert_tracks(tuples)
                ledger.upsert_shards([(f"jamendo-p{page}", 0, len(tuples), 0)])
            return len(tuples)

        with ThreadPoolExecutor(max_workers=4) as ex, \
             tqdm(total=pages, desc="JAMENDO scan", unit="page") as bar:
            for fut in as_completed({ex.submit(worker, p): p for p in range(1, pages + 1)}):
                try:
                    fut.result()
                except Exception as e:  # noqa: BLE001
                    print(f"[Jamendo] page warn: {e!r}")
                bar.update(1)
        print(f"[Jamendo] discovered {n[0]} permissive track(s); license URLs preserved per row")

    # ------------------------------------------------------------ extraction
    def extract(self, ledger, limit_tracks=None) -> None:
        """Download every registered direct-URL track (generic http source path)."""
        rows = ledger.pending_rows_for_dl()
        if limit_tracks:
            rows = rows[:limit_tracks]
        if not rows:
            print("[Jamendo] nothing with direct download URLs pending")
            return
        print(f"[Jamendo] extracting {len(rows)} track(s) from direct API downloads")
        bar = tqdm(total=len(rows), desc="EXTRACT(jamendo)", unit="track")
        tmp = self.cfg.data_dir / "tmp"
        tmp.mkdir(parents=True, exist_ok=True)

        def work(row):
            tk, dl_url, rel = row["track_key"], row["dl_url"], row["audio_path"]
            if not ledger.claim_track(tk):
                return
            dst = self.cfg.data_dir / (rel or f"audio/unknown/{tk}.mp3")
            dst.parent.mkdir(parents=True, exist_ok=True)
            part = dst.with_name(dst.name + ".part")
            try:
                req = urllib.request.Request(dl_url, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=300) as r, open(part, "wb") as fh:
                    while True:
                        chunk = r.read(1 << 20)
                        if not chunk:
                            break
                        fh.write(chunk)
                data = part.read_bytes()
                m5, s2 = dual_hash(data, self.cfg.hash_buffer)
                from msarchive.state import STATUS_UPLOADED_HF  # noqa: F401
                os_replace(part, dst)
                ledger.mark_downloaded(tk, str(dst.relative_to(self.cfg.data_dir)), len(data), m5, s2)
                bar.update(1)
            except Exception as e:  # noqa: BLE001
                try:
                    part.unlink()
                except OSError:
                    pass
                ledger.mark_failed(tk, repr(e)[:300])
                bar.set_postfix_str("err")

        with ThreadPoolExecutor(max_workers=max(4, self.cfg.extract_workers)) as ex:
            for fut in as_completed({ex.submit(work, r): r for r in rows}):
                try:
                    fut.result()
                except Exception as e:  # noqa: BLE001
                    print(f"[Jamendo] extract warn {e!r}")
        bar.close()

    def __repr__(self) -> str:  # pragma: no cover
        return f"<JamendoSource enabled={self.enabled}>"


def os_replace(a: Path, b: Path) -> None:
    import os
    os.replace(str(a), str(b))


def read_bytes(p: Path) -> bytes:
    return p.read_bytes()
