"""Explicitly confirmed property records omitted by the public project search.

Only reviewed observation IDs are eligible. Public source snapshots contain no
coordinates, place descriptions, comments, or private fields. They are separate
from the project cache, so a project reconciliation cannot erase this evidence.
"""
import json
import requests
from datetime import datetime, timezone

import inat_api
from config import DATA_DIR

MANIFEST_PATH = DATA_DIR / 'reference' / 'confirmed-property-observations.json'
CACHE_PATH = DATA_DIR / 'cache' / 'confirmed-property-observations.json'
SOURCE_FIELDS = (
    'id', 'observed_on', 'observed_at', 'created_at', 'taxon_id', 'taxon_name',
    'common_name', 'iconic_taxon', 'rank', 'quality_grade', 'user_login',
    'photo_url', 'photo_attribution', 'photo_license', 'captive',
    'taxon_native', 'taxon_introduced', 'ancestor_ids', 'order_name',
    'order_common', 'family_name', 'family_common', 'source_updated_at',
    'species_taxon_id', 'species_taxon_name', 'species_common_name',
)


def manifest():
    """The checked-in list, including a reviewed offline source snapshot."""
    return json.loads(MANIFEST_PATH.read_text())['observations']


def sanitize(observation, taxonomy=None):
    """Select public evidence fields; never persist any coordinates."""
    taxon = observation.get('taxon') or {}
    user = observation.get('user') or {}
    photo = next(iter(observation.get('photos') or []), {})
    ancestors = (taxonomy or taxon).get('ancestors') or []
    by_rank = {t.get('rank'): t for t in ancestors}
    order = by_rank.get('order', {})
    family = by_rank.get('family', {})
    species = taxon if taxon.get('rank') == 'species' else by_rank.get('species', {})
    return {
        'id': observation['id'],
        'observed_on': observation.get('observed_on'),
        'observed_at': observation.get('time_observed_at'),
        'created_at': observation.get('created_at'),
        'source_updated_at': observation.get('updated_at'),
        'taxon_id': taxon.get('id'),
        'taxon_name': taxon.get('name'),
        'common_name': taxon.get('preferred_common_name'),
        'iconic_taxon': taxon.get('iconic_taxon_name'),
        'rank': taxon.get('rank'),
        'quality_grade': observation.get('quality_grade'),
        'user_login': user.get('login'),
        'captive': observation.get('captive'),
        'taxon_native': taxon.get('native'),
        'taxon_introduced': taxon.get('introduced'),
        'photo_url': (photo.get('url') or '').replace('square.', 'medium.') or None,
        'photo_attribution': photo.get('attribution'),
        'photo_license': photo.get('license_code'),
        'ancestor_ids': taxon.get('ancestor_ids') or [],
        'order_name': order.get('name'),
        'order_common': order.get('preferred_common_name'),
        'family_name': family.get('name'),
        'family_common': family.get('preferred_common_name'),
        'species_taxon_id': species.get('id'),
        'species_taxon_name': species.get('name'),
        'species_common_name': species.get('preferred_common_name'),
    }


def records():
    """Load the latest explicit status, falling back only when never refreshed.

    A successful lookup that no longer returns an observation writes a null
    tombstone. A corrected/coarser ID replaces the former snapshot, rather than
    silently restoring its previously countable identity during an offline build.
    """
    cached = json.loads(CACHE_PATH.read_text()) if CACHE_PATH.exists() else {}
    result = {}
    for entry in manifest():
        oid = int(entry['observation_id'])
        state = cached.get(str(oid))
        # A newer checked-in source review outranks an older restored CI cache.
        checked_at = state.get('checked_at') if state else None
        reviewed_at = entry.get('source_checked_at')
        if checked_at and reviewed_at:
            if datetime.fromisoformat(reviewed_at.replace('Z', '+00:00')) > datetime.fromisoformat(checked_at.replace('Z', '+00:00')):
                state = None
        snapshot = entry['snapshot'] if state is None else state['snapshot']
        if snapshot is None:
            result[oid] = None
            continue
        if int(snapshot['id']) != oid:
            raise ValueError(f'Confirmed observation {oid}: mismatched snapshot ID')
        # Re-apply the allowlist when reading too, including local cache files.
        row = {key: snapshot.get(key) for key in SOURCE_FIELDS}
        row['url'] = f'https://www.inaturalist.org/observations/{oid}'
        row['source'] = 'iNaturalist'
        row['source_url'] = row['url']
        row['repeat_history_known'] = True  # A dated observation, not a life-list-only row.
        row['property_provenance'] = 'Confirmed by property owner'
        result[oid] = row
    return result


def refresh():
    """Refresh only approved IDs, through the existing sequential paced client.

    Transport failures propagate before writing anything. Missing records are
    explicit statuses; neither failures nor missing records restore older IDs.
    """
    entries = manifest()
    ids = [int(entry['observation_id']) for entry in entries]
    observations = []
    for oid in ids:
        try:
            observations.extend(inat_api.fetch_observations([oid]))
        except requests.HTTPError as error:
            if error.response is None or error.response.status_code != 404:
                raise
    taxon_ids = sorted({obs['taxon']['id'] for obs in observations if obs.get('taxon')})
    taxonomy = {}
    for start in range(0, len(taxon_ids), 30):
        taxonomy.update({taxon['id']: taxon
                         for taxon in inat_api.fetch_taxa(taxon_ids[start:start + 30])})
    found = {int(obs['id']): sanitize(obs, taxonomy.get((obs.get('taxon') or {}).get('id')))
             for obs in observations}
    checked_at = datetime.now(timezone.utc).isoformat()
    payload = {str(oid): {'checked_at': checked_at, 'snapshot': found.get(oid)}
               for oid in ids}
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = CACHE_PATH.with_suffix('.tmp')
    temporary.write_text(json.dumps(payload, indent=2) + '\n')
    temporary.replace(CACHE_PATH)
    print(f'[confirmed-property] {len(found)}/{len(ids)} public records available')
    return len(found), 0
