#!/usr/bin/env python3
"""Upload selected tile assets to Cloudflare R2 with Wrangler.

This is a pragmatic fallback when S3-compatible credentials are unavailable.
It is intentionally resumable and scoped: use it for a high-priority AOI or zoom
range, not as the preferred full-bucket sync path.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TILES = ROOT / "public" / "data" / "tiles"
OPS = ROOT / "ops" / "r2_tile_uploads"
BUCKET = "crisis-damage-intelligence"


def content_type(path: Path) -> str:
    if path.suffix.lower() == ".webp":
        return "image/webp"
    return "application/octet-stream"


def object_key(path: Path) -> str:
    return "data/" + path.relative_to(ROOT / "public" / "data").as_posix()


def load_done(path: Path) -> set[str]:
    if not path.exists():
        return set()
    done: set[str] = set()
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        if item.get("ok"):
            done.add(item["key"])
    return done


def upload_one(path: Path, attempts: int) -> dict:
    key = object_key(path)
    cmd = [
        "npx",
        "wrangler",
        "r2",
        "object",
        "put",
        f"{BUCKET}/{key}",
        "--remote",
        "--file",
        str(path),
        "--content-type",
        content_type(path),
        "--cache-control",
        "public, max-age=31536000, immutable",
    ]
    last_error = ""
    for attempt in range(1, attempts + 1):
        proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
        if proc.returncode == 0:
            return {"ok": True, "key": key, "path": str(path), "attempt": attempt, "bytes": path.stat().st_size}
        last_error = (proc.stderr or proc.stdout)[-2000:]
        time.sleep(min(10, attempt * 2))
    return {"ok": False, "key": key, "path": str(path), "error": last_error}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aoi", required=True, help="AOI tile folder, e.g. emsr884-aoi12-caraballeda")
    parser.add_argument("--kind", choices=["before", "after"], action="append", help="Tile kind to include. Defaults to all kinds.")
    parser.add_argument("--min-zoom", type=int, default=0)
    parser.add_argument("--max-zoom", type=int, default=99)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--limit", type=int, default=0, help="Optional max files for smoke tests")
    parser.add_argument("--stop-after", type=int, default=0, help="Stop cleanly after this many uploads in the current run")
    parser.add_argument("--attempts", type=int, default=3)
    args = parser.parse_args()

    aoi_dir = TILES / args.aoi
    if not aoi_dir.exists():
        raise SystemExit(f"AOI tile directory not found: {aoi_dir}")

    kinds = set(args.kind or [p.name for p in aoi_dir.iterdir() if p.is_dir()])
    files: list[Path] = []
    for kind in sorted(kinds):
        kind_dir = aoi_dir / kind
        if not kind_dir.exists():
            continue
        for zoom_dir in sorted([p for p in kind_dir.iterdir() if p.is_dir()], key=lambda p: int(p.name)):
            zoom = int(zoom_dir.name)
            if args.min_zoom <= zoom <= args.max_zoom:
                files.extend(sorted(zoom_dir.rglob("*.webp")))
    if args.limit:
        files = files[: args.limit]

    OPS.mkdir(parents=True, exist_ok=True)
    log_path = OPS / f"{args.aoi}_{'-'.join(sorted(kinds))}_z{args.min_zoom}-{args.max_zoom}.jsonl"
    done = load_done(log_path)
    todo = [path for path in files if object_key(path) not in done]
    if args.stop_after:
        todo = todo[: args.stop_after]
    manifest = {
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "aoi": args.aoi,
        "kinds": sorted(kinds),
        "min_zoom": args.min_zoom,
        "max_zoom": args.max_zoom,
        "selected_files": len(files),
        "already_done": len(done),
        "todo": len(todo),
        "stop_after": args.stop_after,
        "log_path": str(log_path),
    }
    print(json.dumps(manifest, indent=2), flush=True)
    if not todo:
        return

    with log_path.open("a") as log:
        pool = ThreadPoolExecutor(max_workers=max(1, args.workers))
        futures = {pool.submit(upload_one, path, args.attempts): path for path in todo}
        completed = 0
        failures = 0
        try:
            for future in as_completed(futures):
                result = future.result()
                completed += 1
                if not result.get("ok"):
                    failures += 1
                log.write(json.dumps(result) + "\n")
                log.flush()
                print("." if result.get("ok") else "F", end="", flush=True)
                if completed % 80 == 0:
                    print(f" {completed}/{len(todo)} failures={failures}", flush=True)
        except KeyboardInterrupt:
            for future in futures:
                future.cancel()
            pool.shutdown(wait=False, cancel_futures=True)
            print(f"\ninterrupted after {completed}/{len(todo)} completed; rerun the same command to resume", flush=True)
            raise SystemExit(130)
        else:
            pool.shutdown(wait=True)
    print("\ncomplete", flush=True)


if __name__ == "__main__":
    main()
