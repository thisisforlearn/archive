# msarchive — open, permissively-licensed music archiver

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)
**Author: Vaibhav Agarwal (archiver)** — nekomeowpurr@proton.me — https://github.com/thisisforlearn/archive

Preserves **permissively-licensed** music (Creative Commons / CC0 / Free Art / Free
Music Philosophy) from the Free Music Archive preservation mirror, pushes it to the
**Internet Archive** as per-artist items with full attribution, and mirrors every
upload hourly to a public **Hugging Face** dataset so AI research can use it — while
always crediting the original artists.

- **Uploads are authored by Vaibhav Agarwal (archiver)** on every IA item, HF file,
  ATTRIBUTION.csv row and MANIFEST.csv row.
- **Please check out and support the original artists** — each track links back to
  its original FMA artist/album page; the archive exists for preservation and
  ethical open research, never to bypass the originals.
- Runs on **Kaggle** 12-hour CPU sessions: fully resumable, hourly checkpoints,
  nothing crashes — a session dying costs one re-run, not data.

## Pipeline

```
restore (HF ledger merge + audio re-fetch)
   → scan     (972 parquet shards, ranged metadata reads only — a few MB, never 520 GB)
   → extract  (row-group streaming; md5+sha256 in one AVX2-accelerated pass)
   → IA       (checksum-skip uploads, retries, ATTRIBUTION.csv sidecar, search aliases)
   → HF       (hourly dedupe mirror; server decides what is missing)
```
Extraction and IA upload run **in parallel** (threads) to maximize music-per-hour,
with a `Guard` watchdog: RAM/disk admission gating + tmp cleanup, so the session
survives instead of being OOM-killed.

## Famous work aliases

`msarchive/aliases.py` carries a curated nickname knowledge base (~180 works):
"Symphony No. 5 in C minor, Op. 67" ↔ **"Fate Symphony"** / "The Fate Motif" /
"fate knocking at the door"; "Moonlight Sonata"; "Raindrop Prelude"; "Air on the
G String"; "Ode to Joy"; "The Entertainer"; "Nuvole Bianche"; … Aliases are burned
into IA item `subject` tags + description "notable works" notes, and into
`ATTRIBUTION.csv` / `MANIFEST.csv` (`display_title`, `search_aliases`) so simple
searches hit the right file.

## Usage

```bash
./scripts/setup.sh                       # venv at ~/ml_env + requirements (local rule: no system installs)
cp .env.example .env                     # fill IA_S3_* + HF_TOKEN
source ~/ml_env/bin/activate
python -m msarchive run --max-hours 8    # full pipeline, resumable at any point
```

Commands: `run` · `scan` · `extract` · `upload-ia` · `checkpoint [--final]` · `restore` · `stats`.
Policies: `--policy permissive|strict|flags|all` (default name-based `permissive`).

**Kaggle**: import `notebooks/kaggle_runner.ipynb`, add the three Secrets
(`IA_S3_ACCESS_KEY`, `IA_S3_SECRET_KEY`, `HF_TOKEN`), Internet ON, run for 12 h —
rerun any time; the HF ledger resumes everything.

## What gets uploaded where

| Destination | Content | Credit |
|---|---|---|
| Internet Archive | per-artist items (`vaibhav-archive-music-<artist>`) + ATTRIBUTION.csv | `Vaibhav Agarwal (archiver)`, email, GitHub, `archived-from: Free Music Archive` |
| Hugging Face | audio mirror + `MANIFEST.csv` + `stats.json` + `README.md` card + SQLite ledger | dataset card "Uploaded by Vaibhav Agarwal (archiver)" |

IA keys: https://archive.org/account/s3.php · HF token: write access to your dataset repo.

## Integrity & compliance

- Per-track `md5` + `sha256` in the SQLite ledger; IA uploads use server-side
  checksum skip; HF per-file changes verified against the repo tree.
- Permissive policy = license name decides (CC0/CC-BY×/CC-BY-SA×/Free Art/FMP);
  `strict` also requires FMA's commercial+derivative flags; NC/ND/“Common Law”
  sound-recording licenses are **never** archived; CC-Sampling+ family excluded
  unless `MSARCHIVE_INCLUDE_SAMPLING=1`.
- GPL-3.0-only code — the **audio** retains its own per-track CC license
  (see MANIFEST.csv; CC-BY-SA chains still bind derivatives).

## Journal

- v0.1 — FMA full mirror source (972 shards, ~524 GB, ~106k tracks), ledger with
  restore-from-HF, parallel extract+IA, RAM/disk guard, hour-checkpoint mirror,
  famous-work aliases, permissive policy engine.

*Built by Vaibhav (Vaibhav Agarwal, archiver) with attribution first — please go
listen to (and fund) the original artists.*
