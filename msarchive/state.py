# state.py — SQLite progress ledger: exact knowledge of done / not-done across crashes,
# sessions, and machines. WAL-tuned, batched, merge-capable (HF snapshot merge).
# Author: Vaibhav (Vaibhav Agarwal) — the archiver
# Contact: nekomeowpurr@proton.me | GitHub: https://github.com/thisisforlearn/archive
# Project authority: Vaibhav holds final decision power over this project.
# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

TRACK_STATUS_COLS = ["shard", "row_idx", "title", "artist", "album", "license_code", "license_name", "license_url", "source_url", "artist_url", "album_url", "tags", "genres", "released", "listens", "explicit", "instrumental", "audio_path", "size", "md5", "sha256", "dl_url", "status", "tries", "last_err"]
SHARD_COLS = ["status", "rows_total", "rows_kept", "bytes_total", "tries"]
IA_COLS = ["artist", "status", "files", "files_done", "tries", "last_err"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(
  k TEXT PRIMARY KEY, v TEXT
);
CREATE TABLE IF NOT EXISTS tracks(
  track_key TEXT PRIMARY KEY,        -- '<shard_id>:<row_idx>'
  shard TEXT NOT NULL,
  row_idx INTEGER NOT NULL,
  title TEXT, artist TEXT, album TEXT, composer TEXT,
  license_code INTEGER,
  license_name TEXT, license_url TEXT,
  source_url TEXT, artist_url TEXT, album_url TEXT,
  tags TEXT, genres TEXT, released TEXT, listens INTEGER,
  explicit INTEGER, instrumental INTEGER,
  audio_path TEXT,                   -- repo-relative 'audio/<artist>/<file>.mp3'
  size INTEGER, md5 TEXT, sha256 TEXT,
  dl_url TEXT,                       -- direct-download URL (Jamendo-style sources; NULL for FMA)
  status TEXT NOT NULL DEFAULT 'PENDING',
  tries INTEGER DEFAULT 0, last_err TEXT,
  seq INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_tracks_status ON tracks(status, shard);
CREATE INDEX IF NOT EXISTS ix_tracks_artist ON tracks(artist);
CREATE TABLE IF NOT EXISTS shards(
  path TEXT PRIMARY KEY,
  status TEXT NOT NULL DEFAULT 'SCANNED',   -- SCANNED | EXTRACTED
  rows_total INTEGER, rows_kept INTEGER,
  bytes_total INTEGER, tries INTEGER DEFAULT 0,
  seq INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS ia_items(
  identifier TEXT PRIMARY KEY,
  artist TEXT, status TEXT NOT NULL DEFAULT 'QUEUED',
  files INTEGER DEFAULT 0, files_done INTEGER DEFAULT 0,
  tries INTEGER DEFAULT 0, last_err TEXT,
  seq INTEGER NOT NULL DEFAULT 0
);
"""

STATUS_PENDING = "PENDING"
STATUS_DOWNLOADED = "DOWNLOADED"      # audio extracted to disk, hashed
STATUS_UPLOADED_HF = "UPLOADED_HF"    # mirrored to HF repo
STATUS_UPLOADED_IA = "UPLOADED_IA"    # pushed to Internet Archive
STATUS_FAILED = "FAILED"


class Ledger:
    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.path = db_path
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False, timeout=120)
        self._conn.isolation_level = None  # autocommit; batches via BEGIN/COMMIT
        self._conn.row_factory = sqlite3.Row  # name-based row access everywhere
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA temp_store=MEMORY")
        self._conn.execute("PRAGMA cache_size=-65536")
        self._conn.execute("PRAGMA mmap_size=268435456")
        with self._lock:
            self._conn.executescript(SCHEMA)
        # Monotonic, machine-independent seq: epoch-ms << 20 | 20-bit counter.
        self._base = int(time.time() * 1000) << 20
        self._i = 0

    def _nseq(self) -> int:
        self._i += 1
        return self._base | (self._i & 0xFFFFF)

    # ---- meta ------------------------------------------------------------
    def get_meta(self, k: str, d=None):
        with self._lock:
            row = self._conn.execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
            return row[0] if row else d

    def write_meta(self, k: str, v: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO meta(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
                (k, v),
            )

    # ---- shards ------------------------------------------------------------
    def upsert_shards(self, rows: list[tuple]) -> None:
        with self._lock, self._conn:
            self._conn.executemany(
                """INSERT INTO shards(path, status, rows_total, rows_kept, bytes_total, seq)
                   VALUES(?, 'SCANNED', ?, ?, ?, ?)
                   ON CONFLICT(path) DO UPDATE SET
                     rows_total=excluded.rows_total, rows_kept=excluded.rows_kept,
                     bytes_total=excluded.bytes_total, status=CASE WHEN shards.status='EXTRACTED' THEN 'EXTRACTED' ELSE 'SCANNED' END,
                     seq=max(shards.seq, excluded.seq)""",
                [(*r, self._nseq()) for r in rows],
            )

    def mark_shard_extracted(self, path: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE shards SET status='EXTRACTED', seq=? WHERE path=?", (self._nseq(), path)
            )

    def pending_shards(self, limit: int | None = None) -> list[str]:
        with self._lock:
            q = "SELECT path FROM shards WHERE status='SCANNED' ORDER BY path"
            if limit:
                q += " LIMIT %d" % int(limit)
            return [r[0] for r in self._conn.execute(q)]

    def scans_done(self) -> bool:
        with self._lock:
            return bool(self._conn.execute("SELECT 1 FROM shards LIMIT 1").fetchone())

    # ---- tracks ------------------------------------------------------------
    def insert_tracks(self, rows: list[tuple]) -> None:
        with self._lock, self._conn:
            self._conn.executemany(
                """INSERT INTO tracks(
                     track_key, shard, row_idx, title, artist, album, composer,
                     license_code, license_name, license_url, source_url,
                     artist_url, album_url, tags, genres, released, listens,
                     explicit, instrumental, audio_path, dl_url, status, seq)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'PENDING', ?)
                   ON CONFLICT(track_key) DO UPDATE SET
                     title=excluded.title, artist=excluded.artist, album=excluded.album,
                     composer=COALESCE(tracks.composer, excluded.composer),
                     license_name=excluded.license_name, license_url=excluded.license_url,
                     source_url=excluded.source_url, tags=excluded.tags, genres=excluded.genres,
                     audio_path=COALESCE(tracks.audio_path, excluded.audio_path),
                     dl_url=COALESCE(tracks.dl_url, excluded.dl_url),
                     seq=max(tracks.seq, excluded.seq)""",
                [(*r, self._nseq()) for r in rows],
            )

    def claim_track(self, track_key: str) -> bool:
        """Atomically claim a PENDING/FAILED track (retry cap: 4 attempts)."""
        with self._lock, self._conn:
            cur = self._conn.execute(
                "UPDATE tracks SET tries=tries+1, last_err=NULL, seq=? "
                "WHERE track_key=? AND status IN ('PENDING','FAILED') AND tries < 4",
                (self._nseq(), track_key),
            )
            return cur.rowcount == 1

    def mark_downloaded(self, track_key: str, audio_path: str, size: int, md5: str, sha256: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE tracks SET audio_path=?, size=?, md5=?, sha256=?, status=?, seq=? WHERE track_key=?",
                (audio_path, size, md5, sha256, STATUS_DOWNLOADED, self._nseq(), track_key),
            )

    def mark_failed(self, track_key: str, err: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE tracks SET status=?, last_err=?, seq=? WHERE track_key=?",
                (STATUS_FAILED, (err or "unknown")[:500], self._nseq(), track_key),
            )

    def mark_track_hf(self, keys: list[str]) -> None:
        if not keys:
            return
        with self._lock, self._conn:
            self._conn.executemany(
                "UPDATE tracks SET status=?, seq=? WHERE track_key=? AND status IN (?,?)",
                [(STATUS_UPLOADED_HF, self._nseq(), k, STATUS_DOWNLOADED, STATUS_UPLOADED_IA) for k in keys],
            )

    def mark_track_ia(self, keys: list[str]) -> None:
        if not keys:
            return
        with self._lock, self._conn:
            self._conn.executemany(
                "UPDATE tracks SET status=?, seq=? WHERE track_key=?",
                [(STATUS_UPLOADED_IA, self._nseq(), k) for k in keys],
            )

    def tracks_to_extract(self, shard: str | None = None, limit: int | None = None) -> list[sqlite3.Row]:
        with self._lock:
            base = "SELECT track_key, row_idx, title, artist, album, license_code FROM tracks WHERE status IN ('PENDING','FAILED')"
            args: list = []
            if shard:
                base += " AND shard=?"
                args.append(shard)
            base += " ORDER BY row_idx"
            if limit:
                base += " LIMIT %d" % int(limit)
            return self._conn.execute(base, args).fetchall()

    def pending_tracks_by_shard(self) -> dict[str, list[tuple[int, str]]]:
        """Claimable (tries<4) pending rows grouped by shard: [(row_idx, track_key), ...]."""
        with self._lock:
            out: dict[str, list[tuple[int, str]]] = {}
            for sh, ridx, tk in self._conn.execute(
                "SELECT shard, row_idx, track_key FROM tracks "
                "WHERE status IN ('PENDING','FAILED') AND tries < 4 ORDER BY shard, row_idx"
            ):
                out.setdefault(sh, []).append((ridx, tk))
            return out

    def get_track_field(self, track_key: str, field: str) -> str | None:
        assert field in ("audio_path", "sha256", "md5", "size", "title", "artist", "dl_url")
        with self._lock:
            row = self._conn.execute(
                f"SELECT {field} FROM tracks WHERE track_key=?", (track_key,)
            ).fetchone()
        return row[0] if row else None

    def pending_rows_for_dl(self) -> list[sqlite3.Row]:
        """Direct-download rows (Jamendo-style sources) not yet on disk."""
        with self._lock:
            return self._conn.execute(
                "SELECT track_key, dl_url, audio_path, title FROM tracks "
                "WHERE dl_url IS NOT NULL AND status IN ('PENDING','FAILED') AND tries < 4 "
                "ORDER BY shard, row_idx"
            ).fetchall()

    def uploaded_paths(self, statuses: tuple[str, ...]) -> list[sqlite3.Row]:
        qs = ",".join("?" * len(statuses))
        with self._lock:
            return self._conn.execute(
                f"""SELECT track_key, audio_path, sha256, size, artist, title, album,
                           composer, license_name, license_url, source_url
                    FROM tracks WHERE status IN ({qs}) AND audio_path IS NOT NULL""",
                statuses,
            ).fetchall()

    def audio_root_relative(self) -> list[str]:
        with self._lock:
            return [r[0] for r in self._conn.execute(
                "SELECT DISTINCT audio_path FROM tracks WHERE audio_path IS NOT NULL"
            )]

    def stats(self) -> dict:
        with self._lock:
            res = dict(self._conn.execute("SELECT status, COUNT(*) FROM tracks GROUP BY status"))
            n_shards = self._conn.execute("SELECT status, COUNT(*) FROM shards GROUP BY status").fetchall()
            agg = self._conn.execute(
                "SELECT COALESCE(SUM(size),0), COALESCE(SUM(listens),0) FROM tracks WHERE audio_path IS NOT NULL"
            ).fetchone()
            artists = self._conn.execute(
                "SELECT COUNT(DISTINCT artist) FROM tracks WHERE audio_path IS NOT NULL"
            ).fetchone()[0]
        res.update({
            "shards": dict(n_shards),
            "audio_bytes": agg[0] or 0,
            "total_listens": agg[1] or 0,
            "artists": artists or 0,
            "ops": self._i,
        })
        return res

    # ---- IA items -----------------------------------------------------------
    def upsert_ia_items(self, rows: list[tuple]) -> None:
        with self._lock, self._conn:
            self._conn.executemany(
                """INSERT INTO ia_items(identifier, artist, status, files, seq)
                   VALUES(?, ?, 'QUEUED', ?, ?)
                   ON CONFLICT(identifier) DO UPDATE SET
                     files=max(ia_items.files, excluded.files),
                     seq=max(ia_items.seq, excluded.seq)""",
                [(*r, self._nseq()) for r in rows],
            )

    def next_ia_batch(self, limit: int) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(
                "SELECT identifier, artist FROM ia_items WHERE status IN ('QUEUED','FAILED') "
                "ORDER BY identifier LIMIT ?", (limit,),
            ).fetchall()

    def set_ia_status(self, identifier: str, status: str, done: int | None = None, err: str | None = None) -> None:
        with self._lock, self._conn:
            if done is None:
                self._conn.execute(
                    "UPDATE ia_items SET status=?, last_err=CASE WHEN ? IS NULL THEN last_err ELSE ? END, seq=? WHERE identifier=?",
                    (status, err, err, self._nseq(), identifier),
                )
            else:
                self._conn.execute(
                    "UPDATE ia_items SET status=?, files_done=files_done+?, seq=? WHERE identifier=?",
                    (status, done, self._nseq(), identifier),
                )

    # ---- HF snapshot merge ---------------------------------------------------
    def snapshot(self, to_path: Path) -> None:
        """Consistent copy via sqlite backup API (safe while writers run)."""
        to_path.parent.mkdir(parents=True, exist_ok=True)
        dst = sqlite3.connect(str(to_path))
        with self._lock:
            self._conn.backup(dst)
        dst.commit()
        dst.close()

    def merge_from(self, other_path: Path) -> None:
        """Union-merge an HF snapshot into the live ledger; the higher seq wins per row."""
        other_path = Path(other_path)
        if not other_path.exists():
            return
        with self._lock, self._conn:
            self._conn.execute("ATTACH DATABASE ? AS hf", (str(other_path),))
            for table, keycol, cols in (
                ("tracks", "track_key", TRACK_STATUS_COLS),
                ("shards", "path", SHARD_COLS),
                ("ia_items", "identifier", IA_COLS),
            ):
                collist = ", ".join(cols)
                self._conn.execute(
                    f"INSERT INTO {table}({keycol}, {collist}, seq) "
                    f"SELECT {keycol}, {collist}, seq FROM hf.{table} WHERE true "
                    f"ON CONFLICT({keycol}) DO NOTHING"
                )
                self._conn.execute(
                    f"""UPDATE {table} SET ({collist})=(
                          SELECT {collist} FROM hf.{table} h
                          WHERE h.{keycol}={table}.{keycol} AND h.seq > {table}.seq
                        ) WHERE EXISTS (
                          SELECT 1 FROM hf.{table} h
                          WHERE h.{keycol}={table}.{keycol} AND h.seq > {table}.seq)"""
                )
            self._conn.execute("DETACH DATABASE hf")

    def close(self) -> None:
        with self._lock:
            self._conn.close()
