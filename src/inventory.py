"""Shared species identities for inventory views and the public summary.

The observation cache retains the submitted taxon. Species rosters use species
IDs, so a named infraspecies can otherwise become a second species (or even be
assigned to a different group). Resolve only unambiguous scientific-name matches
against known species; unresolved identities and hybrids remain unchanged.
"""

from collections import Counter

import pandas as pd
import curated_observations


INFRASPECIFIC_RANKS = frozenset({
    'subspecies', 'variety', 'form', 'subvariety', 'subform',
})
PROPERTY_ROSTERS = (
    'moth_taxa', 'butterfly_taxa', 'odonate_taxa', 'mammal_taxa',
    'plant_taxa', 'amphibian_taxa', 'reptile_taxa',
)

ROSTER_ANCESTORS = {
    'moth_taxa': 47157, 'butterfly_taxa': 47224, 'odonate_taxa': 47792,
    'mammal_taxa': 40151, 'plant_taxa': 47126,
    'amphibian_taxa': 20978, 'reptile_taxa': 26036,
}


def property_observations(conn):
    """One row per source observation, with explicit property provenance.

    The curated snapshot takes precedence for approved IDs, even if a later
    project refresh starts returning them. This strips coordinates from those
    rows and respects a newer missing/coarser source status without duplication.
    """
    rows = pd.read_sql_query('SELECT * FROM property_obs', conn)
    rows = rows.assign(source='iNaturalist', source_url=rows.get('url', pd.NA),
                       repeat_history_known=True, property_provenance='Project search')
    curated = curated_observations.records()
    if 'id' in rows:
        rows = rows[~rows['id'].isin(curated)]
    # Confirmation is evidence of wild property occurrence. Keep a captive
    # correction in the source cache, but withdraw it from all inventory views.
    additions = [row for row in curated.values() if row is not None and not row.get('captive')]
    if additions:
        extra = pd.DataFrame(additions)
        rows = pd.concat([rows, extra], ignore_index=True, sort=False)
    return rows


def property_roster(conn, table):
    """Add confirmed species to a property roster, retaining regional pools."""
    rows = pd.read_sql_query(f'SELECT * FROM {table}', conn)
    if table not in ROSTER_ANCESTORS:
        return rows
    reviewed = curated_observations.records()
    if not reviewed:
        return rows
    source_rows = [row for row in reviewed.values() if row is not None]
    canonical = normalize_species(pd.DataFrame(source_rows), conn)
    curated = [row for row in canonical.to_dict('records')
               if row['rank'] == 'species'
               and not row.get('captive')
               and ROSTER_ANCESTORS[table] in (row.get('ancestor_ids') or [])
               and not (table == 'moth_taxa' and 47224 in (row.get('ancestor_ids') or []))]
    project_rows = normalize_species(pd.read_sql_query('SELECT * FROM property_obs', conn), conn)
    project_records = dict(zip(project_rows['id'], project_rows['taxon_id']))
    # A changed/deleted reviewed source must not survive in an older roster.
    eligible = {row['id']: row['taxon_id'] for row in curated}
    if 'obs_count' in rows:
        withdrawn_counts = Counter(
            old_tid for oid, old_tid in project_records.items()
            if oid in reviewed and eligible.get(oid) != old_tid
        )
        independent = project_rows[
            ~project_rows['id'].isin(reviewed) & project_rows['captive'].ne(1)
        ]
        independent_counts = independent['taxon_id'].value_counts()
        for old_tid, withdrawn_count in withdrawn_counts.items():
            match = rows['taxon_id'] == old_tid
            counts = rows.loc[match, 'obs_count']
            # A fresh roster may already omit a stale project observation.
            # Preserve the portion corroborated by independent wild records.
            floor = independent_counts.get(old_tid, 0)
            removable = (counts - floor).clip(lower=0, upper=withdrawn_count)
            rows.loc[match, 'obs_count'] = counts - removable
        rows = rows[rows['obs_count'].isna() | rows['obs_count'].gt(0)].copy()
    for tid in {r['taxon_id'] for r in curated}:
        observations = [r for r in curated if r['taxon_id'] == tid]
        source = observations[0]
        match = rows['taxon_id'] == tid
        if match.any():
            if 'obs_count' in rows:
                rows.loc[match, 'obs_count'] += sum(project_records.get(r['id']) != tid for r in observations)
        else:
            row = {key: source.get(key) for key in rows.columns}
            row['obs_count'] = len(observations)
            rows = pd.concat([rows, pd.DataFrame([row])], ignore_index=True)
    return rows


def normalize_species(observations, conn):
    """Return a counting copy, preserving every observation and source link.

    A finer-rank name must extend exactly one cached species binomial at a word
    boundary. This deliberately does not guess parent IDs from a genus, merge
    hybrids, or collapse an unknown taxon. Raw observation loaders remain raw.
    """
    out = observations.copy()
    required = {'taxon_id', 'taxon_name', 'rank'}
    if not required.issubset(out.columns):
        return out
    finer = out['rank'].isin(INFRASPECIFIC_RANKS)
    if not finer.any():
        return out

    columns = ['taxon_id', 'taxon_name', 'common_name']
    known = [out.loc[out['rank'] == 'species'].reindex(columns=columns)]
    # A supplemental infraspecies may have no parent in the project roster.
    # Use only the species ancestor supplied by its public taxon record.
    parents = [{'taxon_id': row.get('species_taxon_id'),
                'taxon_name': row.get('species_taxon_name'),
                'common_name': row.get('species_common_name')}
               for row in curated_observations.records().values() if row is not None]
    if parents:
        known.append(pd.DataFrame(parents))
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for table in PROPERTY_ROSTERS:
        if table in tables:
            roster = pd.read_sql_query(f'SELECT * FROM {table}', conn)
            known.append(roster.reindex(columns=columns))
    known = pd.concat(known, ignore_index=True).dropna(subset=['taxon_id', 'taxon_name'])
    candidates = {}
    for name, rows in known.groupby('taxon_name'):
        # Roster names are species-ranked; reject ambiguous cached identities.
        if len(str(name).split()) == 2 and rows['taxon_id'].nunique() == 1:
            candidates[str(name)] = rows.iloc[0]

    for index, row in out.loc[finer].iterrows():
        name = row['taxon_name']
        if not isinstance(name, str):
            continue
        parts = name.split()
        parent_name = ' '.join(parts[:2])
        parent = candidates.get(parent_name)
        if parent is None or len(parts) < 3 or '×' in name:
            continue
        out.loc[index, 'taxon_id'] = parent['taxon_id']
        out.loc[index, 'taxon_name'] = parent_name
        out.loc[index, 'rank'] = 'species'
        if 'common_name' in out:
            out.loc[index, 'common_name'] = parent['common_name']
    return out


def species_taxonomy(conn):
    """Keep cached child ancestry when a resolved parent has no metadata.

    Order/family are shared by an infraspecies and its species. Do not overwrite
    a cached parent or invent a value if child cache entries disagree.
    """
    meta = pd.read_sql_query('SELECT * FROM taxon_meta', conn)
    for row in curated_observations.records().values():
        if row is None:
            continue
        match = meta['taxon_id'] == row['taxon_id']
        if match.any():
            for column in meta.columns:
                if row.get(column) is not None:
                    meta.loc[match, column] = row[column]
        else:
            meta = pd.concat([meta, pd.DataFrame([
                {key: row.get(key) for key in meta.columns}])], ignore_index=True)
    raw = property_observations(conn)[['taxon_id', 'taxon_name', 'common_name', 'rank']].drop_duplicates()
    resolved = normalize_species(raw, conn)
    aliases = pd.DataFrame({'original': raw['taxon_id'], 'parent': resolved['taxon_id']})
    aliases = aliases[aliases.original != aliases.parent].dropna().drop_duplicates()
    projected = aliases.merge(meta, left_on='original', right_on='taxon_id')
    additions = []
    for parent, rows in projected.groupby('parent'):
        existing = meta[meta.taxon_id == parent]
        record = existing.iloc[0].to_dict() if not existing.empty else {'taxon_id': parent}
        for column in meta.columns.drop('taxon_id'):
            if pd.notna(record.get(column)) and record.get(column) != '':
                continue
            values = rows[column].dropna()
            values = values[values != ''].unique()
            if len(values) == 1:
                record[column] = values[0]
        if existing.empty:
            additions.append(record)
        else:
            for column, value in record.items():
                meta.loc[existing.index, column] = value
    if additions:
        meta = pd.concat([meta, pd.DataFrame(additions)], ignore_index=True)
    return meta
