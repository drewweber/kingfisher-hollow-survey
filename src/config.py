"""Central configuration for the Kingfisher Hollow iNaturalist pipeline.

All iNat identifiers below were verified against the live API (not the CSV
export-job IDs, which were never valid place_ids):

    Property : project_id 249580  (collection project, place 218351
               "Michigan Hollow - silo house")
    County   : place_id 653       (Tioga County, NY)
    State    : place_id 48        (New York)
"""

from pathlib import Path

# --- iNaturalist identifiers -------------------------------------------------
PROPERTY_PROJECT_ID = 249580
COUNTY_PLACE_ID = 653
STATE_PLACE_ID = 48
MY_USERNAME = "drewweber"

# iNat taxa for the moth section: moths = Lepidoptera minus the butterflies.
LEPIDOPTERA_TAXON_ID = 47157
BUTTERFLY_TAXON_ID = 47224
MAMMALIA_TAXON_ID = 40151
PLANTAE_TAXON_ID = 47126
AMPHIBIA_TAXON_ID = 20978
REPTILIA_TAXON_ID = 26036

# Regional reference pool for the moth gap analysis. Tioga County itself is
# undersampled, so a distance radius (crossing into the better-covered Ithaca
# area and PA) gives a truer picture of what moths could occur on the property.
REGION_RADIUS_KM = 80   # ≈ 50 miles

# Property centroid (computed from observation averages) — used for weather API.
PROPERTY_LAT = 42.2744
PROPERTY_LON = -76.4926

# --- Paths -------------------------------------------------------------------
# Resolve everything relative to the repo root (parent of this src/ dir) so the
# scripts work the same whether launched by hand or by launchd.
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
PUBLIC_DIR = ROOT / "public"   # Cloudflare Pages publish dir (index.html)
LOGS_DIR = ROOT / "logs"
DB_PATH = DATA_DIR / "inat.db"

# --- Behaviour ---------------------------------------------------------------
# Ranks counted as "species level" — species and anything finer. Coarser IDs
# (genus, family, …) represent observations not resolved to a species and are
# excluded from all counts, lists, and uniqueness stats.
SPECIES_RANKS = ("species", "subspecies", "variety", "form", "hybrid",
                 "subvariety", "subform")

STATS_TTL_DAYS = 30         # refresh cached uniqueness stats older than this
                            # (counts drift slowly; keeps nightly churn small —
                            #  new property species are always refreshed
                            #  immediately regardless of this TTL)
PER_PAGE = 200              # iNat max page size
REQUEST_PAUSE = 1.0         # seconds between cursor requests (be polite)
USER_AGENT = "kingfisher-hollow-pipeline (https://www.inaturalist.org/projects/kingfisher-hollow-biodiversity-survey)"

for _d in (DATA_DIR, PUBLIC_DIR, LOGS_DIR):
    _d.mkdir(exist_ok=True)
