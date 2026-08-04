import React, { useState, useEffect } from 'react'
import { loadZones, LEGACY_ZONES } from '../lib/zoneDraw'
import PageTitle from '../components/PageTitle'
import { SectionHeader, OrnateRule } from '../components/ilm/Ilm'
import { getAllTeams, getBase, enterFloor, resolveEvent, resolveExplore, previewFloor, getNarrative, getHero, getLegacies, getSupportBoons, finalizeCombat } from '../api/client'

// Compact chips for the deploy panel — which support boons ride into THIS
// climb (combat-relevant only; economy boons live in their facilities).
function boonChips(b) {
  if (!b) return []
  const pct = v => `${Math.round((v || 0) * 100)}%`
  const chips = []  // { icon: boon-set sigil name, label }
  if (b.feast_stat_pct) chips.push({ icon: 'FEAST', label: `FEAST +${b.feast_stat_pct}%` })
  if (b.war_str_pct) chips.push({ icon: 'WAR_RATIONS', label: `WAR RATIONS +${b.war_str_pct}%` })
  if (b.formation_pct) chips.push({ icon: 'FORMATION', label: `FORMATION +${b.formation_pct}%` })
  if (b.advisor_str_pct) chips.push({ icon: 'WAR_COUNCIL', label: `WAR COUNCIL +${b.advisor_str_pct}%` })
  if (b.alch_draught_pct) chips.push({ icon: 'DRAUGHT', label: `DRAUGHTS +${b.alch_draught_pct}%` })
  if (b.medic_shield_pct) chips.push({ icon: 'SURGERY', label: `+${b.medic_shield_pct}% HP` })
  if (b.medic_regen_pct) chips.push({ icon: 'SURGERY', label: `REGEN ${pct(b.medic_regen_pct)}` })
  if (b.medic_poison_pct) chips.push({ icon: 'TOXIN', label: `TOXIN ${pct(b.medic_poison_pct)}` })
  if (b.quartermaster_barrier_pct) chips.push({ icon: 'BARRIER', label: `BARRIER −${pct(b.quartermaster_barrier_pct)}` })
  if (b.quartermaster_kit_charges) chips.push({ icon: 'FIELD_KIT', label: `${b.quartermaster_kit_charges} KIT${b.quartermaster_kit_charges > 1 ? 'S' : ''}` })
  if (b.smith_dmg_reduction_pct) chips.push({ icon: 'PLATE', label: `PLATE −${pct(b.smith_dmg_reduction_pct)}` })
  if (b.blessing_resist_pct) chips.push({ icon: 'BLESSING', label: `RESIST +${pct(b.blessing_resist_pct)}` })
  if (b.priest_death_saves) chips.push({ icon: 'DEATH_SAVE', label: `${b.priest_death_saves} DEATH-SAVE${b.priest_death_saves > 1 ? 'S' : ''}` })
  if (b.tactician_first_strike) chips.push({ icon: 'FIRST_STRIKE', label: 'FIRST STRIKE' })
  else if (b.tactician_bonus_mana) chips.push({ icon: 'FIRST_STRIKE', label: `+${b.tactician_bonus_mana} MANA` })
  if (b.scout_sabotage_pct) chips.push({ icon: 'SABOTAGE', label: `SABOTAGE −${pct(b.scout_sabotage_pct)}` })
  if (b.scout_mark_pct) chips.push({ icon: 'MARK', label: `MARK −${pct(b.scout_mark_pct)}` })
  return chips
}
import DeathCeremony from '../components/DeathCeremony'
import DailyDungeons from '../components/DailyDungeons'
import StakesBanner from '../components/StakesBanner'
import { arenaUpdateFloor, getArenaToken } from '../api/arenaServerClient'
import { emitToast } from '../toastBus'
import { playDeedChime, setBgmScene, playMusicStinger } from '../audio'
import { scanCombatForDiscoveries } from '../codexBus'
import CombatArena from '../components/CombatArena'
import FairyGuide from '../components/FairyGuide'
import { CardFrame } from '../components/HeroCard'
import { EquipmentTypeIcon } from '../components/EquipmentTypeIcon'
import GameIcon from '../components/GameIcon'
import Sigil from '../components/Sigil'
import Tip, { TIPS } from '../components/Tip'

// Time-skip combat persistence — see resumeTurnIndex below. Discard
// anything older than this even if found; a fight left "in progress" for
// an hour+ is more likely a stale/abandoned tab than one worth resuming.
const ACTIVE_COMBAT_KEY = 'tower_active_combat'
const ACTIVE_COMBAT_MAX_AGE_MS = 20 * 60 * 1000
const TURN_DELAY_MS = 800

function saveActiveCombat(result, resolvedFloor) {
  try {
    sessionStorage.setItem(ACTIVE_COMBAT_KEY, JSON.stringify({
      result, resolvedFloor, deployedAt: Date.now(),
    }))
  } catch {}
}

function clearActiveCombat() {
  try { sessionStorage.removeItem(ACTIVE_COMBAT_KEY) } catch {}
}

function loadActiveCombat() {
  try {
    const raw = sessionStorage.getItem(ACTIVE_COMBAT_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (!parsed?.deployedAt || Date.now() - parsed.deployedAt > ACTIVE_COMBAT_MAX_AGE_MS) {
      clearActiveCombat()
      return null
    }
    return parsed
  } catch {
    return null
  }
}

// The 10 biomes, one per 10-floor zone — derived from enemy_families.py's
// spawn tables. Art lives in /images/floors/<slug>.png; the zone tile grid
// uses it as a background so each stretch of the climb reads distinctly.
// Order matches combat_service.py's band tiers (the spawn-table ground
// truth): beginner/intermediate/veteran/advanced/mighty/ascendant/
// MYTHIC=Leviathan's Graveyard (61-70, the sea band)/apex/dread/ancient.
// 2026-07-15 re-theme: Dread Peaks moved to 41-50 (the winged-beast band),
// Leviathan's Graveyard restored at 61-70, Blood Lake now covers apex's
// hydras/nagas at 71-80. ashen_depths.png is spare until a band fits it.
// Drawn per player from the 64-plate library (lib/zoneDraw.js), not fixed.
// Module-level and mutable so zoneFor/floorArtFor keep their old signatures —
// they are called from several render paths and threading zone state through
// all of them would be a much larger change for no behavioural gain.
//
// Starts as the legacy ten so the very first render has real zones, then the
// draw replaces it once the manifest lands. Enemies are picked by floor number
// on the backend, so which zones a player draws never affects what they fight.
let ZONES = LEGACY_ZONES

// Zones above the built-out 100-floor table just repeat the final boneyard
// biome rather than breaking — nothing past floor 100 is designed yet.
function zoneFor(zoneIndex) {
  return ZONES[Math.min(zoneIndex, ZONES.length - 1)]
}

// The combat backdrop — the entered floor's zone art. Only rendered once
// you're IN a floor (CombatArena); the zone grid keeps its own tile art.
function floorArtFor(floorNumber) {
  if (!floorNumber) return null
  const z = zoneFor(Math.floor((floorNumber - 1) / 10))
  // Library zones carry their own resolved path; legacy zones still live under
  // /images/floors/. Both shapes have to work, because a save made before the
  // library existed falls back to the legacy ten.
  return z.art || `/images/floors/${z.slug}.png`
}

// Teams carry names (shared with the Squad Overview's toe_team_names store)
// so the deploy panel reads "TEAM ECHO", not "TEAM 1" (mock parity).
const DEFAULT_TEAM_NAMES = { 1: 'ECHO', 2: 'EMBER', 3: 'ONYX', 4: 'GALE', 5: 'VOW' }
function teamNameFor(id) {
  try {
    const saved = JSON.parse(localStorage.getItem('toe_team_names') || '{}')
    return (saved[id] || DEFAULT_TEAM_NAMES[id] || `TEAM ${id}`)
  } catch { return DEFAULT_TEAM_NAMES[id] || `TEAM ${id}` }
}
// Single legible power number for a hero (mirrors HeroesPage.heroPower).
function heroPower(h) {
  const stats = (h.strength || 0) + (h.intelligence || 0) + (h.endurance || 0) + (h.agility || 0) + (h.willpower || 0) + (h.luck || 0)
  return Math.round((h.level || 1) * 40 + stats * 12 + (h.max_health || 0) * 1.5)
}

const FLOOR_ICONS = {
  field_combat: 'class_rogue',
  miniboss: 'boss_skull',
  miniboss_survival: 'element_water',
  miniboss_behemoth: 'element_earth',
  miniboss_assassin: 'thief_knife',
  miniboss_twins: 'class_twins',
  boss: 'boss_demon',
  resource: 'gem',
  event: 'mystery_encounter',
  survival: 'class_defender',
  defend: 'tower',
  explore: 'map',
  escort: 'creature_horse',
  conquest: 'element_fire',
  war: 'class_warrior',
  retrieve: 'coin_pouch',
  ambush: 'element_dark',
  blitz: 'element_lightning',
  cursed_ground: 'element_ritual',
}

// FLOOR_TYPE_INFO colors are 3-digit hex shorthand (#a44) — appending an
// alpha suffix directly (`${color}22`) produces an invalid 5-digit hex
// string that browsers silently drop, falling back to a plain white/gray
// <button> background (confirmed bug: floor tiles went blank-white).
// Expands to 6-digit hex first so the alpha suffix actually forms valid
// 8-digit #RRGGBBAA.
function hexWithAlpha(hex, alpha) {
  const expanded = hex.length === 4
    ? '#' + [...hex.slice(1)].map(c => c + c).join('')
    : hex
  return `${expanded}${alpha}`
}

const FLOOR_TYPE_INFO = {
  field_combat: { color: '#b65', label: 'Field Combat', blurb: 'A looser skirmish, open ground.' },
  miniboss: { color: '#c63', label: 'Miniboss', blurb: 'A tougher single enemy.' },
  miniboss_survival: { color: '#368', label: 'Miniboss: Survival', blurb: 'Endurance check — outlast a real wave.' },
  miniboss_behemoth: { color: '#765', label: 'Miniboss: Behemoth', blurb: 'DPS check — huge HP/DEF, tiny attack.' },
  miniboss_assassin: { color: '#a13', label: 'Miniboss: Assassin', blurb: 'Tank check — blinding speed, brutal burst.' },
  miniboss_twins: { color: '#759', label: 'Miniboss: Twins', blurb: 'Comp check — one resists physical, one resists magic.' },
  // miniboss_mirror retired — no counterplay; existing cached floors are
  // re-rolled by a DB migration, so nothing renders this type anymore.
  boss: { color: '#e33', label: 'Boss', blurb: 'The floor\'s guardian.' },
  event: { color: '#86c', label: 'Event', blurb: 'A choice encounter.' },
  survival: { color: '#c44', label: 'Survival', blurb: 'A fight against a larger enemy wave.' },
  defend: { color: '#64a', label: 'Defend', blurb: 'A fight to hold a chokepoint.' },
  explore: { color: '#4a6', label: 'Explore', blurb: 'A risk/reward discovery.' },
  escort: { color: '#c93', label: 'Escort', blurb: 'Protect an NPC — a win lifts the team\'s morale.' },
  conquest: { color: '#933', label: 'Conquest', blurb: 'A larger enemy wave — clear it by force.' },
  war: { color: '#722', label: 'War', blurb: 'The hardest non-boss fight on this floor.' },
  retrieve: { color: '#a82', label: 'Retrieve', blurb: 'Something valuable is guarded here.' },
  ambush: { color: '#414', label: 'Ambush', blurb: 'Enemies get a guaranteed first strike.' },
  blitz: { color: '#dd4', label: 'Blitz', blurb: 'Enemies grow stronger every round — burst them down fast.' },
  cursed_ground: { color: '#5a3', label: 'Cursed Ground', blurb: 'Your team starts the fight already debuffed.' },
}

// Floor gameplay type -> custom floor sigil (floor/<NAME>.svg). Several
// gameplay types share one icon (all miniboss variants -> MINIBOSS, the
// hold/assault variants -> ELITE_COMBAT). Sigil renders nothing when the
// file is absent, so the text label still reads until floor art is dropped in.
const FLOOR_SIGIL = {
  field_combat: 'STANDARD_COMBAT',
  miniboss: 'MINIBOSS',
  miniboss_survival: 'MINIBOSS',
  miniboss_behemoth: 'MINIBOSS',
  miniboss_assassin: 'MINIBOSS',
  miniboss_twins: 'MINIBOSS',
  boss: 'BOSS_ROOM',
  event: 'NARRATIVE_EVENT',
  survival: 'SURVIVAL_SWARM',
  defend: 'ELITE_COMBAT',
  explore: 'NARRATIVE_EVENT',
  escort: 'ESCORT',
  conquest: 'ELITE_COMBAT',
  war: 'ELITE_COMBAT',
  retrieve: 'RETRIEVAL',
  ambush: 'ELITE_COMBAT',
  blitz: 'BLITZ',
  cursed_ground: 'NARRATIVE_EVENT',
}

function FloorBadge({ type }) {
  const info = FLOOR_TYPE_INFO[type]
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: '0.25rem',
      background: info?.color || '#555',
      padding: '0.15rem 0.4rem',
      borderRadius: 4,
      fontSize: '0.7rem',
      textTransform: 'uppercase',
      letterSpacing: '0.5px'
    }}>
      {FLOOR_SIGIL[type] && <Sigil set="floor" name={FLOOR_SIGIL[type]} size={11} />}
      {info?.label || type}
    </span>
  )
}

// Survival Swarm is a random 35%-chance ALTERNATIVE rolled inside a
// miniboss floor's combat resolution (services/combat_service.py's
// SWARM_SURVIVAL_CHANCE) — not its own floor type, so the static
// "Miniboss: A tougher single enemy" blurb was actively wrong (and
// confusing — see the 30-50 enemy swarm) whenever that roll landed.
const SURVIVAL_SWARM_INFO = { color: '#c44', label: 'Survival Swarm', blurb: 'An overwhelming horde — outlast the clock, don\'t try to clear it.' }

function FloorTypeCallout({ type, isSurvivalSwarm }) {
  const info = isSurvivalSwarm ? SURVIVAL_SWARM_INFO : FLOOR_TYPE_INFO[type]
  if (!info) return null
  return (
    <div style={{
      maxWidth: '600px',
      margin: '0 auto 1.5rem auto',
      textAlign: 'center',
      padding: '0.6rem 1rem',
      background: `${info.color}22`,
      border: `1px solid ${info.color}`,
      borderRadius: 6,
    }}>
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem', fontFamily: 'Cinzel, serif', textTransform: 'uppercase', letterSpacing: '1px', color: info.color }}>
        {!isSurvivalSwarm && FLOOR_SIGIL[type] && <Sigil set="floor" name={FLOOR_SIGIL[type]} size={16} color={info.color} />}
        {isSurvivalSwarm && <Sigil set="floor" name="SURVIVAL_SWARM" size={16} color={info.color} />}
        {info.label} Floor
      </span>
      <span className="text-dim" style={{ marginLeft: '0.6rem', fontSize: '0.85rem' }}>
        {info.blurb}
      </span>
    </div>
  )
}

// Multi-team floors run as N parallel arenas (see team_results), each with
// its own initial_state — the post-combat summary screen still wants one
// combined roster, so merge them here instead of duplicating this in both
// call sites.
function mergedCombatEntities(result) {
  const teamResults = (result?.combat?.team_results || result?.team_results || []).filter(Boolean)
  if (teamResults.length > 0) {
    const heroes = teamResults.flatMap(tr => tr.initial_state?.heroes || [])
    const enemies = teamResults.flatMap(tr => tr.initial_state?.enemies || [])
    return { heroes, enemies }
  }
  return result?.initial_state || result?.combat?.initial_state || null
}

function heroCombatStatus(heroId, lastResult, combatEntities) {
  if (lastResult.combat?.dead_heroes?.includes(heroId)) return 'kia'
  const surv = lastResult.combat?.surviving_heroes?.find(s => s.id === heroId)
  if (!surv) return 'unknown'
  const entity = combatEntities?.heroes?.find(h => h.id === heroId)
  if (entity && surv.health < entity.max_health) return 'injured'
  return 'alive'
}

function PostCombatScreen({ lastResult, combatEntities, onReturn, onRerun, busy }) {
  if (!lastResult) return null;

  const metrics = lastResult.combat?.combat_metrics || {};
  const maxDmg = Math.max(1, ...Object.values(metrics));
  const mvpId = Object.entries(metrics).sort((a, b) => b[1] - a[1])[0]?.[0]
  const wasVictory = !lastResult.run_over && lastResult.combat?.winner !== 'enemies';
  const continueLabel = wasVictory ? 'ONWARD' : 'RETREAT'
  const accent = wasVictory ? 'var(--gold-hi)' : 'var(--red-hi)'

  // Diamond-masked combat face, with the same 3-step portrait fallback.
  const Face = ({ h, dim }) => (
    <span style={{ width: 52, height: 52, flex: 'none', clipPath: 'polygon(50% 0,100% 50%,50% 100%,0 50%)', background: 'var(--bg-panel)', display: 'inline-block', overflow: 'hidden' }}>
      <img src={`/heroes/${h.id}/card-image?mini=true`} draggable={false}
        style={{ width: '100%', height: '100%', objectFit: 'cover', objectPosition: 'center', filter: dim ? 'grayscale(1) brightness(.7)' : 'none' }}
        onError={(e) => {
          if (e.target.dataset.stage === 'raw') { e.target.onerror = null; e.target.src = '/icons/mystery_encounter.png'; e.target.style.opacity = '0.4' }
          else { e.target.dataset.stage = 'raw'; e.target.src = `/${h.portrait_path}` }
        }} />
    </span>
  )

  const spoils = []
  if (lastResult.gold_gained > 0) spoils.push({ c: 'var(--gold-hi)', v: `+${lastResult.gold_gained.toLocaleString()}`, k: 'GOLD' })
  if (lastResult.gems_gained > 0) spoils.push({ c: '#00ffff', v: `+${lastResult.gems_gained.toLocaleString()}`, k: 'GEMS · RECORD', glow: true })
  if (lastResult.ingredients_gained > 0) spoils.push({ c: 'var(--green-hi)', v: `+${lastResult.ingredients_gained.toLocaleString()}`, k: 'INGREDIENTS' })
  if (lastResult.materials_gained) Object.entries(lastResult.materials_gained).forEach(([mat, qty]) => spoils.push({ c: 'var(--violet)', v: `×${qty}`, k: mat.toUpperCase() }))

  return (
    <div className="ilm-victory">
      {/* slash banner */}
      <div className={`ilm-vic-slash ${wasVictory ? 'win' : 'lose'}`}>
        <span className="ilm-vic-dia" style={{ background: 'linear-gradient(135deg,#ffd88a,#b89762)' }} />
        <span className="ilm-vic-word" style={{ color: wasVictory ? 'var(--text-hi)' : 'var(--red-hi)' }}>{wasVictory ? 'VICTORY' : 'DEFEAT'}</span>
        <span className="ilm-vic-dia" style={{ background: 'linear-gradient(135deg,#c8a9f5,#8b46d6)' }} />
      </div>
      {lastResult.chatter_line ? (
        <div className="ilm-vic-sub">“{lastResult.chatter_line.line}” <span className="text-dim" style={{ fontStyle: 'normal', fontSize: '0.8rem' }}>— {lastResult.chatter_line.name}</span></div>
      ) : lastResult.narrative ? (
        <div className="ilm-vic-sub">{lastResult.narrative}</div>
      ) : null}

      {/* SPOILS — framed as an illuminated plate: hairline border + the four
          gold corner ticks (screenshot-density pass). */}
      <div className="ilm-vic-body" style={{ position: 'relative', border: '1px solid rgba(184,151,98,.16)', padding: '18px 22px 20px' }}>
        <span className="ilm-corner" />
        <span className="ilm-corner ilm-corner-r" />
        <span className="ilm-corner ilm-corner-bl" />
        <span className="ilm-corner ilm-corner-br" />
        {(spoils.length > 0 || lastResult.equipment_drop || lastResult.blueprint_found) && (
          <>
            <SectionHeader ornate style={{ marginBottom: 12 }}>Spoils</SectionHeader>
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 20 }}>
              {spoils.map((s, i) => (
                <div key={i} className="ilm-vic-spoil" style={s.glow ? { boxShadow: '0 0 18px rgba(0,255,255,.25)', borderColor: 'rgba(0,255,255,.4)' } : undefined}>
                  <span style={{ width: 12, height: 12, transform: 'rotate(45deg)', background: s.c, display: 'inline-block' }} />
                  <span style={{ fontWeight: 700, fontSize: '1.35rem', color: '#efe8da' }}>{s.v}</span>
                  <span className="ilm-micro">{s.k}</span>
                </div>
              ))}
              {lastResult.equipment_drop && (
                <div className="ilm-vic-spoil" style={{ boxShadow: '0 0 18px rgba(255,179,0,.2)', borderColor: 'rgba(255,179,0,.5)' }}>
                  <EquipmentTypeIcon item={lastResult.equipment_drop} fontSize="1.4rem" glow="var(--gold-hi)" />
                  <div>
                    <div style={{ fontFamily: "'Cinzel',serif", fontWeight: 700, fontSize: '0.78rem', color: 'var(--text-hi)' }}>{lastResult.equipment_drop.name}</div>
                    <div style={{ fontFamily: "'Cinzel',serif", fontSize: '0.56rem', letterSpacing: '.16em', color: 'var(--gold-max)' }}>{String(lastResult.equipment_drop.rarity).toUpperCase()} · DROP</div>
                  </div>
                </div>
              )}
              {lastResult.blueprint_found && (
                <div className="ilm-vic-spoil">
                  <GameIcon name="scroll" size={18} />
                  <span style={{ fontFamily: "'Cinzel',serif", fontWeight: 700, fontSize: '0.8rem', color: 'var(--gold-hi)' }}>{lastResult.blueprint_found}</span>
                  <span className="ilm-micro">BLUEPRINT</span>
                </div>
              )}
            </div>
          </>
        )}

        {/* BATTLE REPORT */}
        <SectionHeader ornate right={<span className="ilm-micro" style={{ color: 'var(--gold-hi)' }}>DAMAGE DEALT</span>} style={{ marginBottom: 10 }}>Battle Report</SectionHeader>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {combatEntities?.heroes?.map(h => {
            const dmg = metrics[h.id] || 0
            const pct = (dmg / maxDmg) * 100
            const status = heroCombatStatus(h.id, lastResult, combatEntities)
            const isMvp = dmg > 0 && String(h.id) === String(mvpId)
            const fallen = status === 'kia'
            const rowClass = isMvp ? 'mvp' : fallen ? 'fallen' : status === 'injured' ? 'injured' : ''
            return (
              <div key={h.id} className={`ilm-vic-row ${rowClass}`}>
                <Face h={h} dim={fallen} />
                <span className="ilm-vic-name" style={fallen ? { color: 'var(--red-hi)' } : undefined}>{h.name}</span>
                {isMvp ? <span className="ilm-vic-badge mvp">♛ MVP</span>
                  : fallen ? <span className="ilm-vic-badge fallen">✝ FALLEN</span>
                  : status === 'injured' ? <span className="ilm-vic-badge injured">INJURED</span>
                  : <span style={{ width: 58, flex: 'none' }} />}
                <div style={{ flex: 1 }}>
                  <div style={{ height: 5, background: 'rgba(0,0,0,.5)' }}>
                    <div style={{ height: '100%', width: `${pct}%`, background: isMvp ? 'linear-gradient(90deg,#b89762,#ffd88a)' : fallen ? 'linear-gradient(90deg,#7a3030,#a05040)' : 'linear-gradient(90deg,#b89762,#d8bb84)', transition: 'width 1s ease-out' }} />
                  </div>
                </div>
                <span style={{ fontFamily: "'Cormorant Garamond',serif", fontWeight: 700, fontSize: '1.1rem', width: 72, textAlign: 'right', color: isMvp ? 'var(--gold-max)' : fallen ? 'var(--red-hi)' : '#efe8da' }}>{dmg.toLocaleString()}</span>
              </div>
            )
          })}
        </div>

        {/* level-ups / skill ascensions */}
        {(lastResult.level_ups?.length > 0 || lastResult.combat?.skill_upgrades) && (
          <div style={{ marginTop: 14, display: 'flex', flexDirection: 'column', gap: 6 }}>
            {lastResult.level_ups?.map((msg, i) => (
              <div key={i} style={{ fontSize: '0.85rem', color: msg.startsWith('  ') ? 'var(--star5)' : 'var(--gold-hi)', fontFamily: "'Cinzel',serif", letterSpacing: '.04em' }}>⬆ {msg.trim()}</div>
            ))}
            {lastResult.combat?.skill_upgrades && Object.values(lastResult.combat.skill_upgrades).flat().map((u, i) => (
              <div key={`s${i}`} style={{ fontSize: '0.85rem', color: '#e0aaff', fontFamily: "'Cinzel',serif", letterSpacing: '.04em' }}>✦ {u.skill_name} → {u.new_tier}</div>
            ))}
          </div>
        )}

        {/* actions */}
        <div style={{ display: 'flex', justifyContent: 'center', gap: 14, marginTop: 22 }}>
          <button className="ilm-btn ilm-btn-violet" onClick={onReturn} disabled={busy} style={{ padding: '0.85rem 2.2rem' }}>{continueLabel}</button>
          <button className="ilm-btn ilm-btn-ghost" onClick={onRerun} disabled={busy} style={{ padding: '0.85rem 1.6rem' }}>RERUN FLOOR</button>
        </div>
      </div>
    </div>
  )
}

// ── The Ascent screen (Illuminated spec) ───────────────────────────────
// Left console (stacked FLOOR title, next-floor panel, deploy, readiness)
// + a diagonal climb path of floor diamonds + a zone rail along the bottom.
function AscentScreen({
  selectedZone, setSelectedZone, selectedFloor, setSelectedFloor,
  highestFloor, maxZone, zoneFloorTypes, floorPreview,
  team, deployTeamIds, setDeployTeamIds,
  advancing, error, onEnter, onRush, onDailyGates, onFormation,
}) {
  const zone = zoneFor(selectedZone)
  const startFloor = selectedZone * 10 + 1
  const floors = Array.from({ length: 10 }, (_, i) => startFloor + i)
  const nextFloor = highestFloor + 1
  // Company boons riding into this climb (from stationed supports).
  const [boons, setBoons] = useState(null)
  useEffect(() => { getSupportBoons().then(setBoons).catch(() => {}) }, [])
  const chips = boonChips(boons)
  const teamsNeeded = selectedFloor === 1 ? 1 : Math.floor((selectedFloor - 1) / 20) + 1
  const activeIds = deployTeamIds.slice(0, teamsNeeded)
  const notReady = activeIds.some(id => !team[id.toString()] || team[id.toString()].length === 0)
  // Trust the backend on reveal: it returns floor_type only for floors the
  // player has actually walked (floors stay unknown ahead — user rule).
  const selPreview = zoneFloorTypes[selectedFloor]
  const selInfo = selPreview?.floor_type ? FLOOR_TYPE_INFO[selPreview.floor_type] : null
  // Learned intel from having WALKED this floor — condition/elite/boss phases
  // are deterministic facts, so remembering them between attempts is real.
  const selIntel = selPreview || {}
  const PHASE_LABELS = {
    summon: 'calls reinforcements', harden: 'hardens its carapace', ritual: 'heals mid-fight',
    quicken: 'quickens', fury: 'flies into a fury', shed_armor: 'sheds its armor for speed',
    cataclysm: 'unleashes a cataclysm', second_summon: 'calls mass reinforcements',
  }
  const selIsBoss = selectedFloor % 10 === 0
  const bossFloorInZone = startFloor + 9
  const readyHeroes = (team[activeIds[0]?.toString()] || [])

  // Diagonal path: floor i sits at (x,y) climbing bottom-left → top-right.
  // The climb area now fills the whole page height (flex), so the path
  // starts low and spreads across the full vertical — the old 23% base
  // left the bottom half of tall screens empty.
  const posFor = (i) => ({
    left: `${10 + i * 8.6}%`,
    bottom: `${12 + i * 8}%`,
  })

  return (
    <div className="ent-1" style={{ display: 'grid', gridTemplateColumns: '416px 1fr', gap: '2.5rem', alignItems: 'stretch', minHeight: 560, flex: 1 }}>

      {/* ============ LEFT CONSOLE ============ */}
      <div style={{ display: 'flex', flexDirection: 'column' }}>
        <div className="ilm-eyebrow" style={{ marginBottom: 2 }}>THE ASCENT</div>
        <div className="ilm-title-stack">
          <div className="ghost">TOWER</div>
          <div className="solid">FLOOR {selectedFloor}</div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 2 }}>
          <span className="ilm-micro" style={{ color: 'var(--muted)' }}>DEEPEST CLIMB</span>
          <OrnateRule />
          <span style={{ fontFamily: 'Cinzel, serif', fontSize: 13, color: 'var(--gold-hi)' }}>FLOOR {highestFloor}</span>
        </div>

        {/* next-floor panel */}
        <div style={{ marginTop: 20, border: '1px solid rgba(184,151,98,.4)', background: 'linear-gradient(150deg,rgba(124,58,214,.14),rgba(12,7,24,.5))', padding: '16px 18px', clipPath: 'polygon(0 0,100% 0,100% 100%,12px 100%)' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}>
            <span style={{ fontFamily: 'Cinzel, serif', fontWeight: 700, letterSpacing: '.18em', fontSize: 12, color: 'var(--text-hi)', textTransform: 'uppercase' }}>
              {selIsBoss ? 'Floor Type · Boss' : selInfo ? `Floor Type · ${selInfo.label}` : 'Floor Type · Unknown'}
            </span>
            <span className="ilm-mono" style={{ width: 26, height: 26, border: '1px solid rgba(216,187,132,.7)', background: '#1c1030' }}>
              <span style={{ color: 'var(--gold-hi)', fontSize: 11 }}>✦</span>
            </span>
          </div>
          <div style={{ fontSize: '0.92rem', fontStyle: 'italic', color: '#c8b8dd', marginTop: 8, lineHeight: 1.45 }}>
            {floorPreview?.blurb || selInfo?.blurb || 'The floor reveals itself only to those who enter. Deaths beyond this threshold are permanent.'}
          </div>
          {/* learned intel — only present on floors you've walked before */}
          {(selIntel.condition || selIntel.elite || selIntel.boss_phases) && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 5, marginTop: 10, borderTop: '1px solid rgba(184,151,98,.18)', paddingTop: 9 }}>
              {selIntel.condition && (
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
                  <span style={{ fontFamily: 'Cinzel, serif', letterSpacing: '.14em', fontSize: 9.5, color: 'var(--lavender)', flex: 'none' }}>◆ {selIntel.condition.name}</span>
                  <span style={{ fontSize: '0.8rem', fontStyle: 'italic', color: 'var(--muted)' }}>{selIntel.condition.desc}</span>
                </div>
              )}
              {selIntel.elite && (
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
                  <span style={{ fontFamily: 'Cinzel, serif', letterSpacing: '.14em', fontSize: 9.5, color: 'var(--red-hi)', flex: 'none' }}>◆ ELITE</span>
                  <span style={{ fontSize: '0.8rem', fontStyle: 'italic', color: 'var(--muted)' }}>a {selIntel.elite} prowls this floor</span>
                </div>
              )}
              {selIntel.boss_phases && (
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
                  <span style={{ fontFamily: 'Cinzel, serif', letterSpacing: '.14em', fontSize: 9.5, color: 'var(--red-hi)', flex: 'none' }}>◆ KNOWN PHASES</span>
                  <span style={{ fontSize: '0.8rem', fontStyle: 'italic', color: 'var(--muted)' }}>
                    wounded, it {selIntel.boss_phases.map(k => PHASE_LABELS[k] || k).join(', then ')}
                  </span>
                </div>
              )}
            </div>
          )}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 10 }}>
            <span style={{ width: 7, height: 7, transform: 'rotate(45deg)', background: 'var(--red)', display: 'inline-block' }} />
            <span style={{ fontFamily: 'Cinzel, serif', letterSpacing: '.2em', fontSize: 11, color: 'var(--red-hi)' }}>BOSS AWAITS ON FLOOR {bossFloorInZone}</span>
          </div>
        </div>

        {/* stakes + actions */}
        {/* company boons — what the stationed supports send with the party */}
        {chips.length > 0 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 12 }}>
            {chips.map((c, i) => (
              <span key={i} style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontFamily: 'Cinzel, serif', fontSize: 9.5, letterSpacing: '.1em', color: 'var(--gold-hi)', border: '1px solid rgba(184,151,98,.35)', background: 'rgba(184,151,98,.08)', padding: '3px 9px', whiteSpace: 'nowrap' }}>
                <Sigil set="boon" name={c.icon} size={12} />
                {c.label}
              </span>
            ))}
          </div>
        )}
        <StakesBanner variant="souls" compact style={{ marginTop: 14 }} />
        <div style={{ display: 'flex', gap: 12, marginTop: 10 }}>
          <button className="btn btn-primary" style={{ flex: 1, padding: '13px 0', fontSize: '0.9rem', letterSpacing: '.24em' }}
            onClick={onEnter} disabled={advancing || notReady}>
            {advancing ? 'ENTERING…' : 'BEGIN ASCENT'}
          </button>
          <button className="btn" style={{ padding: '13px 20px', fontSize: '0.82rem', letterSpacing: '.24em' }}
            onClick={onFormation} title="Rearrange your teams on the Squad Overview">
            FORMATION
          </button>
          {selectedFloor <= highestFloor && (
            <button className="btn" style={{ padding: '13px 20px', fontSize: '0.82rem', letterSpacing: '.2em' }}
              onClick={onRush} disabled={advancing || notReady}
              title="Re-run this cleared floor instantly for XP and gold">
              RUSH
            </button>
          )}
        </div>
        {error && <div className="text-red text-sm" style={{ marginTop: 10 }}>{error}</div>}

        {/* daily gates entry */}
        <button onClick={onDailyGates}
          style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 12, border: '1px solid rgba(216,187,132,.45)',
            background: 'linear-gradient(90deg,rgba(184,151,98,.12),transparent)', padding: '9px 14px', cursor: 'pointer',
            clipPath: 'polygon(0 0,100% 0,100% 100%,10px 100%)', width: '100%', textAlign: 'left' }}>
          <span style={{ width: 9, height: 9, transform: 'rotate(45deg)', background: '#ffd88a', boxShadow: '0 0 8px rgba(255,216,138,.6)', display: 'inline-block', flex: 'none' }} />
          <span style={{ fontFamily: 'Cinzel, serif', fontWeight: 700, letterSpacing: '.2em', fontSize: 10, color: 'var(--gold-hi)' }}>THE DAILY GATES</span>
          <span style={{ fontSize: 12, fontStyle: 'italic', color: 'var(--muted)' }}>gold · materials · seals</span>
          <span style={{ flex: 1 }} />
          <span style={{ fontFamily: 'Cinzel, serif', fontSize: 11, color: 'var(--gold-hi)' }}>›</span>
        </button>

        {/* deploy */}
        <div style={{ marginTop: 22, display: 'flex', flexDirection: 'column', gap: 10 }}>
          {Array.from({ length: teamsNeeded }).map((_, idx) => (
            <div key={idx}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
                <span className="ilm-micro" style={{ color: 'var(--muted)' }}>DEPLOY · TEAM {idx + 1}</span>
                <OrnateRule />
              </div>
              <select className="input" style={{ width: '100%', fontFamily: 'Cinzel, serif', fontSize: '0.8rem', letterSpacing: '.08em' }}
                value={deployTeamIds[idx]}
                onChange={e => { const n = [...deployTeamIds]; n[idx] = parseInt(e.target.value); setDeployTeamIds(n) }}>
                {[1,2,3,4,5,6,7,8,9,10].map(id => {
                  const count = team[id.toString()] ? team[id.toString()].length : 0
                  return <option key={id} value={id}>TEAM {id} ({count}/5)</option>
                })}
              </select>
            </div>
          ))}
        </div>

        {/* team readiness strip — named team + power + morale (mock parity) */}
        <div style={{ marginTop: 'auto', paddingTop: 26 }}>
          <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 12 }}>
            <span style={{ fontFamily: 'Cinzel, serif', letterSpacing: '.3em', fontSize: 13, color: 'var(--muted)' }}>
              TEAM <span style={{ color: 'var(--text-hi)' }}>{teamNameFor(deployTeamIds[0])}</span>
            </span>
            {readyHeroes.length > 0 && (
              <span style={{ fontFamily: 'Cinzel, serif', fontSize: 12, letterSpacing: '.14em', color: 'var(--gold-hi)' }}>
                POWER {readyHeroes.reduce((s, h) => s + heroPower(h), 0).toLocaleString()}
              </span>
            )}
          </div>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
            {readyHeroes.length > 0 ? (
              <>
                {readyHeroes.map(h => (
                  <span key={h.id} title={`${h.name} · Lv.${h.level}`}
                    style={{ width: 66, height: 66, flex: 'none', clipPath: 'polygon(50% 0,100% 50%,50% 100%,0 50%)', background: 'linear-gradient(135deg,#1c1030,#0c0718)', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', overflow: 'hidden' }}>
                    {h.portrait_path && !h.portrait_path.includes('default_') ? (
                      /* face pic, not full body (Liam: full body ONLY in detail/leader spotlight) */
                      <img src={`/heroes/${h.id}/card-image?mini=1`} alt={h.name} draggable={false}
                        onError={(e) => { if (!e.currentTarget.dataset.fb) { e.currentTarget.dataset.fb = '1'; e.currentTarget.src = `/${h.portrait_path}` } else { e.currentTarget.style.display = 'none' } }}
                        style={{ width: '100%', height: '100%', objectFit: 'cover', objectPosition: 'center' }} />
                    ) : (
                      <span style={{ fontFamily: 'Cinzel, serif', fontSize: 16, color: 'var(--gold-hi)' }}>{h.name[0]}</span>
                    )}
                  </span>
                ))}
                <span style={{ width: '100%', fontSize: 15, fontStyle: 'italic', color: 'var(--muted)', marginTop: 6, whiteSpace: 'nowrap' }}>
                  {(() => {
                    const avg = readyHeroes.reduce((s, h) => s + (h.morale ?? 100), 0) / readyHeroes.length
                    return `Morale ${avg >= 70 ? 'steady' : avg >= 40 ? 'shaken' : 'fearful'} · ${readyHeroes.length} of 5 ready`
                  })()}
                </span>
              </>
            ) : (
              <span className="text-dim" style={{ fontStyle: 'italic', fontSize: '0.85rem' }}>No heroes assigned to Team {teamNameFor(deployTeamIds[0])}.</span>
            )}
          </div>
        </div>
      </div>

      {/* ============ CLIMB PATH ============ */}
      {/* No zone art here — the environment render belongs to combat only;
          the ascent keeps the pure ink field so the climb path breathes. */}
      <div style={{ position: 'relative', display: 'flex', flexDirection: 'column',
        background: 'radial-gradient(90% 80% at 62% 40%, rgba(96,42,168,.22), rgba(0,0,0,0) 60%)' }}>

        {/* the climb area — floor diamonds live here, kept clear of the zone
            footer below so the two never crowd each other. */}
        <div style={{ position: 'relative', flex: 1, overflow: 'hidden', minHeight: 440 }}>

        {/* zone label top */}
        <div style={{ position: 'absolute', left: 30, top: 24, display: 'flex', alignItems: 'center', gap: 12, zIndex: 4 }}>
          <span style={{ height: 1, width: 60, background: 'rgba(184,151,98,.35)' }} />
          <span style={{ fontFamily: 'Cinzel, serif', letterSpacing: '.3em', fontSize: 12, color: 'var(--gold-hi)' }}>ZONE {selectedZone + 1} · {zone.name.toUpperCase()}</span>
          <span style={{ fontFamily: 'Cinzel, serif', letterSpacing: '.2em', fontSize: 11, color: 'var(--muted)' }}>FLOORS {startFloor}–{startFloor + 9}</span>
        </div>
        <div style={{ position: 'absolute', left: 30, top: 46, fontSize: '0.8rem', fontStyle: 'italic', color: 'var(--muted)', maxWidth: 460, textShadow: '0 1px 4px rgba(0,0,0,.9)', zIndex: 4 }}>
          {zone.blurb}
        </div>

        {/* connecting polyline */}
        <svg style={{ position: 'absolute', inset: 0, pointerEvents: 'none' }} width="100%" height="100%" preserveAspectRatio="none" viewBox="0 0 100 100">
          <polyline points={floors.map((f, i) => {
            const p = posFor(i); return `${parseFloat(p.left)},${100 - parseFloat(p.bottom)}`
          }).join(' ')} fill="none" stroke="rgba(184,151,98,.35)" strokeWidth="0.3" vectorEffect="non-scaling-stroke" strokeDasharray="1 1.6" />
        </svg>

        {/* floor diamonds */}
        {floors.map((f, i) => {
          const isLocked = f > nextFloor
          const isNext = f === nextFloor
          const isSelected = f === selectedFloor
          const isBoss = f % 10 === 0
          const cleared = f <= highestFloor
          const pos = posFor(i)
          const size = isNext ? 88 : 56
          let border = '1px solid rgba(184,151,98,.4)'
          let bg = 'rgba(12,7,24,.7)'
          let numColor = 'var(--muted)'
          if (isNext) { border = '1px solid var(--gold-hi)'; bg = 'linear-gradient(150deg,#2a1650,#140b22)'; numColor = 'var(--text-hi)' }
          if (isBoss) { border = '1px solid rgba(192,64,64,.8)'; bg = 'linear-gradient(150deg,#2a0d12,#140b22)'; numColor = 'var(--red-hi)' }
          if (isLocked) { border = '1px dashed rgba(150,110,230,.5)'; bg = 'rgba(12,7,24,.5)'; numColor = 'var(--lavender)' }
          return (
            <button key={`${selectedZone}-${f}`} disabled={isLocked} onClick={() => setSelectedFloor(f)}
              style={{ position: 'absolute', left: pos.left, bottom: pos.bottom, width: size, height: size,
                transform: 'translate(-50%, 50%)', background: 'none', border: 'none', padding: 0,
                cursor: isLocked ? 'not-allowed' : 'pointer', zIndex: isNext ? 5 : 3 }}
              title={zoneFloorTypes[f]?.floor_type ? FLOOR_TYPE_INFO[zoneFloorTypes[f].floor_type]?.label : (isLocked ? 'Locked' : isNext ? 'Next' : '')}>
              {/* the rise lives on this wrapper — the button's centering
                  transform and the diamond's rotate stay untouched. Keyed on
                  the zone so switching zones replays the ascent. */}
              <div style={{ position: 'absolute', inset: 0, animation: `floor-rise .5s cubic-bezier(.2,.9,.3,1) ${0.08 + i * 0.09}s both` }}>
                <div style={{ position: 'absolute', inset: isNext ? 8 : 6, transform: 'rotate(45deg)', border,
                  background: bg, boxShadow: isBoss ? '0 0 22px rgba(192,64,64,.4)' : 'none',
                  animation: isNext ? 'tile-pulse 3.5s ease-in-out infinite' : undefined,
                  outline: isSelected ? '2px solid var(--gold-max)' : undefined, outlineOffset: 3 }} />
                <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontFamily: 'Cinzel, serif', fontWeight: isNext ? 900 : 400, fontSize: isNext ? 26 : (isBoss ? 19 : 15), color: numColor }}>
                  {isLocked ? '?' : f}
                </div>
                <div style={{ position: 'absolute', left: '50%', top: '100%', transform: 'translateX(-50%)', whiteSpace: 'nowrap',
                  fontFamily: 'Cinzel, serif', fontSize: 9, letterSpacing: '.24em', marginTop: 2,
                  color: isNext ? 'var(--gold-hi)' : isBoss ? 'var(--red)' : 'var(--text-dim)' }}>
                  {isNext ? 'NEXT' : isBoss ? 'BOSS' : cleared ? 'CLEARED' : ''}
                </div>
              </div>
            </button>
          )
        })}

        </div>{/* /climb area */}

        {/* zone rail — its OWN footer band under the climb, so the diamonds
            never crowd the floors. A clean horizontal strip (mock parity). */}
        <div style={{ flex: 'none', borderTop: '1px solid rgba(184,151,98,.18)', background: 'linear-gradient(rgba(10,7,19,0),rgba(10,7,19,.5))', padding: '14px 30px 16px', display: 'flex', alignItems: 'flex-end', gap: 26 }}>
          {Array.from({ length: Math.max(maxZone + 1, 1) + (maxZone + 1 <= 9 ? 1 : 0) }).map((_, z) => {
            const unlocked = z <= maxZone
            const active = z === selectedZone
            const roman = ['I','II','III','IV','V','VI','VII','VIII','IX','X'][z] || (z + 1)
            const lo = z * 10 + 1, hi = z * 10 + 10
            const sz = active ? 50 : 44
            return (
              <button key={z} disabled={!unlocked} onClick={() => setSelectedZone(z)}
                style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8, background: 'none', border: 'none', cursor: unlocked ? 'pointer' : 'default', opacity: unlocked ? 1 : 0.5 }}>
                <span className="ilm-mono" style={{ width: sz, height: sz,
                  border: active ? '1px solid var(--gold-hi)' : unlocked ? '1px solid rgba(184,151,98,.5)' : '1px dashed rgba(150,110,230,.5)',
                  background: active ? 'linear-gradient(150deg,#2a1650,#140b22)' : 'linear-gradient(150deg,rgba(28,16,48,.6),rgba(12,7,24,.5))',
                  boxShadow: active ? '0 0 20px rgba(184,151,98,.45)' : 'none' }}>
                  <span style={{ fontSize: active ? 18 : 15, fontWeight: 700, color: active ? 'var(--text-hi)' : unlocked ? 'var(--gold-hi)' : 'var(--lavender)' }}>{roman}</span>
                </span>
                <span style={{ fontFamily: 'Cinzel, serif', fontSize: 10, letterSpacing: '.16em', color: active ? 'var(--gold-hi)' : 'var(--text-dim)' }}>{unlocked ? `${lo}–${hi}` : '?'}</span>
              </button>
            )
          })}
        </div>
      </div>
    </div>
  )
}

export default function TowerPage({ onGoldChange, onNavigate }) {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [dailyOpen, setDailyOpen] = useState(false)
  // Bumped once the zone draw resolves. ZONES is module-level (see above), so
  // mutating it alone would not repaint — this is what makes the drawn zones
  // actually appear. Fires once; the seed is persisted so it never redraws.
  const [zonesReady, setZonesReady] = useState(0)
  useEffect(() => {
    let alive = true
    loadZones().then((z) => {
      if (!alive) return
      ZONES = z
      setZonesReady((n) => n + 1)
    })
    return () => { alive = false }
  }, [])
  
  const [team, setTeam] = useState({})
  const [base, setBase] = useState(null)
  const [highestFloor, setHighestFloor] = useState(0)

  // GUI State
  const [selectedZone, setSelectedZone] = useState(0)
  const [selectedFloor, setSelectedFloor] = useState(1)
  const [resolvedFloor, setResolvedFloor] = useState(null)
  const [deployTeamIds, setDeployTeamIds] = useState([1, 2, 3, 4, 5])

  // Combat/Event State
  const [advancing, setAdvancing] = useState(false)
  const [lastResult, setLastResult] = useState(null)
  const [pendingEvent, setPendingEvent] = useState(null)
  const [resolving, setResolving] = useState(false)
  const [eventResolution, setEventResolution] = useState(null)
  const [pendingExplore, setPendingExplore] = useState(null)
  const [exploreResolution, setExploreResolution] = useState(null)

  
  const [combatEntities, setCombatEntities] = useState(null)
  const [postCombatPhase, setPostCombatPhase] = useState(false)
  // Death Ceremony queue — when a combat result carries dead_heroes, the
  // fallen who EARNED A LEGACY (see legacy_service.qualifies_for_legacy —
  // level 30+, 10+ unique floors, or a career mentor) get the full rite,
  // one after another, on the post-combat screen. Lesser deaths pass
  // quietly to the Memorial's roll. Legacy rows are written synchronously
  // during combat resolution, so they're queryable by the time the result
  // lands; matched by hero_id. De-duped per result.
  const [deathQueue, setDeathQueue] = useState([])
  const processedDeathsRef = React.useRef(null)
  useEffect(() => {
    const dead = lastResult?.combat?.dead_heroes
    if (!postCombatPhase || !dead?.length) return
    const key = JSON.stringify(dead) + (resolvedFloor || selectedFloor)
    if (processedDeathsRef.current === key) return
    processedDeathsRef.current = key
    Promise.all([
      getLegacies().catch(() => []),
      ...dead.map(id => getHero(id).catch(() => null)),
    ]).then(([legacies, ...heroes]) => {
      const legacyByHero = new Map(
        (Array.isArray(legacies) ? legacies : legacies?.legacies || [])
          .filter(l => l.hero_id != null)
          .map(l => [l.hero_id, l])
      )
      const enshrined = heroes.filter(h => h && legacyByHero.has(h.id)).map(h => ({
        ...h,
        floor: resolvedFloor || selectedFloor,
        legacy: legacyByHero.get(h.id)?.title || undefined,
        eulogy: legacyByHero.get(h.id)?.flavor_text || undefined,
      }))
      if (enshrined.length) setDeathQueue(q => [...q, ...enshrined])
    })
  }, [postCombatPhase, lastResult])
  const [arenasFinished, setArenasFinished] = useState(0)
  // When a real fight starts animating, we stash it here so leaving the
  // Tower tab (which unmounts this whole page — the app renders exactly
  // one tab's component at a time) and coming back doesn't just lose the
  // fight. On remount we restore it and fast-forward the animation by
  // exactly how long the player was gone, instead of replaying from turn 1.
  const [resumeTurnIndex, setResumeTurnIndex] = useState(-1)
  // Guards concludeCombat so a fight's deferred deaths are finalized exactly
  // once — the multi-arena onComplete and React's double-invoked state
  // updaters could otherwise fire it twice. Reset when a new fight begins.
  const combatFinalizedRef = React.useRef(false)
  // Indexed by team/arena position — one AI-narrated line per turn, swapped
  // in for the raw damage-number log line once it arrives (see pollTurnNarrative).
  const [turnNarrations, setTurnNarrations] = useState({})
  const [floorPreview, setFloorPreview] = useState(null)
  const [zoneFloorTypes, setZoneFloorTypes] = useState({})

  useEffect(() => {
    refresh()
    // Resume an in-progress fight left running when this tab was last torn
    // down (see saveActiveCombat). Compute how many turns "should have
    // played" from real elapsed time and fast-forward CombatArena to it.
    const active = loadActiveCombat()
    if (active) {
      // Match CombatArena's current speed store (combatSpeed = 1|2|4), with a
      // fallback to the legacy combatSpeed2x flag — the old code only read the
      // legacy key, so 4× players resumed at the wrong fast-forward point.
      const sv = parseInt(localStorage.getItem('combatSpeed') || '')
      const speedMult = (sv === 2 || sv === 4) ? sv : (localStorage.getItem('combatSpeed2x') === '1' ? 2 : 1)
      const elapsedTurns = Math.floor((Date.now() - active.deployedAt) / (TURN_DELAY_MS / speedMult))
      setLastResult(active.result)
      setResolvedFloor(active.resolvedFloor)
      setCombatEntities(mergedCombatEntities(active.result))
      setResumeTurnIndex(elapsedTurns)
    }
  }, [])

  useEffect(() => {
    if (lastResult) return
    if (selectedFloor <= highestFloor) {
      setFloorPreview(null)
      return
    }
    let cancelled = false
    previewFloor(selectedFloor).then(p => { if (!cancelled) setFloorPreview(p) }).catch(() => {})
    return () => { cancelled = true }
  }, [selectedFloor, highestFloor, lastResult])

  // Floor type is deterministic/cached server-side per floor number, so
  // previewing the whole zone's grid up front (not just the one selected
  // floor) is safe — it never changes the outcome, just lets the grid
  // show each tile's real type instead of being blank/generic. Extracted
  // into a callable so it can also be re-run the instant a fight finishes
  // (a just-cleared floor's tile flips from "?" to its revealed type
  // without waiting for the player to switch zones and back).
  async function refreshZoneFloorTypes(zoneIndex = selectedZone) {
    const start = zoneIndex * 10 + 1
    const floors = Array.from({ length: 10 }, (_, i) => start + i)
    const results = await Promise.all(
      floors.map(f => previewFloor(f).then(p => [f, p]).catch(() => [f, null]))
    )
    setZoneFloorTypes(prev => {
      const next = { ...prev }
      for (const [f, p] of results) if (p) next[f] = p
      return next
    })
  }

  useEffect(() => {
    let cancelled = false
    refreshZoneFloorTypes(selectedZone).catch(() => {})
    return () => { cancelled = true }
  }, [selectedZone])

  useEffect(() => {
    // Silently sync highest_floor to the Arena server if logged in
    if (highestFloor > 0 && getArenaToken()) {
      arenaUpdateFloor(highestFloor).catch(() => {})
    }
  }, [highestFloor])

  // silent=true skips the full-page loading flag — used after a fight
  // finalizes (to fold the now-revealed deaths into the deploy roster)
  // without flashing the "Loading..." screen over the post-combat report.
  async function refresh(silent = false) {
    if (!silent) setLoading(true)
    try {
      const [teamsData, baseData] = await Promise.all([getAllTeams(), getBase()]);
      setHighestFloor(baseData.highest_floor || 0);
      setTeam(teamsData)
      setBase(baseData)

      if (!lastResult && baseData.highest_floor > 0) {
        const nextFloor = baseData.highest_floor + 1
        setSelectedFloor(nextFloor)
        setSelectedZone(Math.floor((nextFloor - 1) / 10))
      }
    } catch (e) {
      console.error(e)
    } finally {
      if (!silent) setLoading(false)
    }
  }

  function pollNarrative(narrativeId, attemptsLeft = 4) {
    if (!narrativeId || attemptsLeft <= 0) return
    setTimeout(async () => {
      try {
        const res = await getNarrative(narrativeId)
        if (res.ready && res.narrative) {
          setLastResult(prev => prev ? { ...prev, narrative: res.narrative } : prev)
        } else {
          pollNarrative(narrativeId, attemptsLeft - 1)
        }
      } catch {
        // Flavor text only — silently give up on failure.
      }
    }, 2000)
  }

  // Polls more frequently/eagerly than pollNarrative — combat plays out at
  // 800ms/turn, so the per-turn narration array needs to land mid-fight to
  // be useful, not after the player's already watched the whole thing play
  // out with raw damage-number lines.
  function pollTurnNarrative(narrativeId, arenaIndex, attemptsLeft = 6) {
    if (narrativeId == null || attemptsLeft <= 0) return
    setTimeout(async () => {
      try {
        const res = await getNarrative(narrativeId)
        if (res.ready && Array.isArray(res.narrative)) {
          setTurnNarrations(prev => ({ ...prev, [arenaIndex]: res.narrative }))
        } else if (!res.ready) {
          pollTurnNarrative(narrativeId, arenaIndex, attemptsLeft - 1)
        }
      } catch {
        // Flavor text only — silently give up on failure.
      }
    }, 1000)
  }

  async function enterFloorFlow(floorNumber, { skipAnimation = false } = {}) {
    setAdvancing(true)
    setError(null)
    setEventResolution(null)
    setPendingEvent(null)
    setExploreResolution(null)
    setPendingExplore(null)
    setLastResult(null)
    setResolvedFloor(floorNumber)
    setCombatEntities(null)
    setPostCombatPhase(false)
    setArenasFinished(0)
    setTurnNarrations({})
    setResumeTurnIndex(-1)
    combatFinalizedRef.current = false
    clearActiveCombat()

    try {
      const requiredTeams = (floorNumber - 1) === 0 ? 1 : Math.floor((floorNumber - 1) / 20) + 1
      const result = await enterFloor(floorNumber, deployTeamIds.slice(0, requiredTeams), 'balanced')
      setLastResult(result)
      setCombatEntities(mergedCombatEntities(result))
      scanCombatForDiscoveries(result)  // codex pages unlock on first encounter
      // Deeds — announce each permanent record the fight just earned.
      if (result.deeds_earned?.length) {
        const heroName = (id) => result.combat?.initial_state?.heroes?.find(h => h.id === id)?.name || ''
        result.deeds_earned.slice(0, 3).forEach((d, i) => {
          setTimeout(() => {
            playDeedChime()
            emitToast({
              title: 'DEED RECORDED',
              lines: [{ label: heroName(d.hero_id), value: d.deed }],
              borderColor: 'var(--gold)',
            })
          }, 800 + i * 1400)
        })
      }
      if (result.narrative_id) pollNarrative(result.narrative_id)
      const tnIds = result.turn_narrative_ids || (result.turn_narrative_id != null ? [result.turn_narrative_id] : [])
      tnIds.forEach((id, i) => pollTurnNarrative(id, i))

      if (result.awaiting_choice && result.event) {
        setPendingEvent(result)
      } else if (result.awaiting_choice && result.explore) {
        setPendingExplore(result)
      } else if (skipAnimation) {
        // Already seen this floor — jump straight to the resolution screen
        // instead of replaying the full combat animation. No animation means
        // no timeline to spoil, so reveal the fallen immediately (the refresh
        // below then folds the deaths into the roster).
        combatFinalizedRef.current = true
        try { await finalizeCombat(result.pending_combat_id ?? null) } catch {}
        setPostCombatPhase(true)
      } else {
        // A real animation is about to play — save it so leaving and
        // returning to this tab can resume instead of losing it.
        saveActiveCombat(result, floorNumber)
        // Battle music: boss floors (every 10th, or a boss-typed floor) get the
        // boss theme; miniboss floors get the elite theme; everything else the
        // standard combat theme. The manager keeps it continuous across floors.
        const ft = zoneFloorTypes[floorNumber]?.floor_type
        setBgmScene(
          (floorNumber % 10 === 0 || ft === 'boss') ? 'boss'
            : (ft && ft.startsWith('miniboss')) ? 'elite'
              : 'combat'
        )
      }

      await refresh()
      refreshZoneFloorTypes().catch(() => {})
      if (onGoldChange) onGoldChange()
    } catch (e) {
      setError(e.message)
    } finally {
      setAdvancing(false)
    }
  }

  function handleEnterFloor() {
    return enterFloorFlow(selectedFloor)
  }

  function handleSkipFloor() {
    return enterFloorFlow(selectedFloor, { skipAnimation: true })
  }

  function handleRerun() {
    return enterFloorFlow(resolvedFloor || selectedFloor, { skipAnimation: true })
  }

  // Fired when a fight's animation finishes playing. The fallen's deaths were
  // deferred server-side so they wouldn't spoil on other tabs mid-fight — now
  // that the player has actually watched the battle play out, reveal them:
  // finalize (applies the death + legacy at the DB) BEFORE we flip to the
  // post-combat screen, so the Death Ceremony and Memorial see the legacy,
  // then silently refresh the deploy roster so the fallen drops off the team.
  async function concludeCombat({ won = null } = {}) {
    clearActiveCombat()
    if (won != null) playMusicStinger(won ? 'victory' : 'defeat')
    if (!combatFinalizedRef.current) {
      combatFinalizedRef.current = true
      try { await finalizeCombat(lastResult?.pending_combat_id ?? null) } catch {}
      refresh(true)  // fold now-revealed deaths into the roster, no loading flash
    }
    setPostCombatPhase(true)
  }

  // "The battle fights on" — the first time a player leaves an ongoing fight,
  // explain that combat resolves on its own and they can return anytime.
  const [stepAwayOpen, setStepAwayOpen] = useState(false)
  const [dontRemindStepAway, setDontRemindStepAway] = useState(false)
  function requestBattlefieldExit() {
    if (localStorage.getItem('combatStepAwaySeen') === '1') { handleExit(); return }
    setStepAwayOpen(true)
  }
  function confirmStepAway() {
    if (dontRemindStepAway) localStorage.setItem('combatStepAwaySeen', '1')
    setStepAwayOpen(false)
    handleExit()
  }

  function handleExit() {
    clearActiveCombat()
    setBgmScene('towerAscent')  // back to the floor-select bed
    setLastResult(null)
    setEventResolution(null)
    setExploreResolution(null)
    setPendingEvent(null)
    setPendingExplore(null)
    setAllLogs([])
    setPostCombatPhase(false)
  }

  async function handleEventChoice(choiceId) {
    setResolving(true)
    setError(null)
    try {
      const result = await resolveEvent(resolvedFloor || selectedFloor, deployTeamIds[0], pendingEvent.event.template_id, choiceId, pendingEvent.theme)
      setPendingEvent(null)
      setEventResolution(result)

      if (result.combat) {
        // The choice turned hostile — route through the same animated
        // combat arena as a normal/Explore floor instead of jumping
        // straight to the static narrative-only result box.
        setLastResult(result)
        setArenasFinished(0)
        setTurnNarrations({})
        setResumeTurnIndex(-1)
        combatFinalizedRef.current = false
        setCombatEntities(mergedCombatEntities(result))
        saveActiveCombat(result, resolvedFloor || selectedFloor)
        const tnIds = result.turn_narrative_ids || (result.turn_narrative_id != null ? [result.turn_narrative_id] : [])
        tnIds.forEach((id, i) => pollTurnNarrative(id, i))
      } else {
        setPostCombatPhase(true)
      }

      await refresh()
      refreshZoneFloorTypes().catch(() => {})
      if (onGoldChange) onGoldChange()
    } catch (e) {
      setError(e.message)
    } finally {
      setResolving(false)
    }
  }

  async function handleExploreChoice(choiceId) {
    setResolving(true)
    setError(null)
    try {
      const result = await resolveExplore(resolvedFloor || selectedFloor, deployTeamIds[0], choiceId)
      // Explore always ends in a real fight now — route through the same
      // combat animation as a normal floor, instead of jumping straight to
      // a static result box.
      setExploreResolution(result)
      setLastResult(result)
      setArenasFinished(0)
      setTurnNarrations({})
      setResumeTurnIndex(-1)
      combatFinalizedRef.current = false
      setCombatEntities(mergedCombatEntities(result))
      setPendingExplore(null)
      saveActiveCombat(result, resolvedFloor || selectedFloor)
      const tnIds = result.turn_narrative_ids || (result.turn_narrative_id != null ? [result.turn_narrative_id] : [])
      tnIds.forEach((id, i) => pollTurnNarrative(id, i))

      await refresh()
      refreshZoneFloorTypes().catch(() => {})
      if (onGoldChange) onGoldChange()
    } catch (e) {
      setError(e.message)
    } finally {
      setResolving(false)
    }
  }

  if (loading) return <div className="page text-dim">Loading...</div>

  const maxZone = Math.floor(highestFloor / 10)
  const startFloorOfZone = selectedZone * 10 + 1

  return (
    <div className="page" style={{ display: 'flex', flexDirection: 'column' }}>
      {lastResult ? (
        // Result screen centers in the page's height (no big empty bottom);
        // during combat playback it stays top-aligned so the tall arena has
        // room to breathe.
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: postCombatPhase ? 'center' : 'flex-start' }}>
          {/* Centered Resolution Header — small context label under the
              post-combat slash banner; full title elsewhere in the flow. */}
          {postCombatPhase ? (
            <div style={{ textAlign: 'center', marginBottom: '0.4rem' }}>
              <span style={{ fontFamily: 'Cinzel, serif', letterSpacing: '.5em', fontSize: '0.72rem', color: 'var(--gold-hi)' }}>FLOOR {resolvedFloor}</span>
            </div>
          ) : (
            <div style={{ textAlign: 'center', marginBottom: '2rem' }}>
              <div className="text-dim text-sm" style={{ letterSpacing: 2, textTransform: 'uppercase' }}>Resolution</div>
              <div style={{ fontFamily: 'Cinzel, serif', fontSize: '3rem', color: 'var(--gold)', textShadow: '0 2px 10px rgba(201,168,76,0.3)' }}>
                Floor {resolvedFloor}
              </div>
            </div>
          )}

          {lastResult && <FloorTypeCallout type={lastResult.floor_type} isSurvivalSwarm={
            (lastResult.combat?.team_results || lastResult.team_results || []).some(tr => tr?.initial_state?.is_survival_swarm)
            || lastResult.combat?.initial_state?.is_survival_swarm
            || lastResult.initial_state?.is_survival_swarm
          } />}

          {postCombatPhase && lastResult.run_over && (
            <div className="text-red" style={{ maxWidth: '600px', margin: '0 auto 2rem auto', textAlign: 'center', padding: '1rem', background: 'rgba(192,64,64,0.1)', border: '1px solid #c44', borderRadius: 6 }}>
              ✦ The team was defeated and forced to retreat.
            </div>
          )}

          {error && <div className="text-red text-center" style={{ marginBottom: '1rem' }}>{error}</div>}

          {/* Event UI (Interrupts combat flow if awaiting choice) */}
          {pendingEvent && !postCombatPhase && (
            <div className="ilm-floorevent gold">
              <span className="ilm-corner" /><span className="ilm-corner ilm-corner-r" /><span className="ilm-corner ilm-corner-br" />
              <div className="ilm-floorevent-eyebrow">FLOOR {resolvedFloor || selectedFloor} · AN EVENT UNFOLDS</div>
              <div className="ilm-floorevent-title">A CHOICE</div>
              <div className="ilm-floorevent-narrative">
                {pendingEvent.event_narrative || pendingEvent.event.theme}
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
                {pendingEvent.event.choices.map((choice, ci) => (
                  <button key={choice.id} className="ilm-floorevent-choice" onClick={() => handleEventChoice(choice.id)} disabled={resolving}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
                      <span style={{ fontFamily: "'Cinzel',serif", fontSize: '0.72rem', color: 'var(--gold-hi)', width: 20, flex: 'none' }}>{['I', 'II', 'III', 'IV'][ci] || ci + 1}</span>
                      <span style={{ flex: 1, color: 'var(--text-hi)', fontFamily: "'Cinzel',serif", fontSize: '0.92rem', letterSpacing: '.04em', textAlign: 'left' }}>
                        {choice.label || choice.text || `Choice ${choice.id}`}
                      </span>
                      {(choice.tags || []).map(t => (
                        <span key={t} style={{
                          fontFamily: "'Cinzel',serif", fontSize: '0.52rem', letterSpacing: '.16em', padding: '2px 9px', flex: 'none',
                          color: t === 'MAY TURN TO BATTLE' ? 'var(--red-hi)' : t === 'SAFE' ? 'var(--green-hi)' : t === 'GOLD' ? 'var(--gold-hi)' : 'var(--lavender)',
                          border: `1px solid ${t === 'MAY TURN TO BATTLE' ? 'rgba(192,64,64,.4)' : t === 'SAFE' ? 'rgba(74,154,106,.4)' : t === 'GOLD' ? 'rgba(184,151,98,.4)' : 'rgba(150,110,230,.4)'}`,
                        }}>{t}</span>
                      ))}
                    </div>
                    {choice.hint && (
                      <div className="text-dim" style={{ fontSize: '0.82rem', marginTop: '0.3rem', marginLeft: 34, fontStyle: 'italic', textAlign: 'left' }}>{choice.hint}</div>
                    )}
                  </button>
                ))}
              </div>
              {resolving && <div className="text-dim text-center" style={{ marginTop: '1rem' }}>Resolving…</div>}
              <div style={{ textAlign: 'center', marginTop: '1rem' }}>
                <button className="ilm-btn ilm-btn-ghost" onClick={handleExit} disabled={resolving}>STEP AWAY</button>
              </div>
            </div>
          )}

          {/* Explore UI (Interrupts combat flow if awaiting choice) */}
          {pendingExplore && !postCombatPhase && (
            <div className="ilm-floorevent green">
              <span className="ilm-corner" /><span className="ilm-corner ilm-corner-r" /><span className="ilm-corner ilm-corner-br" />
              <div className="ilm-floorevent-eyebrow" style={{ color: 'var(--green-hi)' }}>A PATH UNTRODDEN</div>
              <div className="ilm-floorevent-title">EXPLORE</div>
              <div className="ilm-floorevent-narrative">
                {pendingExplore.explore.theme}
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
                {pendingExplore.explore.choices.map(choice => (
                  <button key={choice.id} className="ilm-floorevent-choice" onClick={() => handleExploreChoice(choice.id)} disabled={resolving}>
                    <div style={{ color: 'var(--text-hi)', fontFamily: "'Cinzel',serif", fontSize: '0.92rem', letterSpacing: '.04em' }}>{choice.label}</div>
                    {choice.hint && (
                      <div className="text-dim" style={{ fontSize: '0.82rem', marginTop: '0.3rem', fontStyle: 'italic' }}>{choice.hint}</div>
                    )}
                  </button>
                ))}
              </div>
              {resolving && <div className="text-dim text-center" style={{ marginTop: '1rem' }}>Resolving…</div>}
              <div style={{ textAlign: 'center', marginTop: '1rem' }}>
                <button className="ilm-btn ilm-btn-ghost" onClick={handleExit} disabled={resolving}>STEP AWAY</button>
              </div>
            </div>
          )}

          {/* Battlefield UI */}
          {!postCombatPhase && !pendingEvent && !pendingExplore && (
            <div style={{ maxWidth: '1200px', margin: '0 auto' }}>
              {lastResult && !lastResult.awaiting_choice && (() => {
                const teamResults = (lastResult?.combat?.team_results || lastResult?.team_results || []).filter(Boolean)
                if (teamResults.length > 1) {
                  const onArenaComplete = () => {
                    setArenasFinished(prev => {
                      const next = prev + 1
                      if (next >= teamResults.length) {
                        // All parallel arenas done — reveal the fallen and
                        // conclude (guarded so this runs once).
                        concludeCombat()
                      }
                      return next
                    })
                  }
                  return (
                    <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap', justifyContent: 'center' }}>
                      {teamResults.map((tr, i) => (
                        <div key={i} style={{ flex: '1 1 480px', minWidth: '420px' }}>
                          <div style={{ textAlign: 'center', color: 'var(--text-hi)', fontFamily: 'Cinzel, serif', marginBottom: '0.3rem' }}>
                            Team {i + 1}
                          </div>
                          <CombatArena combatData={tr} onComplete={onArenaComplete} turnNarrations={turnNarrations[i]} environment={floorArtFor(lastResult?.floor)} />
                        </div>
                      ))}
                    </div>
                  )
                }
                return (
                  <CombatArena
                    environment={floorArtFor(lastResult?.floor)}
                    combatData={lastResult?.combat || lastResult}
                    onComplete={() => {
                      const won = (lastResult?.combat || lastResult)?.winner === 'heroes'
                      concludeCombat({ won })
                    }}
                    turnNarrations={turnNarrations[0]}
                    initialTurnIndex={resumeTurnIndex}
                  />
                )
              })()}
              <div style={{ textAlign: 'center', marginTop: '1rem' }}>
                <button className="ilm-btn ilm-btn-ghost" onClick={requestBattlefieldExit}>STEP AWAY</button>
              </div>

              {stepAwayOpen && (
                <div className="ilm-modal-scrim" style={{ zIndex: 340 }} onClick={() => setStepAwayOpen(false)}>
                  <div className="ilm-stepaway" onClick={e => e.stopPropagation()}>
                    <span className="ilm-corner" />
                    <div className="ilm-stepaway-title">THE BATTLE FIGHTS ON</div>
                    <div className="ilm-stepaway-body">Combat resolves on its own. Tend to your Base or roster and return anytime — the Chronicle will be waiting.</div>
                    <div style={{ display: 'flex', gap: 10, marginTop: 14 }}>
                      <button className="ilm-btn ilm-btn-violet" onClick={confirmStepAway}>STEP AWAY</button>
                      <button className="ilm-btn ilm-btn-ghost" onClick={() => setStepAwayOpen(false)}>KEEP WATCHING</button>
                    </div>
                    <label className="ilm-stepaway-remind">
                      <input type="checkbox" checked={dontRemindStepAway} onChange={e => setDontRemindStepAway(e.target.checked)} />
                      <span>DON'T REMIND ME AGAIN</span>
                    </label>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Post Combat Screens */}
          {postCombatPhase && (
            <div style={{ maxWidth: '1000px', margin: '0 auto' }}>
              <PostCombatScreen
                lastResult={lastResult}
                combatEntities={combatEntities}
                onReturn={handleExit}
                onRerun={handleRerun}
                busy={advancing}
              />

              {eventResolution && (
                <div className="card" style={{
                  marginTop: '2rem',
                  border: '1px solid var(--green)',
                  background: 'rgba(74,154,106,0.08)',
                  textAlign: 'center'
                }}>
                  <div style={{ fontFamily: 'Cinzel, serif', fontSize: '1.2rem', color: 'var(--green)', marginBottom: '0.5rem' }}>
                    {eventResolution.choice_label || 'Event Resolved'}
                  </div>
                  <div style={{ lineHeight: 1.6, fontSize: '1.05rem' }}>
                    {eventResolution.event_narrative || eventResolution.narrative}
                  </div>
                  {eventResolution.effects?.trait && (
                    <div style={{ marginTop: '1rem', padding: '0.6rem 1rem', border: '1px solid var(--gold)', borderRadius: 6, background: 'rgba(201,168,76,0.08)', display: 'inline-block' }}>
                      <div style={{ fontFamily: 'Cinzel, serif', color: 'var(--gold)', fontSize: '0.95rem' }}>
                        ✦ New Trait: {eventResolution.effects.trait.name}
                      </div>
                      <div className="text-dim" style={{ fontSize: '0.8rem', marginTop: '0.2rem' }}>
                        {eventResolution.effects.trait.desc}
                      </div>
                    </div>
                  )}
                  {eventResolution.effects?.gems > 0 && (
                    <div style={{ marginTop: '1rem', fontSize: '1.1rem', color: '#00ffff' }}>
                      +{eventResolution.effects.gems} <GameIcon name="gem" size={16} />
                    </div>
                  )}
                  {eventResolution.effects?.gold > 0 && (
                    <div className="text-gold" style={{ marginTop: '0.5rem', fontSize: '1.1rem' }}>
                      +{eventResolution.effects.gold}g
                    </div>
                  )}
                </div>
              )}

              {exploreResolution?.explore_loot && (
                <div className="card" style={{
                  marginTop: '2rem',
                  border: '1px solid var(--green)',
                  background: 'rgba(74,154,106,0.08)',
                  textAlign: 'center'
                }}>
                  <div style={{ fontFamily: 'Cinzel, serif', fontSize: '1.2rem', color: 'var(--green)', marginBottom: '0.5rem' }}>
                    Exploration Bonus
                  </div>
                  <div style={{ lineHeight: 1.6, fontSize: '1.05rem' }}>
                    {exploreResolution.explore_loot.summary}
                  </div>
                  {exploreResolution.explore_loot.loot?.desc && (
                    <div className="text-gold" style={{ marginTop: '1rem', fontSize: '1.1rem' }}>
                      {exploreResolution.explore_loot.loot.desc}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

        </div>
      ) : (
        <AscentScreen
          selectedZone={selectedZone}
          setSelectedZone={setSelectedZone}
          selectedFloor={selectedFloor}
          setSelectedFloor={setSelectedFloor}
          highestFloor={highestFloor}
          maxZone={maxZone}
          zoneFloorTypes={zoneFloorTypes}
          floorPreview={floorPreview}
          team={team}
          deployTeamIds={deployTeamIds}
          setDeployTeamIds={setDeployTeamIds}
          advancing={advancing}
          error={error}
          onEnter={handleEnterFloor}
          onRush={handleSkipFloor}
          onDailyGates={() => setDailyOpen(true)}
          onFormation={() => onNavigate && onNavigate('heroes')}
        />
      )}
      {dailyOpen && <DailyDungeons onClose={() => setDailyOpen(false)} />}
      <FairyGuide floor={resolvedFloor || selectedFloor} lastResult={lastResult} fairyGender={base.fairy_gender} highestFloor={highestFloor} />
      {deathQueue.length > 0 && (
        <DeathCeremony hero={deathQueue[0]} onClose={() => setDeathQueue(q => q.slice(1))} />
      )}
    </div>
  )
}
