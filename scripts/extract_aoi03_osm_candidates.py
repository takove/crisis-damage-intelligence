#!/usr/bin/env python3
"""Extract conservative OSM building candidates for AOI03 Antimano.

AOI03 currently has post-event imagery and Vantor pre-event baselines but no
official EMS damage vector. These candidates are not damage claims; they only
provide building geometries for a small before/after chip QA pilot.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
IN_PATH = ROOT / "ops" / "baseline_inventory" / "aoi03_osm_buildings_sample.json"
OUT_PATH = ROOT / "ops" / "baseline_inventory" / "aoi03_osm_building_candidates.geojson"

# Catalog AOI03 bounds are stored as [[min_lat, min_lon], [max_lat, max_lon]].
AOI03_BOUNDS = ((10.412324, -67.045795), (10.547743, -66.923853))


def polygon_area_m2(coords: list[tuple[float, float]]) -> float:
    """Approximate local polygon area for ranking/filtering."""
    if len(coords) < 4:
        return 0.0
    lat0 = sum(lat for _, lat in coords) / len(coords)
    m_per_deg_lon = 111_320 * max(0.1, __import__("math").cos(__import__("math").radians(lat0)))
    m_per_deg_lat = 111_320
    xy = [(lon * m_per_deg_lon, lat * m_per_deg_lat) for lon, lat in coords]
    area = 0.0
    for (x1, y1), (x2, y2) in zip(xy, xy[1:]):
        area += x1 * y2 - x2 * y1
    return abs(area) / 2.0


def inside_aoi(lon: float, lat: float) -> bool:
    return AOI03_BOUNDS[0][0] <= lat <= AOI03_BOUNDS[1][0] and AOI03_BOUNDS[0][1] <= lon <= AOI03_BOUNDS[1][1]


def element_to_feature(element: dict[str, Any]) -> dict[str, Any] | None:
    geom = element.get("geometry") or []
    if len(geom) < 4:
        return None
    coords = [(float(point["lon"]), float(point["lat"])) for point in geom if "lon" in point and "lat" in point]
    if len(coords) < 4:
        return None
    if coords[0] != coords[-1]:
        coords.append(coords[0])
    lons = [lon for lon, _ in coords]
    lats = [lat for _, lat in coords]
    centroid_lon = sum(lons[:-1]) / max(1, len(lons) - 1)
    centroid_lat = sum(lats[:-1]) / max(1, len(lats) - 1)
    if not inside_aoi(centroid_lon, centroid_lat):
        return None
    area_m2 = polygon_area_m2(coords)
    # Keep plausible individual/commercial buildings. Exclude huge campuses and
    # tiny mapper artifacts; this is only for a controlled pilot.
    if area_m2 < 25 or area_m2 > 20_000:
        return None
    tags = element.get("tags", {})
    candidate_id = f"osm_way_{element['id']}"
    return {
        "type": "Feature",
        "properties": {
            "id": candidate_id,
            "source_feature_id": candidate_id,
            "aoi": "emsr884-aoi03-antimano",
            "source": "OpenStreetMap building footprint",
            "official_damage_source": False,
            "damage_gra": "Candidate only",
            "damage_class": "candidate_unverified",
            "damage_percent": None,
            "centroid_lat": centroid_lat,
            "centroid_lon": centroid_lon,
            "google_maps_url": f"https://www.google.com/maps/search/?api=1&query={centroid_lat},{centroid_lon}",
            "building": tags.get("building"),
            "name": tags.get("name"),
            "amenity": tags.get("amenity"),
            "area_m2": round(area_m2, 1),
            "triage_warning": "OSM footprint only. Not official EMS damage. Use only for before/after VLM pilot candidate generation.",
        },
        "geometry": {
            "type": "Polygon",
            "coordinates": [[list(coord) for coord in coords]],
        },
    }


def main() -> None:
    data = json.loads(IN_PATH.read_text())
    features = []
    for element in data.get("elements", []):
        feature = element_to_feature(element)
        if feature:
            features.append(feature)
    features.sort(key=lambda feature: (feature["properties"]["area_m2"], feature["properties"]["id"]))
    payload = {
        "type": "FeatureCollection",
        "name": "aoi03_osm_building_candidates",
        "features": features,
    }
    OUT_PATH.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"Wrote {len(features)} candidates to {OUT_PATH}")
    for feature in features[:10]:
        props = feature["properties"]
        print(props["id"], props["centroid_lat"], props["centroid_lon"], props["area_m2"], props.get("building"), props.get("name"))


if __name__ == "__main__":
    main()
