#!/usr/bin/env python3
"""Generate free chip-QA artifacts for AOI12 v2 features that need new VLM."""

from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from PIL import Image, ImageStat

from run_minimax_ems_before_after_review import chip_path, feature_lonlat, regenerate_chips


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "ops" / "data_acquisition_plan"
AOI_ID = "emsr884-aoi12-caraballeda"
REMAP = OUT_DIR / "aoi12_v1_v2_remap.csv"
V2_GEOJSON = OUT_DIR / "aoi12_gra_v2_builtup.geojson"
QA_CSV = OUT_DIR / "aoi12_v2_new_chip_qa.csv"
QA_JSON = OUT_DIR / "aoi12_v2_new_chip_qa_summary.json"


def utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def public_chip(path: Path) -> str:
    return "/data/chips/" + path.relative_to(ROOT / "public" / "data" / "chips").as_posix()


def load_new_ids() -> list[str]:
    with REMAP.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    return [row["new_id"] for row in rows if row["remap_action"] == "new_regenerate" and row.get("new_id")]


def load_features(feature_ids: list[str]) -> list[dict[str, Any]]:
    wanted = set(feature_ids)
    data = json.loads(V2_GEOJSON.read_text())
    by_id = {(feature.get("properties") or {}).get("id"): feature for feature in data.get("features", [])}
    missing = [feature_id for feature_id in feature_ids if feature_id not in by_id]
    if missing:
        raise SystemExit(f"Missing v2 features in {V2_GEOJSON}: {', '.join(missing[:10])}")
    return [by_id[feature_id] for feature_id in feature_ids]


def image_metrics(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "exists": False,
            "width": "",
            "height": "",
            "mean_rgb": "",
            "valid_pixel_ratio": "",
            "bytes": "",
        }
    image = Image.open(path).convert("RGB")
    stat = ImageStat.Stat(image)
    gray = image.convert("L")
    histogram = gray.point(lambda value: 255 if value > 4 else 0).histogram()
    valid_ratio = histogram[255] / float(image.width * image.height)
    return {
        "exists": True,
        "width": image.width,
        "height": image.height,
        "mean_rgb": round(sum(stat.mean) / 3, 3),
        "valid_pixel_ratio": round(valid_ratio, 4),
        "bytes": path.stat().st_size,
    }


def automated_verdict(before: dict[str, Any], after: dict[str, Any], compare: dict[str, Any]) -> str:
    if not before["exists"]:
        return "skip_missing_before_chip"
    if not after["exists"]:
        return "skip_missing_after_chip"
    if not compare["exists"]:
        return "skip_missing_compare_chip"
    if float(before["valid_pixel_ratio"]) < 0.8 or float(before["mean_rgb"]) < 10:
        return "hold_before_chip_black_or_sparse"
    if float(after["valid_pixel_ratio"]) < 0.8 or float(after["mean_rgb"]) < 10:
        return "hold_after_chip_black_or_sparse"
    return "pass_automated_chip_qa_needs_manual_alignment_review"


def main() -> int:
    checked_at = utc_stamp()
    feature_ids = load_new_ids()
    features = load_features(feature_ids)
    made = regenerate_chips(AOI_ID, features)
    rows: list[dict[str, Any]] = []

    for feature in features:
        props = feature.get("properties") or {}
        feature_id = props["id"]
        center = feature_lonlat(feature)
        before_path = chip_path(AOI_ID, feature_id, "before_event")
        after_path = chip_path(AOI_ID, feature_id, "after_event")
        compare_path = chip_path(AOI_ID, feature_id, "before_after_compare")
        before = image_metrics(before_path)
        after = image_metrics(after_path)
        compare = image_metrics(compare_path)
        verdict = automated_verdict(before, after, compare)
        rows.append(
            {
                "checked_at": checked_at,
                "aoi_id": AOI_ID,
                "feature_id": feature_id,
                "official_ems_damage_gra": props.get("damage_gra", ""),
                "official_ems_damage_percent": props.get("damage_percent", ""),
                "centroid_lat": round(center[1], 8) if center else "",
                "centroid_lon": round(center[0], 8) if center else "",
                "before_chip": public_chip(before_path),
                "after_chip": public_chip(after_path),
                "compare_chip": public_chip(compare_path),
                "before_exists": before["exists"],
                "after_exists": after["exists"],
                "compare_exists": compare["exists"],
                "before_mean_rgb": before["mean_rgb"],
                "after_mean_rgb": after["mean_rgb"],
                "before_valid_pixel_ratio": before["valid_pixel_ratio"],
                "after_valid_pixel_ratio": after["valid_pixel_ratio"],
                "before_bytes": before["bytes"],
                "after_bytes": after["bytes"],
                "compare_bytes": compare["bytes"],
                "automated_verdict": verdict,
                "manual_alignment_review_required": verdict == "pass_automated_chip_qa_needs_manual_alignment_review",
                "vlm_spend_gate": "do_not_run_vlm_until_manual_alignment_review_passes",
            }
        )

    fieldnames = [
        "checked_at",
        "aoi_id",
        "feature_id",
        "official_ems_damage_gra",
        "official_ems_damage_percent",
        "centroid_lat",
        "centroid_lon",
        "before_chip",
        "after_chip",
        "compare_chip",
        "before_exists",
        "after_exists",
        "compare_exists",
        "before_mean_rgb",
        "after_mean_rgb",
        "before_valid_pixel_ratio",
        "after_valid_pixel_ratio",
        "before_bytes",
        "after_bytes",
        "compare_bytes",
        "automated_verdict",
        "manual_alignment_review_required",
        "vlm_spend_gate",
    ]
    with QA_CSV.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    verdict_counts = Counter(row["automated_verdict"] for row in rows)
    summary = {
        "checked_at": checked_at,
        "aoi_id": AOI_ID,
        "candidate_features": len(features),
        "chip_triplets_regenerated": made,
        "verdict_counts": dict(verdict_counts),
        "automated_pass_needing_manual_alignment_review": verdict_counts.get(
            "pass_automated_chip_qa_needs_manual_alignment_review", 0
        ),
        "qa_csv": str(QA_CSV.relative_to(ROOT)),
        "warning": "Automated chip QA only checks existence and black/sparse pixels. Manual alignment/target review is still required before HF spend.",
    }
    QA_JSON.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
