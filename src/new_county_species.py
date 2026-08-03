"""Build the place-agnostic iNaturalist county-species detector."""

import hashlib
import shutil
from pathlib import Path

from config import PUBLIC_DIR


ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIR = ROOT / "new-county-species"
RUNTIME_SOURCE = ROOT / "src" / "new_county_species_runtime.mjs"


def _source_digest():
    digest = hashlib.sha256()
    for filename in ("index.html", "styles.css", "app.js"):
        digest.update((SOURCE_DIR / filename).read_bytes())
    digest.update(RUNTIME_SOURCE.read_bytes())
    return digest.hexdigest()[:12]


def build():
    version = _source_digest()
    route_dir = PUBLIC_DIR / "tools" / "new-county-species"
    assets_dir = PUBLIC_DIR / "assets"
    route_dir.mkdir(parents=True, exist_ok=True)
    assets_dir.mkdir(parents=True, exist_ok=True)
    html = (SOURCE_DIR / "index.html").read_text(encoding="utf-8")
    app = (SOURCE_DIR / "app.js").read_text(encoding="utf-8")
    (route_dir / "index.html").write_text(
        html.replace("__ASSET_VERSION__", version), encoding="utf-8"
    )
    shutil.copyfile(SOURCE_DIR / "styles.css", assets_dir / "new-county-species.css")
    (assets_dir / "new-county-species.js").write_text(
        app.replace("__ASSET_VERSION__", version), encoding="utf-8"
    )
    shutil.copyfile(
        RUNTIME_SOURCE, assets_dir / "new-county-species-runtime.js"
    )
    return route_dir / "index.html"
