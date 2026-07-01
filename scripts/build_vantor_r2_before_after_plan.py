#!/usr/bin/env python3
"""Build an AOI-level before/after plan from the Vantor R2 manifest.

The output is intentionally a planning artifact. It reads only the compact R2
manifest and STAC JSON sidecars, then determines where dated pre/post imagery
can support chip QA before any paid VLM calls are made.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import urllib.request
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "public" / "data" / "catalog.json"
OUT_DIR = ROOT / "ops" / "data_acquisition_plan"
DEFAULT_MANIFEST_URL = "https://pub-35cd6458677c4b4c844a23fb91b0370e.r2.dev/vantor/venezuela-earthquake-jun-2026/manifests/vantor-all-manifest.json"
USER_AGENT = "respuesta-venezuela-vantor-before-after-plan/1.0"

COVERAGE_CSV = OUT_DIR / "vantor_r2_scene_coverage.csv"
PAIRS_CSV = OUT_DIR / "vantor_r2_before_after_pairs.csv"
AOI_SUMMARY_CSV = OUT_DIR / "vantor_r2_before_after_aoi_summary.csv"
SUMMARY_JSON = OUT_DIR / "vantor_r2_before_after_summary.json"


def utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch_json(url: str) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest-url", default=DEFAULT_MANIFEST_URL)
    return parser.parse_args()


def aoi_bbox(aoi: dict[str, Any]) -> list[float]:
    # Catalog bounds are [[south, west], [north, east]].
    return [aoi["bounds"][0][1], aoi["bounds"][0][0], aoi["bounds"][1][1], aoi["bounds"][1][0]]


def intersects(a: list[float], b: list[float]) -> bool:
    return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])


def intersection_bbox(a: list[float], b: list[float]) -> list[float] | None:
    if not intersects(a, b):
        return None
    return [max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])]


def bbox_area_approx_km2(bbox: list[float]) -> float:
    mid_lat = (bbox[1] + bbox[3]) / 2
    width_km = max(0.0, bbox[2] - bbox[0]) * 111.32 * max(0.05, math.cos(math.radians(mid_lat)))
    height_km = max(0.0, bbox[3] - bbox[1]) * 111.32
    return width_km * height_km


def geom_bbox(geometry: dict[str, Any]) -> list[float] | None:
    coords: list[tuple[float, float]] = []

    def walk(value: Any) -> None:
        if (
            isinstance(value, list)
            and len(value) >= 2
            and isinstance(value[0], (int, float))
            and isinstance(value[1], (int, float))
        ):
            coords.append((float(value[0]), float(value[1])))
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(geometry.get("coordinates", []))
    if not coords:
        return None
    return [min(x for x, _ in coords), min(y for _, y in coords), max(x for x, _ in coords), max(y for _, y in coords)]


def feature_point(feature: dict[str, Any]) -> tuple[float, float] | None:
    props = feature.get("properties") or {}
    lon = props.get("centroid_lon")
    lat = props.get("centroid_lat")
    if lon is not None and lat is not None:
        return float(lon), float(lat)
    bbox = geom_bbox(feature.get("geometry") or {})
    if not bbox:
        return None
    return (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2


def damage_layer_path(aoi: dict[str, Any]) -> tuple[Path | None, str]:
    if aoi["id"] == "emsr884-aoi12-caraballeda" and (OUT_DIR / "aoi12_gra_v2_builtup.geojson").exists():
        return OUT_DIR / "aoi12_gra_v2_builtup.geojson", "official_aoi12_gra_v2_ops"
    damage = (aoi.get("layers") or {}).get("damage")
    if not damage:
        return None, "none"
    path = ROOT / "public" / damage.lstrip("/")
    return (path, "public_catalog_damage_layer") if path.exists() else (None, "none")


def load_feature_points(aoi: dict[str, Any]) -> tuple[list[tuple[str, float, float]], str]:
    path, source = damage_layer_path(aoi)
    if not path:
        return [], source
    data = json.loads(path.read_text())
    points: list[tuple[str, float, float]] = []
    for index, feature in enumerate(data.get("features", []), start=1):
        point = feature_point(feature)
        if point is None:
            continue
        props = feature.get("properties") or {}
        feature_id = str(props.get("id") or f"feature_{index:05d}")
        points.append((feature_id, point[0], point[1]))
    return points, source


def covered_feature_ids(points: list[tuple[str, float, float]], bbox: list[float]) -> set[str]:
    return {feature_id for feature_id, lon, lat in points if bbox[0] <= lon <= bbox[2] and bbox[1] <= lat <= bbox[3]}


def num(value: Any, default: float = 999.0) -> float:
    try:
        if value in ("", None):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def compact_bbox(bbox: list[float] | None) -> str:
    if not bbox:
        return ""
    return json.dumps([round(value, 8) for value in bbox], separators=(",", ":"))


def load_vantor_items(manifest_url: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest = fetch_json(manifest_url)
    items: list[dict[str, Any]] = []
    for manifest_item in manifest.get("items", []):
        assets = manifest_item.get("assets") or {}
        stac_url = ((assets.get("stac_item") or {}).get("public_url")) or ""
        stac = fetch_json(stac_url) if stac_url else {}
        props = stac.get("properties") or {}
        bbox = stac.get("bbox") or geom_bbox(stac.get("geometry") or {})
        if not bbox:
            continue
        visual = assets.get("visual") or {}
        thumbnail = assets.get("thumbnail") or {}
        item = {
            "scene_id": manifest_item.get("id") or stac.get("id"),
            "phase": manifest_item.get("phase") or props.get("phase"),
            "acquisition_time": manifest_item.get("datetime") or props.get("datetime"),
            "vehicle": manifest_item.get("vehicle") or props.get("vehicle_name"),
            "cloud_cover": props.get("eo:cloud_cover", manifest_item.get("cloud_cover")),
            "pan_gsd_m": props.get("pan_gsd"),
            "multispectral_gsd_m": props.get("multispectral_gsd"),
            "off_nadir": props.get("view:off_nadir"),
            "sun_elevation": props.get("view:sun_elevation"),
            "bbox": [float(value) for value in bbox],
            "visual_url": visual.get("public_url", ""),
            "visual_bytes": visual.get("size", ""),
            "thumbnail_url": thumbnail.get("public_url", ""),
            "stac_item_url": stac_url,
            "stac_item_bytes": (assets.get("stac_item") or {}).get("size", ""),
            "source_visual_url": visual.get("source_url", ""),
        }
        items.append(item)
    return manifest, items


def scene_gate(row: dict[str, Any]) -> str:
    if row["feature_count_source"] == "none":
        return "coverage_only_no_feature_layer"
    if int(row["features_covered"] or 0) <= 0:
        return "coverage_only_zero_current_features"
    if num(row["pan_gsd_m"]) > 0.8:
        return "blocked_resolution_too_coarse"
    if num(row["cloud_cover"]) > 25:
        return "conditional_cloud_review"
    return "eligible_after_chip_qa"


def pair_coverage_gate(pre: dict[str, Any], post: dict[str, Any], common_features: int) -> str:
    if common_features <= 0:
        return "coverage_only_zero_current_features"
    if max(num(pre["pan_gsd_m"]), num(post["pan_gsd_m"])) > 0.8:
        return "blocked_resolution_too_coarse"
    if max(num(pre["cloud_cover"]), num(post["cloud_cover"])) > 25:
        return "conditional_cloud_review"
    return "eligible_after_chip_qa"


def spend_gate(aoi: dict[str, Any], coverage_gate: str) -> str:
    status = str(aoi.get("status") or "")
    features = int((aoi.get("metrics") or {}).get("features") or 0)
    if features <= 0:
        return "hold_no_current_damage_features"
    if coverage_gate != "eligible_after_chip_qa":
        return f"hold_{coverage_gate}"
    if status == "external-prediction":
        return "external_dedupe_sample_chip_qa_then_vlm"
    if status.startswith("official"):
        return "official_chip_qa_then_vlm"
    return "manual_review_chip_qa_then_vlm"


def action_for_spend_gate(gate: str) -> str:
    return {
        "official_chip_qa_then_vlm": "Generate QA chips for official features, then run HF only for visible/aligned chips.",
        "external_dedupe_sample_chip_qa_then_vlm": "Spatially dedupe and sample external candidates, then chip-QA before HF.",
        "hold_no_current_damage_features": "Hold paid VLM; no current feature layer to review.",
    }.get(gate, "Hold paid VLM until imagery/coverage issue is resolved.")


def pair_sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
    gate_priority = 0 if row["coverage_gate"] == "eligible_after_chip_qa" else 1
    return (
        gate_priority,
        -int(row["common_features_covered"] or 0),
        num(row["pre_cloud_cover"]) + num(row["post_cloud_cover"]),
        num(row["pre_pan_gsd_m"]) + num(row["post_pan_gsd_m"]),
        str(row["pre_acquisition_time"]),
        str(row["post_acquisition_time"]),
    )


def main() -> int:
    args = parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    checked_at = utc_stamp()
    catalog = json.loads(CATALOG.read_text())
    aois = catalog["aois"]
    manifest, items = load_vantor_items(args.manifest_url)

    feature_points: dict[str, list[tuple[str, float, float]]] = {}
    feature_sources: dict[str, str] = {}
    for aoi in aois:
        points, source = load_feature_points(aoi)
        feature_points[aoi["id"]] = points
        feature_sources[aoi["id"]] = source

    coverage_rows: list[dict[str, Any]] = []
    coverage_sets: dict[tuple[str, str], set[str]] = {}
    for item in items:
        for aoi in aois:
            overlap = intersection_bbox(item["bbox"], aoi_bbox(aoi))
            if not overlap:
                continue
            aoi_id = aoi["id"]
            feature_ids = covered_feature_ids(feature_points[aoi_id], item["bbox"])
            row = {
                "checked_at": checked_at,
                "manifest_url": args.manifest_url,
                "manifest_uploaded_at": manifest.get("uploaded_at", ""),
                "aoi_id": aoi_id,
                "aoi_status": aoi.get("status", ""),
                "scene_id": item["scene_id"],
                "phase": item["phase"],
                "acquisition_time": item["acquisition_time"],
                "vehicle": item["vehicle"],
                "cloud_cover": item["cloud_cover"],
                "pan_gsd_m": item["pan_gsd_m"],
                "multispectral_gsd_m": item["multispectral_gsd_m"],
                "off_nadir": item["off_nadir"],
                "sun_elevation": item["sun_elevation"],
                "scene_bbox": compact_bbox(item["bbox"]),
                "aoi_scene_overlap_bbox": compact_bbox(overlap),
                "aoi_scene_overlap_km2": round(bbox_area_approx_km2(overlap), 4),
                "features_covered": len(feature_ids),
                "feature_count_source": feature_sources[aoi_id],
                "visual_url": item["visual_url"],
                "visual_bytes": item["visual_bytes"],
                "thumbnail_url": item["thumbnail_url"],
                "stac_item_url": item["stac_item_url"],
                "stac_item_bytes": item["stac_item_bytes"],
                "license": manifest.get("license", "CC-BY-NC-4.0"),
                "source_role": "vantor_open_data_triage_evidence_not_official_ems",
                "coverage_gate": "",
            }
            row["coverage_gate"] = scene_gate(row)
            coverage_rows.append(row)
            coverage_sets[(aoi_id, str(item["scene_id"]))] = feature_ids

    coverage_by_aoi: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for row in coverage_rows:
        coverage_by_aoi[row["aoi_id"]][row["phase"]].append(row)

    pair_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    for aoi in aois:
        aoi_id = aoi["id"]
        pre_rows = coverage_by_aoi[aoi_id].get("pre", [])
        post_rows = coverage_by_aoi[aoi_id].get("post", [])
        aoi_pairs: list[dict[str, Any]] = []
        for pre in pre_rows:
            for post in post_rows:
                common = coverage_sets[(aoi_id, pre["scene_id"])] & coverage_sets[(aoi_id, post["scene_id"])]
                gate = pair_coverage_gate(pre, post, len(common))
                sgate = spend_gate(aoi, gate)
                pair = {
                    "checked_at": checked_at,
                    "aoi_id": aoi_id,
                    "aoi_status": aoi.get("status", ""),
                    "pair_rank": "",
                    "pre_scene_id": pre["scene_id"],
                    "pre_acquisition_time": pre["acquisition_time"],
                    "pre_vehicle": pre["vehicle"],
                    "pre_cloud_cover": pre["cloud_cover"],
                    "pre_pan_gsd_m": pre["pan_gsd_m"],
                    "pre_visual_url": pre["visual_url"],
                    "pre_thumbnail_url": pre["thumbnail_url"],
                    "post_scene_id": post["scene_id"],
                    "post_acquisition_time": post["acquisition_time"],
                    "post_vehicle": post["vehicle"],
                    "post_cloud_cover": post["cloud_cover"],
                    "post_pan_gsd_m": post["pan_gsd_m"],
                    "post_visual_url": post["visual_url"],
                    "post_thumbnail_url": post["thumbnail_url"],
                    "common_features_covered": len(common),
                    "feature_count_source": feature_sources[aoi_id],
                    "coverage_gate": gate,
                    "spend_gate": sgate,
                    "next_action": action_for_spend_gate(sgate),
                    "evidence_warning": "Vantor before/post imagery is triage evidence only and is not official EMS damage confirmation.",
                }
                aoi_pairs.append(pair)
        aoi_pairs.sort(key=pair_sort_key)
        for index, pair in enumerate(aoi_pairs, start=1):
            pair["pair_rank"] = index
            pair_rows.append(pair)

        best = aoi_pairs[0] if aoi_pairs else {}
        if not pre_rows:
            best_gate = "blocked_no_vantor_pre_event_coverage"
            best_spend_gate = "hold_no_vantor_pre_event_coverage"
            next_action = "Hold before/after VLM; find dated high-resolution pre-event imagery first."
        elif not post_rows:
            best_gate = "blocked_no_vantor_post_event_coverage"
            best_spend_gate = "hold_no_vantor_post_event_coverage"
            next_action = "Hold before/after VLM; find dated post-event imagery first."
        else:
            best_gate = str(best.get("coverage_gate", "coverage_only_zero_current_features"))
            best_spend_gate = str(best.get("spend_gate", "hold_coverage_only_zero_current_features"))
            next_action = str(best.get("next_action", "Hold paid VLM until imagery/coverage issue is resolved."))

        summary_rows.append(
            {
                "aoi_id": aoi_id,
                "aoi_status": aoi.get("status", ""),
                "feature_count": len(feature_points[aoi_id]),
                "feature_count_source": feature_sources[aoi_id],
                "pre_scene_count": len(pre_rows),
                "post_scene_count": len(post_rows),
                "candidate_pair_count": len(aoi_pairs),
                "best_pre_scene_id": best.get("pre_scene_id", ""),
                "best_pre_acquisition_time": best.get("pre_acquisition_time", ""),
                "best_post_scene_id": best.get("post_scene_id", ""),
                "best_post_acquisition_time": best.get("post_acquisition_time", ""),
                "best_common_features_covered": best.get("common_features_covered", 0),
                "best_coverage_gate": best_gate,
                "best_spend_gate": best_spend_gate,
                "next_action": next_action,
            }
        )

    coverage_fields = [
        "checked_at",
        "manifest_url",
        "manifest_uploaded_at",
        "aoi_id",
        "aoi_status",
        "scene_id",
        "phase",
        "acquisition_time",
        "vehicle",
        "cloud_cover",
        "pan_gsd_m",
        "multispectral_gsd_m",
        "off_nadir",
        "sun_elevation",
        "scene_bbox",
        "aoi_scene_overlap_bbox",
        "aoi_scene_overlap_km2",
        "features_covered",
        "feature_count_source",
        "visual_url",
        "visual_bytes",
        "thumbnail_url",
        "stac_item_url",
        "stac_item_bytes",
        "license",
        "source_role",
        "coverage_gate",
    ]
    with COVERAGE_CSV.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=coverage_fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(coverage_rows)

    pair_fields = [
        "checked_at",
        "aoi_id",
        "aoi_status",
        "pair_rank",
        "pre_scene_id",
        "pre_acquisition_time",
        "pre_vehicle",
        "pre_cloud_cover",
        "pre_pan_gsd_m",
        "pre_visual_url",
        "pre_thumbnail_url",
        "post_scene_id",
        "post_acquisition_time",
        "post_vehicle",
        "post_cloud_cover",
        "post_pan_gsd_m",
        "post_visual_url",
        "post_thumbnail_url",
        "common_features_covered",
        "feature_count_source",
        "coverage_gate",
        "spend_gate",
        "next_action",
        "evidence_warning",
    ]
    with PAIRS_CSV.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=pair_fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(pair_rows)

    summary_fields = [
        "aoi_id",
        "aoi_status",
        "feature_count",
        "feature_count_source",
        "pre_scene_count",
        "post_scene_count",
        "candidate_pair_count",
        "best_pre_scene_id",
        "best_pre_acquisition_time",
        "best_post_scene_id",
        "best_post_acquisition_time",
        "best_common_features_covered",
        "best_coverage_gate",
        "best_spend_gate",
        "next_action",
    ]
    with AOI_SUMMARY_CSV.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=summary_fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(summary_rows)

    summary = {
        "checked_at": checked_at,
        "manifest_url": args.manifest_url,
        "manifest_uploaded_at": manifest.get("uploaded_at", ""),
        "manifest_license": manifest.get("license", "CC-BY-NC-4.0"),
        "manifest_items": len(manifest.get("items", [])),
        "stac_items_loaded": len(items),
        "manifest_phase_counts": manifest.get("phase_counts", {}),
        "coverage_rows": len(coverage_rows),
        "pair_rows": len(pair_rows),
        "aoi_count": len(aois),
        "aoi_count_with_pre_coverage": sum(1 for row in summary_rows if int(row["pre_scene_count"]) > 0),
        "aoi_count_with_post_coverage": sum(1 for row in summary_rows if int(row["post_scene_count"]) > 0),
        "aoi_count_with_before_after_pairs": sum(1 for row in summary_rows if int(row["candidate_pair_count"]) > 0),
        "official_aoi_count_ready_for_chip_qa": sum(1 for row in summary_rows if row["best_spend_gate"] == "official_chip_qa_then_vlm"),
        "external_aoi_count_ready_for_dedupe_sample_chip_qa": sum(1 for row in summary_rows if row["best_spend_gate"] == "external_dedupe_sample_chip_qa_then_vlm"),
        "best_spend_gate_counts": {
            gate: sum(1 for row in summary_rows if row["best_spend_gate"] == gate)
            for gate in sorted({str(row["best_spend_gate"]) for row in summary_rows})
        },
        "scene_coverage_csv": str(COVERAGE_CSV.relative_to(ROOT)),
        "before_after_pairs_csv": str(PAIRS_CSV.relative_to(ROOT)),
        "aoi_summary_csv": str(AOI_SUMMARY_CSV.relative_to(ROOT)),
        "warning": "Planning artifact only. Do not treat Vantor/VLM evidence as official EMS damage confirmation.",
    }
    SUMMARY_JSON.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
