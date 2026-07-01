#!/usr/bin/env python3
"""Upload ops/data_acquisition_plan artifacts to Cloudflare R2."""

from __future__ import annotations

import csv
import hashlib
import json
import mimetypes
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "ops" / "data_acquisition_plan"
BUCKET = "crisis-damage-intelligence"
PUBLIC_BASE_URL = "https://pub-35cd6458677c4b4c844a23fb91b0370e.r2.dev"
DEFAULT_PREFIX = "ops/data-acquisition/2026-06-30"
MANIFEST_CSV = DATA_DIR / "r2_upload_manifest.csv"
MANIFEST_JSON = DATA_DIR / "r2_upload_manifest.json"


CONTENT_TYPES = {
    ".csv": "text/csv; charset=utf-8",
    ".geojson": "application/geo+json; charset=utf-8",
    ".gpkg": "application/geopackage+sqlite3",
    ".json": "application/json; charset=utf-8",
    ".jsonl": "application/x-ndjson; charset=utf-8",
    ".md": "text/markdown; charset=utf-8",
    ".png": "image/png",
    ".zip": "application/zip",
}


def utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def content_type(path: Path) -> str:
    return CONTENT_TYPES.get(path.suffix.lower()) or mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def cache_control(path: Path) -> str:
    if path.suffix.lower() in {".zip", ".gpkg", ".geojson"}:
        return "public, max-age=31536000, immutable"
    if "live_products_latest" in path.name:
        return "public, max-age=300"
    return "public, max-age=3600"


def upload(path: Path, key: str) -> None:
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
        cache_control(path),
        "--force",
    ]
    subprocess.check_call(cmd, cwd=ROOT)


def should_upload(path: Path) -> bool:
    if not path.is_file():
        return False
    if path.name.endswith(".tmp"):
        return False
    if path.name in {MANIFEST_CSV.name, MANIFEST_JSON.name}:
        return False
    return path.suffix.lower() in CONTENT_TYPES


def object_key(path: Path, prefix: str) -> str:
    return f"{prefix}/{path.relative_to(DATA_DIR).as_posix()}"


def write_manifests(rows: list[dict[str, Any]]) -> None:
    fields = [
        "uploaded_at",
        "local_path",
        "r2_bucket",
        "r2_key",
        "public_url",
        "bytes",
        "sha256",
        "content_type",
        "cache_control",
        "status",
    ]
    with MANIFEST_CSV.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    MANIFEST_JSON.write_text(json.dumps({"rows": rows}, indent=2) + "\n")


def main() -> int:
    prefix = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PREFIX
    paths = sorted(path for path in DATA_DIR.rglob("*") if should_upload(path))
    rows: list[dict[str, Any]] = []
    uploaded_at = utc_stamp()

    for index, path in enumerate(paths, start=1):
        key = object_key(path, prefix)
        print(f"[{index}/{len(paths)}] upload {path.relative_to(ROOT)} -> {key}", flush=True)
        upload(path, key)
        rows.append(
            {
                "uploaded_at": uploaded_at,
                "local_path": str(path.relative_to(ROOT)),
                "r2_bucket": BUCKET,
                "r2_key": key,
                "public_url": f"{PUBLIC_BASE_URL}/{key}",
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
                "content_type": content_type(path),
                "cache_control": cache_control(path),
                "status": "uploaded",
            }
        )

    write_manifests(rows)
    manifest_rows: list[dict[str, Any]] = []
    for manifest in (MANIFEST_CSV, MANIFEST_JSON):
        key = object_key(manifest, prefix)
        print(f"upload manifest {manifest.relative_to(ROOT)} -> {key}", flush=True)
        upload(manifest, key)
        manifest_rows.append(
            {
                "uploaded_at": utc_stamp(),
                "local_path": str(manifest.relative_to(ROOT)),
                "r2_bucket": BUCKET,
                "r2_key": key,
                "public_url": f"{PUBLIC_BASE_URL}/{key}",
                "bytes": manifest.stat().st_size,
                "sha256": sha256(manifest),
                "content_type": content_type(manifest),
                "cache_control": cache_control(manifest),
                "status": "uploaded",
            }
        )
    rows.extend(manifest_rows)
    write_manifests(rows)
    for manifest in (MANIFEST_CSV, MANIFEST_JSON):
        upload(manifest, object_key(manifest, prefix))

    print(
        json.dumps(
            {
                "uploaded_count": len(rows),
                "uploaded_bytes": sum(int(row["bytes"]) for row in rows),
                "r2_bucket": BUCKET,
                "r2_prefix": prefix,
                "manifest_csv": str(MANIFEST_CSV.relative_to(ROOT)),
                "manifest_json": str(MANIFEST_JSON.relative_to(ROOT)),
                "manifest_url": f"{PUBLIC_BASE_URL}/{object_key(MANIFEST_CSV, prefix)}",
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
