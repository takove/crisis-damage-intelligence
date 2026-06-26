#!/usr/bin/env bash
set -euo pipefail

ZIP_PATH="${1:?Usage: scripts/emsr884-aoi12-ingest.sh AOI12_GRA_ZIP OUT_DIR}"
OUT_DIR="${2:-public/data/aoi/emsr884-aoi12-caraballeda}"

python3 scripts/build_copernicus_ems_package.py "$ZIP_PATH" "$OUT_DIR"

cp "$OUT_DIR/data/ems_builtup_damage.csv" "$OUT_DIR/damage.csv"
cp "$OUT_DIR/data/ems_builtup_damage.geojson" "$OUT_DIR/damage.geojson"
cp "$OUT_DIR/data/ems_builtup_damage.kml" "$OUT_DIR/damage.kml"
cp "$OUT_DIR/metadata/source_metadata.json" "$OUT_DIR/source_metadata.json"

echo "Built EMS package at $OUT_DIR"
echo "Published app-facing files: damage.csv, damage.geojson, damage.kml, source_metadata.json"
echo "Update public/data/catalog.json with the AOI12 layer URLs."
