"""Shared species identities for inventory views and the public summary.

The observation cache retains the submitted taxon. Species rosters use species
IDs, so a named infraspecies can otherwise become a second species (or even be
assigned to a different group). Resolve only unambiguous scientific-name matches
against known species; unresolved identities and hybrids remain unchanged.
"""

import pandas as pd


INFRASPECIFIC_RANKS = frozenset({
    'subspecies', 'variety', 'form', 'subvariety', 'subform',
})
PROPERTY_ROSTERS = (
    'moth_taxa', 'butterfly_taxa', 'odonate_taxa', 'mammal_taxa',
    'plant_taxa', 'amphibian_taxa', 'reptile_taxa',
)


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
    raw = pd.read_sql_query(
        'SELECT DISTINCT taxon_id, taxon_name, common_name, rank FROM property_obs', conn)
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
