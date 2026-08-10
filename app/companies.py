# Add real company slugs here. See README.md for how to find a company's slug.
#
# Keep this list small at first (3-5 per source) — the point of step 2 is to
# verify the pipeline works correctly on real data, not to maximize volume
# on day one. Widen it once ingest.py runs clean.

GREENHOUSE_COMPANIES: list[str] = [
    "upwork",
    "clickup",
    "abnormalsecurity",
    "wayve",
]

LEVER_COMPANIES: list[str] = [
    "bumbleinc",
    "matchgroup",
    "spotify",
    "hive",
]