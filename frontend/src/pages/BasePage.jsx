import React, { useState, useEffect, useRef } from 'react'
import { StackedTitle, Panel, Meter, SectionHeader } from '../components/ilm/Ilm'
import { setBgmScene } from '../audio'
import { getBase, getFacilities, buildFacility, upgradeFacility, assignFacility, removeFacility, listHeroes, configTraining, getMageTowerUpgrades, buyResearchUpgrade, craftMaterialEquipment, craftBandages, getBaseFloors, assignBaseFloor, getLegacies, getHearth, upgradeBase, getMarketCatalog, purchaseMarketItem, getBaseUpgrades, buyBaseUpgrade, getMailList, claimMail, getShip, buildShip, renameShip, refitShip, buyRefitPoint, getSupportBoons } from '../api/client'
import MirrorOfFate from '../components/MirrorOfFate'
import ItemIcon from '../components/ItemIcon'
import TeamBanner from '../components/TeamBanner'
import UpgradeTreePanel from '../components/UpgradeTreePanel'
import RecipeBookPanel from '../components/RecipeBookPanel'
import TrainingGroundsPanel from '../components/TrainingGroundsPanel'
import AthenaeumPanel from '../components/AthenaeumPanel'
import { DiamondPortrait } from '../components/HearthDrawer'
import BannerStudio from '../components/BannerStudio'
import Expeditions from '../components/Expeditions'
import { getBanner } from '../api/client'
import { CookingPanel, RefineAetherPanel, BestiaryPanel, ReliquaryPanel, ChronospherePanel, TranscendencePanel, ShrineRitePanel } from '../components/EndgamePanels'
import LoreJournal from '../components/LoreJournal'
import Memorial from '../components/Memorial'
import GameIcon from '../components/GameIcon'
import Sigil from '../components/Sigil'
import { alertDialog } from '../components/DialogHost'

// Facility type -> custom Sigil filename (UPPER_SNAKE), e.g. "Mage Tower" -> "MAGE_TOWER".
// The backend type is "Wall" but the icon set ships THE_WALL.svg; Vault and
// Transcendence Core have no icon yet, so they use the letter fallback.
const FAC_NAME_ALIAS = { Wall: 'The Wall' }
const facSig = (t) => (t ? String(FAC_NAME_ALIAS[t] || t).toUpperCase().replace(/ /g, '_') : '')
// Facility art is TIERED: /images/facilities/<slug>_t<1-4>.png (slug is the
// plain lowercase type — "Wall" art is wall_tN, unlike its THE_WALL sigil).
// Art tier steps up with facility level (max 50, so ~12-level bands), but
// late-game facilities only shipped their high tiers (a Bestiary was never a
// shack), so clamp to the nearest tier that actually has a file.
const FACILITY_ART_TIERS = {
  alchemist_lab: [1, 2, 3, 4], athenaeum: [1, 2, 3, 4], bastion: [1, 2, 3, 4], bestiary: [3],
  chronosphere: [3, 4], dining_hall: [1, 2, 3, 4], farm: [1, 2, 3, 4],
  forge: [1, 2, 3, 4], infirmary: [1, 2, 3, 4], lobby: [1, 2, 3, 4],
  mage_tower: [1, 2, 3, 4], market: [1, 2, 3, 4], mirror_of_fate: [3, 4],
  reliquary: [2, 3, 4], shrine: [1, 2, 3, 4], skydock: [1, 2, 3, 4],
  tavern: [1, 2, 3, 4], training_grounds: [1, 2, 3, 4],
  transcendence_core: [4], vault: [1, 2, 3, 4], wall: [1, 2, 3, 4],
}
const facArtSlug = (t) => (t ? String(t).toLowerCase().replace(/ /g, '_') : '')
function facArt(type, level = 1) {
  const slug = facArtSlug(type)
  const tiers = FACILITY_ART_TIERS[slug]
  if (!tiers) return null
  const want = level >= 39 ? 4 : level >= 26 ? 3 : level >= 13 ? 2 : 1
  // nearest shipped tier at or below the earned one, else the lowest shipped
  const tier = [...tiers].reverse().find(t => t <= want) ?? tiers[0]
  return `/images/facilities/${slug}_t${tier}.png`
}

// SQLite's CURRENT_TIMESTAMP stores UTC with no timezone marker — passing
// the raw "YYYY-MM-DD HH:MM:SS" string to new Date() makes JS read it as
// LOCAL time, so every chat/mail timestamp displayed hours off (confirmed:
// chatter showing "11:59 PM" at 6:59 PM local). Append the Z so it parses
// as the UTC instant it actually is; toLocaleTimeString then converts.
function parseUtcTimestamp(ts) {
  if (!ts) return new Date()
  return new Date(ts.includes('T') || ts.endsWith('Z') ? ts : ts.replace(' ', 'T') + 'Z')
}


// Kept accurate to the actual backend effects (time_service, restaurant/
// infirmary/alchemist/research/sanctum services, get_workshop_discount) —
// each names the real mechanic and the classes the code actually favors.
const FACILITY_TOOLTIPS = {
  "Market": "Generates passive gold (scales with level) and stocks a small shop. A stationed MERCHANT powers it by branch: Traders swell the gold (up to +140%), Smugglers open black-market prices on the shop instead. Anyone assigned helps a little and earns passive XP.",
  "Farm": "Grows alchemy INGREDIENTS passively (scales with level) — cook them at the Dining Hall or brew them at the Lab. A stationed FARMER (Master Farmer line) swells the harvest; a Forager-line Chef in the Dining Hall adds a Full Larder bonus on top. Beast Tamers instead empower the Bestiary's guardians.",
  "Training Grounds": "Where the bench gets stronger without risking the Tower — drills, sparring, and mentorship. A stationed TACTICIAN also commands every climb by branch: Strategists open with a guaranteed first strike + bonus mana, Commanders hold a Battle Formation (+% all stats), Advisors convene a War Council (Strength + crit; Warlords snowball off kills).",
  "Dining Hall": "Assigned cooks passively restore MORALE for the roster and COOK Farm ingredients into consumables. A stationed CHEF feeds the whole climbing team by branch: Sous Chefs lay a Grand Feast (+% ALL stats), Butchers serve War Rations (Strength + crit), Foragers keep a Full Larder (more Farm ingredients). Power scales with star AND evolution.",
  "Forge": "Crafts weapons, armor, and accessories. A stationed BLACKSMITH works by branch: Weaponsmiths cut crafting gold costs (never free — Master Smiths can even forge a cut above), Armorers temper the whole team's plate (−% damage taken), Artificers' runework speeds Athenaeum research.",
  "Infirmary": "Passively heals TRAUMA and crafts Bandages (auto-used before the next floor). A stationed MEDIC guards the climb by branch: Surgeons raise max HP entering fights, Herbalists brew regen salves (per-round healing), Field Medics coat the party's blades in toxins.",
  "Vault": "Each upgrade expands equipment storage. A stationed QUARTERMASTER makes the stores fight by branch: Scavengers armor the party with an opening damage barrier, Logistics Officers dispatch emergency field kits mid-fight, Merchants run a War Chest (the Vault generates gold).",
  "Alchemist Lab": "Brews potions passively over time. A stationed ALCHEMIST works by branch: Apothecaries brew dramatically faster, Poisoners issue combat draughts (+Strength/Intelligence in fights), Transmuters transmute lead into passive gold.",
  "Tavern": "Assigned hosts take the edge off — passively reduces STRESS for the entire living roster. Bards and Chefs make the best hosts.",
  "Skydock": "Discounts the gold cost of upgrading every OTHER facility (up to 50% off), scaling with Skydock level — Magic Engineers triple their contribution. This is where magic battleships will be built: Magic Engineers craft the greatest hulls, but any high-Mental hero can apprentice here for a basic vessel.",
  "Wall": "The base's FOUNDATION — no other facility can be upgraded above the Wall's level, so raise it first. Every level also adds flat defense rating for the coming Raid system (opt-in): raiders must breach the Wall before the Bastion's garrison ever engages.",
  "Bastion": "Your garrison for the coming Raid system (raiding is opt-in). Stationed heroes contribute their strength behind the Wall's cover — and a Magic Engineer's arcane cannons DOUBLE the whole garrison, letting even 1★ heroes hold the line.",
  "Shrine": "Assigned clergy slowly deepen the whole roster's LOYALTY (affinity). A stationed PRIEST blesses the climb by branch: Oracles grant death-saves (a hero refuses a fatal blow — 6★+ only), Chaplains lend physical & magic resistance, Confessors deepen loyalty fastest and calm the roster's stress.",
  "Mage Tower": "Conducts magical research for permanent upgrades. Magic Engineers are the most effective researchers, then Mages, then Spellswords.",
  "Athenaeum": "The company's research hall. Assigned scholars generate INSIGHT that flows into whichever study is active on the research map — five disciplines, plus emergent confluences where two mastered schools weave together. Mages and Magic Engineers study fastest.",
  "Mirror of Fate": "Pay gold to instantly reveal a hero's hidden Talent. The Mirror's level sets the detail: a vague tier at first, a numeric range at Lv.5, the exact number at Lv.10.",
  "Bestiary": "Houses beasts captured in the Tower — kept beasts add their menace to your base's defense. A stationed SCOUT hunts by branch: Pathfinders master the hunt (better capture odds, bigger catches, Rangers take Alphas), Trackers mark the strongest enemy each fight (shredded defenses), Spies sabotage enemy camps (they enter weakened).",
  "Reliquary": "A museum of your conquests — mount the Trophies major Bosses drop (every 10th floor) to grant permanent, roster-wide passive buffs.",
  "Chronosphere": "Bend time once per day: instantly simulate hours of passive base generation (gold, ingredients, XP, fatigue recovery). Upgrades increase the hours skipped.",
  "Transcendence Core": "The endgame furnace — feed it staggering amounts of gold to permanently empower your entire roster, one infusion at a time. Each infusion costs more than the last.",
}

// Facility categories for the filter chips. Anything unlisted falls under
// "Economy" as a sensible default.
const FACILITY_CATEGORY = {
  "Market": "Economy", "Farm": "Economy", "Dining Hall": "Economy", "Vault": "Economy",
  "Alchemist Lab": "Economy", "Forge": "Economy", "Skydock": "Economy",
  "Training Grounds": "Support", "Infirmary": "Support", "Tavern": "Support",
  "Shrine": "Support", "Mirror of Fate": "Support", "Mage Tower": "Support",
  "Athenaeum": "Support",
  "Wall": "Military", "Bastion": "Military",
  "Bestiary": "Endgame", "Reliquary": "Endgame", "Chronosphere": "Endgame", "Transcendence Core": "Endgame",
}
const FACILITY_CATEGORIES = ["All", "Economy", "Support", "Military", "Endgame"]
function facilityCategory(type) { return FACILITY_CATEGORY[type] || "Economy" }

// Which support lineage draws power from each facility (mirrors backend
// support_service.SUPPORT_FACILITY) — for the boon banner in the facility modal.
const FACILITY_SUPPORT_CLASS = {
  'Dining Hall': 'Chef', 'Infirmary': 'Medic', 'Bestiary': 'Scout', 'Forge': 'Blacksmith',
  'Vault': 'Quartermaster', 'Training Grounds': 'Tactician', 'Shrine': 'Priest',
  'Alchemist Lab': 'Alchemist', 'Market': 'Merchant', 'Farm': 'Farmer',
}
// Turn the raw /base/support payload into a readable boon for a facility.
// null = facility has no support class. active=false = no specialist assigned
// (or that branch's mechanic isn't wired yet).
function facilityBoon(facType, boons) {
  const cls = FACILITY_SUPPORT_CLASS[facType]
  if (!cls || !boons) return null
  const tiers = boons.tiers || {}, branches = boons.branches || {}, b = boons
  const mastery = tiers[cls] || 0
  const branch = branches[cls]            // undefined = unassigned, null = unevolved
  const assigned = cls in tiers
  const pct = v => `${Math.round((v || 0) * 100)}%`
  let title = null, lines = []
  if (cls === 'Chef') {
    if (branch === 'Butcher') { title = 'War Rations'; lines = [`+${b.war_str_pct}% Strength`, `+${pct(b.war_crit)} crit chance`]; if (b.chef_morale_boost) lines.push(`Iron Chef: +${b.chef_morale_boost} morale entering fights`) }
    else if (branch === 'Forager') { title = 'Full Larder'; lines = [`+${pct(b.chef_larder_ingredient_bonus)} Farm ingredients`] }
    else if (b.feast_stat_pct) { title = branch === 'Sous Chef' ? 'Grand Feast' : 'Feast'; lines = [`+${b.feast_stat_pct}% ALL stats to deployed heroes`]; if (b.chef_wellfed_regen) lines.push(`Master Chef: well-fed regen (${pct(b.chef_wellfed_regen)}/round)`) }
  } else if (cls === 'Medic') {
    if (branch === 'Field Medic' && b.medic_poison_pct) { title = 'Toxin Kit'; lines = [`Deployed heroes poison on hit (${pct(b.medic_poison_pct)} max HP / turn)`]; if (b.alch_enemy_poison) lines.push('Plague Doctor: enemies start every fight afflicted') }
    else if (branch === 'Herbalist') { title = 'Regen Salves'; lines = [`Heal ${pct(b.medic_regen_pct)} max HP every combat round`]; if (b.medic_cleanse) lines.push('Miracle Worker: afflictions burn off twice as fast') }
    else if (b.medic_shield_pct) { title = branch === 'Surgeon' ? 'Field Surgery' : 'Field Dressing'; lines = [`+${b.medic_shield_pct}% max HP entering every fight`]; if (b.medic_stitch_pct) lines.push(`CMO: once/fight emergency stitch (${pct(b.medic_stitch_pct)} HP)`) }
  } else if (cls === 'Priest') {
    if (branch === 'Chaplain') { title = 'Blessing'; lines = [`+${pct(b.blessing_resist_pct)} physical & magic resistance`]; if (b.priest_blessing_heal) lines.push(`Saint: fight-start mending (${pct(b.priest_blessing_heal)} HP)`) }
    else if (branch === 'Confessor' && b.priest_loyalty_bonus) { title = 'Absolution'; lines = [`+${b.priest_loyalty_bonus} loyalty per Shrine pulse`]; if (b.priest_calm_stress) lines.push(`High Confessor: −${b.priest_calm_stress} roster stress per pulse`) }
    else if (b.priest_death_saves) { title = 'Guardian Fate'; lines = [`${b.priest_death_saves} death-save${b.priest_death_saves > 1 ? 's' : ''} per hero, per fight`]; if (b.priest_foresee) lines.push('Prophet: one fatal blow foreseen & dodged per fight') }
  } else if (cls === 'Tactician') {
    if (branch === 'Commander') { title = 'Battle Formation'; lines = [`+${b.formation_pct}% all combat stats`]; if (b.tact_laststand_pct) lines.push(`General: survivors +${pct(b.tact_laststand_pct)} per fallen ally`) }
    else if (branch === 'Advisor' && b.advisor_crit) { title = 'War Council'; lines = [`+${b.advisor_str_pct}% Strength`, `+${pct(b.advisor_crit)} crit chance`]; if (b.tact_snowball_pct) lines.push(`Warlord: kills grant +${pct(b.tact_snowball_pct)} ATK (stacking)`) }
    else if (b.tactician_bonus_mana) { title = b.tactician_first_strike ? 'Opening Gambit' : 'Field Orders'; lines = [b.tactician_first_strike ? `Guaranteed first strike + ${b.tactician_bonus_mana} opening mana` : `+${b.tactician_bonus_mana} opening mana`]; if (b.tact_haste_agi) lines.push('Grand Strategist: opening haste (2 rounds)') }
  } else if (cls === 'Quartermaster') {
    if (branch === 'Logistics Officer' && b.quartermaster_kit_charges) { title = 'Field Kits'; lines = [`${b.quartermaster_kit_charges} emergency heal${b.quartermaster_kit_charges > 1 ? 's' : ''} (${pct(b.quartermaster_kit_heal_pct)} HP) mid-fight`]; if (b.qm_kit_mana) lines.push('Guildmaster: kits also restore mana & purge afflictions') }
    else if (branch === 'Merchant' && b.vault_gold_bonus) { title = 'War Chest'; lines = [`The Vault generates +${pct(b.vault_gold_bonus)} passive gold`]; if (b.qm_warchest_gold_pct) lines.push(`Tycoon: +${pct(b.qm_warchest_gold_pct)} gold from every floor`) }
    else if (b.quartermaster_barrier_pct) { title = branch === 'Scavenger' ? 'Deep Stores' : 'Standing Orders'; lines = [`${pct(b.quartermaster_barrier_pct)} damage barrier for the first ${b.quartermaster_barrier_rounds} rounds`]; if (b.qm_hoard_loot_pct) lines.push(`Hoarder: +${pct(b.qm_hoard_loot_pct)} gold & materials from floors`) }
  } else if (cls === 'Merchant' && b.merchant_income_bonus) {
    title = 'Bull Market'; lines = [`+${pct(b.merchant_income_bonus)} passive gold`]
  } else if (cls === 'Scout' && b.scout_capture_bonus) {
    title = 'Master of the Hunt'; lines = [`+${pct(b.scout_capture_bonus)} beast capture chance`, `+${pct(b.scout_beast_power_pct)} power on beasts you catch`]
    if (b.scout_elite_hunt) lines.push('Ranger: chance to capture ALPHA beasts')
  } else if (cls === 'Scout' && b.scout_mark_pct) {
    title = "Predator's Mark"; lines = [`The strongest enemy enters with −${pct(b.scout_mark_pct)} defenses`]
    if (b.scout_mark_armor_pen) lines.push(`Infiltrator: team +${pct(b.scout_mark_armor_pen)} armor pen`)
  } else if (cls === 'Scout' && b.scout_sabotage_pct) {
    title = 'Sabotage'; lines = [`Enemies enter every fight at −${pct(b.scout_sabotage_pct)} stats & HP`]
  } else if (cls === 'Blacksmith' && b.smith_dmg_reduction_pct) {
    title = 'Tempered Plate'; lines = [`Deployed heroes take −${pct(b.smith_dmg_reduction_pct)} damage`]
  } else if (cls === 'Blacksmith' && b.smith_research_pct) {
    title = 'Runework'; lines = [`+${b.smith_research_pct}% Athenaeum insight rate`]
  } else if (cls === 'Farmer' && b.farmer_beast_defense_mult) {
    title = 'Menagerie'; lines = [`Guarding beasts contribute +${pct(b.farmer_beast_defense_mult)} base defense`]
  } else if (cls === 'Farmer' && b.farmer_income_bonus) {
    title = 'Bountiful Harvest'; lines = [`+${pct(b.farmer_income_bonus)} passive ingredients`]
  } else if (cls === 'Blacksmith' && b.craft_discount_pct) {
    title = 'Master Forge'; lines = [`−${b.craft_discount_pct}% crafting gold cost`]
    if (b.smith_rarity_chance) lines.push(`Master Smith: ${pct(b.smith_rarity_chance)} chance crafts come out +1 rarity`)
  } else if (cls === 'Alchemist' && b.alch_draught_pct) {
    title = 'Combat Draughts'; lines = [`Deployed heroes +${b.alch_draught_pct}% Strength & Intelligence`]
    if (b.alch_enemy_poison) lines.push('Brewmaster: enemies start every fight poisoned')
  } else if (cls === 'Alchemist' && b.alch_transmute_gold) {
    title = 'Transmutation'; lines = [`The Lab transmutes ~${b.alch_transmute_gold} gold per level over time`]
  } else if (cls === 'Alchemist' && b.brew_bonus) {
    title = 'Master Brewer'; lines = [`Faster passive brewing (+${pct(b.brew_bonus)}/tick)`]
  } else if (cls === 'Merchant' && b.smuggler_discount_pct) {
    title = 'Black Market'; lines = [`−${b.smuggler_discount_pct}% on every Market purchase`]
    if (b.merchant_income_bonus) lines.push(`Contraband: +${pct(b.merchant_income_bonus)} passive gold`)
  }
  return { cls, mastery, branch, assigned, active: !!title && lines.length > 0, title, lines }
}

// Tiny inline sparkline showing the real diminishing-returns curve a
// stationed floor follows: stat_bonus_pct = (total_lp / sqrt(headcount)) / 10
// (see get_floor_lp in base_service.py — the backend value this curve is
// built from, not a separate frontend-side recalculation). Steep drop from
// 1→2 heroes, flattening out by 4-5 — exactly the "diminishing returns"
// shape, just keyed on crowding a floor rather than a level number.
function DiminishingReturnsCurve({ curve, current }) {
  if (!curve || curve.length < 2) return null
  const w = 80, h = 28, pad = 3
  const maxVal = curve[0].stat_bonus_pct || 1
  const points = curve.map((pt, i) => {
    const x = pad + (i / (curve.length - 1)) * (w - pad * 2)
    const y = h - pad - (pt.stat_bonus_pct / maxVal) * (h - pad * 2)
    return { x, y, ...pt }
  })
  const pathD = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(' ')
  const currentPt = points[Math.min(current, points.length) - 1]
  return (
    <svg width={w} height={h} style={{ marginTop: '0.25rem', overflow: 'visible' }}>
      <path d={pathD} fill="none" stroke="rgba(74,222,128,0.5)" strokeWidth="1.5" />
      {currentPt && (
        <circle cx={currentPt.x} cy={currentPt.y} r="3" fill="var(--gold)">
          <title>{`${current} stationed → +${currentPt.stat_bonus_pct}% stats`}</title>
        </circle>
      )}
    </svg>
  )
}

export default function BasePage({ onGoldChange, onSubTabChange, tourTargetSubTab }) {
  const [activeTab, setActiveTab] = useState('lobby')
  const [facilityFilter, setFacilityFilter] = useState('All')
  // C: card (big art) vs list (compact rows) view for facilities — persisted.
  const [facilityView, setFacilityView] = useState(() => localStorage.getItem('toe_fac_view') || 'cards')
  function setFacView(v) { setFacilityView(v); try { localStorage.setItem('toe_fac_view', v) } catch {} }
  // Which built facility's detail panel is expanded in the grid (mockup:
  // compact cards; clicking opens the facility's management panel inline).
  const [selFacId, setSelFacId] = useState(null)
  const [boons, setBoons] = useState(null)  // /base/support — resolved support-class effects for display
  const [base, setBase] = useState(null)
  const [facilitiesData, setFacilitiesData] = useState(null)
  const [baseHeroes, setBaseHeroes] = useState([])
  const [msg, setMsg] = useState(null)
  const [facilityLoading, setFacilityLoading] = useState(false)
  // Facility BGM: the Dining Hall & Tavern play the tavern track while open;
  // the ref means we only revert to hub when leaving a tavern facility, so we
  // never stomp an overlay scene (Memorial/Synthesis) that set its own music.
  const facSceneRef = useRef(false)
  useEffect(() => {
    const fac = facilitiesData?.built?.find(f => f.id === selFacId)
    const isTavern = fac && (fac.type === 'Dining Hall' || fac.type === 'Tavern')
    if (isTavern) { setBgmScene('tavern'); facSceneRef.current = true }
    else if (facSceneRef.current) { setBgmScene('hub'); facSceneRef.current = false }
  }, [selFacId, facilitiesData])
  const [mageUpgrades, setMageUpgrades] = useState(null)
  const [crafting, setCrafting] = useState(false)
  const [bandageQty, setBandageQty] = useState(1)
  const [marketCatalog, setMarketCatalog] = useState({})
  const [purchasing, setPurchasing] = useState(false)
  const [baseUpgrades, setBaseUpgrades] = useState([])
  const [upgradingId, setUpgradingId] = useState(null)
  
  // Mail
  const [banner, setBanner] = useState(null)
  const [showBannerStudio, setShowBannerStudio] = useState(false)
  // Expeditions launch from the Skydock hull now — they were never multiplayer,
  // so they moved off the World page to where the ship actually lives.
  const [showExpeditions, setShowExpeditions] = useState(false)
  const [showMemorial, setShowMemorial] = useState(false)
  const [showLore, setShowLore] = useState(false)
  const [rehouseMode, setRehouseMode] = useState(false)
  const [mailList, setMailList] = useState([])
  const [claiming, setClaiming] = useState(false)
  
  // Legacy & Floors
  const [legacies, setLegacies] = useState([])
  const [expandedLegacyId, setExpandedLegacyId] = useState(null)
  const [legacyPage, setLegacyPage] = useState(0)
  const LEGACIES_PER_PAGE = 10
  const [floorsData, setFloorsData] = useState(null)
  const [assigning, setAssigning] = useState(false)
  // The lobby feed IS the Hearth feed (per-hero latest lines) — same data
  // the top-bar CHATTER drawer shows, so chatter reads identically wherever
  // you meet it. Only the framing differs: the drawer adds the reply actions.
  const [chats, setChats] = useState([])
  const [newChatIds, setNewChatIds] = useState(new Set())
  const seenChatIds = React.useRef(new Set())
  const hasLoadedChatsOnce = React.useRef(false)

  function applyChats(data) {
    // The Hearth now returns threaded CONVERSATIONS; flatten them (newest
    // first, lines in spoken order) so the compact lobby feed shows one
    // coherent recent exchange rather than scattered one-liners.
    const convos = (data && data.conversations) || []
    const list = convos.flatMap(c => (c.lines || []).map((l, i) => ({
      ...l, location: c.location, created_at: c.created_at, _k: `${l.speaker}|${c.created_at}|${i}`,
    })))
    const keyOf = (l) => l._k
    const fresh = hasLoadedChatsOnce.current ? list.filter(l => !seenChatIds.current.has(keyOf(l))).map(keyOf) : []
    list.forEach(l => seenChatIds.current.add(keyOf(l)))
    hasLoadedChatsOnce.current = true
    setChats(list)
    if (fresh.length) {
      setNewChatIds(new Set(fresh))
      setTimeout(() => setNewChatIds(new Set()), 3000)
    }
  }
  
  const [sortMode, setSortMode] = useState('level-desc')
  const [filterClass, setFilterClass] = useState('All')
  const [ship, setShip] = useState(null)
  const [shipBusy, setShipBusy] = useState(false)
  const [shipNameDraft, setShipNameDraft] = useState('')
  
  useEffect(() => { loadAll() }, [])

  useEffect(() => { onSubTabChange?.(activeTab) }, [activeTab])

  // Hero Chatter feed polls on its own, faster cadence than the rest of the
  // page — it should feel like an ongoing conversation, not a static log
  // that only updates on a full page reload.
  useEffect(() => {
    const interval = setInterval(() => {
      getHearth().then(applyChats).catch(() => {})
    }, 20000)
    return () => clearInterval(interval)
  }, [])

  async function loadAll() {
    getBanner().then(setBanner).catch(() => {})
    try {
      const [b, fac, heroes, leg, flrs, ch, catalog, upgrades, mail] = await Promise.all([
        getBase(),
        getFacilities(),
        listHeroes(true),
        getLegacies().catch(() => ({ legacies: [] })),
        getBaseFloors().catch(() => ({ floors: [], base_heroes: [] })),
        getHearth().catch(() => ({ conversations: [] })),
        getMarketCatalog().catch(() => ({})),
        getBaseUpgrades().catch(() => []),
        getMailList().catch(() => [])
      ])
      setBase(b)
      setFacilitiesData(fac)
      setBaseHeroes(heroes.filter(h => h.is_alive === 1 && h.is_on_team === 0))
      setLegacies(leg.legacies || [])
      setFloorsData(flrs)
      applyChats(ch)
      setMarketCatalog(catalog)
      setBaseUpgrades(upgrades)
      setMailList(mail)
      getShip().then(setShip).catch(() => {})
      getSupportBoons().then(setBoons).catch(() => {})
      
      const hasMage = fac.built?.some(f => f.type === 'Mage Tower')
      if (hasMage) {
        const mage = await getMageTowerUpgrades().catch(() => null)
        setMageUpgrades(mage)
      }
    } catch (e) {
      console.error(e)
    }
  }

  const handleUpgradeBase = async () => {
    try {
      await upgradeBase()
      alertDialog("Base Upgraded! Max Roster Size increased.")
      loadAll()
      if (onGoldChange) onGoldChange()
    } catch(e) { alertDialog(e.message || "Failed to upgrade") }
  }



  async function handleBuyBaseUpgrade(upgradeId) {
    setUpgradingId(upgradeId)
    try {
      await buyBaseUpgrade(upgradeId)
      loadAll()
      if (onGoldChange) onGoldChange()
    } catch (e) {
      alertDialog(e.message)
    } finally {
      setUpgradingId(null)
    }
  }

  async function handleBuildFacility(type) {
    setFacilityLoading(true)
    try {
      await buildFacility(type)
      loadAll()
      if (onGoldChange) onGoldChange()
    } catch (e) {
      alertDialog(e.message)
    } finally {
      setFacilityLoading(false)
    }
  }

  async function handleUpgradeFacility(facId) {
    setFacilityLoading(true)
    try {
      await upgradeFacility(facId)
      loadAll()
      if (onGoldChange) onGoldChange()
    } catch (e) {
      alertDialog(e.message)
    } finally {
      setFacilityLoading(false)
    }
  }

  async function handleAssignFacility(facId, heroId) {
    setFacilityLoading(true)
    try {
      const res = await assignFacility(facId, heroId)
      if (res?.chatter_line) setMsg(res.chatter_line)
      loadAll()
    } catch (e) {
      alertDialog(e.message)
    } finally {
      setFacilityLoading(false)
    }
  }

  async function handleRemoveFacility(heroId) {
    setFacilityLoading(true)
    try {
      await removeFacility(heroId)
      loadAll()
    } catch (e) {
      alertDialog(e.message)
    } finally {
      setFacilityLoading(false)
    }
  }

  async function handleBuyResearch(upgradeId) {
    setFacilityLoading(true)
    try {
      await buyResearchUpgrade(upgradeId)
      loadAll()
    } catch (e) {
      alertDialog(e.message)
    } finally {
      setFacilityLoading(false)
    }
  }

  async function handleCraft(heroId, slot) {
    setCrafting(true)
    try {
      await craftMaterialEquipment(heroId, slot)
      loadAll()
      if (onGoldChange) onGoldChange()
      import('../audio').then(a => a.playCraftClang()).catch(() => {})
      alertDialog("Crafted successfully!")
    } catch (e) {
      alertDialog(e.message)
    } finally {
      setCrafting(false)
    }
  }

  async function handleCraftBandages(heroId, qty = 1) {
    setCrafting(true)
    try {
      const res = await craftBandages(heroId, qty)
      loadAll()
      if (onGoldChange) onGoldChange()
      alertDialog(`The gauze is rolled — ${res.total} bandage${res.total === 1 ? '' : 's'} in stock. Auto-used on your most injured heroes before the next floor.`)
    } catch (e) {
      alertDialog(e.message)
    } finally {
      setCrafting(false)
    }
  }

  async function handlePurchase(itemId) {
    setPurchasing(true)
    try {
      const res = await purchaseMarketItem(itemId)
      loadAll()
      if (onGoldChange) onGoldChange()
      const detail = res.material ? `${res.amount}x ${res.material}` : res.ingredients ? `${res.ingredients} ingredients` : ''
      alertDialog(`Purchased ${res.item}! +${detail}`)
    } catch (e) {
      alertDialog(e.message)
    } finally {
      setPurchasing(false)
    }
  }

  async function handleAssignFloor(heroId, floorNum) {
    setAssigning(true)
    try {
      await assignBaseFloor(heroId, floorNum === null ? 0 : floorNum)
      loadAll()
    } catch(e) {
      alertDialog(e.message || e)
    } finally {
      setAssigning(false)
    }
  }

  async function handleClaimMail(mailId) {
    setClaiming(true)
    try {
      await claimMail(mailId)
      loadAll()
      if (onGoldChange) onGoldChange()
    } catch(e) {
      alertDialog(e.message || e)
    } finally {
      setClaiming(false)
    }
  }

  if (!base) return <div className="page text-dim">Loading...</div>
  if (!facilitiesData) return <div className="page text-dim">Loading facilities...</div>

  let materials = {}
  try { materials = JSON.parse(base.materials || '{}') } catch {}

  
  let goldGen = 0;
  let ingredientsGen = 0;
  let aetherGen = 0;
  if (facilitiesData && facilitiesData.built) {
    facilitiesData.built.forEach(f => {
      let multiplier = 1.0 + ((f.heroes?.length || 0) * 0.10);
      if (f.type === 'Market') goldGen += Math.floor(100 * f.level * multiplier);
      if (f.type === 'Farm') ingredientsGen += Math.floor(5 * f.level * multiplier);
      if (f.type === 'Skydock') aetherGen += Math.floor(2 * f.level * multiplier);
    });
  }

  // Three tabs only, horizontal (mock). Mail lives in the top bar, the Lore
  // Journal opens as an overlay from the lobby, legacies live in the lobby
  // panel + Memorial.
  const renderTabs = () => (
    <div className="ilm-subtabs">
      {[['lobby', 'LOBBY'], ['foundations', 'FOUNDATIONS'], ['facilities', 'FACILITIES'], ['floors', 'HIERARCHY']].map(([tab, label]) => {
        const locked = !!tourTargetSubTab && tab !== tourTargetSubTab
        return (
          <button key={tab}
            className={`ilm-subtab ${activeTab === tab ? 'active' : ''} ${tab === tourTargetSubTab ? 'glow' : ''}`}
            disabled={locked}
            onClick={() => { if (!locked) setActiveTab(tab) }}
            style={locked ? { opacity: 0.35, cursor: 'not-allowed' } : undefined}>
            {label}
          </button>
        )
      })}
    </div>
  )


const getGenRate = (fac) => {
    const rates = { Market: [100, 'Gold'], Farm: [5, 'Ingredients'], Skydock: [2, 'Aether'] };
    if (!rates[fac.type]) return null;
    const [per, resName] = rates[fac.type];
    let multiplier = 1.0 + ((fac.heroes || []).length * 0.10);
    let amt = Math.floor(per * fac.level * multiplier);
    return `Generating: +${amt} ${resName} / 5 mins`;
  };

  // Management body for a facility — assigned heroes, assignment control, and
  // every type-specific panel (crafting/market/research/mirror/training/
  // endgame). Rendered inline under the grid when a facility is selected.
  function renderFacilityDetail(fac) {
    return (
      <>
        {/* Skydock → the Shipyard (magic battleship) */}
        {fac.type === 'Skydock' && ship && (
          <div style={{ marginBottom: '1rem', border: '1px solid rgba(160,80,255,0.4)', overflow: 'hidden' }}>
            <div style={{ width: '100%', aspectRatio: '21/9', overflow: 'hidden', position: 'relative', background: 'radial-gradient(ellipse at 50% 80%, rgba(60,30,100,0.4), #08060e)' }}>
              {ship.tier > 0 ? (
                <img src={`/images/battleships/battleship_t${ship.tier}.png`} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover', objectPosition: 'center' }} />
              ) : (
                <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: '0.4rem' }}>
                  <div style={{ fontFamily: 'Cinzel, serif', letterSpacing: '0.2em', color: 'var(--text-dim)' }}>THE DRYDOCK IS EMPTY</div>
                  <div className="text-dim" style={{ fontSize: '0.8rem', fontStyle: 'italic' }}>Lay a keel below.</div>
                </div>
              )}
              <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(to bottom, rgba(0,0,0,0) 55%, rgba(10,10,14,0.95) 100%)' }} />
              {ship.tier > 0 && banner && (
                <div style={{ position: 'absolute', top: 8, right: 12 }} title="Your banner flies from the mast">
                  <TeamBanner banner={banner} size={56} />
                </div>
              )}
            </div>
            <div style={{ padding: '1rem' }}>
              {/* THE SKY CHARTS — expeditions launch from the hull docked here */}
              {ship.tier > 0 && (
                <button onClick={() => setShowExpeditions(true)}
                  style={{ display: 'flex', alignItems: 'center', gap: 12, width: '100%', textAlign: 'left', cursor: 'pointer', marginBottom: '1rem',
                    border: '1px solid rgba(150,110,230,.45)', background: 'linear-gradient(120deg,rgba(42,22,80,.28),rgba(12,7,24,.5))', padding: '11px 16px',
                    clipPath: 'polygon(0 0,100% 0,100% 100%,10px 100%)' }}>
                  <span style={{ width: 9, height: 9, transform: 'rotate(45deg)', background: 'var(--lavender)', boxShadow: '0 0 8px var(--lavender)', flex: 'none' }} />
                  <span style={{ fontFamily: "'Cinzel',serif", fontWeight: 700, letterSpacing: '.2em', fontSize: 12, color: 'var(--text-hi)' }}>THE SKY CHARTS</span>
                  <span style={{ fontStyle: 'italic', fontSize: 13, color: 'var(--muted)' }}>dispatch expeditions — they sail while you sleep</span>
                  <span style={{ flex: 1 }} />
                  <span style={{ fontFamily: "'Cinzel',serif", fontSize: 12, letterSpacing: '.18em', color: 'var(--gold-hi)' }}>ENTER ›</span>
                </button>
              )}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem' }}>
                <div>
                  <h3 style={{ fontFamily: 'Cinzel, serif', color: '#b06aff', margin: 0 }}>
                    ⚓ {ship.tier > 0 ? (ship.ship_name || ship.ship.name) : 'Shipyard'}
                    {ship.tier > 0 && <span className="text-dim" style={{ fontSize: '0.8rem', marginLeft: '0.6rem' }}>{ship.ship.name} · Tier {ship.tier}/5</span>}
                  </h3>
                  {ship.tier > 0 && (
                    <div className="text-dim" style={{ fontSize: '0.82rem', fontStyle: 'italic', marginTop: '0.3rem', maxWidth: 560 }}>{ship.ship.desc}</div>
                  )}
                </div>
                {ship.defense && (
                  <div title="Base defense rating for the coming Raid system: Wall + Bastion garrison + docked ship."
                    style={{ fontFamily: 'Cinzel, serif', fontSize: '0.8rem', color: 'var(--text-dim)', textAlign: 'right', cursor: 'help' }}>
                    Defense <span style={{ color: 'var(--gold)', fontSize: '1.1rem' }}>{ship.defense.total}</span>
                    <div style={{ fontSize: '0.65rem' }}>Wall {ship.defense.wall} · Garrison {ship.defense.garrison} · Ship {ship.defense.ship}{ship.defense.beasts > 0 && <> · Beasts {ship.defense.beasts}</>}</div>
                  </div>
                )}
              </div>
              {ship.tier > 0 && (
                <div style={{ display: 'flex', gap: '1.2rem', marginTop: '0.6rem', fontSize: '0.8rem' }}>
                  <span className="text-dim">Crew capacity <span style={{ color: 'var(--text-hi)' }}>{ship.ship.crew}</span></span>
                  <span className="text-dim">Firepower <span style={{ color: 'var(--text-hi)' }}>{ship.ship.defense}</span></span>
                  <form style={{ marginLeft: 'auto', display: 'flex', gap: '0.4rem' }} onSubmit={async (e) => {
                    e.preventDefault()
                    if (!shipNameDraft.trim()) return
                    try { await renameShip(shipNameDraft); setShipNameDraft(''); getShip().then(setShip) } catch (err) { alertDialog(err.message) }
                  }}>
                    <input className="input" placeholder="Name your ship…" value={shipNameDraft} onChange={e => setShipNameDraft(e.target.value)}
                      style={{ background: 'rgba(0,0,0,0.3)', border: '1px solid var(--border)', padding: '0.25rem 0.5rem', color: '#fff', borderRadius: 4, fontSize: '0.78rem', width: 160 }} />
                    <button className="btn" type="submit" style={{ fontSize: '0.7rem', padding: '0.25rem 0.6rem' }} disabled={!shipNameDraft.trim()}>Christen</button>
                  </form>
                </div>
              )}
              {/* refit — a free point pool across Speed / Firepower / Armor.
                  Tier is the hull class; refit makes each ship unique. */}
              {ship.tier > 0 && ship.refit && (
                <div style={{ marginTop: '0.9rem', borderTop: '1px solid var(--border)', paddingTop: '0.8rem' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
                    <span style={{ width: 7, height: 7, transform: 'rotate(45deg)', background: 'var(--lavender)', display: 'inline-block' }} />
                    <span style={{ fontFamily: "'Cinzel',serif", letterSpacing: '.26em', fontSize: 10, color: 'var(--lavender)' }}>REFIT</span>
                    <span style={{ height: 1, flex: 1, background: 'rgba(150,110,230,.25)' }} />
                    <span style={{ fontFamily: "'Cinzel',serif", fontSize: 9, letterSpacing: '.14em', color: ship.refit.unspent > 0 ? 'var(--gold-hi)' : 'var(--muted)' }}>
                      {ship.refit.unspent} UNSPENT · POOL {ship.refit.pool}
                    </span>
                  </div>
                  <div style={{ display: 'flex', gap: 18, alignItems: 'center', flexWrap: 'wrap' }}>
                    {[['speed', 'SPEED'], ['fire', 'FIREPOWER'], ['armor', 'ARMOR']].map(([stat, label]) => (
                      <div key={stat} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span style={{ fontFamily: "'Cinzel',serif", fontSize: 9, letterSpacing: '.18em', color: 'var(--muted)', width: 74 }}>{label}</span>
                        <button onClick={async () => { try { setShip(prev => prev); await refitShip(stat, -1); getShip().then(setShip) } catch (err) { alertDialog(err.message) } }}
                          disabled={(ship.refit.allocated[stat] || 0) <= 0}
                          style={{ width: 24, height: 24, border: '1px solid rgba(150,110,230,.45)', background: 'none', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontFamily: "'Cinzel',serif", color: 'var(--lavender)', cursor: 'pointer', opacity: (ship.refit.allocated[stat] || 0) <= 0 ? 0.4 : 1 }}>−</button>
                        <span style={{ fontFamily: "'Cormorant Garamond',serif", fontWeight: 700, fontSize: 19, color: 'var(--text-hi)', width: 24, textAlign: 'center' }}>{ship.refit.allocated[stat] || 0}</span>
                        <button onClick={async () => { try { await refitShip(stat, 1); getShip().then(setShip) } catch (err) { alertDialog(err.message) } }}
                          disabled={ship.refit.unspent <= 0}
                          style={{ width: 24, height: 24, border: '1px solid rgba(150,110,230,.45)', background: 'none', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontFamily: "'Cinzel',serif", color: 'var(--lavender)', cursor: 'pointer', opacity: ship.refit.unspent <= 0 ? 0.4 : 1 }}>＋</button>
                      </div>
                    ))}
                    <span style={{ flex: 1 }} />
                    {ship.refit.next_point_cost != null && (
                      <button onClick={async () => {
                        try {
                          const res = await buyRefitPoint()
                          alertDialog(`The fitters take ${res.cost.toLocaleString()}g — +1 refit point (${res.points} owned).`)
                          getShip().then(setShip); getBase().then(setBase)
                        } catch (err) { alertDialog(err.message) }
                      }}
                        style={{ cursor: 'pointer', fontFamily: "'Cinzel',serif", fontWeight: 600, letterSpacing: '.16em', fontSize: 9, color: '#cdbfe4', background: 'none', border: '1px solid rgba(150,110,230,.45)', padding: '7px 14px', clipPath: 'polygon(6px 0,100% 0,calc(100% - 6px) 100%,0 100%)' }}>
                        BUY POINT · {ship.refit.next_point_cost.toLocaleString()}G
                      </button>
                    )}
                  </div>
                  <div style={{ fontSize: 12, fontStyle: 'italic', color: 'var(--muted)', marginTop: 8 }}>
                    Points move freely — Firepower and Armor harden the docked hull's defense; Speed pays off on expeditions.
                  </div>
                </div>
              )}
              {ship.next ? (
                <div style={{ marginTop: '0.9rem', borderTop: '1px solid var(--border)', paddingTop: '0.8rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.6rem' }}>
                  <div>
                    <div style={{ fontFamily: 'Cinzel, serif', fontSize: '0.85rem', color: 'var(--text-hi)' }}>
                      {ship.tier > 0 ? 'Next hull' : 'Lay a keel'}: {ship.next.name} <span className="text-gold">({ship.next.cost.toLocaleString()}g)</span>
                    </div>
                    <div className="text-dim" style={{ fontSize: '0.72rem', marginTop: '0.2rem' }}>
                      {ship.next.requires === 'engineer'
                        ? 'Requires a Magic Engineer assigned to the Skydock.'
                        : 'Requires a Magic Engineer — or any hero with 70+ Mental aptitude — assigned to the Skydock.'}
                    </div>
                    {ship.blocker && <div style={{ fontSize: '0.72rem', color: 'var(--red)', marginTop: '0.2rem' }}>{ship.blocker}</div>}
                  </div>
                  <button className="btn" disabled={!ship.can_build || shipBusy}
                    onClick={async () => {
                      setShipBusy(true)
                      try {
                        const res = await buildShip()
                        alertDialog(`The ${res.name} takes to the sky! (Tier ${res.tier}) The fitters grant ${res.refit_points_granted ?? 3} refit points.`)
                        getShip().then(setShip); getBase().then(setBase)
                      } catch (err) { alertDialog(err.message) } finally { setShipBusy(false) }
                    }}
                    style={{ border: '1px solid #b06aff', color: '#d0a0ff', background: 'rgba(80,30,130,0.2)', padding: '0.5rem 1.2rem' }}>
                    {shipBusy ? 'Building…' : ship.tier > 0 ? 'Lay the Next Keel' : 'Build Ship'}
                  </button>
                </div>
              ) : (
                <div style={{ marginTop: '0.9rem', fontFamily: 'Cinzel, serif', fontSize: '0.8rem', color: '#b06aff', textAlign: 'center' }}>
                  ✦ The greatest hull the Skydock can produce. The sky is yours. ✦
                </div>
              )}
            </div>
          </div>
        )}

        {/* assigned heroes — Illuminated diamond chips */}
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: '1rem' }}>
          {fac.heroes.map(h => (
            <div key={h.id} style={{ display: 'flex', alignItems: 'center', gap: 12, border: '1px solid rgba(184,151,98,.3)', background: 'rgba(12,7,24,.45)', padding: '8px 14px' }}>
              <span style={{ position: 'relative', width: 38, height: 38, transform: 'rotate(45deg)', flex: 'none', border: '1px solid rgba(216,187,132,.55)', background: 'linear-gradient(135deg,#1c1030,#0c0718)', display: 'flex', alignItems: 'center', justifyContent: 'center', overflow: 'hidden' }}>
                {h.portrait_path && !h.portrait_path.includes('default_') ? (
                  /* face shot, not full body (Liam): backend mini = crop-only face; raw portrait only as fallback */
                  <img src={`/heroes/${h.id}/card-image?mini=1`} alt={h.name} draggable={false}
                    onError={(e) => { if (!e.currentTarget.dataset.fb) { e.currentTarget.dataset.fb = '1'; e.currentTarget.src = `/${h.portrait_path}` } }}
                    style={{ width: '142%', height: '142%', objectFit: 'cover', objectPosition: 'center', transform: 'rotate(-45deg)', flex: 'none' }} />
                ) : (
                  <span style={{ transform: 'rotate(-45deg)', fontFamily: "'Cinzel',serif", fontWeight: 700, fontSize: 13, color: 'var(--gold-hi)' }}>{h.name[0]}</span>
                )}
              </span>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontFamily: "'Cinzel',serif", fontWeight: 700, fontSize: 12, letterSpacing: '.06em', color: 'var(--text-hi)', whiteSpace: 'nowrap' }}>{h.name.toUpperCase()}</div>
                {h.class_name && <div style={{ fontFamily: "'Cinzel',serif", fontSize: 8, letterSpacing: '.16em', color: 'var(--muted)', marginTop: 2 }}>{String(h.class_name).toUpperCase()}</div>}
              </div>
              <button onClick={() => handleRemoveFacility(h.id)} title="Send back to the roster"
                style={{ background: 'none', border: 'none', color: 'var(--muted)', cursor: 'pointer', fontSize: 12, padding: '0 0 0 4px' }}>✕</button>
              {fac.type === 'Forge' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginLeft: 6 }}>
                  <button onClick={() => handleCraft(h.id, 'weapon')} disabled={crafting} className="btn btn-gold" style={{ padding: '0.2rem 0.6rem', fontSize: '0.62rem' }}>WEAPON · 100g + 3 IRON + 1 BONE</button>
                  <button onClick={() => handleCraft(h.id, 'armor')} disabled={crafting} className="btn btn-gold" style={{ padding: '0.2rem 0.6rem', fontSize: '0.62rem' }}>ARMOR · 100g + 2 CRYSTAL + 2 IRON</button>
                  <button onClick={() => handleCraft(h.id, 'accessory')} disabled={crafting} className="btn btn-gold" style={{ padding: '0.2rem 0.6rem', fontSize: '0.62rem' }}>ACCESSORY · 100g + 3 DUST + 1 EAR</button>
                </div>
              )}
            </div>
          ))}
        </div>

        {/* Infirmary — the ward + field supplies (spec "Infirmary - Illuminated") */}
        {fac.type === 'Infirmary' && (() => {
          const hurting = baseHeroes
            .filter(h => (h.trauma ?? 0) > 0)
            .sort((a, b) => (b.trauma ?? 0) - (a.trauma ?? 0))
            .slice(0, 5)
          const untroubled = baseHeroes.length - hurting.length
          const crafter = fac.heroes.find(h => /medic|priest/i.test(h.class_name || '')) || fac.heroes[0]
          const stock = materials.Bandage || 0
          const cost = bandageQty * 15
          return (
            <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', margin: '0.5rem 0 1rem' }}>
              {/* recovery ward */}
              <div style={{ flex: '1.2 1 320px', minWidth: 300 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 10 }}>
                  <span style={{ fontFamily: "'Cinzel',serif", letterSpacing: '.3em', fontSize: 11, color: 'var(--gold)' }}>THE WARD · HEAVIEST MINDS FIRST</span>
                  <span style={{ height: 1, flex: 1, background: 'rgba(184,151,98,.2)' }} />
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {hurting.length === 0 && (
                    <div style={{ textAlign: 'center', fontSize: 13.5, fontStyle: 'italic', color: '#6f628c', padding: '14px 0' }}>
                      Every mind in the roster breathes easy — the ward stands empty.
                    </div>
                  )}
                  {hurting.map(h => {
                    const t = h.trauma ?? 0
                    const heavy = t >= 50
                    const mid = t >= 20 && !heavy
                    const border = heavy ? 'rgba(192,64,64,.45)' : mid ? 'rgba(232,163,76,.4)' : 'rgba(184,151,98,.3)'
                    const barBorder = heavy ? 'rgba(192,64,64,.35)' : mid ? 'rgba(232,163,76,.3)' : 'rgba(143,191,159,.3)'
                    const bar = heavy ? 'linear-gradient(90deg,#7a3030,#c05050)' : mid ? 'linear-gradient(90deg,#7a5220,#e8a34c)' : 'linear-gradient(90deg,#3a6a4a,#8fbf9f)'
                    const tag = heavy ? '#d98a8a' : mid ? '#e8a34c' : '#8fbf9f'
                    return (
                      <div key={h.id} style={{ border: `1px solid ${border}`, background: heavy ? 'linear-gradient(90deg,rgba(60,16,22,.3),rgba(12,7,24,.6))' : 'rgba(12,7,24,.5)', padding: '9px 14px' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                          <span style={{ fontFamily: "'Cinzel',serif", fontWeight: heavy ? 700 : 600, fontSize: 12.5, letterSpacing: '.08em', color: heavy ? 'var(--text-hi)' : '#e7ddc9' }}>{h.name.toUpperCase()}</span>
                          <span style={{ fontFamily: "'Cinzel',serif", fontSize: 9, letterSpacing: '.14em', color: tag }}>TRAUMA {t}{heavy ? ' · SHAKEN' : ''}</span>
                        </div>
                        <div style={{ height: 5, background: 'rgba(0,0,0,.5)', border: `1px solid ${barBorder}`, marginTop: 7 }}>
                          <div style={{ width: `${Math.min(100, t)}%`, height: '100%', background: bar }} />
                        </div>
                        <div style={{ fontSize: 12.5, fontStyle: 'italic', color: 'var(--muted)', marginTop: 5 }}>
                          {heavy ? 'The ward heals them as time passes — rest hastens it.' : mid ? 'Mending — a rest and a warm meal will see it off.' : 'Clear within the hour.'}
                        </div>
                      </div>
                    )
                  })}
                  {hurting.length > 0 && untroubled > 0 && (
                    <div style={{ textAlign: 'center', fontSize: 13.5, fontStyle: 'italic', color: '#6f628c', padding: '6px 0' }}>
                      The rest of the roster breathes easy — {untroubled} minds untroubled.
                    </div>
                  )}
                </div>
              </div>

              {/* field supplies */}
              <div style={{ position: 'relative', flex: '1 1 280px', minWidth: 270, border: '1px solid rgba(224,133,133,.45)', background: 'linear-gradient(160deg,rgba(60,16,22,.22),rgba(12,7,24,.65))', padding: '16px 18px 70px', clipPath: 'polygon(0 0,100% 0,100% 100%,14px 100%)' }}>
                <div style={{ position: 'absolute', left: 0, top: 0, width: 12, height: 12, borderLeft: '2px solid #e08585', borderTop: '2px solid #e08585' }} />
                <div style={{ fontFamily: "'Cinzel',serif", letterSpacing: '.26em', fontSize: 10, color: '#e08585' }}>FIELD SUPPLIES</div>
                <div style={{ fontFamily: "'Cinzel',serif", fontWeight: 900, fontSize: 19, color: 'var(--text-hi)', marginTop: 5 }}>CRAFT BANDAGES</div>
                <div style={{ fontSize: 13.5, fontStyle: 'italic', color: '#c9a8ae', marginTop: 3 }}>Auto-used on your most injured heroes before the next floor.</div>
                <div style={{ marginTop: 14, display: 'flex', flexDirection: 'column', gap: 6 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 14 }}>
                    <span style={{ color: '#c9bfa8' }}>Cost per bandage</span>
                    <span style={{ fontFamily: "'Cinzel',serif", fontSize: 12, color: '#a8dfb8' }}>15 INGREDIENTS</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 14 }}>
                    <span style={{ color: '#c9bfa8' }}>In stock</span>
                    <span style={{ fontFamily: "'Cinzel',serif", fontSize: 12, color: 'var(--text-hi)' }}>{stock}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 14 }}>
                    <span style={{ color: '#c9bfa8' }}>Crafter</span>
                    <span style={{ fontFamily: "'Cinzel',serif", fontSize: 12, color: crafter ? 'var(--text-hi)' : '#d98a8a' }}>
                      {crafter ? `${crafter.name.toUpperCase()}${crafter.class_name ? ` · ${String(crafter.class_name).toUpperCase()}` : ''}` : 'NONE ASSIGNED'}
                    </span>
                  </div>
                </div>
                <div style={{ marginTop: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ fontFamily: "'Cinzel',serif", fontSize: 10, letterSpacing: '.18em', color: 'var(--muted)' }}>QUANTITY</span>
                  <button onClick={() => setBandageQty(q => Math.max(1, q - 1))} style={{ width: 26, height: 26, border: '1px solid rgba(224,133,133,.45)', background: 'none', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontFamily: "'Cinzel',serif", color: '#e08585', cursor: 'pointer' }}>−</button>
                  <span style={{ fontFamily: "'Cormorant Garamond',serif", fontWeight: 700, fontSize: 22, color: 'var(--text-hi)', width: 30, textAlign: 'center' }}>{bandageQty}</span>
                  <button onClick={() => setBandageQty(q => Math.min(20, q + 1))} style={{ width: 26, height: 26, border: '1px solid rgba(224,133,133,.45)', background: 'none', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontFamily: "'Cinzel',serif", color: '#e08585', cursor: 'pointer' }}>+</button>
                  <span style={{ flex: 1 }} />
                  <span style={{ fontSize: 13, fontStyle: 'italic', color: 'var(--muted)' }}>{cost} ingredients</span>
                </div>
                <div style={{ fontSize: 12.5, fontStyle: 'italic', color: 'var(--muted)', marginTop: 10 }}>Only a Medic or Priest assigned to the ward rolls gauze worth trusting.</div>
                <button disabled={crafting || !crafter || (base.ingredients ?? 0) < cost}
                  onClick={() => handleCraftBandages(crafter.id, bandageQty)}
                  style={{ position: 'absolute', left: 18, right: 18, bottom: 16, textAlign: 'center', cursor: 'pointer', fontFamily: "'Cinzel',serif", fontWeight: 700, letterSpacing: '.2em', fontSize: 12, color: '#0a0710', background: 'linear-gradient(120deg,#f0b8b8,#c05050)', border: 'none', padding: '10px 0', clipPath: 'polygon(10px 0,100% 0,calc(100% - 10px) 100%,0 100%)', boxShadow: '0 8px 24px rgba(192,80,80,.35)', opacity: crafting || !crafter || (base.ingredients ?? 0) < cost ? 0.5 : 1 }}>
                  {crafting ? 'ROLLING…' : 'ROLL THE GAUZE'}
                </button>
              </div>
            </div>
          )
        })()}

        {/* assignment */}
        {fac.heroes.length < fac.slots_unlocked && (
          <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem' }}>
            <select id={`assign-${fac.id}`} className="input" style={{ flex: 1 }}>
              <option value="">Assign hero...</option>
              {baseHeroes.filter(h => !fac.heroes.find(fh => fh.id === h.id)).map(h => (
                <option key={h.id} value={h.id}>{h.name} ({h.class_name})</option>
              ))}
            </select>
            <button className="btn btn-primary" onClick={() => {
              const sel = document.getElementById(`assign-${fac.id}`)
              if (sel && sel.value) handleAssignFacility(fac.id, parseInt(sel.value))
            }} disabled={facilityLoading}>Assign</button>
          </div>
        )}

        {/* Market Shop */}
        {fac.type === 'Market' && Object.keys(marketCatalog).length > 0 && (
          <div style={{ marginTop: '1rem', background: 'rgba(0,0,0,0.2)', padding: '0.75rem', borderRadius: 6 }}>
            <div className="text-dim" style={{ marginBottom: '0.5rem', fontSize: '0.85rem' }}>Shop</div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: '0.5rem' }}>
              {Object.entries(marketCatalog).map(([itemId, item]) => (
                <div key={itemId} className="card" style={{ padding: '0.5rem', display: 'flex', flexDirection: 'column', gap: '0.3rem' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                    <ItemIcon name={item.name} kind="material" size={26} />
                    <div style={{ fontSize: '0.85rem', fontWeight: 'bold' }}>{item.name}</div>
                  </div>
                  <button className="btn btn-gold" onClick={() => handlePurchase(itemId)}
                    disabled={purchasing || (item.currency === 'gold' ? base.gold : base.gems) < item.cost}
                    style={{ fontSize: '0.72rem', padding: '0.3rem', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6 }}>
                    <span style={{ width: 8, height: 8, transform: 'rotate(45deg)', display: 'inline-block', flex: 'none', background: item.currency === 'gold' ? '#7a5a20' : '#5a2a90', boxShadow: item.currency === 'gem' ? '0 0 6px rgba(90,42,144,.8)' : 'none' }} />
                    {item.cost} {item.currency === 'gold' ? 'GOLD' : 'GEMS'}
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Mage Tower Research */}
        {fac.type === 'Mage Tower' && mageUpgrades && (
          <div style={{ marginTop: '1rem', background: 'rgba(0,0,0,0.2)', padding: '0.75rem', borderRadius: 6 }}>
            <div style={{ color: 'var(--purple)', marginBottom: '0.5rem' }}>Research Points: {mageUpgrades.points}</div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))', gap: '0.5rem' }}>
              {mageUpgrades.upgrades.map(u => (
                <div key={u.id} className="card" style={{ padding: '0.5rem' }}>
                  <div style={{ fontSize: '0.85rem', fontWeight: 'bold' }}>{u.name} (Lv.{u.level}/{u.max_level})</div>
                  <div style={{ fontSize: '0.7rem', color: 'var(--text-dim)', margin: '0.2rem 0 0.5rem' }}>{u.desc}</div>
                  <button className="btn" onClick={() => handleBuyResearch(u.id)} disabled={facilityLoading || u.level >= u.max_level || mageUpgrades.points < u.cost} style={{ width: '100%', fontSize: '0.75rem', padding: '0.2rem' }}>
                    {u.level >= u.max_level ? 'MAX' : `Research (${u.cost} RP)`}
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* The Athenaeum research map */}
        {fac.type === 'Athenaeum' && (
          <AthenaeumPanel aether={base.aether} onResourceChange={() => { loadAll(); if (onGoldChange) onGoldChange() }} />
        )}

        {/* Mirror of Fate */}
        {fac.type === 'Mirror of Fate' && (
          <MirrorOfFate level={fac.level} gold={base.gold} onGoldChange={() => { loadAll(); if (onGoldChange) onGoldChange() }} />
        )}

        {/* Base-upgrade enhancement tracks */}
        {fac.type === 'Infirmary' && (
          <UpgradeTreePanel upgrade={baseUpgrades.find(u => u.id === 'infirmary')} gold={base.gold} busy={upgradingId === 'infirmary'} onBuy={handleBuyBaseUpgrade} />
        )}
        {fac.type === 'Forge' && (
          <>
            <UpgradeTreePanel upgrade={baseUpgrades.find(u => u.id === 'forge')} gold={base.gold} busy={upgradingId === 'forge'} onBuy={handleBuyBaseUpgrade} />
            <RecipeBookPanel assignedHeroes={fac.heroes} gold={base.gold} materials={materials} onCrafted={() => { loadAll(); if (onGoldChange) onGoldChange() }} />
          </>
        )}

        {/* Training Grounds */}
        {fac.type === 'Training Grounds' && (
          <TrainingGroundsPanel onChanged={() => { loadAll() }} />
        )}

        {/* Economy + endgame facility panels */}
        {fac.type === 'Dining Hall' && <CookingPanel facility={fac} onResourceChange={() => { loadAll(); if (onGoldChange) onGoldChange() }} />}
        {fac.type === 'Alchemist Lab' && <RefineAetherPanel facility={fac} onResourceChange={() => { loadAll(); if (onGoldChange) onGoldChange() }} />}
        {fac.type === 'Bestiary' && <BestiaryPanel />}
        {fac.type === 'Shrine' && <ShrineRitePanel facility={fac} onResourceChange={() => loadAll()} />}
        {fac.type === 'Reliquary' && <ReliquaryPanel />}
        {fac.type === 'Chronosphere' && <ChronospherePanel onResourceChange={() => { loadAll(); if (onGoldChange) onGoldChange() }} />}
        {fac.type === 'Transcendence Core' && <TranscendencePanel gold={base.gold} onResourceChange={() => { loadAll(); if (onGoldChange) onGoldChange() }} />}
      </>
    )
  }

  // Interior backdrop art tracks the Wall: gate variant once a Wall stands,
  // open palisade before one exists; visual tier steps with Wall level
  // (same 13/26/39 bands as facility card art).
  const wallFac = facilitiesData?.built?.find(f => f.type === 'Wall')
  const bdTier = wallFac ? (wallFac.level >= 39 ? 4 : wallFac.level >= 26 ? 3 : wallFac.level >= 13 ? 2 : 1) : 1
  const backdrop = `/images/base/interior_${wallFac ? 'gate' : 'nogate'}_t${bdTier}.png`

  return (
    <div className="page">
      {/* No page backdrop — the painted interiors belong to individual
          facilities, not the whole base (user call: it messes with the vibe). */}
      <div className="ilm-base-layout">
        {/* ═══ persistent left console (Home Base mockup) ═══ */}
        <aside className="ilm-base-console">
          {(() => {
            // Title changes per sub-tab (user ask): Lobby keeps HOME BASE·HAVEN;
            // Facilities and Hierarchy get their own solid + ghost stacks.
            const t = activeTab === 'facilities'
              ? { eyebrow: 'Between Climbs', solid: 'FACILITIES', ghost: 'THE WORKS' }
              : activeTab === 'foundations'
                // FOUNDATIONS is a long word — smaller sizes so it stays inside
                // the 420px console instead of running under the art panels.
                ? { eyebrow: 'Home Base', solid: 'FOUNDATIONS', ghost: 'BEDROCK', solidSize: 42, ghostSize: 38 }
              : activeTab === 'floors'
                ? { eyebrow: 'Home Base', solid: 'HIERARCHY', ghost: 'ASCEND' }
                : { eyebrow: 'Between Climbs', solid: 'HOME BASE', ghost: 'HAVEN' }
            return <StackedTitle eyebrow={t.eyebrow} ghost={t.ghost} solid={t.solid} solidSize={t.solidSize} ghostSize={t.ghostSize} />
          })()}

          {renderTabs()}

          {/* HIERARCHY tab console — the mock shows the hierarchy LEDGER here
              (not the income/chatter, which belong to the Lobby), so the floors
              on the right get the whole canvas and can be big. */}
          {activeTab === 'floors' && floorsData ? (() => {
            const raised = floorsData.floors.length
            const housed = floorsData.floors.reduce((s2, f) => s2 + f.heroes.length, 0)
            const nextUnlockTower = (raised + 1) * 10
            return (
              <>
                <div style={{ fontSize: 16, fontStyle: 'italic', color: '#c8b8dd', lineHeight: 1.6, marginTop: 6 }}>
                  Every hero lives on a floor of your base. The fewer souls a floor houses, the greater
                  its blessing on each — spread thin for power, pack deep for coverage.
                </div>
                <div style={{ marginTop: 20 }}>
                  {[['FLOORS RAISED', raised, 'var(--gold-hi)'], ['HEROES HOUSED', housed, 'var(--text-hi)'], ['NEXT FLOOR', `AT TOWER FLOOR ${nextUnlockTower}`, 'var(--gold-hi)']].map(([k, v, c]) => (
                    <div key={k} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', padding: '12px 0', borderBottom: '1px solid rgba(184,151,98,.2)' }}>
                      <span style={{ fontFamily: "'Cinzel',serif", letterSpacing: '.22em', fontSize: 11, color: 'var(--muted)' }}>{k}</span>
                      <span style={{ fontFamily: typeof v === 'number' ? "'Cormorant Garamond',serif" : "'Cinzel',serif", fontWeight: 700, fontSize: typeof v === 'number' ? 24 : 13, letterSpacing: typeof v === 'number' ? 0 : '.1em', color: c }}>{v}</span>
                    </div>
                  ))}
                </div>
                <button className="btn btn-primary" onClick={() => setRehouseMode(m => !m)}
                  style={{ width: '100%', marginTop: 20, padding: '14px 0', fontSize: '0.9rem', letterSpacing: '.24em' }}>
                  {rehouseMode ? 'DONE REHOUSING' : 'REHOUSE HEROES'}
                </button>
                {rehouseMode && (
                  <div style={{ fontSize: 13, fontStyle: 'italic', color: 'var(--muted)', marginTop: 12, lineHeight: 1.5 }}>
                    Drag a soul between floors — or click one to send them down to the Foundations.
                  </div>
                )}
              </>
            )
          })() : (
            <>
              <div className="ilm-base-stat">
                <span className="ilm-base-stat-k">GOLD INCOME</span>
                <span className="ilm-base-stat-v" style={{ color: 'var(--gold-hi)' }}>+{(goldGen * 288).toLocaleString()} / day</span>
              </div>
              <div className="ilm-base-stat">
                <span className="ilm-base-stat-k">INGREDIENTS</span>
                <span className="ilm-base-stat-v" style={{ color: '#8fbf9f' }}>+{(ingredientsGen * 288).toLocaleString()} / day</span>
              </div>
              <div className="ilm-base-stat">
                <span className="ilm-base-stat-k">AETHER</span>
                <span className="ilm-base-stat-v" style={{ color: '#8fb8ff' }}>+{(aetherGen * 288).toLocaleString()} / day</span>
              </div>
              <div className="ilm-base-stat">
                <span className="ilm-base-stat-k">ROSTER</span>
                <span className="ilm-base-stat-v">
                  <b style={{ color: 'var(--text-hi)' }}>{baseHeroes.length} heroes</b>
                  {(() => { const shaken = baseHeroes.filter(h => (h.morale ?? 100) < 40).length; return shaken > 0 ? <span style={{ color: '#d98a8a' }}> · {shaken} shaken</span> : null })()}
                </span>
              </div>

              {/* hero chatter */}
              <div style={{ marginTop: '1.4rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
                  <span style={{ width: 7, height: 7, transform: 'rotate(45deg)', background: 'var(--gold)', display: 'inline-block' }} />
                  <span style={{ fontFamily: "'Cinzel',serif", letterSpacing: '.3em', fontSize: '0.6rem', color: 'var(--gold)' }}>HERO CHATTER</span>
                </div>
                {chats.length === 0 && <div className="text-dim" style={{ fontSize: '0.85rem', fontStyle: 'italic' }}>The halls are quiet for now.</div>}
                {chats.slice(0, 4).map(l => (
                  <div key={l._k} className={`ilm-base-chatter ${newChatIds.has(l._k) ? 'fresh' : ''}`}
                    style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                    <span style={{ padding: 5, flex: 'none' }}>
                      <DiamondPortrait heroId={l.hero_id} name={l.speaker} size={26} shaken={l.mood === 'shaken'} />
                    </span>
                    <span style={{ minWidth: 0 }}>
                      <span className="ilm-base-chatter-who">{(l.speaker || 'A hero').toUpperCase()}</span>
                      <span className="ilm-base-chatter-line"> — “{l.message}”</span>
                    </span>
                  </div>
                ))}
              </div>
            </>
          )}
        </aside>

        {/* ═══ main content column ═══ */}
        <main className="ilm-base-main">

      {activeTab === 'lobby' && (() => {
        // Weary check feeds a single pointer line — mending itself belongs to
        // the facilities now (Dining Hall / rest between floors), so the old
        // Rest & Recovery panel is gone per Liam.
        const hurting = baseHeroes
          .filter(h => (h.morale ?? 100) < 70 || (h.trauma ?? 0) > 30)
          .sort((a, b) => (a.morale ?? 100) - (b.morale ?? 100))
        const recentLegacies = legacies.slice(0, 2)
        const floor = base.highest_floor || 0
        // 10-floor bands = zones; progress within the current band.
        const bandStart = Math.floor(floor / 10) * 10
        const bandPct = ((floor - bandStart) / 10) * 100
        // What the Tower still holds locked: floor-gated facilities, nearest first.
        const sealed = (facilitiesData?.available || [])
          .filter(f => f.floor_restricted && f.unlock_floor > floor)
          .sort((a, b) => a.unlock_floor - b.unlock_floor)
          .slice(0, 4)
        return (
        <div style={{ display: 'flex', gap: 24, alignItems: 'flex-start', flexWrap: 'wrap' }}>
          {/* ── center column ── */}
          <div style={{ flex: '1.2 1 420px', minWidth: 380, display: 'flex', flexDirection: 'column', gap: 16 }}>
            {/* the climb — tower progress + what the next floors unseal */}
            <div style={{ border: '1px solid rgba(184,151,98,.4)', background: 'linear-gradient(160deg,rgba(20,11,34,.5),rgba(12,7,24,.6))', padding: '16px 18px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <span style={{ width: 7, height: 7, transform: 'rotate(45deg)', background: 'var(--gold)', display: 'inline-block' }} />
                <span style={{ fontFamily: "'Cinzel',serif", letterSpacing: '.3em', fontSize: 11, color: 'var(--gold)' }}>THE CLIMB</span>
                <span style={{ height: 1, flex: 1, background: 'rgba(184,151,98,.2)' }} />
                <span style={{ fontFamily: "'Cinzel',serif", fontSize: 10, letterSpacing: '.18em', color: '#ffd88a' }}>DEEPEST · FLOOR {floor}</span>
              </div>
              <div style={{ fontSize: 14.5, fontStyle: 'italic', color: 'var(--muted)', marginTop: 8, lineHeight: 1.45 }}>
                {floor === 0
                  ? 'The first floor waits. Everything the base becomes starts with the climb.'
                  : 'Every floor taken feeds the base — and the Tower keeps its best rooms sealed above.'}
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 12 }}>
                <span style={{ fontFamily: "'Cinzel',serif", fontSize: 10, letterSpacing: '.16em', color: 'var(--muted)', whiteSpace: 'nowrap' }}>FLOORS {bandStart}–{bandStart + 10}</span>
                <div style={{ flex: 1 }}><Meter pct={bandPct} glow /></div>
              </div>
              <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 7 }}>
                {sealed.length === 0 ? (
                  <div style={{ fontStyle: 'italic', color: 'var(--muted)', fontSize: 14 }}>Nothing near stands sealed — the Tower owes its next secret to a deeper floor.</div>
                ) : sealed.map(f => (
                  <div key={f.type} style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
                    <span style={{ fontFamily: "'Cinzel',serif", fontSize: 12, letterSpacing: '.12em', color: 'var(--text-hi)' }}>{f.type.toUpperCase()}</span>
                    <span style={{ height: 1, flex: 1, background: 'rgba(184,151,98,.15)' }} />
                    <span style={{ fontFamily: "'Cinzel',serif", fontSize: 10, letterSpacing: '.14em', color: f.unlock_floor - floor <= 2 ? '#8fbf9f' : 'var(--muted)' }}>
                      UNSEALS AT FLOOR {f.unlock_floor}
                    </span>
                  </div>
                ))}
              </div>
              {hurting.length > 0 && (
                <div style={{ marginTop: 12, fontSize: 13.5, fontStyle: 'italic', color: '#d9b98a' }}>
                  {hurting.length === 1 ? `${hurting[0].name} climbs weary` : `${hurting.length} souls climb weary`} — the Dining Hall and a slow floor mend what the Tower bruises.
                </div>
              )}
              {msg && <div style={{ marginTop: 10, fontSize: 14, fontStyle: 'italic', color: '#8fbf9f' }}>{msg}</div>}
            </div>

            {/* legacies of the fallen */}
            <div style={{ border: '1px solid rgba(150,110,230,.35)', background: 'linear-gradient(160deg,rgba(42,22,80,.28),rgba(12,7,24,.6))', padding: '16px 18px', clipPath: 'polygon(0 0,100% 0,100% 100%,12px 100%)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <span style={{ width: 7, height: 7, transform: 'rotate(45deg)', background: 'var(--violet)', display: 'inline-block' }} />
                <span style={{ fontFamily: "'Cinzel',serif", letterSpacing: '.3em', fontSize: 11, color: 'var(--lavender)' }}>LEGACIES OF THE FALLEN</span>
                <span style={{ height: 1, flex: 1, background: 'rgba(150,110,230,.25)' }} />
                <span style={{ fontFamily: "'Cinzel',serif", fontSize: 10, letterSpacing: '.18em', color: 'var(--muted)' }}>{legacies.length} REMEMBERED</span>
              </div>
              <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 9, fontSize: 16 }}>
                {recentLegacies.length === 0 && (
                  <div style={{ fontStyle: 'italic', color: 'var(--muted)', fontSize: 14 }}>No hero has yet fallen. May it stay that way.</div>
                )}
                {recentLegacies.map(leg => {
                  const bonus = (() => { try { return JSON.parse(leg.bonus_json || '{}') } catch { return {} } })()
                  return (
                    <div key={leg.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 12 }}>
                      <span style={{ minWidth: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        <span style={{ fontFamily: "'Cinzel',serif", fontSize: 12.5, letterSpacing: '.1em', color: 'var(--text-hi)' }}>{(leg.hero_name || '').toUpperCase()}</span>
                        <span style={{ fontStyle: 'italic', color: 'var(--muted)' }}> — {leg.is_sacrifice ? 'given to the rite' : 'fell in the Tower'}</span>
                      </span>
                      <span style={{ color: 'var(--lavender)', fontWeight: 600, whiteSpace: 'nowrap' }}>{bonus.primary_bonus?.desc || leg.title || ''}</span>
                    </div>
                  )
                })}
                <button onClick={() => setShowMemorial(true)}
                  style={{ background: 'none', border: 'none', cursor: 'pointer', textAlign: 'left', padding: 0, fontFamily: "'Cinzel',serif", fontSize: 10, letterSpacing: '.24em', color: 'var(--muted)', marginTop: 2 }}>
                  VIEW THE MEMORIAL ›
                </button>
              </div>
            </div>

            {/* lore journal teaser */}
            <button onClick={() => setShowLore(true)}
              style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, border: '1px solid rgba(184,151,98,.28)', background: 'rgba(12,7,24,.4)', padding: '12px 18px', cursor: 'pointer', width: '100%' }}>
              <span style={{ fontFamily: "'Cinzel',serif", letterSpacing: '.24em', fontSize: 11, color: '#c9bfa8' }}>LORE JOURNAL</span>
              <span style={{ fontSize: 15, fontStyle: 'italic', color: 'var(--muted)' }}>chronicles written by the climb</span>
              <span style={{ fontFamily: "'Cinzel',serif", fontSize: 12, color: 'var(--gold-hi)' }}>READ ›</span>
            </button>

            {/* treasury ledger */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 12 }}>
              {[
                ['TREASURY', base.gold.toLocaleString(), 'var(--gold-hi)', goldGen > 0 ? `+${goldGen} / 5m` : null],
                ['INGREDIENTS', (base.ingredients ?? 0).toLocaleString(), '#8fbf9f', ingredientsGen > 0 ? `+${ingredientsGen} / 5m` : null],
                ['AETHER', (base.aether || 0).toLocaleString(), '#8fb8ff', aetherGen > 0 ? `+${aetherGen} / 5m` : null],
              ].map(([k, v, c, gen]) => (
                <div key={k} style={{ border: '1px solid rgba(184,151,98,.25)', background: 'rgba(12,7,24,.45)', padding: '10px 14px' }}>
                  <div style={{ fontFamily: "'Cinzel',serif", letterSpacing: '.22em', fontSize: 9, color: 'var(--muted)' }}>{k}</div>
                  <div style={{ fontFamily: "'Cormorant Garamond',serif", fontWeight: 700, fontSize: 22, color: c, lineHeight: 1.2 }}>{v}</div>
                  {gen && <div style={{ fontFamily: "'Cinzel',serif", fontSize: 8, letterSpacing: '.12em', color: 'var(--muted)' }}>{gen}</div>}
                </div>
              ))}
            </div>
          </div>

          {/* ── right: the hanging banner ── */}
          <div style={{ flex: '1 1 320px', minWidth: 300, position: 'relative', paddingTop: 16 }}>
            {/* hanging rod + the two cords the banner is suspended from — the
                cords bridge the rod to the cloth so it reads as CONNECTED, not
                floating below a bar. */}
            <div style={{ position: 'relative', height: 20, zIndex: 2 }}>
              <div style={{ position: 'absolute', left: 10, right: 10, top: 8, height: 3, background: 'linear-gradient(90deg,rgba(184,151,98,0),#b89762 12%,#b89762 88%,rgba(184,151,98,0))' }} />
              <div style={{ position: 'absolute', left: 6, top: 2, width: 14, height: 14, transform: 'rotate(45deg)', border: '1px solid var(--gold)', background: '#0c0718' }} />
              <div style={{ position: 'absolute', right: 6, top: 2, width: 14, height: 14, transform: 'rotate(45deg)', border: '1px solid var(--gold)', background: '#0c0718' }} />
              {/* cords */}
              <div style={{ position: 'absolute', left: 'calc(50% - 58px)', top: 9, width: 1, height: 22, background: 'linear-gradient(#b89762,rgba(184,151,98,.35))' }} />
              <div style={{ position: 'absolute', left: 'calc(50% + 57px)', top: 9, width: 1, height: 22, background: 'linear-gradient(#b89762,rgba(184,151,98,.35))' }} />
            </div>
            {/* banner cloth — unfurls from the rod on mount (scaleY), then sways.
                The unfurl and the sway live on separate nested elements so the
                scaleY and the rotate can't fight each other. The cloth top sits
                just below the rod (the thin cords bridge the small gap) — it is
                NOT tucked under the rod, so the whole banner, tip included,
                lights up in the entrance sweep. */}
            <div style={{ transformOrigin: 'top center', animation: 'banner-unfurl 0.95s cubic-bezier(.2,.9,.3,1) both', display: 'flex', flexDirection: 'column', alignItems: 'center', marginTop: 0 }}>
              <div style={{ transformOrigin: 'top center', animation: 'banner-sway 7s ease-in-out 0.95s infinite', display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
              <div className="hover-brighten" onClick={() => setShowBannerStudio(true)} title="Click to customize your Team Banner" style={{ cursor: 'pointer', position: 'relative', animation: 'banner-lightup 1.4s ease-out both' }}>
                <TeamBanner banner={banner} size={250} style={{ alignItems: 'flex-start' }} />
                {/* one-shot light sweep down the cloth as it lands — from the very top */}
                <div style={{ position: 'absolute', left: '50%', top: 0, width: Math.round(250 / 1.8), height: 250, transform: 'translateX(-50%)', overflow: 'hidden', pointerEvents: 'none', clipPath: 'polygon(0 0,100% 0,100% 82%,50% 100%,0 82%)' }}>
                  <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(180deg,transparent,rgba(230,215,255,.55),transparent)', animation: 'banner-shine 1.5s ease-out 0.5s both' }} />
                </div>
              </div>
              <div style={{ textAlign: 'center', marginTop: 14 }}>
                {/* World name is Tower-granted, never player-chosen */}
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10 }}>
                  <span title="Every Master's world is named by the Tower itself" style={{ fontFamily: "'Cinzel',serif", fontWeight: 700, letterSpacing: '.3em', fontSize: 17, color: 'var(--text-hi)' }}>{base.name?.toUpperCase()}</span>
                </div>
                <div style={{ fontFamily: "'Cinzel',serif", letterSpacing: '.24em', fontSize: 10, color: 'var(--muted)', marginTop: 5 }}>
                  LOBBY LV {base.level} · ROSTER {baseHeroes.length} / {base.max_roster_size || 10}
                  {base.difficulty && base.difficulty !== 'normal' && <span style={{ color: base.difficulty === 'hard' ? '#d98a8a' : '#8fbf9f' }}> · {base.difficulty.toUpperCase()}</span>}
                </div>
              </div>
              </div>
            </div>
            <div style={{ textAlign: 'center', marginTop: 22 }}>
              <button onClick={() => setShowBannerStudio(true)}
                style={{ fontFamily: "'Cinzel',serif", fontWeight: 600, letterSpacing: '.24em', fontSize: 12, color: '#cdbfe4', background: 'none', border: '1px solid rgba(150,110,230,.45)', padding: '10px 22px', clipPath: 'polygon(10px 0,100% 0,calc(100% - 10px) 100%,0 100%)', cursor: 'pointer' }}>
                BANNER STUDIO
              </button>
            </div>
          </div>
        </div>
        )
      })()}

      {/* ═══ FOUNDATIONS — the base's structure: the Lobby (roster roof) and the
          Wall (facility ceiling), as two big art panels each clearly upgradeable. ═══ */}
      {activeTab === 'foundations' && (() => {
        const cap = base.max_roster_size || 10
        const wall = facilitiesData?.built?.find(f => f.type === 'Wall')
        const wallLevel = wall?.level ?? 1
        // artPos frames each image inside the strip: the lobby art is 2.33:1
        // (near the strip's shape, slight crop), the wall art is 16:9 so the
        // strip can only show a band of it — aim that band at the gate.
        const panels = [
          { key: 'lobby', title: 'THE LOBBY', art: facArt('Lobby', base.level), artPos: 'center 62%', sigil: 'LOBBY', lv: base.level,
            desc: 'The heart of the base — every level widens the roster’s roof.',
            stat: `CAPACITY ${baseHeroes.length} / ${cap}`, pct: (baseHeroes.length / cap) * 100,
            action: { label: `UPGRADE · ${(5000 * base.level).toLocaleString()}`, onClick: handleUpgradeBase, disabled: base.gold < 5000 * base.level } },
          { key: 'wall', title: 'THE WALL', art: facArt('Wall', wallLevel), artPos: 'center 38%', sigil: 'WALL', lv: wallLevel,
            desc: 'The bulwark. No facility may rise above the Wall — raise it to unlock deeper upgrades.',
            stat: `FACILITY CEILING · LV ${wallLevel}`, pct: null,
            action: (wall && wall.level < wall.max_level) ? { label: `UPGRADE · ${wall.upgrade_cost}g`, onClick: () => handleUpgradeFacility(wall.id), disabled: base.gold < wall.upgrade_cost } : null },
        ]
        return (
          // Stacked, full-width — each panel is a long strip, so the wide art
          // shows nearly its whole scene instead of a side-by-side crop.
          <div style={{ display: 'flex', flexDirection: 'column', gap: 22 }}>
            {panels.map(p => (
              <div key={p.key} className="ilm-foundation-panel">
                {p.art && <img src={p.art} alt="" className="ilm-foundation-art" style={{ objectPosition: p.artPos }} onError={(e) => { e.currentTarget.style.display = 'none' }} />}
                <span className="ilm-foundation-scrim" />
                <span className="ilm-corner" /><span className="ilm-corner ilm-corner-r" />
                <div className="ilm-foundation-body">
                  <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
                    <span className="ilm-mono" style={{ width: 44, height: 44, flex: 'none' }}><Sigil set="facility" name={p.sigil} size={24} color="var(--gold-hi)" fallback={<span style={{ color: 'var(--gold-hi)' }}>◆</span>} /></span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
                        <span style={{ fontFamily: "'Cinzel',serif", fontWeight: 900, fontSize: '1.7rem', color: 'var(--text-hi)', letterSpacing: '.04em', textShadow: '0 1px 8px rgba(0,0,0,.95)' }}>{p.title}</span>
                        <span className="ilm-micro" style={{ color: 'var(--gold-hi)' }}>LV {p.lv}</span>
                      </div>
                      <div className="text-dim" style={{ fontStyle: 'italic', fontSize: '0.9rem', textShadow: '0 1px 6px rgba(0,0,0,.95)', marginTop: 2 }}>{p.desc}</div>
                    </div>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginTop: 16 }}>
                    <span className="ilm-micro" style={{ color: 'var(--muted)', whiteSpace: 'nowrap' }}>{p.stat}</span>
                    {p.pct != null ? <div style={{ flex: 1 }}><Meter pct={p.pct} glow /></div> : <span style={{ flex: 1 }} />}
                    {p.action
                      ? <button className="ilm-btn ilm-btn-gold" onClick={p.action.onClick} disabled={p.action.disabled}>{p.action.label}</button>
                      : <span className="ilm-micro" style={{ color: 'var(--muted)' }}>MAX LEVEL</span>}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )
      })()}

      {activeTab === 'facilities' && (() => {
        // Wall lives on the Foundations tab now (with the Lobby), so keep it out
        // of the buildable-facilities grid.
        const catMatch = fac => (facilityFilter === 'All' || facilityCategory(fac.type) === facilityFilter) && fac.type !== 'Wall'
        const built = facilitiesData.built.filter(catMatch).sort((a, b) => a.cost - b.cost)
        const inCat = facilitiesData.available.filter(catMatch).sort((a, b) => a.cost - b.cost)
        let avail = inCat.filter(f => !f.floor_restricted)
        if (avail.length === 0 && inCat.length > 0) {
          const nf = Math.min(...inCat.map(f => f.unlock_floor))
          avail = inCat.filter(f => f.unlock_floor === nf)
        }
        const selFac = facilitiesData.built.find(f => f.id === selFacId)
        const cap = base.max_roster_size || 10
        return (
          <>
            {/* filter chips + card/list view toggle */}
            <div className="ilm-fac-chips">
              {FACILITY_CATEGORIES.map(cat => (
                <button key={cat} className={`ilm-fac-chip ${facilityFilter === cat ? 'active' : ''}`} onClick={() => setFacilityFilter(cat)}>
                  {cat.toUpperCase()}
                </button>
              ))}
              <span style={{ flex: 1 }} />
              <span className="ilm-fac-count" style={{ marginRight: 12 }}>{built.length} OF {built.length + avail.length}</span>
              <div className="ilm-fac-viewtoggle">
                {[['cards', '▦ CARDS'], ['list', '☰ LIST']].map(([v, label]) => (
                  <button key={v} className={`ilm-fac-viewbtn ${facilityView === v ? 'active' : ''}`} onClick={() => setFacView(v)}>{label}</button>
                ))}
              </div>
            </div>

            {/* facilities grid — the Lobby moved to the Lobby tab (A1). The grid
                scrolls within its OWN region (B) so the base page never grows
                unbounded as more facilities get built. */}
            <div className="ilm-fac-scroll">
            {facilityView === 'list' ? (
            <div className="ilm-fac-list">
              {built.map(fac => (
                <button key={fac.id} className={`ilm-fac-listrow ${selFacId === fac.id ? 'sel' : ''}`}
                  onClick={() => setSelFacId(selFacId === fac.id ? null : fac.id)}>
                  <span className="ilm-mono ilm-fac-mono" style={{ width: 30, height: 30 }}><Sigil set="facility" name={facSig(fac.type)} size={17} color="var(--gold-hi)" fallback={<span style={{ color: 'var(--gold-hi)' }}>{fac.type[0]}</span>} /></span>
                  <span className="ilm-fac-card-name" style={{ flex: 1 }}>{fac.type}</span>
                  {getGenRate(fac) && <span style={{ fontSize: '0.72rem', color: 'var(--green-hi)', marginRight: 12, whiteSpace: 'nowrap' }}>{getGenRate(fac).replace('Generating: ', '')}</span>}
                  <span className="ilm-fac-lv" style={{ marginRight: 14 }}>LV {fac.level}</span>
                  {fac.level < fac.max_level && (
                    <span className={`ilm-fac-listaction ${fac.wall_capped ? 'capped' : ''}`}
                      onClick={(e) => { e.stopPropagation(); if (!fac.wall_capped && base.gold >= fac.upgrade_cost) handleUpgradeFacility(fac.id) }}
                      title={fac.wall_capped ? `Wall Lv.${fac.level + 1} required` : `Upgrade (${fac.upgrade_cost}g)`}>
                      {fac.wall_capped ? (<><Sigil set="facility" name={facSig('Wall')} size={11} color="var(--red-hi)" fallback={<span>◱</span>} /> WALL {fac.level + 1}</>) : `UPGRADE · ${fac.upgrade_cost}g`}
                    </span>
                  )}
                </button>
              ))}
              {avail.map(fac => (
                <div key={fac.type} className="ilm-fac-listrow locked">
                  <span className="ilm-mono ilm-fac-mono" style={{ width: 30, height: 30, opacity: .55 }}><Sigil set="facility" name={facSig(fac.type)} size={17} color="var(--muted)" fallback={<span style={{ color: 'var(--muted)' }}>{fac.type[0]}</span>} /></span>
                  <span className="ilm-fac-card-name" style={{ flex: 1, color: 'var(--text-dim)' }}>{fac.type}</span>
                  {fac.floor_restricted
                    ? <span style={{ fontSize: '0.72rem', color: 'var(--lavender)', marginRight: 14, whiteSpace: 'nowrap' }}>Sealed · floor {fac.unlock_floor}</span>
                    : <span className="ilm-fac-listaction build" onClick={() => { if (base.gold >= fac.cost) handleBuildFacility(fac.type) }} title={`Build (${fac.cost}g)`}>BUILD · {fac.cost}g</span>}
                </div>
              ))}
            </div>
            ) : (
            <div className="ilm-fac-grid">
              {built.map(fac => (
                <button key={fac.id} className={`ilm-fac-card ${selFacId === fac.id ? 'sel' : ''}`}
                  onClick={() => setSelFacId(selFacId === fac.id ? null : fac.id)}>
                  <div className="ilm-fac-card-art">
                    {facArt(fac.type, fac.level) && (
                      <img src={facArt(fac.type, fac.level)} alt="" className="ilm-fac-card-art-img"
                        onError={(e) => { e.currentTarget.style.display = 'none' }} />
                    )}
                    <span className="ilm-fac-card-art-ph">facility art png · full bleed</span>
                  </div>
                  <div className="ilm-fac-card-body">
                    <span className="ilm-mono ilm-fac-mono"><Sigil set="facility" name={facSig(fac.type)} size={20} color="var(--gold-hi)" fallback={<span style={{ color: 'var(--gold-hi)' }}>{fac.type[0]}</span>} /></span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div className="ilm-fac-card-name">{fac.type}</div>
                      {getGenRate(fac) && <div className="ilm-fac-card-gen">{getGenRate(fac).replace('Generating: ', '')}</div>}
                    </div>
                    <span className="ilm-fac-lv">LV {fac.level}</span>
                  </div>
                  {fac.level < fac.max_level && (
                    <span className={`ilm-fac-upgrade ${fac.wall_capped ? 'capped' : ''}`}
                      onClick={(e) => { e.stopPropagation(); if (!fac.wall_capped && base.gold >= fac.upgrade_cost) handleUpgradeFacility(fac.id) }}
                      title={fac.wall_capped ? `Wall Lv.${fac.level + 1} required` : `Upgrade (${fac.upgrade_cost}g)`}>
                      {fac.wall_capped ? (
                        <><Sigil set="facility" name={facSig('Wall')} size={13} color="var(--red-hi)" fallback={<span>◱</span>} /> WALL LV.{fac.level + 1}</>
                      ) : `UPGRADE · ${fac.upgrade_cost}g`}
                    </span>
                  )}
                </button>
              ))}
              {avail.map(fac => (
                <div key={fac.type} className="ilm-fac-card locked">
                  <div className="ilm-fac-card-art">
                    {!fac.floor_restricted && facArt(fac.type, 1) && (
                      <img src={facArt(fac.type, 1)} alt="" className="ilm-fac-card-art-img" style={{ opacity: 0.35, filter: 'grayscale(.5)' }}
                        onError={(e) => { e.currentTarget.style.display = 'none' }} />
                    )}
                    <span className="ilm-fac-card-art-ph">{fac.floor_restricted ? '?' : 'buildable'}</span>
                  </div>
                  <div className="ilm-fac-card-body">
                    <span className="ilm-mono ilm-fac-mono" style={{ opacity: 0.55 }}><Sigil set="facility" name={facSig(fac.type)} size={20} color="var(--muted)" fallback={<span style={{ color: 'var(--muted)' }}>{fac.type[0]}</span>} /></span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div className="ilm-fac-card-name" style={{ color: 'var(--text-dim)' }}>{fac.type}</div>
                      {fac.floor_restricted
                        ? <div className="ilm-fac-card-gen" style={{ color: 'var(--lavender)' }}>Sealed until floor {fac.unlock_floor}</div>
                        : <div className="ilm-fac-card-gen" title={FACILITY_TOOLTIPS[fac.type] || 'Base facility.'}>Ready to raise</div>}
                    </div>
                  </div>
                  {!fac.floor_restricted && (
                    <span className="ilm-fac-upgrade build" onClick={() => { if (base.gold >= fac.cost) handleBuildFacility(fac.type) }}
                      title={`Build (${fac.cost}g)`}>
                      BUILD · {fac.cost}g
                    </span>
                  )}
                </div>
              ))}
            </div>
            )}
            </div>{/* /ilm-fac-scroll */}

            {/* Detail opens as a MODAL overlay (like Hero Detail) instead of a
                panel appended below the grid — clicking a card no longer drops
                the content way down the page. Scrim scrolls (align-items:
                flex-start), modal max-width:100% is zoom-safe. */}
            {selFac && (
              // Default scrim z-index (1000) sits ABOVE the topbar (z-index 100);
              // the earlier zIndex:100 override let the topbar cover the modal's
              // top edge. Centered both axes — the modal caps at max-height and
              // scrolls internally, so centering never clips a tall facility.
              <div className="ilm-modal-scrim" style={{ padding: '28px' }} onClick={() => setSelFacId(null)}>
                <div className="ilm-facmodal" onClick={e => e.stopPropagation()}>
                  <span className="ilm-corner" />
                  <span className="ilm-corner ilm-corner-r" />
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
                    <span className="ilm-mono" style={{ width: 34, height: 34 }}><Sigil set="facility" name={facSig(selFac.type)} size={20} color="var(--gold-hi)" fallback={<span style={{ color: 'var(--gold-hi)' }}>{selFac.type[0]}</span>} /></span>
                    <span style={{ fontFamily: "'Cinzel',serif", fontWeight: 900, fontSize: '1.3rem', color: 'var(--text-hi)' }}>{selFac.type}</span>
                    <span className="ilm-micro" style={{ color: 'var(--gold-hi)' }}>LV {selFac.level}</span>
                    <span title={FACILITY_TOOLTIPS[selFac.type] || 'Base facility.'} style={{ color: 'var(--gold)', cursor: 'help', fontSize: '0.8rem' }}>[?]</span>
                    <button className="ilm-close" style={{ marginLeft: 'auto' }} onClick={() => setSelFacId(null)}>✕</button>
                  </div>
                  {(() => {
                    const boon = facilityBoon(selFac.type, boons)
                    if (!boon) return null
                    if (boon.active) {
                      import('../codexBus').then(c => c.unlockCodex('boons', 'COMPANY BOONS')).catch(() => {})
                      return (
                        <div className="ilm-boon-banner active">
                          <div className="ilm-boon-eyebrow">◆ COMPANY BOON · ACTIVE</div>
                          <div className="ilm-boon-title">{boon.title}</div>
                          {boon.lines.map((l, i) => <div key={i} className="ilm-boon-line">{l}</div>)}
                          <div className="ilm-boon-foot">via a mastery-{boon.mastery} {boon.branch || boon.cls} in the {selFac.type}</div>
                        </div>
                      )
                    }
                    return (
                      <div className="ilm-boon-banner">
                        <div className="ilm-boon-eyebrow" style={{ color: 'var(--muted)' }}>◇ COMPANY BOON · DORMANT</div>
                        <div className="ilm-boon-line" style={{ marginTop: 4 }}>
                          {boon.assigned
                            ? `This ${boon.branch || boon.cls}'s boon grows with mastery and evolution — keep leveling them.`
                            : `Assign a ${boon.cls} here to activate this facility's boon.`}
                        </div>
                      </div>
                    )
                  })()}
                  {renderFacilityDetail(selFac)}
                </div>
              </div>
            )}
          </>
        )
      })()}

      {showBannerStudio && (
        <BannerStudio
          onClose={() => setShowBannerStudio(false)}
          onSaved={() => getBanner().then(setBanner).catch(() => {})}
        />
      )}

      {showMemorial && <Memorial onClose={() => setShowMemorial(false)} />}
      {showLore && <LoreJournal onClose={() => setShowLore(false)} />}
      {showExpeditions && <Expeditions onClose={() => setShowExpeditions(false)} />}

      {activeTab === 'floors' && floorsData && (() => {
        // ── HIERARCHY — the base climbs like the Tower does (mock "Base
        // Hierarchy"): Floor I is the widest foundation at the bottom, each
        // raised floor stacks above it, the next floor waits sealed at the
        // top. Rows rise bottom-first (floor-rise stagger). Heroes are
        // draggable diamonds; drop on a floor to rehouse.
        const floors = [...floorsData.floors].sort((a, b) => a.floor_number - b.floor_number)
        const raised = floors.length
        const housed = floors.reduce((s2, f) => s2 + f.heroes.length, 0)
        const nextUnlockTower = (raised + 1) * 10
        const ORDINAL = ['', 'FIRST', 'SECOND', 'THIRD', 'FOURTH', 'FIFTH', 'SIXTH', 'SEVENTH', 'EIGHTH', 'NINTH', 'TENTH']
        const ROMANS = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X']
        const stacked = [...floors].reverse() // render top-down: highest floor first
        return (
          <div style={{ display: 'flex', justifyContent: 'center' }}>
            {/* the stack — foundations widest at the bottom, each floor narrowing
                upward, the sealed next floor full-width on top. The ledger moved
                to the left console (mock parity), so the whole canvas is the
                stack: tall bars, big hero diamonds. */}
            <div className="ent-1" style={{ flex: '1 1 100%', maxWidth: 1100, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 18 }}>
              {/* sealed next floor — full width, prominent */}
              <div className="ent-fade" style={{ width: '100%', border: '1px dashed rgba(150,110,230,.45)', background: 'rgba(12,7,24,.3)', padding: '18px 24px', display: 'flex', alignItems: 'center', gap: 16 }}>
                <span style={{ width: 40, height: 40, transform: 'rotate(45deg)', border: '1px dashed rgba(200,169,245,.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', flex: 'none' }}>
                  <span style={{ transform: 'rotate(-45deg)', fontFamily: "'Cinzel',serif", fontSize: 12, color: 'var(--lavender)' }}>{ROMANS[raised] || raised + 1}</span>
                </span>
                <div>
                  <div style={{ fontFamily: "'Cinzel',serif", fontWeight: 700, letterSpacing: '.18em', fontSize: 14, color: 'var(--lavender)' }}>
                    {ORDINAL[raised + 1] || `${raised + 1}TH`} FLOOR — SEALED
                  </div>
                  <div style={{ fontFamily: "'Cinzel',serif", letterSpacing: '.18em', fontSize: 9, color: 'var(--muted)', marginTop: 3 }}>
                    RAISED WHEN THE TOWER'S {nextUnlockTower}TH FALLS
                  </div>
                </div>
              </div>

              {stacked.map(f => {
                const fromBottom = f.floor_number            // 1 = foundations
                // foundations (floor 1) widest; each floor up loses ~12%, floor
                // to the count so a tall tower still fits.
                const step = Math.min(12, 44 / Math.max(raised, 1))
                const width = Math.max(52, 100 - (raised - f.floor_number) * step)
                return (
                  <div key={f.floor_number}
                    onDragOver={(e) => e.preventDefault()}
                    onDrop={(e) => { e.preventDefault(); const hid = e.dataTransfer.getData('heroId'); if (hid) handleAssignFloor(hid, f.floor_number) }}
                    style={{ width: `${width}%`, minHeight: 70, border: '1px solid rgba(184,151,98,.35)', background: 'linear-gradient(160deg,rgba(42,22,80,.22),rgba(12,7,24,.55))', padding: '16px 24px',
                      display: 'flex', alignItems: 'center', gap: 16,
                      animation: `floor-rise .55s cubic-bezier(.2,.9,.3,1) ${0.1 + (fromBottom - 1) * 0.12}s both` }}>
                    <span style={{ width: 42, height: 42, transform: 'rotate(45deg)', border: '1px solid var(--gold-hi)', background: 'linear-gradient(150deg,#2a1650,#140b22)', display: 'flex', alignItems: 'center', justifyContent: 'center', flex: 'none', boxShadow: '0 0 12px rgba(184,151,98,.3)' }}>
                      <span style={{ transform: 'rotate(-45deg)', fontFamily: "'Cinzel',serif", fontWeight: 700, fontSize: 15, color: 'var(--text-hi)' }}>{ROMANS[f.floor_number - 1]}</span>
                    </span>
                    <div style={{ flex: 1, display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', minWidth: 0 }}>
                      {f.heroes.map(h => (
                        <span key={h.id} draggable
                          onDragStart={(e) => e.dataTransfer.setData('heroId', String(h.id))}
                          onClick={() => { if (rehouseMode && f.floor_number !== 1) handleAssignFloor(h.id, 1) }}
                          title={`${h.name} · Lv ${h.level} ${h.hero_class}${rehouseMode && f.floor_number !== 1 ? ' — click to send to the Foundations' : ''}`}
                          style={{ width: 52, height: 52, transform: 'rotate(45deg)', flex: 'none', cursor: 'grab', border: '1px solid rgba(216,187,132,.55)', background: '#140b22', display: 'flex', alignItems: 'center', justifyContent: 'center', overflow: 'hidden' }}>
                          {h.portrait_path && !h.portrait_path.includes('default_') ? (
                            /* face shot, not full body (Liam) — mini crop, raw as fallback */
                            <img src={`/heroes/${h.id}/card-image?mini=1`} alt={h.name} draggable={false}
                              onError={(e) => { if (!e.currentTarget.dataset.fb) { e.currentTarget.dataset.fb = '1'; e.currentTarget.src = `/${h.portrait_path}` } }}
                              style={{ width: '142%', height: '142%', objectFit: 'cover', objectPosition: 'center', transform: 'rotate(-45deg)', flex: 'none', pointerEvents: 'none' }} />
                          ) : (
                            <span style={{ transform: 'rotate(-45deg)', fontFamily: "'Cinzel',serif", fontSize: 15, color: 'var(--gold-hi)' }}>{h.name[0]}</span>
                          )}
                        </span>
                      ))}
                      {rehouseMode && (
                        <span style={{ width: 44, height: 44, transform: 'rotate(45deg)', flex: 'none', border: '1px dashed rgba(150,110,230,.4)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                          <span style={{ transform: 'rotate(-45deg)', color: 'var(--muted)', fontSize: 14 }}>+</span>
                        </span>
                      )}
                    </div>
                    <div style={{ textAlign: 'right', flex: 'none' }}>
                      <div style={{ fontFamily: "'Cormorant Garamond',serif", fontWeight: 700, fontSize: 28, color: 'var(--lavender)', lineHeight: 1 }}>+{f.stat_bonus_pct}%</div>
                      <div style={{ fontFamily: "'Cinzel',serif", letterSpacing: '.16em', fontSize: 9, color: 'var(--muted)', marginTop: 4 }}>PER HERO · {f.heroes.length} HOUSED</div>
                    </div>
                  </div>
                )
              })}

              <div style={{ fontFamily: "'Cinzel',serif", letterSpacing: '.3em', fontSize: 11, color: 'var(--muted)', marginTop: 4 }}>THE FOUNDATIONS</div>
            </div>
          </div>
        )
      })()}

        </main>
      </div>
    </div>
  )
}
