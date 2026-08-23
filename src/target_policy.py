"""Conservative eligibility rules for regional survey gap targets.

An iNaturalist radius search is not a wildlife checklist.  It can contain zoo
animals, domestic stock, classroom specimens, escaped pets, transported
hitchhikers, fossils, and records with unusably broad coordinates.  A new row
therefore must not become a Kingfisher Hollow target automatically.

These positive lists use current iNaturalist scientific names for taxa reviewed
as plausible in the site's Southern Tier / Central Appalachian setting.  They
are grounded in the NYSDEC New York fauna checklist and the Tioga Unit animal
occurrence list, then updated for current taxonomy and confirmed property
records.  Additions require an explicit range and habitat review.

Sources:
https://extapps.dec.ny.gov/docs/wildlife_pdf/vertchklst0410.pdf
https://extapps.dec.ny.gov/docs/lands_forests_pdf/tiogaump.pdf
https://dec.ny.gov/sites/default/files/2024-04/reptilesstatusassessments.pdf

Policy reviewed: 2026-08-23.
"""


VETTED_REGIONAL_TARGET_NAMES = {
    "mammals": frozenset({
        "Didelphis virginiana",
        "Sorex cinereus",
        "Sorex dispar",
        "Sorex fumeus",
        "Sorex hoyi",
        "Sorex palustris",
        "Cryptotis parvus",
        "Blarina brevicauda",
        "Condylura cristata",
        "Parascalops breweri",
        "Scalopus aquaticus",
        "Myotis lucifugus",
        "Myotis leibii",
        "Myotis septentrionalis",
        "Myotis sodalis",
        "Lasionycteris noctivagans",
        "Perimyotis subflavus",
        "Eptesicus fuscus",
        "Lasiurus borealis",
        "Lasiurus cinereus",
        "Ursus americanus",
        "Procyon lotor",
        "Pekania pennanti",
        "Mustela nivalis",
        "Mustela richardsonii",
        "Neogale frenata",
        "Neogale vison",
        "Mephitis mephitis",
        "Lontra canadensis",
        "Canis latrans",
        "Vulpes vulpes",
        "Urocyon cinereoargenteus",
        "Lynx rufus",
        "Marmota monax",
        "Tamias striatus",
        "Sciurus carolinensis",
        "Tamiasciurus hudsonicus",
        "Glaucomys volans",
        "Glaucomys sabrinus",
        "Castor canadensis",
        "Peromyscus maniculatus",
        "Peromyscus leucopus",
        "Synaptomys cooperi",
        "Clethrionomys gapperi",
        "Microtus chrotorrhinus",
        "Microtus pennsylvanicus",
        "Microtus pinetorum",
        "Ondatra zibethicus",
        "Zapus hudsonius",
        "Napaeozapus insignis",
        "Erethizon dorsatum",
        "Sylvilagus floridanus",
        "Lepus americanus",
        "Odocoileus virginianus",
    }),
    "amphibians": frozenset({
        "Necturus maculosus",
        "Ambystoma jeffersonianum",
        "Ambystoma laterale",
        "Ambystoma maculatum",
        "Notophthalmus viridescens",
        "Desmognathus fuscus",
        "Desmognathus ochrophaeus",
        "Plethodon cinereus",
        "Plethodon glutinosus",
        "Plethodon wehrlei",
        "Hemidactylium scutatum",
        "Gyrinophilus porphyriticus",
        "Eurycea bislineata",
        "Eurycea longicauda",
        "Anaxyrus americanus",
        "Dryophytes versicolor",
        "Pseudacris crucifer",
        "Pseudacris triseriata",
        "Lithobates catesbeianus",
        "Lithobates clamitans",
        "Lithobates sylvaticus",
        "Lithobates pipiens",
        "Lithobates palustris",
    }),
    "reptiles": frozenset({
        "Chelydra serpentina",
        "Sternotherus odoratus",
        "Clemmys guttata",
        "Glyptemys insculpta",
        "Chrysemys picta",
        "Plestiodon anthracinus",
        "Nerodia sipedon",
        "Storeria dekayi",
        "Storeria occipitomaculata",
        "Thamnophis sirtalis",
        "Thamnophis saurita",
        "Diadophis punctatus",
        "Opheodrys vernalis",
        "Coluber constrictor",
        "Pantherophis alleghaniensis",
        "Lampropeltis triangulum",
    }),
}
