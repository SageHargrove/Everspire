// Per-player tower zones, drawn from the 64-plate library.
//
// WHY THIS IS SAFE. Zone identity is cosmetic. Enemies are chosen by FLOOR
// NUMBER (backend _enemy_pool_for_floor -> wave 1-10), never by zone slug, so
// redrawing a player's zones changes what they SEE and not one thing about what
// they fight. Combat balance is untouched by anything in this file.
//
// WHY DRAW AT ALL. There were 11 plates for 10 zones, so every player without
// generation climbed identical scenery. With 64, the chance a given zone of
// yours also appears in another player's tower is about 10/64 — roughly 16%
// instead of 100%.
//
// The draw is SEEDED and the seed is persisted. Redrawing on every load would
// make the tower feel unmoored — you would climb a different building each
// session — and would also desync the zone name shown in chat from the one on
// screen. Seed once, keep it forever.

const MANIFEST = '/images/floor_library/zones.json'
const SEED_KEY = 'toe_zone_seed'

// Zone index i covers floors i*10+1 .. i*10+10, so the bands line up with the
// backend's floor bands: 1-30 low, 31-70 mid, 71+ high.
const BAND_BY_INDEX = ['low', 'low', 'low', 'mid', 'mid', 'mid', 'mid', 'high', 'high', 'high']

// The pre-library zones. Kept as the fallback for three real cases: the fetch
// failing, a save written before the library existed, and a slug whose art has
// since been deleted. A missing plate must never break the climb.
export const LEGACY_ZONES = [
  { name: 'Overgrown Caverns', slug: 'overgrown_caverns', blurb: 'Root-choked tunnels where goblins, spiders, and wolves den.' },
  { name: 'Savage Badlands', slug: 'savage_badlands', blurb: 'Sun-cracked wastes ruled by orcs, ogres, and trolls.' },
  { name: 'Sunken Swamp', slug: 'sunken_swamp', blurb: 'Fetid mire crawling with hobgoblins, lizardmen, and gnolls.' },
  { name: 'Profane Catacombs', slug: 'profane_catacombs', blurb: 'Desecrated halls of grave scarabs, ghouls, and their jackal wardens.' },
  { name: 'Dread Peaks', slug: 'dread_peaks', blurb: 'Storm-lashed summits hunted by wyverns, manticores, and griffons.' },
  { name: 'Crystalline Labyrinth', slug: 'crystalline_depths', blurb: 'A maze of living stone — wardens, animated armor, and juggernauts keep the walls.' },
  { name: "Leviathan's Graveyard", slug: 'leviathans_graveyard', blurb: 'A drowned dark of leviathan bones — the drowned crew still keeps its watch.' },
  { name: 'Blood Lake', slug: 'blood_lake', blurb: 'Crimson waters prowled by nagas, giants, and the knights of the dead.' },
  { name: 'Abyssal Rift', slug: 'abyssal_rift', blurb: 'A wound in reality leaking imps, hellhounds, and pit fiends.' },
  { name: "Dragon's Boneyard", slug: 'dragons_boneyard', blurb: 'The final ascent — liches, dragons, and dracoliches guard the peak.' },
]

// mulberry32 — small, fast, and DETERMINISTIC across browsers. Math.random()
// cannot be used here: the same seed has to produce the same tower on every
// machine, or a player's zones would differ between their desktop and the web
// build even though it is one account.
function rng(seed) {
  let a = seed >>> 0
  const next = function () {
    a |= 0; a = (a + 0x6D2B79F5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
  // Discard the first few. mulberry32's opening output is weakly distributed,
  // and it showed: two unrelated seeds both drew the same first zone, which
  // would have made every player's floor 1-10 look alike — the exact problem
  // this file exists to solve, reintroduced at the most visible zone.
  next(); next(); next()
  return next
}

export function zoneSeed() {
  let s = localStorage.getItem(SEED_KEY)
  if (!s) {
    s = String((Math.random() * 0xffffffff) >>> 0)
    localStorage.setItem(SEED_KEY, s)
  }
  return Number(s) >>> 0
}

// Exported for the "reroll my tower" case and for tests.
export function setZoneSeed(seed) {
  localStorage.setItem(SEED_KEY, String(seed >>> 0))
}

function pickBanded(pool, band, rand, used) {
  const avail = pool.filter((z) => z.band === band && !used.has(z.slug))
  if (!avail.length) return null
  const z = avail[Math.floor(rand() * avail.length)]
  used.add(z.slug)
  return z
}

/** Ten zones for this player, or the legacy ten if the library is unusable. */
export function drawZones(manifest, seed) {
  if (!Array.isArray(manifest) || manifest.length < 10) return LEGACY_ZONES
  const rand = rng(seed)
  const used = new Set()
  const out = BAND_BY_INDEX.map((band, i) => {
    // Fall back through the bands rather than returning a hole: a library
    // short on one band should still yield ten zones.
    const z = pickBanded(manifest, band, rand, used)
      || pickBanded(manifest, 'mid', rand, used)
      || pickBanded(manifest, 'low', rand, used)
      || pickBanded(manifest, 'high', rand, used)
    return z ? { ...z, art: `/images/floor_library/${z.band}_${z.slug}.png` } : LEGACY_ZONES[i]
  })
  return out
}

export async function loadZones() {
  try {
    const res = await fetch(MANIFEST, { cache: 'force-cache' })
    if (!res.ok) throw new Error(`manifest ${res.status}`)
    return drawZones(await res.json(), zoneSeed())
  } catch (e) {
    console.warn('[zones] falling back to legacy zones:', e.message)
    return LEGACY_ZONES
  }
}
