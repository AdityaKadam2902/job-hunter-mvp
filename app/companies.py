# Add real company slugs here. See README.md for how to find a company's slug.
#
# Keep this list small at first (3-5 per source) — the point of step 2 is to
# verify the pipeline works correctly on real data, not to maximize volume
# on day one. Widen it once ingest.py runs clean.

GREENHOUSE_COMPANIES: list[str] = [
    "upwork",
    "abnormalsecurity",
    "wayve",
]

LEVER_COMPANIES: list[str] = [
    "bumbleinc",
    "matchgroup",
    "spotify",
    "hive",
]

# RemoteOK: no per-company slug needed. One tag covers many companies at
# once — this is the low-maintenance way to widen coverage instead of
# hunting down individual company ATS slugs one at a time.
REMOTEOK_TAGS: list[str] = [
    "machine-learning",
    "python",
    "ai",
]

# Ashby: same public-API pattern as Greenhouse/Lever. Confirmed real,
# currently-active Ashby-hosted boards — Ramp especially skews toward
# fintech/AI engineering roles.
ASHBY_COMPANIES: list[str] = [
    "ramp", "jerry", "alan"
]

# Workday: format is (tenant, wd_server, site, display_name). Unlike the
# other ATS platforms, all four parts vary per company with no predictable
# pattern — find them from a company's careers URL, which looks like
# https://{tenant}.{wd_server}.myworkdayjobs.com/en-US/{site}
# These four are confirmed real, currently-active tenants.
WORKDAY_COMPANIES: list[tuple[str, str, str, str]] = [
    ("nvidia", "wd5", "NVIDIAExternalCareerSite", "NVIDIA"),
    ("salesforce", "wd12", "External_Career_Site", "Salesforce"),
    ("adobe", "wd5", "external_experienced", "Adobe"),
    ("hp", "wd5", "ExternalCareerSite", "HP"),
]