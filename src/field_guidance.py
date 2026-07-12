"""Conservative, offline field guidance for gap-list targets.

The report database tells us which species are plausible and when nearby
observers find them.  This module turns that evidence into a consistent field
checklist without pretending a photograph can resolve every difficult taxon.
Guidance is deliberately keyed to stable taxon IDs by the caller, while the
profiles here describe repeatable family-level evidence standards.
"""

from __future__ import annotations

from copy import deepcopy


GROUP_PROFILES = {
    "moths": {
        "habitat_tags": ["forest edge", "riparian corridor"],
        "method_tags": ["UV light", "host search"],
        "finding": (
            "Run a UV or actinic sheet where the creek corridor meets varied vegetation, then check nearby trunks and foliage before dawn.",
            "Favor humid, calm nights above 60 F with the moon down; revisit after warm fronts because species turnover can be rapid.",
        ),
        "id": (
            "Compare the full forewing shape and line pattern, not color alone; wear, flash and reflected UV can change apparent color.",
            "Check whether forewing marks continue onto the hindwing and record antenna, palp and abdomen shape when visible.",
        ),
        "photos": (
            "Square dorsal frame with both forewings sharp from costa to inner margin.",
            "Side or head-on frame showing antennae, palps, thorax and resting posture.",
            "Hindwing and abdomen-tip frame if the moth will safely open its wings.",
        ),
        "limitation": "Keep the identification provisional when the decisive wing pattern or structural views are missing; some moths require expert examination beyond photographs.",
    },
    "butterflies": {
        "habitat_tags": ["sunny edge", "nectar patch"],
        "method_tags": ["day transect", "nectar watch"],
        "finding": (
            "Walk sunny creek banks, shrub edges and flower patches slowly between 10 AM and 3 PM, pausing where insects patrol or return to the same perch.",
            "Check damp soil, scat and mineral seeps as well as flowers; puddling often reveals species that pass quickly over nectar patches.",
        ),
        "id": (
            "Use the combination of wing shape, spot placement and both wing surfaces; a single distant upper-side view is often not enough.",
            "Record antenna clubs, tails, eye spots and the exact ventral hindwing pattern before wear removes small marks.",
        ),
        "photos": (
            "Sharp upper-side frame with all four wings in one plane.",
            "Sharp underside frame showing the complete hindwing and forewing tip.",
            "Close side view of antenna clubs, legs and any tails or eye spots.",
        ),
        "limitation": "Worn, closed-wing or distant butterflies may only support a genus or species-group identification; retain that level when key underside marks are absent.",
    },
    "odonates": {
        "habitat_tags": ["pond edge", "creek corridor"],
        "method_tags": ["sunny water patrol", "perch watch"],
        "finding": (
            "Work pond, creek, seep and wet-meadow edges on warm, bright, low-wind days, watching repeated patrol routes before trying to approach a perch.",
            "Revisit early and late in the day when adults bask lower; inspect emergent stems and bridge abutments for tenerals and exuviae.",
        ),
        "id": (
            "Check face color, thoracic stripe pattern, wing tint and venation, abdominal segment markings and terminal appendages as one character set.",
            "Separate sex and maturity effects from species marks; immature and female odonates often do not match the familiar adult-male color.",
        ),
        "photos": (
            "Dorsal frame showing thoracic stripes, all four wing bases and the entire abdomen.",
            "True side frame showing the face, thorax and abdominal segment pattern.",
            "Magnified terminal frame showing appendages and the final abdominal segments.",
        ),
        "limitation": "Female, immature and closely related odonates can require appendage, genital-lamina or wing-venation details; do not force a species ID from overall color.",
    },
}


FAMILY_PROFILES = {
    # Moths
    "Sphingidae": {
        "habitat_tags": ["flower patch", "hardwood edge"],
        "method_tags": ["dusk watch", "UV light", "larval search"],
        "finding": "Watch deep flowers at dusk, then run UV beside grape, cherry, ash, viburnum and other likely larval hosts.",
        "id": "Compare forewing shape, thoracic stripes, abdomen bands and hindwing color; clearwing species also require transparent-window and leg-color details.",
    },
    "Saturniidae": {
        "habitat_tags": ["hardwood canopy", "forest edge"],
        "method_tags": ["UV light", "larval search"],
        "finding": "Run a bright sheet near mature hardwood canopy from late evening through the pre-dawn hours and search host foliage for large larvae by day.",
        "id": "Record wing shape, eye spots or transparent windows, band placement, body color and antenna width; sex can strongly change antenna shape.",
    },
    "Geometridae": {
        "habitat_tags": ["forest understory", "riparian shrubs"],
        "method_tags": ["UV light", "day flush"],
        "finding": "Use a low UV sheet beside layered understory vegetation and gently flush shaded trunks and leaves during the day.",
        "id": "Trace antemedial and postmedial lines across both wings, then compare discal spots, wing edge and resting posture; many pugs need more than a worn dorsal view.",
    },
    "Noctuidae": {
        "habitat_tags": ["forest edge", "old field"],
        "method_tags": ["UV light", "sugar bait"],
        "finding": "Combine UV with fermented sugar bait along the forest edge; check flowers and grasses for stem borers and day-active noctuids.",
        "id": "Map the orbicular, reniform and claviform spots plus basal, antemedial and postmedial lines; add hindwing and leg views for close noctuid pairs.",
    },
    "Erebidae": {
        "habitat_tags": ["forest edge", "lichen trunks"],
        "method_tags": ["UV light", "sugar bait"],
        "finding": "Use UV and sugar bait near mature trunks, grape tangles and humid creek-edge vegetation; inspect lichen-covered bark by day.",
        "id": "Photograph the complete forewing and exposed hindwing, plus abdomen bands and resting shape; underwings cannot be confirmed without the hindwing pattern.",
    },
    "Notodontidae": {
        "habitat_tags": ["hardwood canopy", "forest edge"],
        "method_tags": ["UV light", "larval search"],
        "finding": "Run UV beneath oak, birch, poplar, willow, cherry and hickory canopy and beat lower host branches for distinctive larvae.",
        "id": "Compare forewing tooth or tuft shape, basal streaks, line angles and hindwing tone; photograph the side profile because thoracic and abdominal tufts are useful.",
    },
    "Tortricidae": {
        "habitat_tags": ["host foliage", "shrub edge"],
        "method_tags": ["beating sheet", "UV light"],
        "finding": "Beat and inspect rolled leaves, buds and fruiting shrubs near the creek edge, then run a small UV light close to the suspected host.",
        "id": "Resolve the costal fold, basal patch, median fascia, terminal fascia and palp shape in a square-on macro; many tortricids remain genus-level without specimen evidence.",
        "limitation": "Many Tortricidae cannot be separated reliably from ordinary field photographs. Use a conservative genus or species-group ID unless a specialist confirms visible diagnostic marks.",
    },
    "Crambidae": {
        "habitat_tags": ["wet meadow", "graminoid edge"],
        "method_tags": ["day flush", "UV light"],
        "finding": "Walk grasses, sedges and wetland vegetation to flush adults at short range, and place UV close to rather than far above the graminoid layer.",
        "id": "Record snout and palp length, resting posture, longitudinal or transverse wing marks and the hindwing; grass-veneers often need a perfectly square dorsal frame.",
    },
    "Pyralidae": {
        "habitat_tags": ["forest edge", "stored plant material"],
        "method_tags": ["UV light", "host-sign search"],
        "finding": "Run UV near fruiting shrubs, fungi, woody debris and outbuildings, then look for webbing or feeding sign on the suspected food source.",
        "id": "Compare palp projection, forewing fasciae and discal spots, wing shape and hindwing shade; photograph the head and side profile as well as the dorsum.",
    },
    "Sesiidae": {
        "habitat_tags": ["sunny host patch", "shrub edge"],
        "method_tags": ["day watch", "host-stem search"],
        "finding": "Watch flowers and sunlit host stems from late morning through early afternoon; inspect borer exit holes and fresh frass rather than relying on lights.",
        "id": "Compare transparent wing-window shape, dark wing borders, body-band color, leg color and antennae; wasp mimicry makes a sharp side view essential.",
    },
    "Gracillariidae": {
        "habitat_tags": ["host foliage", "leaf mines"],
        "method_tags": ["leaf-mine search", "macro photography"],
        "finding": "Search leaves for fresh mines, folds or tents and document the host plant before looking for the tiny adult nearby.",
        "id": "Pair the adult with host and mine architecture; photograph head tuft, forewing streaks and scale tufts under magnification.",
        "limitation": "Adult photographs alone often do not support a species ID in this family. Host identity and mine form, rearing, genitalia or DNA may be required.",
    },
    "Gelechiidae": {
        "habitat_tags": ["host foliage", "old field"],
        "method_tags": ["host search", "macro photography"],
        "finding": "Search tied, mined or folded leaves on likely hosts and use a small light close to the vegetation layer.",
        "id": "Record palp length and curve, forewing scale tufts and spots, and hindwing shape in a high-magnification series.",
        "limitation": "Many gelechiids require genitalia or DNA. A field photograph should remain at genus or family when the visible characters are not diagnostic.",
    },
    # Butterflies
    "Papilionidae": {
        "habitat_tags": ["creek crossing", "mud puddle", "flower patch"],
        "method_tags": ["puddling watch", "dusk patrol"],
        "finding": "Watch creek crossings and damp soil late morning, then check tall nectar flowers and hilltop or edge patrol routes.",
        "id": "Compare tail shape, rows of dorsal and ventral spots, hindwing crescents and sex-specific scaling; photograph both surfaces before the butterfly departs.",
    },
    "Pieridae": {
        "habitat_tags": ["sunny meadow", "woodland spring flora"],
        "method_tags": ["day transect", "host-patch watch"],
        "finding": "Walk sunny openings and host patches repeatedly; spring woodland whites may fly low and briefly before canopy leaf-out.",
        "id": "Use ventral hindwing veining or marbling, forewing-tip pattern and dorsal dark borders; do not identify a distant white butterfly from size alone.",
    },
    "Lycaenidae": {
        "habitat_tags": ["shrub edge", "canopy edge"],
        "method_tags": ["perch watch", "nectar watch"],
        "finding": "Watch flowering shrubs and canopy-edge perches, especially early or late in the daily flight period when hairstreaks descend to nectar.",
        "id": "Compare the entire ventral spot band, number and position of tails, orange and blue tornal patches, and antenna clubs; add the upper side if possible.",
    },
    "Nymphalidae": {
        "habitat_tags": ["woodland edge", "sap and fruit"],
        "method_tags": ["day transect", "fruit bait"],
        "finding": "Check sunny trails, sap flows, carrion, scat and overripe fruit as well as flowers; many woodland nymphalids patrol rather than nectar.",
        "id": "Compare upper- and underside bands, eye spots, commas or silver marks, wing edge and forewing-tip shape; worn adults can lose the key color field.",
    },
    "Hesperiidae": {
        "habitat_tags": ["graminoid edge", "wet meadow"],
        "method_tags": ["slow transect", "nectar watch"],
        "finding": "Walk sedge and grass edges slowly and watch compact nectar patches; skippers often return to the same low perch after a short flight.",
        "id": "Photograph dorsal and ventral hindwings, forewing stigma if present, antenna-club hook and body posture; orange-and-brown color alone does not separate grass skippers.",
        "limitation": "Worn female grass skippers can be inseparable from one photograph. Retain a species-group ID unless the stigma, ventral pattern and antenna club are all clear.",
    },
    # Dragonflies and damselflies
    "Calopterygidae": {
        "habitat_tags": ["shaded creek", "riffle edge"],
        "method_tags": ["creek walk", "perch watch"],
        "finding": "Walk shaded and sun-flecked creek reaches slowly, watching display perches over riffles and low streamside leaves.",
        "id": "Compare wing pigmentation extent, body sheen, female wing spots and the final abdominal segments; exposure can make metallic color unreliable.",
    },
    "Coenagrionidae": {
        "habitat_tags": ["pond vegetation", "slow creek edge"],
        "method_tags": ["close-focus search", "net and release"],
        "finding": "Search low emergent vegetation and sheltered bank pockets at close range; return when the sun reaches the water and adults rise from grass.",
        "id": "Record the black-and-blue pattern on each abdominal segment, eye spots, thoracic stripes and male appendages or female ovipositor; the terminal close-up is decisive.",
        "limitation": "Many bluets and forktails require a sharp terminal view and sex-specific characters. Overall blue or green color is not enough for species identification.",
    },
    "Lestidae": {
        "habitat_tags": ["seasonal wetland", "sedge edge"],
        "method_tags": ["vegetation sweep", "close-focus search"],
        "finding": "Inspect sedges and rushes around seasonal water, especially late summer when spreadwings perch obliquely with wings partly open.",
        "id": "Compare thoracic stripes, pruinosity, ovipositor or male terminal appendages and the exact pattern on the final abdominal segments.",
        "limitation": "Spreadwings frequently require close terminal appendage or ovipositor views; distant side photographs should remain genus-level.",
    },
    "Aeshnidae": {
        "habitat_tags": ["pond patrol", "forest opening"],
        "method_tags": ["patrol watch", "evening flight"],
        "finding": "Watch repeated pond, creek and clearing patrol loops, including the last hour of light; choose a fixed point where the dragonfly repeatedly turns.",
        "id": "Capture face and eye color, both thoracic stripes, abdominal spot shape, wing tint and terminal appendages; a netted-and-released individual is sometimes needed.",
    },
    "Gomphidae": {
        "habitat_tags": ["creek gravel", "sunny bank"],
        "method_tags": ["bank walk", "exuvia search"],
        "finding": "Search sunny gravel, logs and low leaves along the creek, and inspect bridgework and emergent roots for exuviae after morning emergence.",
        "id": "Compare face pattern, thoracic stripes, dorsal abdominal marks, club shape and male appendages; photograph the terminal segments from above and side.",
    },
    "Cordulegastridae": {
        "habitat_tags": ["cold seep", "small stream"],
        "method_tags": ["stream patrol watch", "exuvia search"],
        "finding": "Walk cold seep and narrow stream channels, watching low repeated patrols and checking vertical banks or roots for emergence skins.",
        "id": "Compare yellow thoracic stripes and abdominal rings, face pattern, wing triangle details and terminal appendages; obtain a sharp dorsal abdomen series.",
    },
    "Corduliidae": {
        "habitat_tags": ["pond patrol", "creek opening"],
        "method_tags": ["patrol watch", "exuvia search"],
        "finding": "Watch fast patrols over pond margins and creek openings, then search emergent stems for exuviae early in the day.",
        "id": "Record facial markings, thoracic hair and sheen, wing-base color, abdominal spots and terminal appendages; flight impression alone is not diagnostic.",
    },
    "Libellulidae": {
        "habitat_tags": ["pond edge", "sunny perch"],
        "method_tags": ["perch watch", "close-focus photography"],
        "finding": "Circle sunny pond and wet-meadow perches repeatedly; approach after an adult returns to the same twig, rock or emergent stem.",
        "id": "Compare face color, wing-base patches, pterostigma, leg color, abdominal side and dorsal patterns, and terminal appendages; account for sex and maturity.",
    },
}


NAME_PROFILES = (
    ("clearwing", {
        "method_tags": ["day watch", "host-stem search"],
        "id": "Measure the shape of every transparent wing window and dark border, then compare body bands, leg color and tail tuft; include a side view that shows the legs.",
    }),
    ("underwing", {
        "method_tags": ["sugar bait", "trunk search"],
        "id": "A closed forewing is insufficient: record the complete hindwing ground color and dark band shape, plus the forewing pattern and body size.",
    }),
    ("pug", {
        "method_tags": ["macro photography", "UV light"],
        "id": "Keep the moth square to the lens and resolve the tiny discal spot, cross-line angles and abdominal marks; many Eupithecia cannot be safely named from photographs.",
        "limitation": "Most worn or poorly aligned pugs should remain Eupithecia or a species group unless a specialist confirms a diagnostic photo character.",
    }),
    ("dagger", {
        "id": "Compare the complete forewing line-and-dash pattern and add a hindwing and side view; several dagger moth adults are not reliably separable without larvae or expert examination.",
        "limitation": "Some dagger moths are safer as Acronicta or a named complex from adult photographs; larvae, genitalia or expert review may be needed.",
    }),
    ("leafroller", {
        "method_tags": ["rolled-leaf search", "beating sheet"],
    }),
    ("borer", {
        "method_tags": ["host-stem search", "frass search"],
        "finding": "Inspect the suspected host for fresh frass, wilting shoots, exit holes or pupal cases and record the host in the same observation series.",
    }),
    ("hairstreak", {
        "method_tags": ["canopy-edge watch", "nectar watch"],
    }),
    ("skipper", {
        "method_tags": ["slow grass transect", "nectar watch"],
    }),
    ("dancer", {
        "habitat_tags": ["rocky creek", "sunny bank"],
    }),
    ("bluets", {
        "method_tags": ["net and release", "terminal macro"],
    }),
    ("bluet", {
        "method_tags": ["net and release", "terminal macro"],
    }),
    ("darner", {
        "method_tags": ["patrol watch", "evening flight"],
    }),
    ("meadowhawk", {
        "habitat_tags": ["wet meadow", "sunny perch"],
    }),
)


def _merge_unique(base, additions):
    return list(dict.fromkeys([*base, *additions]))


def guidance_profile(group, family_name="", common_name=""):
    """Return merged group, family and name guidance for one target."""
    profile = deepcopy(GROUP_PROFILES[group])
    family = FAMILY_PROFILES.get(family_name) or {}
    for key, value in family.items():
        if key in {"habitat_tags", "method_tags"}:
            profile[key] = _merge_unique(value, profile.get(key, []))
        elif key in {"finding", "id", "photos"}:
            current = list(profile.get(key, ()))
            additions = list(value) if isinstance(value, (tuple, list)) else [value]
            profile[key] = tuple(_merge_unique(additions, current))
        else:
            profile[key] = value

    label = (common_name or "").casefold()
    for needle, override in NAME_PROFILES:
        if needle not in label:
            continue
        for key, value in override.items():
            if key in {"habitat_tags", "method_tags"}:
                profile[key] = _merge_unique(value, profile.get(key, []))
            elif key in {"finding", "id", "photos"}:
                current = list(profile.get(key, ()))
                additions = list(value) if isinstance(value, (tuple, list)) else [value]
                profile[key] = tuple(_merge_unique(additions, current))
            else:
                profile[key] = value
    return profile


def lookalike_distinction(group, profile, peer_common, peer_scientific):
    """Conservative comparison text for a named regional congener.

    The database can name real local alternatives, but it does not contain a
    diagnostic key.  We therefore name the evidence set that must differ and
    say when to stop at genus rather than inventing a mark.
    """
    peer = peer_common or peer_scientific
    if group == "moths":
        return (
            f"Eliminate {peer} by comparing the complete forewing line and spot pattern, "
            "wing shape, hindwing, antennae and palps. If that combination is not visible "
            "or a specialist cannot confirm it, retain the genus rather than using color alone."
        )
    if group == "butterflies":
        return (
            f"Eliminate {peer} with both wing surfaces: compare spot-band placement, wing "
            "edge, tails or eye spots and antenna clubs. Wear can erase small differences."
        )
    return (
        f"Eliminate {peer} by comparing face color, thoracic stripes, the pattern on each "
        "abdominal segment and terminal appendages. Sex and maturity must match before color is compared."
    )


def build_guidance(group, family_name, common_name, season_label, regional_count,
                   lookalikes):
    """Build all required offline guidance fields for a target."""
    profile = guidance_profile(group, family_name, common_name)
    seasonal = (
        f"Nearby records place this species in {season_label}. Concentrate effort inside that "
        "window, but allow for warm-year shifts of one to two weeks."
    )
    observation_word = "observation" if regional_count == 1 else "observations"
    reason = (
        f"Not yet recorded at Kingfisher Hollow; {regional_count:,} nearby reference "
        f"{observation_word} make it a practical comparison target."
    )
    comparisons = [
        {
            "name": peer.get("common_name") or peer.get("scientific_name"),
            "scientific_name": peer.get("scientific_name", ""),
            "distinction": lookalike_distinction(
                group, profile, peer.get("common_name", ""), peer.get("scientific_name", "")
            ),
        }
        for peer in lookalikes[:3]
    ]
    return {
        "habitat_tags": profile["habitat_tags"],
        "method_tags": profile["method_tags"],
        "target_reason": reason,
        "finding_help": [seasonal, *profile["finding"][:2]],
        "id_help": list(profile["id"][:3]),
        "lookalikes": comparisons,
        "photo_checklist": list(profile["photos"][:3]),
        "id_limitations": profile["limitation"],
    }
