# Ops Scripts

This folder contains monitoring scripts that can later be connected to GitHub Actions.

Packaged import scripts live in:

- `scripts/build_copernicus_ems_package.py`
- `scripts/emsr884-aoi12-ingest.sh`

Keep GitHub Actions jobs batch-oriented and write static exports back to object storage or committed `public/data` fixtures only when files are small.
