"""Vetted, field-visible differences for Field Targets comparison pairs.

Only pairs listed here are presented as lookalikes. This deliberately avoids
turning an arbitrary congener or family member into an implied confusion
species. Characters describe what is visible on a live insect or a sharp field
photograph. When those characters do not support a species identification, the
profile names the higher taxonomic level to use.
"""

from __future__ import annotations


STATUS_LABELS = {
    "field": "Field-separable",
    "conditional": "Conditional field ID",
    "not_field": "Not field-separable",
}


def _difference(feature, first, second):
    return {"feature": feature, "first": first, "second": second}


def _pair(first, second, status, decision, differences=(), report_as="", sources=()):
    return {
        "taxa": (first, second),
        "status": status,
        "decision": decision,
        "report_as": report_as,
        "differences": tuple(differences),
        "sources": tuple(sources),
    }


BUGGUIDE = "https://bugguide.net/"
BAMONA = "https://www.butterfliesandmoths.org/"
WISCONSIN_ODONATA = "https://wiatri.net/inventory/odonata/speciesaccounts/"
MASS_AUDUBON_BUTTERFLIES = (
    "https://www.massaudubon.org/nature-wildlife/insects-arachnids/"
    "butterfly-atlas/find-a-butterfly"
)
TIGER_SWALLOWTAIL_PAPER = "https://doi.org/10.3897/zookeys.1228.142202"
CLEMENSIA_REVISION = "https://doi.org/10.3897/zookeys.788.26048"
ILLINOIS_SPHINX_GUIDE = (
    "https://www.ideals.illinois.edu/items/120617/bitstreams/395785/data.pdf"
)
OHIO_BUTTERFLY_GUIDE = (
    "https://dam.assets.ohio.gov/image/upload/ohiodnr.gov/documents/wildlife/"
    "backyard-wildlife/Butterflies%20and%20Skippers%20of%20Ohio%20Field%20Guide%20pub204.pdf"
)


# A comparison normally comes from the 80 km regional pool. These three are
# documented, range-plausible confusions that are absent from the current pool,
# so retain the minimum iNaturalist metadata needed to illustrate them.
CURATED_PEER_TAXA = {
    "Catocala luctuosa": {
        "taxon_id": 216294,
        "common_name": "Hulst's Underwing",
        "scientific_name": "Catocala luctuosa",
    },
    "Eumorpha achemon": {
        "taxon_id": 122356,
        "common_name": "Achemon Sphinx",
        "scientific_name": "Eumorpha achemon",
    },
    "Pseudothyris sepulchralis": {
        "taxon_id": 82788,
        "common_name": "Mournful Thyris Moth",
        "scientific_name": "Pseudothyris sepulchralis",
    },
}


# Some current targets are distinctive or lack a close regional congener. They
# still need a visible confusion disposition instead of a silently missing
# comparison section. Each note names the broader thing that can mislead a
# field observer and the evidence needed to avoid over-identification.
NO_NAMED_COMPARISON_NOTES = {
    "Eustixia pupula": (
        "No close regional species is currently vetted for a named comparison. "
        "Other small white crambids can look similar in a distant image, so confirm "
        "the complete spotted forewing pattern and retain Crambidae when it is blurred."
    ),
    "Eichlinia cucurbitae": (
        "The main field confusion is with wasps and other clearwing moths rather "
        "than one close regional species. Photograph both scaled wings, the orange-"
        "and-black abdomen, and the host or stem-borer sign before using a species name."
    ),
    "Perithemis tenera": (
        "No close regional amberwing is currently documented. Females can be mistaken "
        "for other small patterned skimmers, so confirm the very small size, short stout "
        "abdomen, yellowish legs, wing patches, and red stigmas together."
    ),
    "Amphiagrion saucium": (
        "No second red damsel is documented in the regional pool. Immature pond damsels "
        "can appear orange, so confirm the small red-and-black body, short black legs, "
        "and terminal structures rather than relying on color alone."
    ),
    "Tachopteryx thoreyi": (
        "No close regional petaltail is documented. Confirm the widely separated eyes, "
        "long parallel-sided stigmas, gray-and-black body, and characteristic trunk or "
        "log perching; keep an incomplete flight view at family level."
    ),
}


PAIR_PROFILES = (
    # Moths: clear macromoth differences.
    _pair(
        "Hemaris thysbe",
        "Hemaris diffinis",
        "conditional",
        (
            "Use a species name only when the leg color and side of the head and "
            "thorax are visible. Otherwise report Hemaris sp.; the width and shape "
            "of the clear wing borders vary too much to decide this pair alone."
        ),
        (
            _difference(
                "Legs",
                "Pale cream to whitish legs, sometimes with darker shading on the hind legs.",
                "Black legs, including the forelegs.",
            ),
            _difference(
                "Eye stripe and thorax side",
                "No heavy black stripe running from the eye down toward the foreleg.",
                "A strong black eye stripe continues down the side of the thorax toward the foreleg.",
            ),
        ),
        "Hemaris sp.",
        (BUGGUIDE,),
    ),
    _pair(
        "Hyles lineata",
        "Hyles gallii",
        "field",
        (
            "A sharp dorsal photograph showing the complete forewing and abdomen "
            "normally supports a species identification."
        ),
        (
            _difference(
                "Forewing",
                "A crisp white stripe runs from the wing base to the apex, with several fine pale lines below it.",
                "The long pale stripe is broader and cream colored against a more even olive-brown forewing, without the same stack of fine white lines.",
            ),
            _difference(
                "Abdomen",
                "Black-and-white side patches form a strongly checked abdomen.",
                "Pale side spots are smaller and the abdomen reads as a more continuous dark body.",
            ),
        ),
        sources=(BUGGUIDE, BAMONA),
    ),
    _pair(
        "Haploa clymene",
        "Haploa confusa",
        "field",
        "Use a species name when the full dorsal pattern is visible on an unworn moth.",
        (
            _difference(
                "Central black mark",
                "A clean black bar runs lengthwise and meets a crossbar, creating a distinct T or dagger-shaped mark.",
                "Black bands form an irregular branching network rather than one clean central T.",
            ),
            _difference(
                "White areas",
                "Large uninterrupted white fields remain on both sides of the central black mark.",
                "Additional black branches divide the white field into smaller patches.",
            ),
        ),
        sources=(BUGGUIDE,),
    ),
    _pair(
        "Schinia florida",
        "Schinia arcigera",
        "field",
        "The fresh adult colors and hindwing separate this pair in a complete dorsal view.",
        (
            _difference(
                "Forewing",
                "Bright pink forewings have pale yellow at the lower base and beyond the subterminal line.",
                "Velvety chocolate- to red-brown forewings have smooth dark lines and no bright pink-and-yellow field.",
            ),
            _difference(
                "Hindwing and body",
                "Creamy white hindwings accompany a pink head and pale yellow dorsal body.",
                "The hindwing is yellow-and-black or nearly all black, and the body is dark brown.",
            ),
        ),
        sources=(BAMONA, "https://pnwmoths.biol.wwu.edu/"),
    ),
    _pair(
        "Spodoptera ornithogalli",
        "Spodoptera frugiperda",
        "conditional",
        (
            "These marks work best on fresh males. Worn adults and many females "
            "should be reported as Spodoptera sp. unless reviewed by a specialist."
        ),
        (
            _difference(
                "Pale diagonal streak",
                "A long, sharp cream-white streak runs diagonally from the reniform spot toward the forewing tip.",
                "No equally long clean diagonal streak crosses the outer forewing.",
            ),
            _difference(
                "Forewing tip",
                "The apex is mottled but lacks a single isolated square white apical spot.",
                "Males often show a distinct pale or white spot near the apex with a darker triangular mark beside it.",
            ),
        ),
        "Spodoptera sp.",
        (BUGGUIDE,),
    ),
    _pair(
        "Ennomos magnaria",
        "Ennomos subsignaria",
        "field",
        "The ground color and cross-lines are visible in an ordinary dorsal photograph.",
        (
            _difference(
                "Ground color",
                "Warm ochre, tawny, or orange-brown wings.",
                "White to cream wings with much less warm pigment.",
            ),
            _difference(
                "Cross-lines",
                "Two brown cross-lines stand out against the orange-brown wing.",
                "Fine gray-brown speckling and lines cross a white wing.",
            ),
        ),
        sources=(BUGGUIDE,),
    ),
    _pair(
        "Metalectra discalis",
        "Metalectra quadrisignata",
        "field",
        "A sharp dorsal photograph of a fresh moth normally separates this pair.",
        (
            _difference(
                "Pale forewing patches",
                "The forewing is dark brown with a single conspicuous pale reniform area and a pale patch near the inner margin.",
                "Four bold creamy-white patches, two on each forewing, create the characteristic four-spotted pattern.",
            ),
            _difference(
                "Overall contrast",
                "The pattern is mottled and comparatively low-contrast.",
                "The pale patches are sharply bounded and strongly contrast with the dark wing.",
            ),
        ),
        sources=(BUGGUIDE,),
    ),
    _pair(
        "Renia sobrialis",
        "Renia adspergillus",
        "conditional",
        "Use these characters only on a fresh, square dorsal view; worn moths should remain Renia sp.",
        (
            _difference(
                "Wing surface",
                "The forewing is relatively smooth and even brown between the cross-lines.",
                "The forewing is densely peppered with small dark speckles.",
            ),
            _difference(
                "Cross-lines",
                "The postmedial line is clean and easy to follow across the wing.",
                "Speckling breaks up the cross-lines and gives the wing a grainier appearance.",
            ),
        ),
        "Renia sp.",
        (BUGGUIDE,),
    ),
    # Moths: pairs that ordinary field photographs cannot safely resolve.
    _pair(
        "Epinotia medioviridana",
        "Epinotia lindana",
        "not_field",
        (
            "Ordinary field photographs do not provide a reliable character set "
            "for this pair. Report Epinotia sp. unless a specialist confirms a "
            "diagnostic macro photograph or a specimen."
        ),
        report_as="Epinotia sp.",
        sources=(BUGGUIDE,),
    ),
    _pair(
        "Stigmella quercipulchella",
        "Stigmella intermedia",
        "not_field",
        (
            "Adults are not reliably separable in the field. Report Stigmella sp. "
            "An occupied mine documented with its host leaf, or a reared adult, can "
            "support a narrower identification."
        ),
        report_as="Stigmella sp.",
        sources=(BUGGUIDE,),
    ),
    _pair(
        "Cameraria hamameliella",
        "Cameraria guttifinitella",
        "conditional",
        (
            "Do not identify a free adult to species from an ordinary photograph. "
            "A mine with the host leaf in the same record can support the species; "
            "otherwise report Cameraria sp."
        ),
        (
            _difference(
                "Host and mine",
                "A blotch mine on witch-hazel (Hamamelis), documented with the complete host leaf.",
                "A mine on poison ivy or poison oak (Toxicodendron), documented with the complete host leaf.",
            ),
        ),
        "Cameraria sp.",
        (BUGGUIDE,),
    ),
    _pair(
        "Phyllocnistis insignis",
        "Phyllocnistis vitifoliella",
        "conditional",
        (
            "The tiny adults are not reliably separated in the field. Use the mine "
            "only when the host is documented; otherwise report Phyllocnistis sp."
        ),
        (
            _difference(
                "Host and serpentine mine",
                "A narrow serpentine mine on aster-family foliage, with the host plant shown.",
                "A narrow serpentine mine on grape (Vitis), with the host plant shown.",
            ),
        ),
        "Phyllocnistis sp.",
        (BUGGUIDE,),
    ),
    _pair(
        "Acronicta lobeliae",
        "Acronicta americana",
        "not_field",
        (
            "Adult forewing variation overlaps and an ordinary photograph is not a "
            "safe species-level key for this pair. Report Acronicta sp. unless a "
            "specialist confirms the full pattern or a diagnostic larva is documented."
        ),
        report_as="Acronicta sp.",
        sources=(BUGGUIDE,),
    ),
    _pair(
        "Acronicta rubricoma",
        "Acronicta insularis",
        "not_field",
        (
            "Worn adults and single dorsal photographs do not reliably separate this "
            "pair. Report Acronicta sp. unless a specialist confirms diagnostic "
            "characters or a diagnostic larva is documented."
        ),
        report_as="Acronicta sp.",
        sources=(BUGGUIDE,),
    ),
    _pair(
        "Feltia subgothica",
        "Feltia herilis",
        "conditional",
        (
            "Use a species name only for a fresh adult with every forewing spot and "
            "line sharp. Worn or oblique photographs should remain Feltia sp."
        ),
        (
            _difference(
                "Reniform and orbicular spots",
                "Both pale spots are sharply outlined in black and sit in a strongly contrasting dark median area.",
                "The pale spots and surrounding median area are usually less sharply contrasted.",
            ),
            _difference(
                "Longitudinal streaking",
                "Black wedges and streaks below the reniform create a distinctly striped outer forewing.",
                "The outer forewing is more evenly mottled and lacks the same set of bold black wedges.",
            ),
        ),
        "Feltia sp.",
        (BUGGUIDE,),
    ),
    _pair(
        "Anicla infecta",
        "Anicla illapsa",
        "not_field",
        (
            "The variable forewing patterns overlap in routine field photographs. "
            "Report Anicla sp. unless an expert confirms a sharp, unworn specimen-level view."
        ),
        report_as="Anicla sp.",
        sources=(BUGGUIDE,),
    ),
    _pair(
        "Nemapogon clematella",
        "Nemapogon granella",
        "not_field",
        (
            "These tineid moths are not reliably separated from ordinary field "
            "photographs. Report Nemapogon sp. unless a specialist confirms the adult."
        ),
        report_as="Nemapogon sp.",
        sources=(BUGGUIDE,),
    ),
    _pair(
        "Hypenodes caducus",
        "Hypenodes fractilinea",
        "conditional",
        (
            "A fresh, perfectly square macro may support the species. If the cross-line "
            "angles are blurred or scales are missing, report Hypenodes sp."
        ),
        (
            _difference(
                "Postmedial line",
                "The postmedial line is smooth and gently curved across the forewing.",
                "The postmedial line is visibly broken and kinked into short angled sections.",
            ),
            _difference(
                "Outer wing",
                "The area beyond the postmedial line is comparatively even.",
                "Dark fragments along and beyond the broken line give the outer wing a jagged appearance.",
            ),
        ),
        "Hypenodes sp.",
        (BUGGUIDE,),
    ),
    # Butterflies.
    _pair(
        "Papilio polyxenes",
        "Papilio troilus",
        "field",
        "A clear upper- or underside view normally separates these swallowtails.",
        (
            _difference(
                "Hindwing spot row",
                "Two rows of orange-yellow spots run across the hindwing; females may also have blue between them.",
                "A single row of pale green-blue spots crosses the hindwing, with one orange spot near the body.",
            ),
            _difference(
                "Forewing spots",
                "Large yellow spots form two obvious rows across the forewing.",
                "The pale forewing spots are smaller and greener, leaving the wing more extensively black.",
            ),
        ),
        sources=(MASS_AUDUBON_BUTTERFLIES,),
    ),
    _pair(
        "Satyrium calanus",
        "Satyrium caryaevorus",
        "not_field",
        (
            "Published wing-pattern tendencies overlap and do not consistently "
            "separate Banded from Hickory Hairstreak. Report the Banded/Hickory "
            "Hairstreak pair unless genitalia or other specialist evidence resolves it."
        ),
        report_as="Banded/Hickory Hairstreak pair",
        sources=(MASS_AUDUBON_BUTTERFLIES,),
    ),
    _pair(
        "Satyrium calanus",
        "Satyrium liparops",
        "field",
        "A sharp underside view normally separates this pair.",
        (
            _difference(
                "Blue tail spot",
                "The prominent blue spot is not capped with orange.",
                "The prominent blue-gray spot has a clear orange cap.",
            ),
            _difference(
                "Postmedian band",
                "The dark spots form a comparatively narrow, compact band.",
                "The dark marks are broader and more widely separated, creating a strongly striped look.",
            ),
        ),
        sources=(MASS_AUDUBON_BUTTERFLIES,),
    ),
    _pair(
        "Satyrium liparops",
        "Satyrium acadica",
        "field",
        "A complete underside view normally separates this pair.",
        (
            _difference(
                "Postmedian marks",
                "Broad, separated dark bars cross both wings.",
                "A thin, more continuous line crosses the wings.",
            ),
            _difference(
                "Orange hindwing marks",
                "The blue-gray tail spot carries a strong orange cap.",
                "A row of orange crescents extends farther along the hindwing margin.",
            ),
        ),
        sources=(MASS_AUDUBON_BUTTERFLIES,),
    ),
    _pair(
        "Nymphalis antiopa",
        "Nymphalis l-album",
        "field",
        "Either a clear dorsal or ventral view normally separates these tortoiseshells.",
        (
            _difference(
                "Dorsal border",
                "A broad pale yellow border surrounds a dark maroon wing, with a row of blue spots just inside it.",
                "The wing is orange-brown and heavily mottled, without a continuous pale yellow outer border.",
            ),
            _difference(
                "Underside mark",
                "The dark underside lacks a central white L-shaped mark.",
                "A crisp white L-shaped mark sits in the center of the hindwing underside.",
            ),
        ),
        sources=(MASS_AUDUBON_BUTTERFLIES,),
    ),
    _pair(
        "Erynnis baptisiae",
        "Erynnis juvenalis",
        "conditional",
        (
            "Use a species name only when the forewing and underside hindwing are both "
            "clear. Females or worn adults without those views should remain Erynnis sp."
        ),
        (
            _difference(
                "Forewing glassy spots",
                "Usually has a compact row of small glassy forewing spots; males can be nearly spotless.",
                "Has two distinct pale apical spots plus additional glassy spots forming a more complete forewing arc.",
            ),
            _difference(
                "Hindwing underside",
                "Usually plain brown with weak or absent pale spots.",
                "Shows two obvious pale spots near the leading edge of the hindwing underside.",
            ),
        ),
        "Erynnis sp.",
        (MASS_AUDUBON_BUTTERFLIES,),
    ),
    _pair(
        "Lon hobomok",
        "Lon zabulon",
        "conditional",
        (
            "Fresh males are field-separable; dark females require both surfaces and "
            "may be safest as Lon sp. when worn."
        ),
        (
            _difference(
                "Male upper side",
                "A broad orange patch fills most of the forewing and joins the orange hindwing center.",
                "The orange forewing patch is more sharply bounded by dark brown, and the hindwing has a darker border.",
            ),
            _difference(
                "Female underside",
                "Dark females show a purplish-gray hindwing with squarish pale spots.",
                "Dark females show a warmer brown hindwing with a pale, frosted outer margin.",
            ),
        ),
        "Lon sp.",
        (MASS_AUDUBON_BUTTERFLIES,),
    ),
    _pair(
        "Euphyes vestris",
        "Euphyes dion",
        "field",
        "A complete hindwing underside normally separates fresh adults.",
        (
            _difference(
                "Hindwing underside",
                "Nearly plain dark brown, sometimes with only faint pale spots.",
                "A long pale cream ray runs through the center of the dark hindwing.",
            ),
            _difference(
                "Size and shape",
                "Smaller and compact, with a relatively plain underside.",
                "Larger and more elongated, with the central pale ray conspicuous at rest.",
            ),
        ),
        sources=(MASS_AUDUBON_BUTTERFLIES,),
    ),
    _pair(
        "Euphyes vestris",
        "Euphyes conspicua",
        "conditional",
        (
            "A sharp underside is required. Without the hindwing pattern, report Euphyes sp."
        ),
        (
            _difference(
                "Hindwing underside",
                "Plain dark brown or weakly spotted, without a crisp pale band.",
                "A curved row of pale spots forms a visible band across the hindwing.",
            ),
        ),
        "Euphyes sp.",
        (MASS_AUDUBON_BUTTERFLIES,),
    ),
    _pair(
        "Boloria bellona",
        "Boloria myrina",
        "field",
        "A sharp hindwing underside normally separates this pair.",
        (
            _difference(
                "Hindwing underside",
                "Mottled brown and violet-gray, without a continuous row of bright silver spots.",
                "A row of distinct silver-white spots lines the outer hindwing.",
            ),
            _difference(
                "Upper side",
                "The orange upper side is darker and more heavily marked near the wing bases.",
                "The orange upper side is brighter and the black markings are more evenly spaced.",
            ),
        ),
        sources=(MASS_AUDUBON_BUTTERFLIES,),
    ),
    _pair(
        "Polites peckius",
        "Polites themistocles",
        "field",
        "A complete hindwing underside normally separates fresh adults.",
        (
            _difference(
                "Hindwing underside",
                "A large pale yellow patch forms a rough ray or block through the center.",
                "The hindwing is comparatively plain tawny-orange with no large central pale patch.",
            ),
            _difference(
                "Forewing edge",
                "The orange patch is separated from the outer edge by a dark border.",
                "Orange reaches the leading edge and gives the wing its tawny-edged appearance.",
            ),
        ),
        sources=(MASS_AUDUBON_BUTTERFLIES,),
    ),
    _pair(
        "Polites peckius",
        "Polites egeremet",
        "field",
        "A complete hindwing underside normally separates fresh adults.",
        (
            _difference(
                "Hindwing underside",
                "A broad, pale yellow central patch contrasts strongly with the brown wing.",
                "A small bent row of pale spots forms a broken dash rather than one broad patch.",
            ),
            _difference(
                "Overall tone",
                "Warm orange-brown and strongly two-toned below.",
                "Darker chocolate-brown below with smaller, sharper pale marks.",
            ),
        ),
        sources=(MASS_AUDUBON_BUTTERFLIES,),
    ),
    _pair(
        "Polygonia interrogationis",
        "Polygonia comma",
        "field",
        "Either a clear upper side or hindwing underside normally separates this pair.",
        (
            _difference(
                "Forewing upper side",
                "A distinct black horizontal dash sits near the center in addition to the round black spots.",
                "The extra horizontal dash is absent.",
            ),
            _difference(
                "Silver underside mark",
                "The silver mark is split into a curved line and a separate dot, forming a question mark.",
                "The silver mark is a single curved comma.",
            ),
        ),
        sources=(MASS_AUDUBON_BUTTERFLIES,),
    ),
    _pair(
        "Polygonia progne",
        "Polygonia comma",
        "field",
        "A clear hindwing underside normally separates this pair.",
        (
            _difference(
                "Underside pattern",
                "The underside is finely streaked and gray, with a frosted appearance.",
                "The underside is more coarsely mottled brown and less evenly gray.",
            ),
            _difference(
                "Silver mark",
                "The small silver comma is thin and usually hooked at both ends.",
                "The comma is heavier and sits on a more contrasting dark patch.",
            ),
        ),
        sources=(MASS_AUDUBON_BUTTERFLIES,),
    ),
    _pair(
        "Tharsalea epixanthe",
        "Tharsalea hyllus",
        "field",
        "A sharp upper-side view normally separates this pair.",
        (
            _difference(
                "Size and upper side",
                "Tiny, with a dark sooty-brown upper side and a narrow orange band.",
                "Much larger, with broad copper-orange areas and bold dark spotting.",
            ),
            _difference(
                "Hindwing underside",
                "Pale gray with small dark spots and a narrow orange marginal line.",
                "Paler gray-white with larger black spots and a stronger orange border.",
            ),
        ),
        sources=(MASS_AUDUBON_BUTTERFLIES,),
    ),
    _pair(
        "Vanessa virginiensis",
        "Vanessa cardui",
        "field",
        "A complete hindwing underside normally separates these ladies.",
        (
            _difference(
                "Hindwing underside eye spots",
                "Two very large blue-centered eye spots dominate the hindwing.",
                "Four smaller eye spots form a row across the hindwing.",
            ),
            _difference(
                "Upper forewing",
                "A small white spot sits inside the orange field near the forewing center.",
                "The orange field is more continuously mottled and lacks that isolated central white spot.",
            ),
        ),
        sources=(MASS_AUDUBON_BUTTERFLIES,),
    ),
    _pair(
        "Limenitis arthemis",
        "Limenitis archippus",
        "field",
        "A dorsal view normally separates these admiral-pattern butterflies.",
        (
            _difference(
                "Hindwing black line",
                "No black transverse line crosses the orange-red hindwing.",
                "A distinct black line crosses each hindwing.",
            ),
            _difference(
                "Upper-side color",
                "The red-spotted form is dark blue-black with red-orange marginal spots.",
                "The wing is broadly orange with black veins and borders.",
            ),
        ),
        sources=(MASS_AUDUBON_BUTTERFLIES,),
    ),
    _pair(
        "Asterocampa clyton",
        "Asterocampa celtis",
        "field",
        "A clear upper-side view normally separates the two emperors.",
        (
            _difference(
                "Forewing eye spots",
                "The two dark submarginal eye spots are small or weak and lack strong blue centers.",
                "Two bold black eye spots near the forewing edge contain blue centers.",
            ),
            _difference(
                "Upper-side pattern",
                "The wing is more evenly tawny-brown with a broad pale band.",
                "The wing is grayer and more intricately spotted, especially toward the forewing tip.",
            ),
        ),
        sources=(MASS_AUDUBON_BUTTERFLIES,),
    ),
    _pair(
        "Poanes massasoit",
        "Poanes viator",
        "field",
        "A sharp hindwing underside normally separates these wetland skippers.",
        (
            _difference(
                "Hindwing underside",
                "A compact row of pale spots sits on a dark chocolate-brown wing.",
                "A broad pale ray runs lengthwise through the center of the hindwing.",
            ),
            _difference(
                "Wing shape",
                "More compact, with a shorter, rounder hindwing.",
                "Broader-winged and more elongated, especially across the hindwing.",
            ),
        ),
        sources=(MASS_AUDUBON_BUTTERFLIES,),
    ),
    # Dragonflies and damselflies.
    _pair(
        "Argia moesta",
        "Argia apicalis",
        "conditional",
        (
            "Mature males are usually field-separable. Females require a sharp wing "
            "tip showing the cells below the stigma; otherwise report Argia sp."
        ),
        (
            _difference(
                "Mature male",
                "Thorax becomes chalky white with blurred dark stripes; abdomen is dark with a pale gray tip.",
                "Thorax stays blue at the front rather than becoming chalky white.",
            ),
            _difference(
                "Female wing cells",
                "Two cells lie directly below the stigma.",
                "One cell lies directly below the stigma.",
            ),
        ),
        "Argia sp.",
        (WISCONSIN_ODONATA,),
    ),
    _pair(
        "Argia moesta",
        "Argia fumipennis",
        "field",
        "A mature male in a clear dorsal or side view normally separates this pair.",
        (
            _difference(
                "Mature male thorax",
                "Chalky white pruinosity covers the thorax.",
                "Thorax and much of the abdomen are violet-purple, without a chalk-white coating.",
            ),
            _difference(
                "Abdomen",
                "Mostly black with only the tip pale gray.",
                "Extensive violet-purple coloring remains across the abdomen.",
            ),
        ),
        sources=(WISCONSIN_ODONATA,),
    ),
    _pair(
        "Argia fumipennis",
        "Argia translata",
        "field",
        "A mature male in a complete side view normally separates this pair.",
        (
            _difference(
                "Body color",
                "Mature male is conspicuously violet-purple across the thorax and abdomen.",
                "Mature male is mostly black to deep brown, with limited blue at the abdominal tip.",
            ),
            _difference(
                "Thoracic stripes",
                "Purple shoulder stripes remain obvious against darker seams.",
                "Thorax reads nearly uniform dark, without broad violet shoulder fields.",
            ),
        ),
        sources=(WISCONSIN_ODONATA,),
    ),
    # Bluets can often be narrowed with color pattern, but a dependable species
    # identification requires the sex-specific terminal structures. Keep the
    # field app honest when those structures are not resolved.
    _pair(
        "Enallagma civile",
        "Enallagma aspersum",
        "not_field",
        (
            "Ordinary field views do not safely resolve this pair across sex, age, "
            "and color variation. Report Enallagma sp. unless a sharp close-up "
            "shows the male terminal appendages or female mesostigmal plates."
        ),
        report_as="Enallagma sp.",
        sources=(WISCONSIN_ODONATA,),
    ),
    _pair(
        "Enallagma civile",
        "Enallagma exsulans",
        "not_field",
        (
            "Body pattern alone is not a dependable separation for this pair. "
            "Report Enallagma sp. unless the male terminal appendages or female "
            "mesostigmal plates are sharp enough for a diagnostic key."
        ),
        report_as="Enallagma sp.",
        sources=(WISCONSIN_ODONATA,),
    ),
    _pair(
        "Enallagma civile",
        "Enallagma ebrium",
        "not_field",
        (
            "Blue-and-black abdominal pattern can overlap with sex and maturity. "
            "Report Enallagma sp. unless a diagnostic view of the male terminal "
            "appendages or female mesostigmal plates is available."
        ),
        report_as="Enallagma sp.",
        sources=(WISCONSIN_ODONATA,),
    ),
    _pair(
        "Enallagma civile",
        "Enallagma antennatum",
        "not_field",
        (
            "Color can suggest one of these species but does not establish it from "
            "an ordinary field photograph. Report Enallagma sp. unless the male "
            "terminal appendages or female mesostigmal plates are diagnostic."
        ),
        report_as="Enallagma sp.",
        sources=(WISCONSIN_ODONATA,),
    ),
    _pair(
        "Enallagma civile",
        "Enallagma hageni",
        "not_field",
        (
            "This pair should not be decided from blue body pattern alone. Report "
            "Enallagma sp. unless the male terminal appendages or female mesostigmal "
            "plates are shown clearly enough for a diagnostic key."
        ),
        report_as="Enallagma sp.",
        sources=(WISCONSIN_ODONATA,),
    ),
    _pair(
        "Enallagma civile",
        "Enallagma basidens",
        "not_field",
        (
            "Thoracic stripes and abdominal color are supporting clues, not a safe "
            "species decision for this pair. Report Enallagma sp. unless the male "
            "terminal appendages or female mesostigmal plates are diagnostic."
        ),
        report_as="Enallagma sp.",
        sources=(WISCONSIN_ODONATA,),
    ),
    _pair(
        "Enallagma civile",
        "Enallagma traviatum",
        "not_field",
        (
            "Proportions and blue pattern are not sufficient to confirm this pair "
            "from an ordinary field view. Report Enallagma sp. unless the male "
            "terminal appendages or female mesostigmal plates are diagnostic."
        ),
        report_as="Enallagma sp.",
        sources=(WISCONSIN_ODONATA,),
    ),
    _pair(
        "Leucorrhinia intacta",
        "Leucorrhinia frigida",
        "field",
        "Mature males are field-separable in a sharp dorsal view.",
        (
            _difference(
                "Male abdomen",
                "One isolated yellow spot sits on segment 7 of an otherwise black abdomen.",
                "White pruinosity covers the base of the abdomen; there is no isolated yellow dot on segment 7.",
            ),
            _difference(
                "Body shape",
                "Abdomen is narrow and evenly black beyond the yellow dot.",
                "Body is shorter and stubbier, with the pale basal frosting conspicuous.",
            ),
        ),
        sources=(WISCONSIN_ODONATA,),
    ),
    _pair(
        "Leucorrhinia frigida",
        "Leucorrhinia proxima",
        "conditional",
        (
            "Mature males can be separated with a complete dorsal and side view. "
            "Females and immature individuals may require expert review."
        ),
        (
            _difference(
                "Build",
                "Smaller and visibly stubbier.",
                "Slightly larger with a longer, more slender abdomen.",
            ),
            _difference(
                "Male thorax and waist",
                "No red or yellow waist color beside the white-pruinose abdominal base.",
                "Red or yellow can show on the thorax and waist beside the pale abdominal belt.",
            ),
        ),
        "Leucorrhinia sp.",
        (WISCONSIN_ODONATA,),
    ),
    _pair(
        "Anax junius",
        "Anax longipes",
        "field",
        "A clear view of a mature adult normally separates these large darners.",
        (
            _difference(
                "Male abdomen",
                "Bright blue abdomen with a black dorsal line.",
                "Red to reddish-purple abdomen.",
            ),
            _difference(
                "Thorax and face",
                "Green thorax and a distinct black bullseye mark on the forehead.",
                "Green thorax but no matching black bullseye; the face is paler and the legs are notably long.",
            ),
        ),
        sources=(WISCONSIN_ODONATA,),
    ),
    _pair(
        "Celithemis elisa",
        "Celithemis eponina",
        "field",
        "The wing pattern separates this pair even at moderate photographic distance.",
        (
            _difference(
                "Wing markings",
                "Small dark basal patches and dark wing tips; no broad orange bands cross the wings.",
                "Broad orange-and-brown bands cross all four wings.",
            ),
            _difference(
                "Abdomen",
                "Yellow or red heart-shaped spots run down a slender dark abdomen.",
                "Abdomen is orange with broad dark markings and appears heavier.",
            ),
        ),
        sources=(WISCONSIN_ODONATA,),
    ),
    _pair(
        "Epitheca princeps",
        "Epitheca cynosura",
        "field",
        "A dorsal flight or perched photograph showing all four wings separates this pair.",
        (
            _difference(
                "Wing pattern",
                "Three dark patches mark each wing: at the base, nodus, and tip.",
                "Wings are largely clear, without the prince baskettail's three-part dark pattern.",
            ),
            _difference(
                "Overall appearance",
                "Large, long-winged, and boldly patterned even in flight.",
                "Smaller and more uniformly brown, with much less obvious wing markings.",
            ),
        ),
        sources=(WISCONSIN_ODONATA,),
    ),
    _pair(
        "Tramea lacerata",
        "Tramea carolina",
        "field",
        "A complete dorsal view normally separates mature adults.",
        (
            _difference(
                "Hindwing saddles",
                "Large black basal patches fill the rear wings.",
                "Basal patches are reddish-brown rather than black.",
            ),
            _difference(
                "Abdomen",
                "Mostly black in mature adults.",
                "Red in mature males and reddish-brown in females.",
            ),
        ),
        sources=(WISCONSIN_ODONATA,),
    ),
    _pair(
        "Nehalennia irene",
        "Nehalennia gracilis",
        "conditional",
        (
            "Males can be separated when the abdominal tip is sharp. Females and "
            "blurred photographs should remain Nehalennia sp."
        ),
        (
            _difference(
                "Male abdominal tip",
                "Blue is confined to a smaller area at the tip, with more dark color on the final segments.",
                "Blue covers more of the abdominal tip.",
            ),
            _difference(
                "Habitat support",
                "Occurs broadly in sedge marshes, pond edges, and fens.",
                "Strongly associated with sphagnum bogs and fens; habitat supports but does not replace the abdominal character.",
            ),
        ),
        "Nehalennia sp.",
        (WISCONSIN_ODONATA,),
    ),
    _pair(
        "Lestes congener",
        "Lestes rectangularis",
        "conditional",
        (
            "Thoracic pattern can suggest the species, but a firm identification "
            "requires a sharp terminal-appendage or ovipositor view. Otherwise report Lestes sp."
        ),
        (
            _difference(
                "Lower thorax",
                "Both sexes have distinct dark spots low on the pale side of the thorax.",
                "The lower thorax lacks the paired dark spots and is comparatively plain.",
            ),
            _difference(
                "Build",
                "Shorter and more robust, especially the female.",
                "Exceptionally long and slender, with a rectangular, elongated appearance.",
            ),
        ),
        "Lestes sp.",
        (WISCONSIN_ODONATA,),
    ),
    _pair(
        "Lestes congener",
        "Lestes vigilax",
        "not_field",
        (
            "Pruinosity and body color overlap, especially with age. A firm species "
            "identification requires male terminal appendages or a female ovipositor "
            "view under magnification; otherwise report Lestes sp."
        ),
        report_as="Lestes sp.",
        sources=(WISCONSIN_ODONATA,),
    ),
    _pair(
        "Arigomphus villosipes",
        "Arigomphus furcifer",
        "conditional",
        (
            "Body pattern can suggest the species, but a firm identification requires "
            "a sharp male appendage or female vulvar-lamina view. Otherwise report Arigomphus sp."
        ),
        (
            _difference(
                "Abdominal club",
                "The club is broad and mostly dark above, with small pale dorsal marks.",
                "The club carries longer forked pale markings and appears more extensively yellow.",
            ),
            _difference(
                "Thorax",
                "Greenish-yellow side stripes are relatively narrow against dark brown.",
                "Paler yellow-green areas are broader and create a brighter thorax.",
            ),
        ),
        "Arigomphus sp.",
        (WISCONSIN_ODONATA,),
    ),
    # Expanded confusion coverage for targets present in the August field set.
    _pair(
        "Catocala cara",
        "Catocala amatrix",
        "conditional",
        (
            "Require a fresh square forewing view and an opened hindwing. The two "
            "large pink-red underwings can occur together; a resting or worn image "
            "should remain Catocala sp."
        ),
        (
            _difference(
                "Forewing ground pattern",
                "Strongly two-toned, with a broad dark chocolate-brown median field contrasting with paler outer areas.",
                "More evenly tan-gray and mottled, with diffuse black basal, apical, and anal dashes rather than one broad dark median field.",
            ),
            _difference(
                "Hindwing support",
                "Deep scarlet-pink with two clean black bands; use this with the forewing rather than as a stand-alone mark.",
                "Orange-red with black median and marginal bands; the shared bright hindwing color is why forewing pattern is essential.",
            ),
        ),
        "Catocala sp.",
        (BUGGUIDE, "https://auth1.dpr.ncparks.gov/moths/view.php?MONA_number=8832"),
    ),
    _pair(
        "Thyris maculata",
        "Pseudothyris sepulchralis",
        "field",
        "A sharp dorsal macro showing the translucent windows and orange scaling normally separates these day-flying moths.",
        (
            _difference(
                "Wing windows",
                "One round translucent whitish window marks each forewing, with two close windows on each hindwing.",
                "More numerous white or translucent spots cross the wings rather than the one-plus-two window pattern.",
            ),
            _difference(
                "Orange scaling",
                "Small but visible orange spots occur on the otherwise blackish wings.",
                "The wings are black and white without the same orange spotting.",
            ),
        ),
        sources=("https://bugguide.net/node/view/4988",),
    ),
    _pair(
        "Eumorpha pandorus",
        "Eumorpha achemon",
        "field",
        "A fresh dorsal view showing both forewings and one opened hindwing normally supports a species identification.",
        (
            _difference(
                "Forewing color",
                "Olive green with darker green angular patches, including a long dark basal patch along the inner margin.",
                "Tan to pinkish brown with sharply defined warm-brown geometric patches and no overall green ground color.",
            ),
            _difference(
                "Hindwing",
                "Dark olive with rosy-brown or pink restricted near the inner margin.",
                "Extensively bright pink from the base to a broken dark submarginal band.",
            ),
        ),
        sources=(ILLINOIS_SPHINX_GUIDE,),
    ),
    _pair(
        "Oreta rosea",
        "Patalene olyzonaria",
        "conditional",
        (
            "The usual pink-and-yellow Rose Hooktip is distinctive. Use this pair for "
            "the all-brown Rose Hooktip form, and retain Geometridae/Drepanidae when "
            "the wing tip or hindwing line is hidden."
        ),
        (
            _difference(
                "Hindwing postmedial line",
                "Wavy or irregular across the hindwing.",
                "Straight across the hindwing.",
            ),
            _difference(
                "Forewing tip and discal spot",
                "Hooked forewing tip; the brown form lacks the Juniper Geometer's black costal discal spot.",
                "A black discal spot sits near the forewing costa, accompanying the straighter line pattern.",
            ),
        ),
        "Drepanidae or Geometridae",
        ("https://bugguide.net/node/view/3668", "https://bugguide.net/node/view/8338"),
    ),
    _pair(
        "Hypena bijugalis",
        "Hypena scabra",
        "not_field",
        (
            "Dimorphic Hypena changes strongly with sex, and worn snout moths overlap "
            "in routine sheet photographs. Report Hypena sp. unless a specialist "
            "confirms a fresh, square adult showing the complete wing pattern."
        ),
        report_as="Hypena sp.",
        sources=(BUGGUIDE,),
    ),
    _pair(
        "Catocala retecta",
        "Catocala luctuosa",
        "not_field",
        (
            "Yellow-gray and Hulst's Underwings are essentially indistinguishable by "
            "photograph or external appearance. Report the Catocala retecta-luctuosa "
            "pair unless specimen or other specialist evidence resolves it."
        ),
        report_as="Catocala retecta-luctuosa pair",
        sources=("https://bugguide.net/node/view/40032",),
    ),
    _pair(
        "Xanthorhoe labradorensis",
        "Xanthorhoe ferrugata",
        "not_field",
        (
            "Carpet moth bands vary with wear and several Xanthorhoe overlap in ordinary "
            "photographs. Report Xanthorhoe sp. unless a specialist confirms a sharp, "
            "unworn dorsal view or specimen-level characters."
        ),
        report_as="Xanthorhoe sp.",
        sources=(BUGGUIDE,),
    ),
    _pair(
        "Amorpha juglandis",
        "Ceratomia undulosa",
        "field",
        "A complete dorsal view normally separates these large gray sphinx moths.",
        (
            _difference(
                "Wing edge and shape",
                "All wing margins are scalloped to wavy, producing a compact, soft-edged outline.",
                "Longer triangular forewings have a comparatively smooth outer edge and pointed apex.",
            ),
            _difference(
                "Line pattern",
                "Mottling may be faint or strong but lacks a stack of crisp black wavy transverse lines.",
                "Several dark wavy lines cross the pale gray forewing and remain the dominant pattern.",
            ),
        ),
        sources=("https://bugguide.net/node/view/4144", BUGGUIDE),
    ),
    _pair(
        "Clemensia umbrata",
        "Clemensia albata",
        "conditional",
        (
            "Use the larger, darker phenotype only on a fresh moth with date and "
            "location context. Worn adults in the Northeast can overlap and should "
            "remain Clemensia sp. without specialist review."
        ),
        (
            _difference(
                "Forewing contrast",
                "Usually more suffused with gray and black, often with a diffuse dark gray postmedial patch near the anal margin.",
                "Usually paler and less contrasting; the dark anal-margin postmedial patch is absent or much more restricted.",
            ),
            _difference(
                "Size and flight support",
                "Averages larger where the species overlap and is mainly univoltine in July to early August.",
                "Averages smaller and has northeastern flight peaks around mid-June and late August, though the flights overlap.",
            ),
        ),
        "Clemensia sp.",
        (CLEMENSIA_REVISION,),
    ),
    _pair(
        "Euphydryas phaeton",
        "Phyciodes tharos",
        "field",
        "Size and the complete dorsal pattern normally separate fresh adults.",
        (
            _difference(
                "Size and ground color",
                "A much larger, mostly black checkerspot with bold cream-white and orange-red spot rows.",
                "A small orange crescent crossed by a fine black network, without the broad black field.",
            ),
            _difference(
                "Marginal spots",
                "Red-orange crescents and pale spots form conspicuous rows along all four wing margins.",
                "Orange dominates the wings and the marginal marks are smaller black-and-orange crescents.",
            ),
        ),
        sources=(BAMONA, MASS_AUDUBON_BUTTERFLIES),
    ),
    _pair(
        "Ancyloxypha numitor",
        "Thymelicus lineola",
        "field",
        "A sharp dorsal view normally separates fresh adults; keep a distant or worn orange skipper at Hesperiinae.",
        (
            _difference(
                "Upper-wing pattern",
                "The forewings are largely blackish, while the orange hindwings have conspicuously wide black borders.",
                "The wings look orange overall, crossed by black veins and edged by comparatively narrow black borders.",
            ),
            _difference(
                "Closed-wing underside",
                "The underwing is a relatively uniform mustard yellow, on a smaller, narrow-winged skipper.",
                "The hindwing is orange with gray-green suffusion instead of one uniform mustard-yellow field.",
            ),
        ),
        sources=(
            f"{MASS_AUDUBON_BUTTERFLIES}?id=175",
            f"{MASS_AUDUBON_BUTTERFLIES}?id=84",
        ),
    ),
    _pair(
        "Thymelicus lineola",
        "Polites themistocles",
        "conditional",
        "Require a head-on antenna view plus the upper forewing; a distant orange skipper should remain Hesperiinae.",
        (
            _difference(
                "Antenna club",
                "The forward-facing underside of the club tip is distinctly black.",
                "The club lacks the same clean black underside and reads tawny to dark brown with the rest of the antenna.",
            ),
            _difference(
                "Upper wing",
                "Small and broadly orange with a short, fine male stigma and relatively even narrow dark border.",
                "Mostly dark brown, with orange concentrated along the leading edge that gives the species its tawny-edged look.",
            ),
        ),
        "grass skipper",
        (MASS_AUDUBON_BUTTERFLIES,),
    ),
    _pair(
        "Limochores mystic",
        "Hesperia sassacus",
        "conditional",
        "Both wing surfaces are needed; worn or closed-wing grass skippers should remain Hesperiinae.",
        (
            _difference(
                "Male forewing dash",
                "The stigma joins or nearly joins another dark mark to make a long, broad dash toward the wing margin.",
                "The upper forewing lacks that long contiguous dash and usually has two small pale apical spots.",
            ),
            _difference(
                "Hindwing underside spots",
                "The pale spot row follows the curve of the outer wing, with an additional pale basal spot.",
                "The middle spots angle outward toward the wing margin instead of following one even curve.",
            ),
        ),
        "grass skipper",
        (MASS_AUDUBON_BUTTERFLIES,),
    ),
    _pair(
        "Aglais milberti",
        "Nymphalis antiopa",
        "field",
        "A clear upper-side view normally separates these dark anglewing butterflies.",
        (
            _difference(
                "Outer band",
                "A broad fiery orange band crosses the outer half of all four dark wings, with blue spots near the margin.",
                "A continuous pale yellow border rims a maroon-black wing, with blue spots just inside it and no broad orange band.",
            ),
            _difference(
                "Wing shape",
                "Smaller, with more sharply angular forewing tips and a compact tortoiseshell outline.",
                "Larger and broad-winged, with the pale border emphasizing a smoother outer outline.",
            ),
        ),
        sources=(MASS_AUDUBON_BUTTERFLIES,),
    ),
    _pair(
        "Lethe eurydice",
        "Lethe appalachia",
        "conditional",
        "Require a sharp hindwing underside; habitat supports the pattern but cannot replace it.",
        (
            _difference(
                "Ventral hindwing medial line",
                "The brown line bends in a conspicuous zigzag.",
                "The corresponding line forms a smoother, more even curve.",
            ),
            _difference(
                "Typical habitat",
                "Most often in open, sunny wet sedge meadows.",
                "Most often in shaded swampy woods and wooded sedge wetlands.",
            ),
        ),
        "Lethe eurydice-appalachia pair",
        (OHIO_BUTTERFLY_GUIDE,),
    ),
    _pair(
        "Papilio canadensis",
        "Papilio glaucus",
        "conditional",
        "Use the two underside bands together. Their ranges and characters overlap, so an incomplete dorsal photograph should remain in the Papilio glaucus complex.",
        (
            _difference(
                "Ventral forewing pale band",
                "Usually the most continuous and even-edged band, with pale lunules not strongly divided by black veins.",
                "Usually separate pale lunules divided by black along the veins, although some lunules coalesce.",
            ),
            _difference(
                "Ventral hindwing anal band",
                "The black strip at the hairy anal edge is usually the thickest of the tiger-swallowtail complex.",
                "The same black strip is usually the thinnest, with a more scalloped pale boundary.",
            ),
        ),
        "Papilio glaucus complex",
        (TIGER_SWALLOWTAIL_PAPER,),
    ),
    _pair(
        "Papilio canadensis",
        "Papilio solstitius",
        "conditional",
        "No single stripe decides this pair. Require both ventral band characters and flight context; otherwise report the Papilio glaucus complex.",
        (
            _difference(
                "Ventral forewing pale band",
                "Usually continuous with a relatively even inner edge.",
                "Pale lunules are broadly joined but usually form a more scalloped inner edge.",
            ),
            _difference(
                "Ventral hindwing anal band",
                "Usually the broadest black strip, often filling more than half of the cell.",
                "Usually intermediate in width between Canadian and Eastern, but overlaps both.",
            ),
        ),
        "Papilio glaucus complex",
        (TIGER_SWALLOWTAIL_PAPER,),
    ),
    _pair(
        "Lycaena hypophlaeas",
        "Tharsalea hyllus",
        "field",
        "A complete underside plus apparent size normally separates these coppers.",
        (
            _difference(
                "Size",
                "Tiny, usually about one inch across.",
                "Noticeably larger and more robust, roughly one and a quarter to one and three-quarter inches across.",
            ),
            _difference(
                "Ventral hindwing orange band",
                "A thin orange line runs near the hindwing margin.",
                "A broad orange band fills much more of the hindwing margin.",
            ),
        ),
        sources=("https://mdc.mo.gov/discover-nature/field-guide/bronze-copper",),
    ),
    _pair(
        "Argynnis atlantis",
        "Argynnis cybele",
        "conditional",
        "Use size, live eye color, and both wing surfaces together; a worn fritillary without those views should remain Argynnis sp.",
        (
            _difference(
                "Size and ventral pale band",
                "Usually the smaller species, with a narrow or absent pale submarginal band below the hindwing.",
                "Usually the largest of the three eastern greater fritillaries, with a broad pale submarginal band below the hindwing.",
            ),
            _difference(
                "Live eye and upper border",
                "Eyes are blue-gray and the upper wing border is extensively black.",
                "Eyes are amber-brown; the upper border is generally less solidly black, especially outside worn females.",
            ),
        ),
        "Argynnis sp.",
        (MASS_AUDUBON_BUTTERFLIES,),
    ),
    _pair(
        "Argynnis atlantis",
        "Argynnis aphrodite",
        "conditional",
        "Eye color must be observed on the living butterfly and paired with both wing surfaces; ambiguous adults should remain Argynnis sp.",
        (
            _difference(
                "Live eye color",
                "Blue-gray eyes.",
                "Amber to brown eyes; preserved specimens lose this distinction.",
            ),
            _difference(
                "Color and upper border",
                "Darker purplish-brown at the base of the hindwing underside, with a heavy black border above.",
                "Oranger at the base of the hindwing underside, with more orange scaling through the upper wing border.",
            ),
        ),
        "Argynnis sp.",
        ("https://accdc.com/mba/profiles/speyeria-aphrodite.html",),
    ),
    _pair(
        "Pieris virginiensis",
        "Pieris rapae",
        "field",
        "A sharp view of the forewing tip and underside normally separates fresh spring adults.",
        (
            _difference(
                "Forewing upper side",
                "Translucent white with little or no dark tip patch and no bold round black spot.",
                "Opaque white with a dark gray-black forewing tip and one or two conspicuous round black spots.",
            ),
            _difference(
                "Hindwing underside",
                "Whitish without a yellow wash, often with hazy gray-brown scaling along the veins.",
                "Usually yellowish to gray-yellow, without the same translucent woodland-white appearance.",
            ),
        ),
        sources=("https://www.butterfliesandmoths.org/species/Pieris-virginiensis",),
    ),
    _pair(
        "Pieris virginiensis",
        "Pieris oleracea",
        "conditional",
        "Native spring whites can overlap. Require a fresh underside and habitat context; otherwise report Pieris sp.",
        (
            _difference(
                "Hindwing underside",
                "Translucent whitish with no yellow tint; gray-brown vein scaling may look hazy rather than green.",
                "Spring adults usually have a yellowish underside with the veins outlined in gray-green; later adults can be much paler.",
            ),
            _difference(
                "Habitat support",
                "Strongly tied to intact spring woodland with toothworts.",
                "Occurs in a wider range of cool moist openings and woodland edges; habitat alone is not diagnostic.",
            ),
        ),
        "Pieris sp.",
        (BAMONA,),
    ),
    _pair(
        "Ladona julia",
        "Plathemis lydia",
        "field",
        "A clear dorsal view normally separates mature adults and most immatures.",
        (
            _difference(
                "Wings",
                "All four wings are clear, without broad black bands.",
                "Broad dark bands cross the wings; mature males develop white patches beyond them.",
            ),
            _difference(
                "Pruinosity",
                "Wide pale shoulder bars top the thorax, and white or gray covers only the basal half of the abdomen.",
                "Mature males have a powdery white abdomen but lack the corporal's paired chalky shoulder bars.",
            ),
        ),
        sources=(WISCONSIN_ODONATA,),
    ),
    _pair(
        "Hetaerina americana",
        "Calopteryx maculata",
        "field",
        "Wing pigmentation and body pattern normally separate these broad-winged damselflies.",
        (
            _difference(
                "Male wings",
                "Mostly clear with a large ruby-red patch confined to the wing bases.",
                "Nearly the entire wing is opaque black, without a clear outer field beyond a red basal patch.",
            ),
            _difference(
                "Female wings",
                "Amber is concentrated at the base and leading edge, with tiny white stigmas near the tips.",
                "Broad wings are evenly smoky brown; white stigmas contrast against the darker full-wing tint.",
            ),
        ),
        sources=(WISCONSIN_ODONATA,),
    ),
    _pair(
        "Phanogomphus exilis",
        "Phanogomphus lividus",
        "not_field",
        (
            "Clubtail body pattern varies with sex and maturity. Report Phanogomphus "
            "sp. unless a diagnostic close-up shows male terminal appendages or the "
            "female vulvar lamina in addition to the thoracic and leg pattern."
        ),
        report_as="Phanogomphus sp.",
        sources=(WISCONSIN_ODONATA,),
    ),
    _pair(
        "Leucorrhinia glacialis",
        "Leucorrhinia proxima",
        "conditional",
        "Mature males are usually separable in dorsal and side views; females and immature adults may require genital or wing-venation detail.",
        (
            _difference(
                "Mature male abdomen",
                "Black with red markings but no white abdominal belt.",
                "A conspicuous white-pruinose belt crosses the base of the otherwise dark abdomen.",
            ),
            _difference(
                "Thorax and waist",
                "Red rings or patches mark the dark thorax and waist.",
                "Red or yellow can occur on the thorax, but pale pruinosity at the abdominal base creates the belted effect.",
            ),
        ),
        "Leucorrhinia sp.",
        (WISCONSIN_ODONATA,),
    ),
    _pair(
        "Lestes eurinus",
        "Lestes inaequalis",
        "conditional",
        "Fresh adults can be separated by build and thoracic pattern; worn or heavily pruinose spreadwings should remain Lestes sp. without terminal detail.",
        (
            _difference(
                "Build and color",
                "Stockier and less green, with a dark green to bluish thorax over pale yellow sides.",
                "Longer and more slender, with a bright metallic-green thorax and lemon-yellow sides.",
            ),
            _difference(
                "Thorax and wings",
                "A dark diagonal lateral thoracic streak is usually visible, and the wings are commonly amber washed.",
                "The dark lateral streak is absent; the wings lack the same strong amber wash.",
            ),
        ),
        "Lestes sp.",
        (WISCONSIN_ODONATA,),
    ),
)


_PAIR_BY_KEY = {
    frozenset(profile["taxa"]): profile
    for profile in PAIR_PROFILES
}


def curated_peer_names(scientific_name):
    """Return only deliberately vetted comparison taxa for one species."""
    names = []
    for profile in PAIR_PROFILES:
        if scientific_name not in profile["taxa"]:
            continue
        first, second = profile["taxa"]
        names.append(second if scientific_name == first else first)
    return names


def curated_peer_taxon(scientific_name):
    """Return fallback metadata for a vetted peer outside the regional pool."""
    record = CURATED_PEER_TAXA.get(scientific_name)
    return dict(record) if record else None


def comparison_note(scientific_name, comparison_count):
    """Explain the comparison coverage so the app never renders a silent blank."""
    if comparison_count:
        coverage = (
            "One vetted potential confusion is shown."
            if comparison_count == 1
            else f"{comparison_count} vetted potential confusions are shown."
        )
        return (
            f"{coverage} These are selected for "
            "regional plausibility or a documented identification risk; they are not "
            "an exhaustive taxonomic key."
        )
    return NO_NAMED_COMPARISON_NOTES.get(
        scientific_name,
        (
            "No named confusion species is vetted for this target yet. Use the "
            "identification traits and photo checklist above, compare the broader "
            "family, and retain a genus or family identification when evidence is incomplete."
        ),
    )


def comparison_profile(target_scientific, peer_scientific):
    """Orient a vetted pair profile from the target toward its comparison."""
    profile = _PAIR_BY_KEY.get(frozenset((target_scientific, peer_scientific)))
    if not profile or target_scientific not in profile["taxa"]:
        return None
    first, second = profile["taxa"]
    target_is_first = target_scientific == first
    differences = []
    for difference in profile["differences"]:
        differences.append({
            "feature": difference["feature"],
            "target": difference["first"] if target_is_first else difference["second"],
            "peer": difference["second"] if target_is_first else difference["first"],
        })
    return {
        "identifiability": profile["status"],
        "identifiability_label": STATUS_LABELS[profile["status"]],
        "differences": differences,
        "decision": profile["decision"],
        "report_as": profile["report_as"],
        "sources": list(profile["sources"]),
    }
