#!/usr/bin/env python3
"""Run the gated AOI12 v2 HF before/after pilot from manual chip QA."""

from __future__ import annotations

import argparse
import csv
import json
import os
import time
from collections import Counter
from pathlib import Path
from typing import Any

from vlm_provider import call_vlm


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "ops" / "data_acquisition_plan"
AOI_ID = "emsr884-aoi12-caraballeda"
MANUAL_QA = OUT_DIR / "aoi12_v2_new_chip_manual_review.csv"
OUT_JSONL = OUT_DIR / "aoi12_v2_hf_pilot_review.jsonl"
OUT_CSV = OUT_DIR / "aoi12_v2_hf_pilot_summary.csv"
OUT_SUMMARY = OUT_DIR / "aoi12_v2_hf_pilot_summary.json"
SMOKE_RESULT = OUT_DIR / "aoi12_v2_hf_smoke_result.json"

BEFORE_SOURCE_LABEL = (
    "Vantor Open Data pre-event reference mosaic, 2025-11-03 / 2026-03-21 / 2026-04-07, "
    "not official EMS before imagery"
)

SYSTEM = (
    "You are assisting emergency earthquake damage triage by comparing pre-event and post-event aerial/satellite chips. "
    "You will receive a before/after comparison chip for the same EMS mapped feature. "
    "The red/white reticle marks the EMS centroid. A yellow/black outline, when visible, marks the EMS feature footprint/geometry. "
    "Be conservative: VLM output is a triage aid, not official confirmation. "
    "Return only valid JSON with keys damage_class, damage_percent, confidence, change_evidence, before_observation, "
    "after_observation, image_alignment, image_quality, action_priority, uncertainty_reason. "
    "damage_class must be one of no_change_visible, minor_visible_damage, possible_major_damage, likely_destroyed, "
    "uncertain_comparison_problem. action_priority must be one of urgent_review, review, deprioritize. "
    "Focus on visible before/after change: new rubble, roof loss, collapse, footprint distortion, exposed floors, debris fields, "
    "shadow/height loss, or clear disappearance. If alignment, resolution, cloud/haze, overexposure, vegetation occlusion, or scene mismatch prevents "
    "comparison, return uncertain_comparison_problem."
)


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key == "HF-TOKEN":
            key = "HF_TOKEN"
        os.environ.setdefault(key, value.strip().strip('"').strip("'"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--sleep", type=float, default=0.5)
    return parser.parse_args()


def local_public_path(public_path: str) -> Path:
    return ROOT / "public" / public_path.lstrip("/")


def load_rows() -> list[dict[str, str]]:
    with MANUAL_QA.open(newline="") as handle:
        rows = [row for row in csv.DictReader(handle) if row["manual_verdict"] == "pilot_ready"]
    return sorted(rows, key=lambda row: int(row["pilot_rank"] or 9999))


def load_done() -> dict[str, dict[str, Any]]:
    done: dict[str, dict[str, Any]] = {}
    if OUT_JSONL.exists():
        for line in OUT_JSONL.read_text().splitlines():
            if line.strip():
                record = json.loads(line)
                done[record["id"]] = record
    return done


def maybe_smoke_record(rows_by_id: dict[str, dict[str, str]]) -> dict[str, Any] | None:
    if not SMOKE_RESULT.exists():
        return None
    data = json.loads(SMOKE_RESULT.read_text())
    feature_id = data.get("id")
    if feature_id not in rows_by_id:
        return None
    row = rows_by_id[feature_id]
    return build_record(row, data["vlm"])


def prompt_for(row: dict[str, str]) -> str:
    return (
        "Compare the before and after chips for emergency earthquake damage triage. "
        "The chip is a side-by-side composite: BEFORE is on the left, AFTER is on the right. "
        "Both panels are centered on the same EMS mapped feature centroid marked by the reticle. "
        "If a yellow/black outline is visible, use it as the mapped EMS feature footprint/geometry and evaluate the outlined area, not only the reticle pixel. "
        f"AOI: {AOI_ID}. Feature: {row['feature_id']}. Official EMS label: {row['official_ems_damage_gra']}. "
        f"Official EMS percent: {row['official_ems_damage_percent']}. "
        f"Before source: {BEFORE_SOURCE_LABEL}. "
        f"Manual chip QA note before VLM: {row['manual_notes']}. "
        "Assess visible physical change between before and after. Do not rely only on the official EMS label. "
        "If the comparison is not fair because of alignment, target ambiguity, cloud/haze, overexposure, or occlusion, "
        "return uncertain_comparison_problem and explain why."
    )


def call_feature(row: dict[str, str]) -> dict[str, Any]:
    compare_chip = local_public_path(row["compare_chip"])
    metadata = {
        "aoi_id": AOI_ID,
        "id": row["feature_id"],
        "official_ems_damage_gra": row["official_ems_damage_gra"],
        "official_ems_damage_percent": row["official_ems_damage_percent"],
        "manual_chip_qa": row["manual_verdict"],
        "manual_notes": row["manual_notes"],
    }
    result = call_vlm(SYSTEM, prompt_for(row), [compare_chip], metadata=metadata, review_type="dated_pre_event_comparison")
    result["before_source"] = BEFORE_SOURCE_LABEL
    return build_record(row, result)


def build_record(row: dict[str, str], vlm: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["feature_id"],
        "aoi_id": AOI_ID,
        "official_ems_damage_gra": row["official_ems_damage_gra"],
        "official_ems_damage_percent": row["official_ems_damage_percent"],
        "centroid_lat": row["centroid_lat"],
        "centroid_lon": row["centroid_lon"],
        "before_event_chip": row["before_chip"],
        "post_event_chip": row["after_chip"],
        "compare_chip": row["compare_chip"],
        "manual_chip_qa": row["manual_verdict"],
        "manual_chip_qa_notes": row["manual_notes"],
        "vlm": vlm,
        "warning": "VLM before/after output is triage evidence only; official EMS labels remain source of record.",
    }


def write_outputs(records: dict[str, dict[str, Any]]) -> None:
    ordered = [records[key] for key in sorted(records)]
    with OUT_JSONL.open("w") as handle:
        for record in ordered:
            handle.write(json.dumps(record, ensure_ascii=True, separators=(",", ":")) + "\n")

    with OUT_CSV.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "id",
                "official_ems_damage_gra",
                "vlm_damage_class",
                "confidence",
                "action_priority",
                "compare_chip",
                "manual_chip_qa_notes",
            ],
            lineterminator="\n",
        )
        writer.writeheader()
        for record in ordered:
            vlm = record.get("vlm") or {}
            writer.writerow(
                {
                    "id": record["id"],
                    "official_ems_damage_gra": record["official_ems_damage_gra"],
                    "vlm_damage_class": vlm.get("damage_class"),
                    "confidence": vlm.get("confidence"),
                    "action_priority": vlm.get("action_priority"),
                    "compare_chip": record["compare_chip"],
                    "manual_chip_qa_notes": record["manual_chip_qa_notes"],
                }
            )

    classes = Counter((record.get("vlm") or {}).get("damage_class", "unknown") for record in ordered)
    priorities = Counter((record.get("vlm") or {}).get("action_priority", "unknown") for record in ordered)
    summary = {
        "aoi_id": AOI_ID,
        "review_type": "dated_pre_event_comparison",
        "records": len(ordered),
        "damage_classes": dict(classes),
        "action_priorities": dict(priorities),
        "jsonl": str(OUT_JSONL.relative_to(ROOT)),
        "csv": str(OUT_CSV.relative_to(ROOT)),
        "warning": "Ops-only pilot. Do not publish into official metrics without human review and AOI12 v2 catalog binding.",
    }
    OUT_SUMMARY.write_text(json.dumps(summary, indent=2) + "\n")


def main() -> int:
    load_env(ROOT / ".env")
    os.environ.setdefault("VLM_PROVIDER", "hf_space")
    os.environ.setdefault("HF_SPACE_ID", "takove/respuesta-venezuela-vlm")
    os.environ.setdefault("HF_VLM_MODEL", "Qwen/Qwen3-VL-8B-Instruct")

    args = parse_args()
    rows = load_rows()
    if args.offset:
        rows = rows[args.offset :]
    if args.limit:
        rows = rows[: args.limit]

    rows_by_id = {row["feature_id"]: row for row in load_rows()}
    records = {} if args.force else load_done()
    smoke = maybe_smoke_record(rows_by_id)
    if smoke and not args.force:
        records.setdefault(smoke["id"], smoke)

    pending = [row for row in rows if args.force or row["feature_id"] not in records]
    print(f"pilot_ready_selected={len(rows)} existing_records={len(records)} pending={len(pending)}")

    for row in pending:
        record = call_feature(row)
        records[record["id"]] = record
        write_outputs(records)
        vlm = record["vlm"]
        print(f"{record['id']} -> {vlm.get('damage_class')} conf={vlm.get('confidence')} priority={vlm.get('action_priority')}", flush=True)
        if args.sleep:
            time.sleep(args.sleep)

    write_outputs(records)
    print(OUT_SUMMARY.read_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
