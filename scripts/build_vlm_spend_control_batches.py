#!/usr/bin/env python3
"""Build VLM spend-control batches from current ingest gates."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "ops" / "data_acquisition_plan"
REMAP = OUT_DIR / "aoi12_v1_v2_remap.csv"
VLM_REUSE = OUT_DIR / "aoi12_vlm_v1_v2_reuse_queue.csv"
PRE_EVENT = OUT_DIR / "pre_event_imagery_coverage_summary.csv"
VANTOR_R2_BEFORE_AFTER = OUT_DIR / "vantor_r2_before_after_aoi_summary.csv"
AOI12_V2_CHIP_QA = OUT_DIR / "aoi12_v2_new_chip_qa_summary.json"
AOI12_V2_MANUAL_QA = OUT_DIR / "aoi12_v2_new_chip_manual_review_summary.json"
AOI12_V2_HF_PILOT = OUT_DIR / "aoi12_v2_hf_pilot_summary.json"
EXTERNAL_OVERLAP = OUT_DIR / "external_prediction_official_overlap_summary.csv"
BATCHES = OUT_DIR / "vlm_spend_control_batches.csv"
SUMMARY = OUT_DIR / "vlm_spend_control_batches_summary.json"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def read_optional_csv(path: Path) -> list[dict[str, str]]:
    return read_csv(path) if path.exists() else []


def read_optional_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text()) if path.exists() else {}


def add_batch(rows: list[dict[str, Any]], **kwargs: Any) -> None:
    rows.append(kwargs)


def main() -> int:
    remap = read_csv(REMAP)
    reuse = read_csv(VLM_REUSE)
    pre_event = {row["aoi_id"]: row for row in read_csv(PRE_EVENT)}
    before_after = {row["aoi_id"]: row for row in read_optional_csv(VANTOR_R2_BEFORE_AFTER)}
    aoi12_chip_qa = read_optional_json(AOI12_V2_CHIP_QA)
    aoi12_manual_qa = read_optional_json(AOI12_V2_MANUAL_QA)
    aoi12_hf_pilot = read_optional_json(AOI12_V2_HF_PILOT)
    external = read_csv(EXTERNAL_OVERLAP)

    rows: list[dict[str, Any]] = []
    add_batch(
        rows,
        batch_id="AOI12_REUSE_EXISTING_VLM",
        source_family="official_ems_gra",
        aoi_scope="emsr884-aoi12-caraballeda",
        candidate_count=sum(1 for row in reuse if row["vlm_action"] == "reuse_existing_vlm_with_v2_binding"),
        estimated_vlm_calls=0,
        action="reuse_existing_results",
        status="ready_no_spend",
        prerequisite="Bind existing rows to v2 IDs from aoi12_vlm_v1_v2_reuse_queue.csv.",
        spend_rationale="No HF spend needed; geometry remap is stable.",
    )
    add_batch(
        rows,
        batch_id="AOI12_RETIRE_STALE_VLM",
        source_family="official_ems_gra",
        aoi_scope="emsr884-aoi12-caraballeda",
        candidate_count=sum(1 for row in reuse if row["vlm_action"] == "retire_existing_vlm_no_v2_binding"),
        estimated_vlm_calls=0,
        action="archive_existing_results",
        status="ready_no_spend",
        prerequisite="Keep retired v1 rows out of public v2 summaries.",
        spend_rationale="No v2 binding exists, so rerunning would spend on stale geometry.",
    )
    new_aoi12 = [row for row in remap if row["remap_action"] == "new_regenerate"]
    aoi12_coverage = pre_event.get("emsr884-aoi12-caraballeda", {})
    aoi12_pairing = before_after.get("emsr884-aoi12-caraballeda", {})
    aoi12_pair_note = (
        f" best_r2_pair={aoi12_pairing.get('best_pre_scene_id', '')}/{aoi12_pairing.get('best_post_scene_id', '')}"
        f"; common_features={aoi12_pairing.get('best_common_features_covered', '')}"
        if aoi12_pairing
        else ""
    )
    aoi12_qa_passes = int(aoi12_chip_qa.get("automated_pass_needing_manual_alignment_review") or len(new_aoi12))
    aoi12_manual_ready = int(aoi12_manual_qa.get("pilot_ready_features") or aoi12_qa_passes)
    aoi12_pilot_records = int(aoi12_hf_pilot.get("records") or 0)
    aoi12_remaining_calls = max(0, aoi12_manual_ready - aoi12_pilot_records)
    aoi12_qa_note = (
        f"; automated_chip_qa_pass={aoi12_qa_passes}; manual_pilot_ready={aoi12_manual_ready}; hf_pilot_records={aoi12_pilot_records}; chip_qa={aoi12_chip_qa.get('qa_csv', '')}"
        if aoi12_chip_qa
        else ""
    )
    add_batch(
        rows,
        batch_id="AOI12_NEW_V2_CHIP_QA_THEN_VLM",
        source_family="official_ems_gra",
        aoi_scope="emsr884-aoi12-caraballeda",
        candidate_count=len(new_aoi12),
        estimated_vlm_calls=aoi12_remaining_calls,
        action="generate_chips_then_run_vlm_if_qa_passes",
        status=(
            "ready_for_human_review_no_more_hf"
            if aoi12_hf_pilot and aoi12_remaining_calls == 0
            else ("blocked_on_manual_alignment_review" if aoi12_chip_qa else "blocked_on_chip_qa")
        ),
        prerequisite=f"Use AOI12 v2 geometries and eligible pre/post Vantor R2 scenes; eligible_pre_scene_count={aoi12_coverage.get('eligible_scene_count', '')}.{aoi12_pair_note}{aoi12_qa_note}",
        spend_rationale="Official v2 added features; spend is justified only after chip QA confirms target visibility/alignment.",
    )
    aoi02 = pre_event.get("emsr884-aoi02-caracas", {})
    add_batch(
        rows,
        batch_id="AOI02_VALIDATE_EXISTING_BEFORE_AFTER",
        source_family="official_ems_gra",
        aoi_scope="emsr884-aoi02-caracas",
        candidate_count=17,
        estimated_vlm_calls=0,
        action="validate_existing_results_and_chip_qa",
        status="ready_no_spend",
        prerequisite=f"Existing before/after rows present; eligible_scene_count={aoi02.get('eligible_scene_count', '')}.",
        spend_rationale="Existing HF run covers AOI02 GRA; spend only if chip QA invalidates a row.",
    )
    for aoi_id in ("emsr884-aoi05-santa-cruz", "emsr884-aoi06-moron", "emsr884-aoi08-san-felipe", "emsr884-aoi10-guacara"):
        coverage = pre_event.get(aoi_id, {})
        pairing = before_after.get(aoi_id, {})
        current_gate = pairing.get("best_coverage_gate") or coverage.get("best_gate", "missing")
        add_batch(
            rows,
            batch_id=f"{aoi_id.upper().replace('-', '_')}_HOLD",
            source_family="official_ems_gra",
            aoi_scope=aoi_id,
            candidate_count="",
            estimated_vlm_calls=0,
            action="hold_before_after_vlm",
            status="blocked_on_pre_event_imagery",
            prerequisite=f"Find high-resolution pre-event coverage; current_gate={current_gate}; pre_scenes={pairing.get('pre_scene_count', '0')}; post_scenes={pairing.get('post_scene_count', '0')}.",
            spend_rationale="No useful Vantor pre-event coverage found, so before/after VLM would be low-quality or impossible.",
        )
    for row in external:
        outside = int(row["high_priority_outside_official_gra"])
        add_batch(
            rows,
            batch_id=f"EXTERNAL_{row['source_name'].upper().replace(' ', '_').replace('/', '_')}_OUTSIDE_OFFICIAL_SAMPLE",
            source_family="microsoft_hdx_external_prediction",
            aoi_scope=row["source_name"],
            candidate_count=outside,
            estimated_vlm_calls=min(outside, 200),
            action="dedupe_chip_qa_sample_then_vlm",
            status="blocked_on_dedupe_and_chip_qa",
            prerequisite="Spatially dedupe against other external layers, require pre-event/post-event coverage, then sample highest-confidence outside-official candidates.",
            spend_rationale="External high-priority candidates outside official GRA may reveal damage outside official polygons, but full-run spend is not justified before dedupe/sampling.",
        )

    fieldnames = [
        "batch_id",
        "source_family",
        "aoi_scope",
        "candidate_count",
        "estimated_vlm_calls",
        "action",
        "status",
        "prerequisite",
        "spend_rationale",
    ]
    with BATCHES.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    summary = {
        "batch_count": len(rows),
        "ready_no_spend": sum(1 for row in rows if row["status"] == "ready_no_spend"),
        "ready_for_human_review_no_more_hf": sum(1 for row in rows if row["status"] == "ready_for_human_review_no_more_hf"),
        "blocked_on_chip_qa": sum(1 for row in rows if "chip_qa" in row["status"]),
        "blocked_on_manual_alignment_review": sum(1 for row in rows if row["status"] == "blocked_on_manual_alignment_review"),
        "blocked_on_pre_event_imagery": sum(1 for row in rows if row["status"] == "blocked_on_pre_event_imagery"),
        "max_recommended_next_vlm_calls_before_more_dedupe": sum(int(row["estimated_vlm_calls"] or 0) for row in rows if row["batch_id"] == "AOI12_NEW_V2_CHIP_QA_THEN_VLM"),
        "external_sample_call_ceiling_after_dedupe": sum(int(row["estimated_vlm_calls"] or 0) for row in rows if row["source_family"] == "microsoft_hdx_external_prediction"),
        "batches_csv": str(BATCHES.relative_to(ROOT)),
    }
    SUMMARY.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
