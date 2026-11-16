# Inventory counting policy

The life list, overview, taxon pages, and public summary use species identities
where the cache supplies an unambiguous species match. The underlying
`property_obs` records are never rewritten or removed by report generation.
`analyze.load_property(species_only=False)` preserves their original taxon IDs,
names, ranks, dates, and evidence URLs.

A species-level counting copy resolves a subspecies, variety, or form to a cached
species only when its scientific name extends an exact species binomial and that
binomial identifies one taxon ID. Species candidates come from species-ranked
property records and the property rosters. This is the same limited name-matching
policy used by the recent-species panel, not a general synonym resolver. Hybrids,
ambiguous names, and finer taxa without a cached species match remain separate.
When a species parent lacks cached order/family metadata, the read path preserves
unambiguous ancestry from its child identification; it does not overwrite known
parent metadata or choose between conflicting child values.

Every observation and its URL remain available after resolution; two
identifications of the same species contribute two records, not two species.

Uniqueness statistics remain attached to their original identification IDs. The
latest-record, county-first, rarity, and activity-log evidence joins use the raw
eligible record frame (`canonical_species=False`), retaining child-specific
names, photos, and comparison counts. Child rarity values are never reassigned
to the parent species, including in species-roster showcases.

The public summary applies the same normalization. The moth observation API also
retains finer-rank observations under their resolved species identity. Its
observation links still lead to the original source identification.

## The moth discrepancy

The two extra moths in the all-life inventory were butterfly subspecies absent
from species-ranked rosters:

- [Limenitis arthemis astyanax](https://www.inaturalist.org/taxa/58585),
  [observation 371315672](https://www.inaturalist.org/observations/371315672),
  belongs to [Limenitis arthemis](https://www.inaturalist.org/taxa/60607).
- [Danaus plexippus plexippus](https://www.inaturalist.org/taxa/235550),
  [observation 307712197](https://www.inaturalist.org/observations/307712197),
  belongs to [Danaus plexippus](https://www.inaturalist.org/taxa/48662).

Both species parents and Papilionoidea ancestry were checked against the
[iNaturalist taxon API](https://api.inaturalist.org/v1/taxa/58585,235550).
The old label fallback assumed any unmatched Lepidoptera was a moth. Unmatched
records now retain their known order label rather than acquiring unsupported
moth membership.

## Consistency checks and intentional scope differences

The build compares the actual moth and butterfly taxon-ID sets in the life list
with their dedicated rosters, then compares the generated API totals with the
life list. A missing taxon cannot be hidden by a different taxon contributing the
same count. A failure lists the mismatched IDs and stops publication preparation;
refresh or investigate the source snapshots rather than forcing the counts.

The all-record plant inventory includes cultivated records. The dedicated plant
roster is wild-only. These sets intentionally differ and are not forced equal.
Seasonal chapters explicitly count original species-level-or-finer taxon IDs,
with their own date and wild-record eligibility filters; those are labeled taxa
and are not the site-wide species inventory.

Validation used a read-only copy of the local 2026-08-16 property snapshot, not a
new sync or a claim about current production totals. It resolved five finer IDs,
reducing the iNaturalist inventory from 1,670 to 1,665 identities while retaining
all observations. Moth (860), butterfly (28), mammal (22), amphibian (10), and
reptile (7) memberships then matched their rosters exactly. Plants had 276
identities versus 261 in the wild roster; all 15 additional species had only
cultivated, casual records. With the checked-in 160-bird eBird list, the generated
all-life/API total was 1,825.
