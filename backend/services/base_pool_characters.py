"""Authored appearances for the shipped base-art pool.

WHY THESE ARE WRITTEN OUT RATHER THAN ROLLED

The runtime uses two appearance sources. A player with an API key gets one
written by Claude per hero (llm_service.generate_hero_profile), which is already
instructed to vary ethnicity, age, body type and hair and to make every hero look
completely different — that path was never the problem. Everyone else falls back
to combinatorial rolls from trait lists, and lists have a ceiling: with six hair
styles, six skins and six features you can roll two heroes that read as the same
person, and you will, often.

The shipped pool is generated ONCE, offline, so it doesn't have to roll anything.
Each character below is written deliberately to be unlike the others: ages from
teenage to elderly, real range in build, weight and ethnicity, facial hair on the
men (the trait lists had NONE, which is most of why every man looked identical),
and hair chosen for SILHOUETTE — shaved, braided, waist-length, tonsured — not
for adjective. "Short messy" and "slicked back" draw the same head.

Each entry describes the PERSON AND THEIR CLOTHING completely. The generator does
not append CLASS_OUTFITS on top, so what is written here is what gets drawn.

Format: (class, gender, description). Two per class per gender, and the class
must exist in portrait_cache.CLASS_OUTFITS or the pool filename won't parse.
"""

CHARACTERS = [
    # ── Acolyte ────────────────────────────────────────────────────────────
    ("Acolyte", "male", "a gaunt elderly man with a shaved tonsured head and a long white beard, deeply lined dark brown skin, milky blind left eye, coarse undyed wool robes and a rope belt, wooden prayer beads"),
    ("Acolyte", "male", "a stocky young East Asian man with a thick black topknot and no facial hair, warm tan skin, a burn scar across one forearm, layered grey-blue temple robes with a red sash"),
    ("Acolyte", "female", "a tall dark-skinned woman in her forties with tightly coiled black hair in a crown braid, broad shoulders, a small silver nose ring, plain cream robes with an indigo mantle"),
    ("Acolyte", "female", "a very young pale girl with cropped ginger hair and heavy freckles, thin and slight, ink-stained fingers, oversized brown novice robes that don't fit her"),

    # ── Alchemist ──────────────────────────────────────────────────────────
    ("Alchemist", "male", "a heavyset middle-aged man with a bald head and an enormous braided ginger beard, ruddy pale skin, thick round smoked goggles pushed up on his forehead, a scorched leather apron over rolled shirtsleeves"),
    ("Alchemist", "male", "a wiry older South Asian man with long grey hair loose to the shoulders and a trimmed white moustache, deep brown skin, acid-pitted hands, a many-pocketed dark green coat"),
    ("Alchemist", "female", "a young Black woman with short bleached-blonde curls against dark skin, a chemical burn scar down one cheek, slim build, a stained canvas apron over a high-collared blouse"),
    ("Alchemist", "female", "a plump pale woman in her fifties with silver hair in a messy bun and thin wire spectacles, laugh lines, a violet shawl over a practical brown workdress"),

    # ── Archer ─────────────────────────────────────────────────────────────
    ("Archer", "male", "a lean elderly hunter with a shaved head and a short white beard, weather-beaten olive skin, a leather eyepatch over the left eye, a worn green hooded cloak and a bracer on the draw arm"),
    ("Archer", "male", "a broad-shouldered dark-skinned man in his thirties with short tight curls and a full beard, a tattoo across the throat, a sleeveless brown jerkin showing heavily muscled arms, quiver at the hip"),
    ("Archer", "female", "a small wiry woman with a shaved undercut and a long black ponytail, golden-brown skin, a hare-lip scar, close-fitting grey scout leathers and a half-cape"),
    ("Archer", "female", "a tall red-haired woman in her forties with a thick single braid to the waist, pale freckled skin, crow's feet, a fur-collared olive coat over a padded gambeson"),

    # ── Berserker ──────────────────────────────────────────────────────────
    ("Berserker", "male", "a colossal bald man with a vast forked black beard and blue spiral tattoos across his scalp and chest, pale scarred skin, bare-chested under a wolf pelt, iron arm rings"),
    ("Berserker", "male", "a lean older man with long grey hair matted into thick locks and a scarred jaw, dark bronze skin, missing two fingers on the left hand, ragged furs and a bare torso wrapped in old bandages"),
    ("Berserker", "female", "a towering muscular woman with a shaved head and painted red war-stripes across dark brown skin, a broken nose, a leather harness and torn breeches, heavy scarring on both arms"),
    ("Berserker", "female", "a stocky pale woman in her thirties with wild copper hair half-shaved on one side, freckles and a split eyebrow, a fur-trimmed sleeveless hauberk, knuckles wrapped in cord"),

    # ── Blacksmith ─────────────────────────────────────────────────────────
    ("Blacksmith", "male", "an immense older man with a soot-blackened bald head and a singed grey beard, thick arms, deep brown skin, a heavy scarred leather apron over a bare chest, tongs at the belt"),
    ("Blacksmith", "male", "a compact young man with short black hair and a wispy first moustache, tan skin, burn speckles up both forearms, a canvas apron over a sweat-soaked undershirt"),
    ("Blacksmith", "female", "a broad muscular woman in her forties with her black hair bound in a tight headwrap, deep brown skin shining with heat, a hammer scar across the chin, a split-leather apron and heavy gloves"),
    ("Blacksmith", "female", "a short heavyset pale woman with cropped white-blonde hair and thick forearms, safety goggles on a cord, a stained apron over a rolled-sleeve tunic"),

    # ── Chef ───────────────────────────────────────────────────────────────
    ("Chef", "male", "a rotund middle-aged man with a magnificent waxed black moustache and a bald crown, olive skin, flour on his sleeves, a double-breasted white coat and a knotted neckerchief"),
    ("Chef", "male", "a lanky young West African man with short twists and a neat goatee, deep brown skin, a knife scar across one knuckle, a plain apron over a rolled-up linen shirt"),
    ("Chef", "female", "an elderly woman with thin white hair under a linen cap, stooped, pale and heavily wrinkled, a wooden spoon tucked in her belt, a much-mended apron over grey skirts"),
    ("Chef", "female", "a tall broad Polynesian woman with a black bun and a facial tattoo along the jaw, warm brown skin, forearms burn-marked, a crisp white coat with sleeves pushed up"),

    # ── Classless ──────────────────────────────────────────────────────────
    ("Classless", "male", "a thin ragged teenage boy with unevenly chopped brown hair, pale dirt-smudged skin, a chipped front tooth, mismatched hand-me-down clothes and no shoes"),
    ("Classless", "male", "a grizzled one-armed old man with a shaved head and heavy stubble, sun-darkened skin, an empty sleeve pinned up, a patched travelling coat and a walking staff"),
    ("Classless", "female", "a middle-aged woman with greying black hair in a practical knot, tired eyes, brown skin, a threadbare shawl over a much-repaired dress, hands rough from work"),
    ("Classless", "female", "a slight young albino woman with long white hair and pale pink eyes, wrapped against the light in layered grey cloth, bare feet, a hesitant posture"),

    # ── Farmer ─────────────────────────────────────────────────────────────
    ("Farmer", "male", "a sun-blackened old man with a wide straw hat over white hair and a long thin beard, deeply weathered brown skin, a hoe over one shoulder, faded blue work clothes"),
    ("Farmer", "male", "a huge slow-moving young man with a bowl-cut of straw-blond hair and a soft round face, sunburnt pale skin, patched overalls and enormous mud-caked boots"),
    ("Farmer", "female", "a wiry old woman with silver hair in a kerchief, deeply lined olive skin, forearms like rope, a canvas seed-apron over a heavy skirt"),
    ("Farmer", "female", "a tall dark-skinned woman in her thirties with short natural hair and a scar across one eyebrow, sleeves rolled past the elbow, a leather yoke and work gloves"),

    # ── Knight ─────────────────────────────────────────────────────────────
    ("Knight", "male", "an aging knight with close-cropped iron-grey hair and a full square beard, pale scarred skin, a ruined left ear, dented steel plate over a faded surcoat"),
    ("Knight", "male", "a young dark-skinned knight with a shaved head and a thin chinstrap beard, polished half-plate over a mail hauberk, a crisp white tabard, gauntlets tucked under one arm"),
    ("Knight", "female", "a tall broad woman with a long blonde braid pinned across the crown, pale freckled skin, a nose broken and reset, well-used plate armour and a heavy riding cloak"),
    ("Knight", "female", "a compact East Asian woman in her forties with black hair in a tight bun, a burn scar along the neck, lacquered scale armour over a deep red underlayer"),

    # ── Mage ───────────────────────────────────────────────────────────────
    ("Mage", "male", "a skeletal ancient man with waist-length white hair and a long forked beard, translucent pale skin, sunken eyes, layered midnight-blue robes hung with charms"),
    ("Mage", "male", "a heavyset young man with short curly black hair and a neat beard, deep brown skin, ink sigils tattooed across both hands, embroidered violet robes worn loose"),
    ("Mage", "female", "a severe middle-aged woman with straight black hair cut sharp at the jaw, olive skin, a thin scar bisecting one eyebrow, high-collared charcoal robes with silver clasps"),
    ("Mage", "female", "an elderly stooped woman with wispy grey hair escaping a hood, pale spotted skin, cataract-clouded eyes, threadbare star-patterned robes and a gnarled staff"),

    # ── Magic Engineer ─────────────────────────────────────────────────────
    ("Magic Engineer", "male", "a middle-aged man with wild grey-streaked hair and a soot-stained beard, tan skin, one brass mechanical eye, a tool-hung leather harness over a scorched coat"),
    ("Magic Engineer", "male", "a slim young Black man with short locs tied back and no facial hair, dark skin, a prosthetic left hand of articulated brass, a many-pocketed canvas coat"),
    ("Magic Engineer", "female", "a small older woman with white hair under a leather cap, magnifying lenses on a hinged frame, pale skin, oil-stained fingers, a padded workshop coat"),
    ("Magic Engineer", "female", "a tall South Asian woman in her thirties with a thick black plait and a burn scar across one cheek, deep brown skin, a tool bandolier over rolled shirtsleeves"),

    # ── Medic ──────────────────────────────────────────────────────────────
    ("Medic", "male", "a calm older man with a bald crown and a close white beard, dark brown skin, wire spectacles, a blood-flecked apron over a plain grey tunic, a satchel of instruments"),
    ("Medic", "male", "a gaunt young man with lank black hair tied back and hollow cheeks, pale skin, exhausted eyes, rolled sleeves and stained linen bandage-wraps up both arms"),
    ("Medic", "female", "a broad matronly woman with grey hair in a bun under a linen cap, ruddy pale skin, forearms strong from lifting, a crisp apron over practical dark skirts"),
    ("Medic", "female", "a young Middle Eastern woman with a dark headscarf and sharp brows, olive skin, a small scar on the chin, a clean white overrobe and a leather instrument roll"),

    # ── Merchant ───────────────────────────────────────────────────────────
    ("Merchant", "male", "a fat prosperous man in his fifties with a shining bald head and an oiled black moustache, olive skin, heavy gold rings, a fur-trimmed brocade coat"),
    ("Merchant", "male", "a lean weathered older man with long grey hair tied at the nape and a wispy beard, sun-darkened skin, a missing eye tooth, a dusty travelling coat hung with pouches"),
    ("Merchant", "female", "a sharp-eyed woman in her forties with black hair in an elaborate coil, tan skin, a jade ear ornament, layered silk robes in ochre and green, an abacus at her belt"),
    ("Merchant", "female", "a young plump Black woman with braided hair wrapped in bright cloth, deep brown skin, a broad gap-toothed smile, a patterned wrap dress and a heavy coin purse"),

    # ── Paladin ────────────────────────────────────────────────────────────
    ("Paladin", "male", "a towering older paladin with a shaved head and a full iron-grey beard, pale scarred skin, a cracked nose, heavy gilded plate over a white surcoat"),
    ("Paladin", "male", "a young dark-skinned paladin with short curls and no beard, an old brand scar on the cheek, polished silver plate with a sunburst emblem and a deep blue cloak"),
    ("Paladin", "female", "a broad-shouldered woman with a blonde crown braid and pale freckled skin, a jaw scar, ornate white-and-gold plate over chainmail, a tabard bearing a star"),
    ("Paladin", "female", "a slender East Asian woman in her fifties with grey-streaked black hair in a tight knot, weathered skin, worn but immaculate plate and a much-mended cloak"),

    # ── Priest ─────────────────────────────────────────────────────────────
    ("Priest", "male", "an ancient priest with a tonsured ring of white hair and a long thin beard, translucent pale skin, stooped over a staff, heavy ceremonial vestments in bone and gold"),
    ("Priest", "male", "a broad middle-aged man with a full black beard and a shaved head, deep brown skin, a heavy pectoral symbol, layered dark green and cream vestments"),
    ("Priest", "female", "a stern woman in her sixties with white hair beneath a stiff wimple, pale lined skin, thin lips, austere black-and-silver vestments"),
    ("Priest", "female", "a young dark-skinned woman with a shaved head and gold ear cuffs, smooth features, embroidered white vestments with a deep crimson stole"),

    # ── Quartermaster ──────────────────────────────────────────────────────
    ("Quartermaster", "male", "a squat barrel-chested older man with a bristling grey moustache and a bald pate, ruddy skin, a ledger under one arm, a padded coat hung with keys"),
    ("Quartermaster", "male", "a tall thin young man with sandy hair in a short ponytail and light stubble, pale skin, a tally-stick behind one ear, a plain uniform coat with rolled cuffs"),
    ("Quartermaster", "female", "a stout no-nonsense woman in her fifties with iron-grey hair in a tight bun, olive skin, a heavy ring of keys at the belt, a sturdy quilted coat"),
    ("Quartermaster", "female", "a tall Black woman with close-cropped hair and a scar across the bridge of the nose, dark skin, a leather satchel of manifests, a fitted supply-corps jacket"),

    # ── Scout ──────────────────────────────────────────────────────────────
    ("Scout", "male", "a wiry old tracker with long grey hair in a single braid and a thin white beard, sun-leathered brown skin, a milky scar over one eye, mottled travelling leathers"),
    ("Scout", "male", "a slight teenage boy with a shaggy black bowl of hair and no facial hair, tan skin, a chipped tooth, oversized hooded cloak and soft-soled boots"),
    ("Scout", "female", "a lean woman in her thirties with a shaved undercut and a dark topknot, golden-brown skin, a thin scar from ear to jaw, close-fitting grey-green leathers"),
    ("Scout", "female", "a small older woman with white hair cropped short, pale weathered skin, deep crow's feet, a mottled cloak and a coil of rope over one shoulder"),

    # ── Spearman ───────────────────────────────────────────────────────────
    ("Spearman", "male", "a tall veteran with an iron-grey topknot and a heavy drooping moustache, tan scarred skin, a missing left ear, lamellar armour over a faded red underrobe"),
    ("Spearman", "male", "a broad young dark-skinned man with short curls and a chinstrap beard, a spear callus on the palm, studded brigandine over a padded jack"),
    ("Spearman", "female", "a tall rangy woman with a long black plait and olive skin, an old puncture scar at the shoulder, light scale armour and a half-cape"),
    ("Spearman", "female", "a stocky pale woman in her forties with cropped blonde hair and a broken nose, a shield strap across the chest, mail over a quilted gambeson"),

    # ── Spellsword ─────────────────────────────────────────────────────────
    ("Spellsword", "male", "a scarred older man with close-cropped silver hair and a short beard, pale skin, faintly glowing sigil tattoos up the neck, half-plate over dark robes"),
    ("Spellsword", "male", "a lean young South Asian man with long black hair tied high and no beard, deep brown skin, rune-etched vambraces, a split robe over light armour"),
    ("Spellsword", "female", "a tall dark-skinned woman with a shaved head and gold temple markings, a burn scar along one forearm, layered plate and violet cloth"),
    ("Spellsword", "female", "a compact woman in her thirties with a red bob cut and pale freckled skin, a thin scar across the lips, sigil-stitched leathers under a short mantle"),

    # ── Tactician ──────────────────────────────────────────────────────────
    ("Tactician", "male", "an elderly strategist with thin white hair and a long wispy beard, stooped, pale spotted skin, wire spectacles, a fur-lined scholar's coat over layered robes"),
    ("Tactician", "male", "a sharp-featured middle-aged Black man with greying temples and a neat beard, dark skin, a campaign map tube slung across the back, a fitted officer's coat"),
    ("Tactician", "female", "a severe young woman with black hair scraped into a tight knot, pale skin, a monocle on a chain, a high-collared charcoal coat with brass buttons"),
    ("Tactician", "female", "a heavyset older woman with grey curls and warm brown skin, reading glasses pushed up, an ink-stained sleeve, a quilted campaign coat"),

    # ── Thief ──────────────────────────────────────────────────────────────
    ("Thief", "male", "a rangy older man with lank greying hair over one eye and heavy stubble, sallow pale skin, two fingers missing, a dark patched coat with too many pockets"),
    ("Thief", "male", "a small quick teenage boy with a shaved head and a broken nose, tan skin, a rope burn around one wrist, close-fitting dark clothes and soft boots"),
    ("Thief", "female", "a slight woman with a black pixie cut and sharp features, olive skin, a silver eyebrow ring, a fitted dark jerkin with hidden sheaths"),
    ("Thief", "female", "a tall Black woman in her forties with tight braids pulled back, dark skin, a knife scar across the throat, a hooded charcoal coat and gloves"),

    # ── Warrior ────────────────────────────────────────────────────────────
    ("Warrior", "male", "a massive older warrior with a bald scarred scalp and a thick greying beard, pale skin, a blinded right eye, battered mail over a wolfskin"),
    ("Warrior", "male", "a young Black man with short curls and a fresh chin scar, powerfully built, dark skin, a bare-armed brigandine and heavy bracers"),
    ("Warrior", "female", "a heavyset woman with a long red braid and pale freckled skin, forearms thick with muscle, a dented breastplate over a padded jack"),
    ("Warrior", "female", "a lean older East Asian woman with grey-black hair in a topknot, weathered skin, a burn scar across the collarbone, worn lamellar and a short cloak"),
]


def by_class_gender():
    """{(class, gender): [desc, ...]} — build_base_pool indexes variants off this."""
    out = {}
    for klass, gender, desc in CHARACTERS:
        out.setdefault((klass, gender), []).append(desc)
    return out
