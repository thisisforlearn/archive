# cli.py — command surface: python -m msarchive <command> [flags]
# All files: Author: Vaibhav (Vaibhav Agarwal) — the archiver |
# nekomeowpurr@proton.me | https://github.com/thisisforlearn/archive | GPL-3.0-only
from __future__ import annotations

import argparse
import sys

from msarchive.config import Config


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="msarchive",
        description="Archive permissively-licensed music to the Internet Archive with a "
                    "Hugging Face mirror and hourly progress ledger. "
                    "Author: Vaibhav (Vaibhav Agarwal) — nekomeowpurr@proton.me — "
                    "https://github.com/thisisforlearn/archive",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("--limit-shards", type=int, default=None)
        sp.add_argument("--limit-tracks", type=int, default=None)
        sp.add_argument("--limit-items", type=int, default=None)
        sp.add_argument("--policy", choices=("permissive", "strict", "flags", "all"), default=None)
        sp.add_argument("--source", choices=("fma_hf", "jamendo"), default=None)
        sp.add_argument("--data-dir", default=None)
        sp.add_argument("--dry-run", action="store_true")

    for name in ("scan", "extract", "upload-ia", "checkpoint", "restore", "stats"):
        s = sub.add_parser(name)
        common(s)
        if name in ("checkpoint",):
            s.add_argument("--final", action="store_true")

    r = sub.add_parser("run")
    common(r)
    r.add_argument("--max-hours", type=float, default=None, help="time budget (Kaggle: 11.5)")
    r.add_argument("--start-at", choices=("all",), default="all")

    args = p.parse_args(argv)
    cfg = Config.from_env(**{
        k: v for k, v in dict(
            data_dir=args.data_dir,
            dry_run=True if args.dry_run else None,
            policy=args.policy,
            max_shards=args.limit_shards,
            max_tracks=args.limit_tracks,
            limit=args.limit_items,
        ).items() if v is not None
    })

    from msarchive.state import Ledger
    from msarchive.hf_sync import HfMirror
    from msarchive.ia_upload import IaUploader
    from msarchive.licenses import PermitPolicy
    from msarchive.sources import get_source
    from msarchive import GREETING
    import msarchive
    print(GREETING.format(v=msarchive.__version__, a=msarchive.__author__,
                          c=msarchive.__contact__, g=msarchive.__github__))

    ledger = Ledger(cfg.db_path)
    try:
        if args.cmd == "stats":
            print(cfg.avx2 and "[arch] AVX2 hashing on", ledger.stats())
            return 0
        if args.cmd == "run":
            if args.dry_run:
                cfg = Config.from_env(**{k: v for k, v in (
                    {**vars(args), "dry_run": True}).items() if k in ("data_dir", "dry_run")})
            from msarchive import runner
            return runner.run_all(cfg, source_name=args.source, max_hours=args.max_hours,
                                  limit_shards=args.limit_shards, limit_tracks=args.limit_tracks,
                                  limit_items=args.limit_items)

        hf = HfMirror(cfg, ledger)
        ia = IaUploader(cfg, ledger)
        policy = PermitPolicy(cfg.policy or "permissive", cfg.include_sampling)

        if args.cmd == "restore":
            hf.restore()
        elif args.cmd == "checkpoint":
            ok = hf.sync("manual", final=args.final)
            print("checkpoint:", "ok" if ok else "failed")
        elif args.cmd == "scan":
            src = get_source(cfg, ledger, args.source)
            if args.source == "jamendo":
                src.scan(ledger, policy, limit_tracks=args.limit_tracks)
            else:
                src.scan(ledger, policy, limit_shards=args.limit_shards, limit_tracks=args.limit_tracks)
        elif args.cmd == "extract":
            src = get_source(cfg, ledger, args.source)
            if args.source == "jamendo":
                src.extract(ledger, limit_tracks=args.limit_tracks)
            else:
                src.extract_all(ledger, limit_tracks=args.limit_tracks)
        elif args.cmd == "upload-ia":
            ia.upload(limit_items=args.limit_items)
    finally:
        ledger.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
