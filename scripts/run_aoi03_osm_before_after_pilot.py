#!/usr/bin/env python3
"""Run a small before/after chip QA pilot for AOI03 OSM candidates.

AOI03 has EMS post-event imagery and Vantor pre-event coverage but no official
EMS damage vector. This script intentionally writes to ops/, not public/data/,
so candidate output cannot be mistaken for operational damage evidence.
"""

from __future__ import annotations

import json
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
import base64
import os
import re
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import run_minimax_ems_before_after_review as vlm


ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT.parent
AOI_ID = "emsr884-aoi03-antimano"
BEFORE_COG = "/vsicurl/https://vantor-opendata.s3.amazonaws.com/events/Venezuela-Earthquake-Jun-2026/B160001100FD1910.tif"
AFTER_COG = OUTPUTS / "emsr884_imagery" / "EMSR884_AOI03_GRA_PRODUCT_LEGION_20260625_1517_ORTHO_cog.tif"
SRC = ROOT / "ops" / "baseline_inventory" / "aoi03_osm_building_candidates.geojson"
OUT_DIR = ROOT / "ops" / "aoi03_osm_before_after_pilot"
CHIP_DIR = OUT_DIR / "chips"

SYSTEM = (
    "You are assisting emergency earthquake damage triage by comparing pre-event and post-event aerial/satellite chips. "
    "This is a candidate-only OpenStreetMap building footprint, not an official damage feature. "
    "The red/white reticle marks the candidate footprint centroid. A yellow/black outline marks the OSM footprint. "
    "Be conservative: VLM output is a triage aid and must not be treated as official confirmation. "
    "Return only valid JSON with keys damage_class, damage_percent, confidence, change_evidence, before_observation, "
    "after_observation, image_alignment, image_quality, action_priority, uncertainty_reason. "
    "damage_class must be one of no_change_visible, minor_visible_damage, possible_major_damage, likely_destroyed, "
    "uncertain_comparison_problem. action_priority must be one of urgent_review, review, deprioritize. "
    "Focus only on visible before/after physical change in the outlined candidate: new rubble, roof loss, collapse, "
    "footprint distortion, exposed floors, debris fields, shadow/height loss, or clear disappearance. If alignment, "
    "resolution, occlusion, clouds, black/missing imagery, or scene mismatch prevents comparison, return uncertain_comparison_problem."
)


def pilot_score(feature: dict) -> tuple[int, float, str]:
    props = feature["properties"]
    # Prefer named residential/mixed buildings in a manageable footprint range.
    building = str(props.get("building") or "")
    name = str(props.get("name") or "")
    area = float(props.get("area_m2") or 0)
    score = 0
    if building in {"house", "apartments", "residential"}:
        score -= 20
    if name and name != "None":
        score -= 8
    if 120 <= area <= 2_500:
        score -= 5
    return score, area, props["id"]


def copy_public_chip(public_path: Path, target_name: str) -> str:
    target = CHIP_DIR / target_name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(public_path, target)
    return str(target.relative_to(OUT_DIR))


def encode_image(path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def call_candidate_vlm(record: dict) -> dict:
    key = os.environ.get("MINIMAX_API_KEY")
    if not key:
        raise SystemExit("MINIMAX_API_KEY missing")
    model = os.environ.get("MINIMAX_MODEL", "MiniMax-M3")
    prompt = (
        "Compare the before and after chips for this OpenStreetMap building-footprint candidate. "
        "This is not an official EMS damage label; it is a QA pilot to determine whether before/after comparison is usable. "
        f"Candidate: {record['id']}. Building tag: {record.get('building')}. Name: {record.get('name')}. "
        f"Before source: {record['before_source']}. After source: {record['after_source']}. "
        "Assess only visible change between the two chips. Do not infer damage from earthquake context alone."
    )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": encode_image(OUT_DIR / record["compare_chip"])}},
                ],
            },
        ],
        "temperature": 0,
    }
    req = Request(
        "https://api.minimax.io/v1/text/chatcompletion_v2",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=90) as resp:
            raw = resp.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"MiniMax HTTP {exc.code}: {detail}") from exc
    data = json.loads(raw)
    text = data["choices"][0]["message"]["content"]
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise ValueError(f"No JSON in MiniMax response: {text[:400]}")
    result = json.loads(match.group(0))
    result["vlm_model"] = model
    result["review_type"] = "osm_candidate_dated_pre_event_comparison"
    result["candidate_only"] = True
    result["official_damage_source"] = False
    return result


def main() -> None:
    vlm.load_env(ROOT / ".env")
    vlm.load_env(ROOT.parents[1] / ".env")
    candidates = json.loads(SRC.read_text())["features"]
    run_vlm = "--run-vlm" in sys.argv
    workers = int(os.environ.get("VLM_WORKERS", "3"))
    limit = 8
    if "--workers" in sys.argv:
        index = sys.argv.index("--workers")
        workers = int(sys.argv[index + 1])
    if "--limit" in sys.argv:
        index = sys.argv.index("--limit")
        limit = int(sys.argv[index + 1])
    selected = sorted(candidates, key=pilot_score)[:limit]
    previous_by_id: dict[str, dict] = {}
    previous_failures_by_id: dict[str, dict] = {}
    out_json = OUT_DIR / "pilot_records.json"
    if out_json.exists() and "--force" not in sys.argv:
        previous = json.loads(out_json.read_text())
        previous_by_id = {record["id"]: record for record in previous.get("records", [])}
        previous_failures_by_id = {failure["id"]: failure for failure in previous.get("failures", [])}
    records = []
    failures = []
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for feature in selected:
        fid = feature["properties"]["id"]
        if fid in previous_by_id and (not run_vlm or previous_by_id[fid].get("vlm")):
            records.append(previous_by_id[fid])
            continue
        if fid in previous_failures_by_id and "--retry-failures" not in sys.argv:
            failures.append(previous_failures_by_id[fid])
            continue
        before_chip = vlm.chip_path(AOI_ID, fid, "before_event")
        after_chip = vlm.chip_path(AOI_ID, fid, "after_event")
        compare_chip = vlm.chip_path(AOI_ID, fid, "before_after_compare")
        for path in (before_chip, after_chip, compare_chip):
            path.unlink(missing_ok=True)
        before_ok = vlm.make_chip(BEFORE_COG, feature, before_chip)
        after_ok = vlm.make_chip(AFTER_COG, feature, after_chip)
        if not before_ok or not after_ok:
            failures.append({"id": fid, "before_ok": before_ok, "after_ok": after_ok})
            continue
        vlm.make_compare_chip(before_chip, after_chip, compare_chip)
        record = {
            "id": fid,
            "aoi_id": AOI_ID,
            "source": "OpenStreetMap building footprint candidate",
            "official_damage_source": False,
            "warning": "Candidate-only pilot. Not official EMS damage and not public operational evidence.",
            "centroid_lat": feature["properties"]["centroid_lat"],
            "centroid_lon": feature["properties"]["centroid_lon"],
            "google_maps_url": feature["properties"]["google_maps_url"],
            "building": feature["properties"].get("building"),
            "name": feature["properties"].get("name"),
            "area_m2": feature["properties"].get("area_m2"),
            "before_source": "Vantor Open Data pre-event reference scene B160001100FD1910, 2026-03-20T14:46:55Z, not official EMS before imagery",
            "after_source": "Copernicus EMSR884 AOI03 post-event Legion COG, 2026-06-25T15:17:00Z",
            "before_event_chip": copy_public_chip(before_chip, f"{fid}_before_event.png"),
            "post_event_chip": copy_public_chip(after_chip, f"{fid}_after_event.png"),
            "compare_chip": copy_public_chip(compare_chip, f"{fid}_before_after_compare.png"),
        }
        records.append(record)
    vlm_pending = [record for record in records if not record.get("vlm")]
    if run_vlm and vlm_pending:
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            futures = {pool.submit(call_candidate_vlm, record): record for record in vlm_pending}
            for future in as_completed(futures):
                record = futures[future]
                record["vlm"] = future.result()
                print(f"{record['id']} -> {record['vlm'].get('damage_class')} conf={record['vlm'].get('confidence')}", flush=True)
    records.sort(key=lambda record: record["id"])
    out_json.write_text(json.dumps({
        "aoi_id": AOI_ID,
        "review_type": "candidate_before_after_chip_qa",
        "warning": "These are OSM building candidates for QA only. They are not official EMS damage features and are not published in the operational catalog.",
        "selected": len(selected),
        "generated": len(records),
        "failures": failures,
        "records": records,
    }, indent=2) + "\n")
    print(f"Selected {len(selected)} candidates; generated {len(records)} chip triplets; failures {len(failures)}")
    print(OUT_DIR / "pilot_records.json")


if __name__ == "__main__":
    main()
