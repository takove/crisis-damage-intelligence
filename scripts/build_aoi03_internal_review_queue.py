#!/usr/bin/env python3
"""Build an internal human-review queue from AOI03 OSM candidate VLM output.

This intentionally writes to ops/, not public/data/. AOI03 candidates are not
official EMS damage features and must not be exposed as confirmed damage.
"""

from __future__ import annotations

import csv
import json
from html import escape
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PILOT_DIR = ROOT / "ops" / "aoi03_osm_before_after_pilot"
PILOT_JSON = PILOT_DIR / "pilot_records.json"
OUT_DIR = ROOT / "ops" / "aoi03_internal_review_queue"

REVIEW_CLASSES = {"likely_destroyed", "possible_major_damage", "minor_visible_damage"}
WARNING = (
    "INTERNAL REVIEW ONLY. OpenStreetMap footprint candidate, not official EMS damage. "
    "VLM before/after output is a triage aid only; absence/presence here is not confirmation."
)


def score(record: dict[str, Any]) -> tuple[int, float, str]:
    vlm = record.get("vlm") or {}
    damage_class = vlm.get("damage_class")
    priority = vlm.get("action_priority")
    try:
        confidence = float(vlm.get("confidence") or 0)
    except (TypeError, ValueError):
        confidence = 0.0
    severity = {
        "likely_destroyed": 0,
        "possible_major_damage": 1,
        "minor_visible_damage": 2,
    }.get(damage_class, 9)
    if priority == "urgent_review":
        severity -= 1
    return severity, -confidence, record["id"]


def row_for(record: dict[str, Any], rank: int) -> dict[str, Any]:
    vlm = record.get("vlm") or {}
    return {
        "rank": rank,
        "id": record["id"],
        "aoi_id": record["aoi_id"],
        "source": record["source"],
        "official_damage_source": False,
        "warning": WARNING,
        "centroid_lat": record["centroid_lat"],
        "centroid_lon": record["centroid_lon"],
        "google_maps_url": record["google_maps_url"],
        "building": record.get("building"),
        "name": record.get("name"),
        "area_m2": record.get("area_m2"),
        "vlm_damage_class": vlm.get("damage_class"),
        "vlm_confidence": vlm.get("confidence"),
        "vlm_action_priority": vlm.get("action_priority"),
        "vlm_change_evidence": vlm.get("change_evidence"),
        "vlm_uncertainty_reason": vlm.get("uncertainty_reason"),
        "compare_chip": str(PILOT_DIR / record["compare_chip"]),
        "before_source": record["before_source"],
        "after_source": record["after_source"],
    }


def point_feature(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "Feature",
        "properties": row,
        "geometry": {
            "type": "Point",
            "coordinates": [float(row["centroid_lon"]), float(row["centroid_lat"])],
        },
    }


def kml_for(rows: list[dict[str, Any]]) -> str:
    placemarks = []
    for row in rows:
        desc = (
            f"<b>Warning:</b> {escape(row['warning'])}<br/>"
            f"<b>VLM:</b> {escape(str(row['vlm_damage_class']))} "
            f"confidence {escape(str(row['vlm_confidence']))}<br/>"
            f"<b>Evidence:</b> {escape(str(row.get('vlm_change_evidence') or ''))}<br/>"
            f"<b>Uncertainty:</b> {escape(str(row.get('vlm_uncertainty_reason') or ''))}<br/>"
            f"<b>Google Maps:</b> <a href='{escape(row['google_maps_url'])}'>open</a>"
        )
        placemarks.append(
            f"""
    <Placemark>
      <name>{escape(str(row['rank']))}. {escape(row['id'])}</name>
      <description><![CDATA[{desc}]]></description>
      <Point><coordinates>{row['centroid_lon']},{row['centroid_lat']},0</coordinates></Point>
    </Placemark>"""
        )
    return (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
        "<kml xmlns=\"http://www.opengis.net/kml/2.2\">\n"
        "  <Document>\n"
        "    <name>AOI03 Internal OSM Candidate VLM Review Queue</name>\n"
        + "".join(placemarks)
        + "\n  </Document>\n</kml>\n"
    )


def main() -> None:
    data = json.loads(PILOT_JSON.read_text())
    candidates = [
        record for record in data.get("records", [])
        if (record.get("vlm") or {}).get("damage_class") in REVIEW_CLASSES
    ]
    candidates.sort(key=score)
    rows = [row_for(record, index + 1) for index, record in enumerate(candidates)]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "review_queue.geojson").write_text(json.dumps({
        "type": "FeatureCollection",
        "name": "aoi03_internal_osm_candidate_vlm_review_queue",
        "warning": WARNING,
        "features": [point_feature(row) for row in rows],
    }, indent=2) + "\n")
    if rows:
        with (OUT_DIR / "review_queue.csv").open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
    else:
        (OUT_DIR / "review_queue.csv").write_text("")
    (OUT_DIR / "review_queue.kml").write_text(kml_for(rows))
    (OUT_DIR / "README.md").write_text(
        "# AOI03 Internal OSM Candidate VLM Review Queue\n\n"
        f"{WARNING}\n\n"
        "Use this only to route human review or requests for better imagery. Do not publish it as an operational damage layer.\n\n"
        f"- Source pilot: `{PILOT_JSON.relative_to(ROOT)}`\n"
        f"- Candidates in queue: {len(rows)}\n"
        "- Outputs: `review_queue.csv`, `review_queue.geojson`, `review_queue.kml`\n"
    )
    print(f"Wrote {len(rows)} review candidates to {OUT_DIR}")


if __name__ == "__main__":
    main()
