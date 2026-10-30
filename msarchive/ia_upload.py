# ia_upload.py — seller-of-provenance: pushes permissively-licensed tracks to the
# Internet Archive as per-artist/album items, with full attribution metadata,
# per-item ATTRIBUTION.csv, checksum-skip (never re-uploads), retries, and the
# archiver credit (Vaibhav Agarwal / email / GitHub) stamped on every item.
# Author: Vaibhav (Vaibhav Agarwal) — the archiver
# Contact: nekomeowpurr@proton.me | GitHub: https://github.com/thisisforlearn/archive
# Project authority: Vaibhav holds final decision power over this project.
# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import io
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from tqdm import tqdm

from msarchive import __github__, GREETING
from msarchive.aliases import (
    aliases_for_row,
    alias_description_notes,
    item_alias_subject,
    styled_title,
)
from msarchive.licenses import attribution_line
from msarchive.sources.fma_hf import slugify
from msarchive.state import (
    STATUS_DOWNLOADED,
    STATUS_UPLOADED_HF,
    STATUS_UPLOADED_IA,
)

DESCRIPTION_TMPL = """Archived from the Free Music Archive (https://freemusicarchive.org) via its
preservation mirror. Every file carries its original license and attribution —
full per-track table in {attr_file}.

{credit}

PLEASE CHECK OUT AND SUPPORT THE ORIGINALS: each track links back to its original
artist/album pages (see source links in the attribution table). These works remain
freely available under their own Creative Commons/public-domain licenses; this
mirror exists so open music stays preserved and usable for AI research.

Archiver: {archivist}
Contact : {email}
Project : {github}
License : per-track (CC-BY / CC BY-SA / CC0 / ...): see ATTRIBUTION.csv
Item    : {artist} — music collection (part {part}/{total})

{alias_notes}

DIRECT DOWNLOAD LINKS (one link per file; format: archive.org/download/<item>/<file>)
{download_links}
"""


class IaUploader:
    def __init__(self, cfg, ledger) -> None:
        self.cfg = cfg
        self.ledger = ledger
        self._session = None
        self._csv_identifier = None  # set per item so ATTRIBUTION rows carry their URLs

    # -------------------------------------------------------------- session
    def session(self):
        """Version-proof IA session.

        internetarchive >= 5.0 accepts credentials ONLY via a config mapping
        ({"s3": {"access": ..., "secret": ...}}); the access_key= kwargs were
        removed long ago. We try the modern path, verify the keys actually
        landed in the session, then fall back to the old kwargs form for
        ancient installs. A live preflight against s3.us.archive.org follows
        so bad keys fail loudly ONCE instead of 10k times in upload loops.
        """
        if self._session is not None:
            return self._session
        import internetarchive
        from msarchive import __version__

        sess = None
        if self.cfg.ia_access_key and self.cfg.ia_secret_key:
            cfgmap = {
                "s3": {"access": self.cfg.ia_access_key, "secret": self.cfg.ia_secret_key},
                "general": {"user_agent_suffix": f"msarchive/{__version__} ({__github__})"},
            }
            attempts = [
                lambda: internetarchive.get_session(config=cfgmap),                       # modern (5.x)
                lambda: internetarchive.get_session(                                      # legacy kwargs
                    access_key=self.cfg.ia_access_key, secret_key=self.cfg.ia_secret_key),
                lambda: internetarchive.session.ArchiveSession(config=cfgmap),            # belt & braces
            ]
            last_err = None
            for make in attempts:
                try:
                    candidate = make()
                except (TypeError, AttributeError, ImportError) as e:  # noqa: PERF203
                    last_err = e
                    continue
                if str(getattr(candidate, "access_key", "") or "") == self.cfg.ia_access_key:
                    sess = candidate
                    break
                last_err = candidate  # session built but keys did not stick
            if sess is None:
                raise RuntimeError(
                    f"[IA] could not construct an authenticated session (tried 3 strategies): {last_err!r}"
                )
        else:
            sess = internetarchive.get_session()  # env/file-driven installs
            if not str(getattr(sess, "access_key", "") or ""):  # pragma: no cover
                print("[IA] warning: no S3 keys in session — uploads will fail; "
                      "set IA_S3_ACCESS_KEY / IA_S3_SECRET_KEY (or IA_ACCESS_KEY / IA_SECRET_KEY)")
        self._validate_keys(sess)
        self._session = sess
        return self._session

    def _validate_keys(self, sess) -> bool:
        """Cheap live preflight: GET s3.us.archive.org with the LOW auth header.

        Valid keys -> 200; wrong keys -> 403 'Authentication failed'.
        Caches the result so one session only tests once.
        """
        if getattr(self, "_keys_ok", False):
            return True
        auth = f"LOW {getattr(sess, 'access_key', '')}:{getattr(sess, 'secret_key', '')}"
        if not sess.access_key:
            return False
        try:
            r = sess.get("https://s3.us.archive.org/", headers={"Authorization": auth}, timeout=20)
        except Exception as e:  # noqa: BLE001 — network flap: warn, do not kill the run
            print(f"[IA] key preflight skipped ({e!r}); continuing and letting uploads retry")
            self._keys_ok = True
            return True
        if r.status_code in (200, 204, 404):
            print("[IA] key preflight OK")
            self._keys_ok = True
            return True
        raise RuntimeError(
            f"[IA] S3 keys REJECTED by archive.org (HTTP {r.status_code}). "
            "Regenerate them at https://archive.org/account/s3.php and rerun."
        )

    # ---------------------------------------------------------- item planning
    def identifier_for(self, artist_slug: str, part: int = 1) -> str:
        base = f"{self.cfg.ia_item_prefix}-{artist_slug}"
        return base if part == 1 else f"{base}-p{part}"

    def plan_items(self) -> list[tuple[str, str, int]]:
        """Group every finished-track artist into (identifier, artist_slug, n_files)."""
        rows = self.ledger.uploaded_paths((STATUS_DOWNLOADED, STATUS_UPLOADED_HF))
        groups: dict[str, list] = {}
        for r in rows:
            aslug = slugify(r["artist"] or "unknown")
            groups.setdefault(aslug, []).append(r)
        out = []
        for aslug, files in sorted(groups.items()):
            for part, chunk in enumerate(range(0, len(files), self.cfg.ia_max_files_per_item), start=1):
                n = min(self.cfg.ia_max_files_per_item, len(files) - chunk)
                out.append((self.identifier_for(aslug, part), aslug, n))
        self.ledger.upsert_ia_items([(ident, aslug, n) for ident, aslug, n in out])
        return out

    # ------------------------------------------------------ download links
    LINKS_MAX = 400  # meta.xml stays lean; the full table always lives in ATTRIBUTION.csv

    @staticmethod
    def download_url(identifier: str, file_name: str) -> str:
        """IA direct-download permalink; spaces/+/& are URI-encoded (%20 style)."""
        from urllib.parse import quote as _q
        return f"https://archive.org/download/{identifier}/{_q(file_name)}"

    def _download_links(self, identifier: str, files: list) -> str:
        lines = [self.download_url(identifier, str(Path(r["audio_path"]).name))
                 for r in files[:self.LINKS_MAX]]
        extra = len(files) - len(lines)
        if extra > 0:
            lines.append(f"... {extra} more — every file (including these) is listed "
                         "with its URL, license and attribution in ATTRIBUTION.csv on this item")
        return "\n".join(lines)

    # ---------------------------------------------------------------- upload
    def _attribution_csv(self, files: list) -> str:
        import csv
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(("file", "title", "display_title", "aliases", "artist", "album",
                    "license", "license_url", "source_url", "download_url",
                    "archiver", "archiver_email", "archiver_github"))
        for r in files:
            name = str(Path(r["audio_path"]).name)
            display = styled_title(r["title"], r["artist"], r["composer"])
            primary, alias = aliases_for_row(r)
            w.writerow((name, r["title"], display,
                        " | ".join(alias[:8]),
                        r["artist"], r["album"], r["license_name"],
                        r["license_url"], r["source_url"],
                        self.download_url(self._csv_identifier or "", name) if getattr(self, "_csv_identifier", None) else "",
                        self.cfg.archivist_name, self.cfg.archivist_email, self.cfg.archivist_github))
        return buf.getvalue()

    def upload(self, identifiers=None, limit_items=None) -> None:
        if not (self.cfg.ia_access_key and self.cfg.ia_secret_key):
            print("[IA] IA_S3_ACCESS_KEY / IA_S3_SECRET_KEY not configured — skipping IA phase "
                  "(set them in .env; keys from https://archive.org/account/s3.php)")
            return
        planned = self.plan_items()
        todo = [p for p in planned if (identifiers is None or p[0] in identifiers)]
        if limit_items:
            todo = todo[:limit_items]
        if not todo:
            print("[IA] no planned items (extract tracks first)")
            return
        print(f"[IA] uploading {len(todo)} item(s) with {self.cfg.ia_workers} workers")

        bar = tqdm(total=len(todo), desc="IA items", unit="item", dynamic_ncols=True)
        fbar = tqdm(total=sum(p[2] for p in todo), desc="IA files", unit="file", dynamic_ncols=True)

        def work(plan):
            identifier, aslug, _ = plan
            self._upload_item(identifier, aslug, fbar)
            bar.update(1)

        with ThreadPoolExecutor(max_workers=self.cfg.ia_workers) as ex:
            fmap = {ex.submit(work, p): p for p in todo}
            for fut in as_completed(fmap):
                try:
                    fut.result()
                except Exception as e:  # noqa: BLE001
                    print(f"[IA] item error {fmap[fut][0]}: {e!r}")
        bar.close()
        fbar.close()

    def _upload_item(self, identifier: str, aslug: str, fbar) -> None:
        from msarchive.state import STATUS_FAILED, STATUS_UPLOADED_IA

        session = self.session()
        item = session.get_item(identifier)
        # Rebuild the deterministic file list for this artist.
        groups = self.ledger.uploaded_paths((STATUS_DOWNLOADED, STATUS_UPLOADED_HF))
        files = [r for r in groups if slugify(r["artist"] or "unknown") == aslug
                 and str(Path(r["audio_path"]).parent.name) == aslug]

        pending = [r for r in files]
        # Files already marked UPLOADED_IA can be skipped locally, EXCEPT when the item
        # identifier points to a previous part split — handled by deterministic ordering.
        if item.exists:
            have = {f["name"] for f in (item.files or [])}
            pending = [r for r in files if str(Path(r["audio_path"]).name) not in have]

        if not pending:
            self.ledger.set_ia_status(identifier, STATUS_UPLOADED_IA)
            return

        self.ledger.set_ia_status(identifier, "UPLOADING", None, None)
        self._csv_identifier = identifier
        attrib = self._attribution_csv(pending)
        alias_subject = item_alias_subject(pending)
        alias_notes = alias_description_notes(pending)
        artist_name = pending[0]["artist"] if pending else aslug
        md = {
            "mediatype": "audio",
            "collection": self.cfg.ia_collection,
            "title": f"{artist_name} — Vaibhav Music Archive",
            "creator": artist_name,
            "description": DESCRIPTION_TMPL.format(
                attr_file="ATTRIBUTION.csv", credit=attribution_line(self.cfg),
                archivist=self.cfg.archivist_name, email=self.cfg.archivist_email,
                github=__github__,
                artist=artist_name,
                part=identifier.rsplit("-p", 1)[-1] if "-p" in identifier else "1",
                total="multi",
                alias_notes=alias_notes,
                download_links=self._download_links(identifier, pending),
            ),
            "subject": ["music", "free music archive", "creative commons", "open music",
                        "vaibhav agarwal", "archiver", "thisisforlearn", *alias_subject],
            "licenseurl": "https://creativecommons.org/licenses/by/4.0/",
            "uploader": self.cfg.archivist_name,
            "archivist": self.cfg.archivist_name,
            "archivist-email": self.cfg.archivist_email,
            "source-project": __github__,
            "archived-from": "Free Music Archive (preservation mirror)",
        }
        try:
            if self.cfg.dry_run:
                print(f"[IA dry-run] would upload {len(pending)} file(s) to {identifier}; keys={sorted(md)}")
                self.ledger.set_ia_status(identifier, "QUEUED")
                return
            r = item.upload(
                files=[str(self.cfg.data_dir / rr["audio_path"]) for rr in pending],
                metadata=md,
                checksum=True,             # IA-side md5 match -> no re-upload
                retries=6,
                retries_sleep=30,
                verbose=True,
                queue_derive=True,
            )
            codes = [getattr(x, "status_code", 0) if not isinstance(x, Exception) else -1
                     for x in (r if isinstance(r, list) else [r])]
            if bad := [c for c in codes if c not in (200, 201)]:
                self.ledger.set_ia_status(identifier, STATUS_FAILED, None, f"status={bad}")
                return
            # provenance sidecar, uploaded after audio so item references resolve.
            # Read from disk (name->path dict); streaming BytesIO dict values are
            # NOT reliably ingested by IA S3 (200-but-NeverNoSuchKey observed).
            tmpdir = self.cfg.data_dir / "tmp"
            tmpdir.mkdir(parents=True, exist_ok=True)
            csv_path = tmpdir / f"ATTRIBUTION-{identifier}.csv"
            csv_path.write_text(attrib, encoding="utf-8")
            item.upload(
                files={"ATTRIBUTION.csv": str(csv_path)},
                metadata={}, checksum=False, retries=3, retries_sleep=10,
                verbose=False, queue_derive=False,
            )
            self.ledger.mark_track_ia([rr["track_key"] for rr in pending], identifier)
            self.ledger.set_ia_status(identifier, STATUS_UPLOADED_IA, len(pending))
            fbar.update(len(pending))
        except Exception as e:  # noqa: BLE001
            self.ledger.set_ia_status(identifier, STATUS_FAILED, None, repr(e)[:400])
            raise
