# Operator Guide - First 5 Minutes

## Objective

Use the map to quickly locate official Copernicus EMSR884 damage polygons, prioritize inspection, and share coordinates/exports with response teams.

## How To Use

1. Open the app and confirm the active AOI is an operational Venezuela AOI, not the xBD demo.
2. Use the AOI selector to switch between `AOI02 Caracas` and `AOI06 Moron`.
3. Read the indicators:
   - `features`: number of built-up polygons in the AOI.
   - `official destroyed/damaged`: `Destroyed` + `Damaged` from EMS.
   - `official possible`: `Possibly damaged` from EMS.
4. Use filters:
   - `All`: every EMS polygon.
   - `Destroyed/Damaged`: only `Destroyed` + `Damaged`.
   - `VLM reviewed`: only items with VLM review, if present.
5. In `Priority`, click an item. The map centers the polygon at zoom 18 and opens the popup.
6. Use the `Google Maps` link to share the location with field teams.
7. Download CSV, GeoJSON, or KML for external analysis, QGIS, Google Earth, or dashboards.

## Data Confidence

- Official Copernicus EMS vector labels are the source of record for AOI02/AOI06.
- `Destroyed` and `Damaged` are treated as confirmed damage from the EMS product.
- `Possibly damaged` is shown separately. Do not count it as confirmed destroyed/damaged.
- VLM, when present, is supporting evidence for prioritization; it does not replace EMS or human validation.

## Do Not Overclaim

- EMS `builtUpA` features may not represent one individual building each.
- Official EMS labels are the source of record for this package.
- VLM and inferred labels are triage aids, not official confirmation.
- Absence of a marked polygon is not proof of no damage.

## Known Limitations

- AOI02/AOI06 validate the EMS vector path, but they do not include before/after imagery in the map.
- `builtUpA` polygons are official built-up assessment features; they are not guaranteed to be one building each.
- Large AOIs may require converting GeoJSON into PMTiles/vector tiles.
- La Guaira/AOI12 still depends on Copernicus publishing the GRA ZIP.

## When AOI12 Becomes Available

1. Download the official AOI12 GRA ZIP.
2. Run the EMS importer.
3. Compare counts against the summary table/PDF.
4. Copy CSV/GeoJSON/KML/metadata into `public/data/aoi/emsr884-aoi12-caraballeda`.
5. Add AOI12 to the catalog.
6. Run browser QA.
7. Publish the static package to Vercel.
