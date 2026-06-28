#!/usr/bin/env python3
"""Second-pass VLM adjudication for the internal AOI03 OSM review queue.

This reads the internal AOI03 candidate queue and re-asks the VLM to adjudicate
the before/after comparison using a stricter standard. Outputs stay under ops/
and must not be treated as official EMS damage.
"""

from __future__ import annotations

import base64
import csv
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
QUEUE = ROOT / "ops" / "aoi03_internal_review_queue" / "review_queue.csv"
OUT_DIR = ROOT / "ops" / "aoi03_internal_review_queue" / "adjudication"

SYSTEM = (
    "You are a conservative second-pass reviewer for emergency earthquake damage triage. "
    "You will see a side-by-side before/after comparison chip for an OpenStreetMap building-footprint candidate. "
    "This is not an official EMS damage feature. Your task is to decide whether the chip is actionable enough for human follow-up. "
    "Be skeptical of low-resolution post-event imagery, haze, seasonal differences, sensor differences, and alignment drift. "
    "Return only valid JSON with keys adjudicated_class, confidence, agreement_with_prior, recommended_action, "
    "why_actionable_or_not, main_uncertainty, needs_better_imagery. "
    "adjudicated_class must be one of no_change_visible, minor_visible_damage, possible_major_damage, likely_destroyed, "
    "uncertain_comparison_problem. confidence must be a number from 0 to 1. agreement_with_prior must be one of agree, downgrade, upgrade, uncertain. "
    "recommended_action must be one of urgent_human_review, human_review, hold_for_better_imagery, deprioritize. "
    "needs_better_imagery must be true or false."
)


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def encode_image(path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def call_minimax(row: dict[str, str]) -> dict:
    key = os.environ.get("MINIMAX_API_KEY")
    if not key:
        raise SystemExit("MINIMAX_API_KEY missing")
    model = os.environ.get("MINIMAX_MODEL", "MiniMax-M3")
    chip = Path(row["compare_chip"])
    if not chip.is_absolute():
        chip = ROOT / chip
    prompt = (
        "Adjudicate this before/after comparison chip using a stricter standard than the first pass. "
        "The left panel is Vantor pre-event reference imagery; the right panel is Copernicus EMS post-event imagery. "
        "The yellow outline is an OpenStreetMap candidate footprint, not an official EMS feature. "
        f"Candidate id: {row['id']}. Name: {row.get('name') or 'unknown'}. Building tag: {row.get('building') or 'unknown'}. "
        f"Prior VLM class: {row.get('vlm_damage_class')}. Prior confidence: {row.get('vlm_confidence')}. "
        f"Prior action priority: {row.get('vlm_action_priority')}. "
        "Decide whether a human should urgently review this candidate, whether it only merits normal review, "
        "or whether the evidence should be held for better imagery."
    )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": encode_image(chip)}},
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
    result["review_type"] = "osm_candidate_second_pass_adjudication"
    result["candidate_only"] = True
    result["official_damage_source"] = False
    return result


def write_outputs(rows: list[dict[str, str]], results: list[dict]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "aoi03_internal_adjudication.json").write_text(
        json.dumps(
            {
                "aoi_id": "emsr884-aoi03-antimano",
                "warning": "INTERNAL REVIEW ONLY. OSM candidates and VLM adjudication are triage aids, not official EMS damage.",
                "review_type": "osm_candidate_second_pass_adjudication",
                "count": len(results),
                "results": results,
            },
            indent=2,
        )
        + "\n"
    )
    if results:
        fields = [
            "rank",
            "id",
            "name",
            "centroid_lat",
            "centroid_lon",
            "google_maps_url",
            "prior_class",
            "prior_confidence",
            "adjudicated_class",
            "adjudicated_confidence",
            "agreement_with_prior",
            "recommended_action",
            "needs_better_imagery",
            "why_actionable_or_not",
            "main_uncertainty",
        ]
        with (OUT_DIR / "aoi03_internal_adjudication.csv").open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for item in results:
                writer.writerow({field: item.get(field, "") for field in fields})
    counts: dict[str, int] = {}
    actions: dict[str, int] = {}
    for item in results:
        counts[item.get("adjudicated_class", "missing")] = counts.get(item.get("adjudicated_class", "missing"), 0) + 1
        actions[item.get("recommended_action", "missing")] = actions.get(item.get("recommended_action", "missing"), 0) + 1
    (OUT_DIR / "summary.json").write_text(
        json.dumps(
            {
                "count": len(results),
                "adjudicated_classes": counts,
                "recommended_actions": actions,
                "warning": "Internal OSM-candidate VLM adjudication only; not official EMS damage.",
            },
            indent=2,
        )
        + "\n"
    )


def main() -> None:
    load_env(ROOT / ".env")
    load_env(ROOT.parent / ".env")
    load_env(ROOT.parents[1] / ".env")
    workers = int(os.environ.get("VLM_WORKERS", "3"))
    limit = None
    if "--workers" in sys.argv:
        workers = int(sys.argv[sys.argv.index("--workers") + 1])
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    rows = list(csv.DictReader(QUEUE.open()))
    if limit:
        rows = rows[:limit]
    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(call_minimax, row): row for row in rows}
        for future in as_completed(futures):
            row = futures[future]
            adjudication = future.result()
            item = {
                "rank": row["rank"],
                "id": row["id"],
                "name": row.get("name"),
                "centroid_lat": row["centroid_lat"],
                "centroid_lon": row["centroid_lon"],
                "google_maps_url": row["google_maps_url"],
                "prior_class": row.get("vlm_damage_class"),
                "prior_confidence": row.get("vlm_confidence"),
                "compare_chip": row.get("compare_chip"),
                "adjudicated_class": adjudication.get("adjudicated_class"),
                "adjudicated_confidence": adjudication.get("confidence"),
                "agreement_with_prior": adjudication.get("agreement_with_prior"),
                "recommended_action": adjudication.get("recommended_action"),
                "needs_better_imagery": adjudication.get("needs_better_imagery"),
                "why_actionable_or_not": adjudication.get("why_actionable_or_not"),
                "main_uncertainty": adjudication.get("main_uncertainty"),
                "adjudication": adjudication,
            }
            results.append(item)
            print(
                f"{row['rank']} {row['id']} -> {item['adjudicated_class']} "
                f"{item['adjudicated_confidence']} {item['recommended_action']}",
                flush=True,
            )
    results.sort(key=lambda item: int(item["rank"]))
    write_outputs(rows, results)
    print(OUT_DIR / "summary.json")


if __name__ == "__main__":
    main()
