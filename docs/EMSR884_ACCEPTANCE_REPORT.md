# EMSR884 Real-Product Acceptance Report

Date: 2026-06-26

## Scope

This validates the canonical Copernicus EMS path using original GRA ZIP products, not extracted folders and not xBD fixtures.

Products tested:

- `outputs/AOI02_Caracas_GRA_v1.zip`
- `outputs/AOI06_Moron_GRA_v1.zip`

## Commands Run

```bash
python3 outputs/damage_pipeline/build_copernicus_ems_package.py \
  outputs/AOI02_Caracas_GRA_v1.zip \
  outputs/ems_acceptance_aoi02_from_zip

python3 outputs/damage_pipeline/build_copernicus_ems_package.py \
  outputs/AOI06_Moron_GRA_v1.zip \
  outputs/ems_acceptance_aoi06_from_zip

ogrinfo -so /vsizip/outputs/AOI02_Caracas_GRA_v1.zip/EMSR884_AOI02_GRA_PRODUCT_v1.gpkg builtUpA_v1
ogrinfo -so /vsizip/outputs/AOI06_Moron_GRA_v1.zip/EMSR884_AOI06_GRA_PRODUCT_v1.gpkg builtUpA_v1

npm run lint
npm run build
```

Browser QA was run against `https://crisis-damage.localhost` with Chrome via Playwright.

## GPKG Detection

Both ZIPs were ingested directly. The importer automatically found:

- AOI02: `EMSR884_AOI02_GRA_PRODUCT_v1.gpkg`, layer `builtUpA_v1`
- AOI06: `EMSR884_AOI06_GRA_PRODUCT_v1.gpkg`, layer `builtUpA_v1`

Detected EMS fields include `damage_gra`, `det_method`, `obj_type`, `name`, `notation`, `or_src_id`, `dmg_src_id`, `cd_value`, and `real`.

## Generated Outputs

AOI02:

- `outputs/ems_acceptance_aoi02_from_zip/data/ems_builtup_damage.csv`
- `outputs/ems_acceptance_aoi02_from_zip/data/ems_builtup_damage.geojson`
- `outputs/ems_acceptance_aoi02_from_zip/data/ems_builtup_damage.kml`
- `outputs/ems_acceptance_aoi02_from_zip/metadata/source_metadata.json`
- `outputs/ems_acceptance_aoi02_from_zip/reports/EMSR884_AOI02_GRA_PRODUCT_summaryTable_v1.xlsx`
- `outputs/ems_acceptance_aoi02_from_zip/reports/EMSR884_AOI02_GRA_PRODUCT_27000_map_v1.pdf`

AOI06:

- `outputs/ems_acceptance_aoi06_from_zip/data/ems_builtup_damage.csv`
- `outputs/ems_acceptance_aoi06_from_zip/data/ems_builtup_damage.geojson`
- `outputs/ems_acceptance_aoi06_from_zip/data/ems_builtup_damage.kml`
- `outputs/ems_acceptance_aoi06_from_zip/metadata/source_metadata.json`
- `outputs/ems_acceptance_aoi06_from_zip/reports/EMSR884_AOI06_GRA_PRODUCT_summaryTable_v1.xlsx`
- `outputs/ems_acceptance_aoi06_from_zip/reports/EMSR884_AOI06_GRA_PRODUCT_19000_map_v1.pdf`

These AOIs were also copied into the Next.js app under `public/data/aoi/emsr884-aoi02-caracas` and `public/data/aoi/emsr884-aoi06-moron`, then added to `public/data/catalog.json`.

## Feature Counts

| AOI | GeoJSON features | CSV rows | Destroyed | Damaged | Possibly damaged |
| --- | ---: | ---: | ---: | ---: | ---: |
| AOI02 Caracas | 17 | 17 | 0 | 0 | 17 |
| AOI06 Moron | 129 | 129 | 2 | 34 | 93 |

## EMS Summary Table Comparison

The copied EMS XLSX summary tables were inspected and match the generated counts:

- AOI02 `_builtUpA_m_v1_aoi`: 17 possibly damaged built-up features.
- AOI06 `_builtUpA_m_v1_aoi`: 2 destroyed, 34 damaged, 93 possibly damaged built-up features.

## Browser QA Evidence

Screenshots:

- `outputs/ems_acceptance_qa/01-aoi02-all-final.png`
- `outputs/ems_acceptance_qa/02-aoi06-severe-final.png`
- `outputs/ems_acceptance_qa/06-aoi06-priority-zoom18-popup.png`

Verified in browser:

- AOI switching works for AOI02 and AOI06.
- AOI02 all filter shows 17 features.
- AOI02 severe filter shows 0 features, matching all features being `Possibly damaged`.
- AOI06 all filter shows 129 features.
- AOI06 severe filter shows 36 features: `Destroyed` + `Damaged`.
- AOI06 VLM-only filter shows 0 features, because these real EMS AOIs have no VLM JSONL attached.
- Download links resolve to static CSV, GeoJSON, and KML.
- Priority click selects `ems_00016`, focuses to zoom 18, opens a popup, and exposes a Google Maps link.

Final QA assertion:

```json
{
  "aoi06Severe": 36,
  "selected": "ems_00016",
  "focused": "ems_00016",
  "zoom": 18,
  "popupLink": "https://www.google.com/maps/search/?api=1&query=10.47542832,-68.21234170833334"
}
```

## Schema Mismatches Found

- EMS `damage_gra` values are title-case strings such as `Destroyed`, `Damaged`, and `Possibly damaged`; the app had to avoid matching `Possibly damaged` as severe just because it contains the word `damaged`.
- ZIP ingestion originally wrote temporary folder names into metadata. This was fixed so metadata now uses product IDs like `EMSR884_AOI02_GRA_v1` and records `source_file` / `source_layer`.
- EMS built-up polygons are official damage assessment features, but they are not guaranteed to equal one building per feature. Counts should be reported as built-up damage features unless a source confirms per-building granularity.
- These GRA vector products do not include before/after raster imagery for the Leaflet overlay. The platform can load raster URLs when available, but AOI02/AOI06 acceptance here validates vector ingestion and static app loading.

## AOI12 Blocker

AOI12 Caraballeda/La Guaira ingestion is blocked only by product availability. Once the GRA ZIP is public/downloadable, the same importer should work if it contains a `*_PRODUCT_v*.gpkg` with a `builtUpA*` layer. No xBD dependency remains in the canonical EMS path.

## Verdict

The platform is now genuinely EMSR884-compatible for GRA ZIP vector products with `builtUpA` damage layers. xBD remains only as a separate VLM benchmark/demo fixture, not the canonical ingestion path.
