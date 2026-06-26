# EMSR884 Real-Product Acceptance Rerun

Date: 2026-06-26

This rerun validates the canonical Copernicus EMS path from original ZIP products, not extracted folders and not xBD.

## Commands Run

```bash
rm -rf outputs/ems_acceptance_rerun_aoi02_from_zip outputs/ems_acceptance_rerun_aoi06_from_zip outputs/ems_acceptance_rerun_qa
mkdir -p outputs/ems_acceptance_rerun_qa

python3 outputs/damage_pipeline/build_copernicus_ems_package.py \
  outputs/AOI02_Caracas_GRA_v1.zip \
  outputs/ems_acceptance_rerun_aoi02_from_zip

python3 outputs/damage_pipeline/build_copernicus_ems_package.py \
  outputs/AOI06_Moron_GRA_v1.zip \
  outputs/ems_acceptance_rerun_aoi06_from_zip

ogrinfo -so /vsizip/outputs/AOI02_Caracas_GRA_v1.zip/EMSR884_AOI02_GRA_PRODUCT_v1.gpkg builtUpA_v1
ogrinfo -so /vsizip/outputs/AOI06_Moron_GRA_v1.zip/EMSR884_AOI06_GRA_PRODUCT_v1.gpkg builtUpA_v1

portless crisis-damage npm run dev
npm run lint
npm run build
```

Browser QA was run with Chrome/Playwright against `https://crisis-damage.localhost`.

## Automatic Layer Detection

Detected directly inside the ZIPs:

- AOI02: `EMSR884_AOI02_GRA_PRODUCT_v1.gpkg`, layer `builtUpA_v1`
- AOI06: `EMSR884_AOI06_GRA_PRODUCT_v1.gpkg`, layer `builtUpA_v1`

Detected layer schema:

- Geometry: `Multi Polygon`
- CRS: EPSG:4326 / WGS84
- Fields: `obj_type`, `name`, `info`, `simplified`, `damage_gra`, `det_method`, `notation`, `or_src_id`, `dmg_src_id`, `cd_value`, `real`

## Generated Files

AOI02:

- `outputs/ems_acceptance_rerun_aoi02_from_zip/data/ems_builtup_damage.csv`
- `outputs/ems_acceptance_rerun_aoi02_from_zip/data/ems_builtup_damage.geojson`
- `outputs/ems_acceptance_rerun_aoi02_from_zip/data/ems_builtup_damage.kml`
- `outputs/ems_acceptance_rerun_aoi02_from_zip/metadata/source_metadata.json`
- `outputs/ems_acceptance_rerun_aoi02_from_zip/reports/EMSR884_AOI02_GRA_PRODUCT_summaryTable_v1.xlsx`
- `outputs/ems_acceptance_rerun_aoi02_from_zip/reports/EMSR884_AOI02_GRA_PRODUCT_27000_map_v1.pdf`

AOI06:

- `outputs/ems_acceptance_rerun_aoi06_from_zip/data/ems_builtup_damage.csv`
- `outputs/ems_acceptance_rerun_aoi06_from_zip/data/ems_builtup_damage.geojson`
- `outputs/ems_acceptance_rerun_aoi06_from_zip/data/ems_builtup_damage.kml`
- `outputs/ems_acceptance_rerun_aoi06_from_zip/metadata/source_metadata.json`
- `outputs/ems_acceptance_rerun_aoi06_from_zip/reports/EMSR884_AOI06_GRA_PRODUCT_summaryTable_v1.xlsx`
- `outputs/ems_acceptance_rerun_aoi06_from_zip/reports/EMSR884_AOI06_GRA_PRODUCT_19000_map_v1.pdf`

## Counts

| AOI | GeoJSON features | CSV rows | Destroyed | Damaged | Possibly damaged |
| --- | ---: | ---: | ---: | ---: | ---: |
| AOI02 Caracas | 17 | 17 | 0 | 0 | 17 |
| AOI06 Moron | 129 | 129 | 2 | 34 | 93 |

## EMS Summary Comparison

The generated counts match the copied EMS summary tables:

- AOI02 summary table: 14 residential + 3 office possibly damaged = 17.
- AOI06 summary table: 2 destroyed, 34 damaged, 93 possibly damaged = 129.

## Browser QA

Screenshots:

- `outputs/ems_acceptance_rerun_qa/00-catalog.png`
- `outputs/ems_acceptance_rerun_qa/01-aoi02-all.png`
- `outputs/ems_acceptance_rerun_qa/02-aoi06-severe.png`
- `outputs/ems_acceptance_rerun_qa/03-aoi06-priority-popup.png`

Assertions from browser QA:

```json
{
  "aoi02All": 17,
  "aoi02Severe": 0,
  "aoi06All": 129,
  "aoi06Severe": 36,
  "aoi06Vlm": 0,
  "prioritySelected": "ems_00016",
  "priorityZoom": 18,
  "popupGoogleMaps": "https://www.google.com/maps/search/?api=1&query=10.47542832,-68.21234170833334"
}
```

Verified:

- AOI02 and AOI06 are in the platform catalog.
- AOI switching works.
- Severity filters work from real EMS `damage_gra`: `Destroyed` + `Damaged` are severe; `Possibly damaged` is not.
- Download links expose CSV, GeoJSON, and KML.
- Priority click centers to zoom 18.
- Popup opens and includes Google Maps.

## Schema Mismatches / Risks Found

- EMS uses `damage_gra` values such as `Destroyed`, `Damaged`, and `Possibly damaged`; substring matching must not classify `Possibly damaged` as severe.
- EMS built-up features are official built-up assessment polygons, not guaranteed one-building-per-feature.
- AOI02/AOI06 GRA ZIPs validate the vector path, but they do not provide the before/after raster tile overlay needed for visual imagery comparison.
- Very large AOIs may need vector tiles/PMTiles instead of raw GeoJSON.

## AOI12 Blocker

AOI12 Caraballeda/La Guaira is blocked by product availability only. Once its GRA ZIP is public/downloadable and includes a `*_PRODUCT_v*.gpkg` with a `builtUpA*` layer, the same importer should ingest it.

## Verdict

The platform is genuinely compatible with Copernicus EMSR884 GRA vector products for the tested AOI02/AOI06 ZIPs. xBD remains separate as a VLM benchmark/demo dataset only.
