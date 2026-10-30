# hf_sync.py — Hugging Face mirror + hourly progress ledger.
#
# Every checkpoint:
#   1. snapshot the SQLite ledger (consistent copy via SQLite backup API),
#   2. regenerate MANIFEST.csv / stats.json / dataset README card,
#   3. upload_folder over the whole data dir — the Hub answers which files
#      already exist and only the missing content transfers (xet dedupe);
#      unchanged files make empty commits. This IS the "only upload what is
#      not already on HF" rule, verified server-authoritatively.
#   4. refresh the repo tree and mark mirrored tracks UPLOADED_HF in the ledger.
#
# Every session boot: restore() merges the last ledger from HF and re-fetches any
# audio that a previous session had already mirrored (so a dead 12h Kaggle session
# costs nothing but a few minutes of xet dedupe).
# Author: Vaibhav (Vaibhav Agarwal) — the archiver
# Contact: nekomeowpurr@proton.me | GitHub: https://github.com/thisisforlearn/archive
# Project authority: Vaibhav holds final decision power over this project.
# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import csv
import io
import time
from pathlib import Path

from tqdm import tqdm

from msarchive import __github__, __version__
from msarchive.licenses import attribution_line
from msarchive.state import (
    STATUS_DOWNLOADED,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_UPLOADED_HF,
    STATUS_UPLOADED_IA,
)

IGNORE = ["tmp/**", "tmp/*", "*.part", "**/.cache/**", ".cache/**", "cache/**"]


class HfMirror:
    def __init__(self, cfg, ledger) -> None:
        self.cfg = cfg
        self.ledger = ledger
        self._api = None
        self._tree: dict[str, dict] = {}
        self._tree_ts: float = 0.0
        # Resolved mirror repo id: starts from cfg, may auto-switch to the
        # token's own namespace if the configured namespace isn't accessible.
        self.repo_id: str = cfg.hf_repo_id

    @property
    def token(self) -> str | None:
        return self.cfg.hf_token

    def api(self):
        if self._api is None:
            from huggingface_hub import HfApi
            self._api = HfApi(token=self.token)
        return self._api

    # ----------------------------------------------------------------- helpers
    def repo_ok(self) -> bool:
        if not self.token:
            print("[HF] HF_TOKEN not set — HF mirror/checkpoints disabled (local-only mode)")
            return False
        return True

    def whoami(self) -> str:
        try:
            return str(self.api().whoami()["name"] or "")
        except Exception:
            return ""

    @staticmethod
    def _repo_leaf(repo_id: str) -> str:
        return repo_id.split("/", 1)[-1] or "vaibhav-music-archive"

    def ensure_repo(self, private: bool = False) -> None:
        from huggingface_hub.errors import RepositoryNotFoundError

        api = self.api()
        me = self.whoami()
        if me:
            print(f"[HF] logged in as '{me}'")
        ns = self.repo_id.split("/", 1)[0] if "/" in self.repo_id else self.repo_id
        if me and ns and ns != me:
            # Keep the configured namespace ONLY if the repo already exists there and
            # the token can see it (e.g. an org you belong to); otherwise switch to the
            # logged-in user's own namespace — avoids the known HF 403 dead-end
            # ("You don't have the rights to create a dataset under the namespace ...").
            known = False
            try:
                api.repo_info(self.repo_id, repo_type="dataset")
                known = True
            except RepositoryNotFoundError:
                known = False  # repo genuinely absent under the other namespace
            except Exception as e:  # noqa: BLE001
                status = getattr(getattr(e, "response", None), "status_code", None)
                known = status != 404  # gated/private/flap — don't switch on guesswork
            if not known:
                new_id = f"{me}/{self._repo_leaf(self.repo_id)}"
                print(f"[HF] token is '{me}' and {self.repo_id} is not yours/absent — "
                      f"using {new_id} (override with MSARCHIVE_HF_REPO_ID)")
                self.repo_id = new_id
        # exist_ok=True: NEVER touches repo contents — creation is a no-op if the
        # repo already exists; nothing is ever deleted or reset here.
        api.create_repo(self.repo_id, repo_type="dataset", private=private, exist_ok=True)
        try:
            self.ledger.write_meta("hf_mirror_repo", self.repo_id)
        except Exception:  # noqa: BLE001
            pass

    def refresh_tree(self) -> dict[str, dict]:
        tree = {}
        for f in self.api().list_repo_tree(self.repo_id, repo_type="dataset",
                                           path_in_repo="", recursive=True):
            name = getattr(f, "path", None) or getattr(f, "rpath", None)
            if not name:
                continue
            tree[name] = {
                "size": int(getattr(f, "size", 0) or 0),
                "sha256": getattr(f, "sha256", None) or (getattr(getattr(f, "lfs", None), "sha256", None) if getattr(f, "lfs", None) else None),
            }
        self._tree = tree
        self._tree_ts = time.time()
        return tree

    # ----------------------------------------------------------------- restore
    def restore(self) -> None:
        """Merge the last ledger snapshot from HF back into the live DB, then
        re-fetch audio that previous sessions had already mirrored."""
        if not self.repo_ok():
            return
        from huggingface_hub import hf_hub_download
        from huggingface_hub.utils import RepositoryNotFoundError
        tmp = self.cfg.data_dir / "tmp"
        tmp.mkdir(parents=True, exist_ok=True)
        try:
            local = hf_hub_download(
                repo_id=self.repo_id, repo_type="dataset",
                filename="state/msarchive.db", local_dir=str(tmp),
                force_download=False, token=self.token,
            )
            self.ledger.merge_from(Path(local))
            print(f"[HF] merged ledger snapshot from {self.repo_id}")
        except RepositoryNotFoundError:
            print("[HF] no prior ledger on the Hub — starting a fresh archive "
                  "(any existing repo files stay untouched; nothing is deleted)")
            self.ensure_repo()
            return
        except Exception as e:  # noqa: BLE001
            print(f"[HF] ledger pull failed ({e!r}); continuing with local state")
            return

        self._restore_audio(hf_hub_download, tmp)

    def _restore_audio(self, hf_hub_download, tmp: Path) -> None:
        """Bring back audio files known-mirrored/extracted upstream but absent locally."""
        tree = self.refresh_tree()
        rows = self.ledger.uploaded_paths(
            (STATUS_DOWNLOADED, STATUS_UPLOADED_HF, STATUS_UPLOADED_IA)
        )
        todo = []
        for r in rows:
            rel = r["audio_path"]
            if rel and rel in tree and not (self.cfg.data_dir / rel).exists():
                todo.append((r["track_key"], rel))
        if not todo:
            print("[HF] audio restore: nothing to fetch")
            return
        print(f"[HF] restoring {len(todo)} already-archived file(s) from the mirror (dedupe-fast)")
        for tk, rel in tqdm(todo, desc="HF restore", unit="file"):
            try:
                hf_hub_download(
                    repo_id=self.repo_id, repo_type="dataset",
                    filename=rel, local_dir=str(self.cfg.data_dir), token=self.token,
                )
                self.ledger.mark_downloaded(tk, rel, int(tree[rel]["size"]), "", "")
            except Exception as e:  # noqa: BLE001
                print(f"[HF] restore miss {rel}: {e!r}")
                self.ledger.mark_failed(tk, "restore-miss")

    # ---------------------------------------------------------------- artifacts
    def write_manifest(self) -> Path:
        from msarchive.aliases import aliases_for_row, styled_title
        out = self.cfg.manifest_dir / "MANIFEST.csv"
        rows = self.ledger.uploaded_paths((STATUS_DOWNLOADED, STATUS_UPLOADED_HF, STATUS_UPLOADED_IA))
        with open(out, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow((
                "file", "title", "display_title", "search_aliases",
                "artist", "album", "license", "license_url",
                "source_url", "uploaded_by", "archiver_email", "project_github",
            ))
            for r in rows:
                primary, alias = aliases_for_row(r)
                w.writerow((
                    r["audio_path"], r["title"],
                    styled_title(r["title"], r["artist"], r["composer"],
                                 primary=primary, aliases=alias),
                    " | ".join(alias[:8]),
                    r["artist"], r["album"], r["license_name"], r["license_url"],
                    r["source_url"],
                    self.cfg.archivist_name, self.cfg.archivist_email, __github__,
                ))
        return out

    def write_stats(self) -> Path:
        import orjson
        st = self.ledger.stats()
        st.update({
            "checkpoint_ts": int(time.time()),
            "archiver": self.cfg.archivist_name,
            "archiver_email": self.cfg.archivist_email,
            "github": __github__,
            "version": __version__,
        })
        out = self.cfg.manifest_dir / "stats.json"
        out.write_bytes(orjson.dumps(st, option=orjson.OPT_INDENT_2))
        return out

    def write_readme(self) -> Path:
        st = self.ledger.stats()
        n_tracks = sum(int(v) for k, v in st.items()
                       if isinstance(v, int) and k in (
                           STATUS_PENDING, STATUS_DOWNLOADED, STATUS_UPLOADED_HF, STATUS_UPLOADED_IA, STATUS_FAILED
                       ))
        gb = st.get("audio_bytes", 0) / (1 << 30)
        artists = st.get("artists", 0)
        text = f"""---
license: other
license_name: per-track-creative-commons
language_notes: audio corpus; per-track licenses recorded in MANIFEST.csv
---

# Vaibhav Music Archive (open, permissively-licensed music preservation)

Mirror of **permissively-licensed** music (FMA full preservation mirror, optional
Jamendo additions): **{n_tracks} tracks (~{gb:.1f} GiB) by {artists} artists**.

Every audio file carries its ORIGINAL Creative Commons license; the full per-track
attribution table (license URL + original source page) is in `manifest/MANIFEST.csv`.

## Credits & provenance

- **Uploaded by {self.cfg.archivist_name}** — {self.cfg.archivist_email}
- Project GitHub: {__github__} (GPL-3.0-only code — this dataset contains third-party audio under its own per-track CC licenses)
- Original corpus: https://freemusicarchive.org — **please check out and support the original
  artists and the Free Music Archive**; this backup exists purely for preservation and
  ethical AI research under the original licenses.

## Famous works — common names

Famous classical / piano works carry search aliases ("Moonlight Sonata",
"Fate Symphony", "fate knocking at the door", "Raindrop Prelude", "Air on the G
String", "Ode to Joy", ...): see `display_title` and `search_aliases` columns in
`MANIFEST.csv`. Alias tags are also embedded in the Internet Archive item
subjects, so searching by common name lands on the right file.

## AI-training note

Only tracks permitting commercial use and derivatives are included (policy:
permissive). See `manifest/MANIFEST.csv` per row for each track's license; honor the
license when re-using (e.g. CC-BY-SA share-alike chains still apply to derivatives).

## Integrity

`state/msarchive.db` is the SQLite progress ledger (per-track md5/sha256, source
geometry). `state/stats.json` carries live counters of the archiver run.
"""
        out = self.cfg.data_dir / "README.md"
        out.write_text(text, encoding="utf-8")
        return out

    # ------------------------------------------------------------------ commit
    def sync(self, reason: str = "checkpoint", final: bool = False) -> bool:
        if not self.repo_ok():
            return False
        import os
        os.environ.setdefault("HF_XET_HIGH_PERFORMANCE", "1")
        t0 = time.time()
        try:
            self.ensure_repo()
        except Exception as e:  # noqa: BLE001
            print(f"[HF] repo ensure failed: {e!r}")
            return False
        self.write_manifest()
        self.write_stats()
        self.write_readme()
        from pathlib import Path as _P
        snap = self.cfg.data_dir / "state" / "msarchive.db"
        try:
            self.ledger.snapshot(snap)
        except Exception as e:  # noqa: BLE001
            print(f"[HF] snapshot warn: {e!r}")

        from huggingface_hub import upload_folder
        from huggingface_hub.utils import HfHubHTTPError
        n_before = self.ledger.stats().get("audio_bytes", 0)
        # SAFETY: upload_folder NEVER deletes remote files unless delete_patterns is
        # passed (Hub docs). We pass none — every checkpoint only adds/overwrites,
        # so audio already mirrored in the repo is preserved across sessions.
        try:
            upload_folder(
                folder_path=str(self.cfg.data_dir),
                repo_id=self.repo_id,
                repo_type="dataset",
                commit_message=f"{reason}: {self.cfg.archivist_name} <{self.cfg.archivist_email}> ({__github__})",
                ignore_patterns=IGNORE,
                token=self.token,
                delete_patterns=None,  # explicit: never remove existing repo files
            )
        except HfHubHTTPError as e:
            print(f"[HF] upload_folder failed: {e}")
            return False
        except FileNotFoundError as e:
            print(f"[HF] transient missing file during mirror scan: {e!r} (next checkpoint retries)")
            # leftover .part files from crashed writers are ignored via IGNORE patterns; retry once
            try:
                upload_folder(
                    folder_path=str(self.cfg.data_dir),
                    repo_id=self.repo_id, repo_type="dataset",
                    commit_message=f"{reason} (retry): {self.cfg.archivist_name}",
                    ignore_patterns=IGNORE, token=self.token,
                    delete_patterns=None,  # never remove existing repo files
                )
            except Exception as e2:  # noqa: BLE001
                print(f"[HF] retry failed: {e2!r}")
                return False
        except Exception as e:  # noqa: BLE001
            print(f"[HF] upload error: {e!r}")
            return False

        # ledger: mark what is verifiably on the Hub now
        try:
            tree = self.refresh_tree()
            done = []
            for r in self.ledger.uploaded_paths((STATUS_DOWNLOADED, STATUS_UPLOADED_HF, STATUS_UPLOADED_IA)):
                rel = r["audio_path"]
                local = (self.cfg.data_dir / rel) if rel else None
                if not rel or rel not in tree or not local.exists():
                    continue
                ls = local.stat().st_size
                if ls <= 0:
                    continue
                sha = tree[rel].get("sha256")
                if (sha and r["sha256"] and sha == r["sha256"]) or tree[rel]["size"] == ls:
                    done.append(r["track_key"])
            self.ledger.mark_track_hf(done)
        except Exception as e:  # noqa: BLE001
            print(f"[HF] tree refresh/mark warn: {e!r}")

        dt = time.time() - t0
        st = self.ledger.stats()
        print(f"[HF] checkpoint complete in {dt:.0f}s — ledger bytes mirrored {n_before / (1 << 30):.2f} GiB → "
              f"{st}")
        return True
