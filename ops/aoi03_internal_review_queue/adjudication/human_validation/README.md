# AOI03 Human Validation Template

INTERNAL REVIEW ONLY. These rows are OSM-candidate leads from before/after VLM adjudication, not official EMS damage.

Use `human_validation_template.csv` or `human_validation_template.jsonl` to record manual review outcomes for the 5 urgent candidates.

Allowed `human_status` values:

- `confirmed_damage`
- `false_positive`
- `needs_better_imagery`
- `needs_field_check`
- `duplicate_or_bad_footprint`

Suggested `human_damage_class` values:

- `destroyed`
- `major_damage`
- `minor_damage`
- `no_visible_damage`
- `unknown`

Rules:

- Fill `reviewer_id` with an internal handle, not personal contact info.
- Fill `reviewed_at_utc` in ISO-8601 UTC format.
- Put a URL/path to independent evidence in `evidence_uri` when available.
- Do not publish these rows as confirmed damage unless `human_status=confirmed_damage` and source/evidence is recorded.
- Absence of a row or a false-positive review is not proof of no damage nearby.
