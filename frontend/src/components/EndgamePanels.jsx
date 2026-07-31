import React, { useState, useEffect } from 'react'
import GameIcon from './GameIcon'
import MinigameShell, { AUTO_RESOLVE_MULT, bestAssignedHero, effectiveStar } from './minigames/MinigameShell'
import CookSequence from './minigames/CookSequence'
import StillControl from './minigames/StillControl'
import SigilTrace from './minigames/SigilTrace'
import HuntGrid from './minigames/HuntGrid'
import {
  getDiningCatalog, cookFood, refineAether,
  getBestiary, releaseBeast, huntBeast, shrineRite,
  getReliquary, mountTrophy,
  getChronosphere, activateChronosphere,
  getTranscendence, infuseTranscendence,
} from '../api/client'

// Inline sub-panels rendered inside their facility's card on the Base page
// (same pattern as the Mage Tower research grid / Mirror of Fate panel).

const panelStyle = { marginTop: '1rem', background: 'rgba(0,0,0,0.2)', padding: '0.75rem', borderRadius: 6 }

function useMsg() {
  const [msg, setMsg] = useState(null)
  return [msg && <div style={{ color: msg.err ? '#f87' : '#8e8', fontSize: '0.85rem', margin: '0.5rem 0' }}>{msg.text}</div>,
    (text, err = false) => setMsg({ text, err })]
}

// ── Dining Hall: cook Farm ingredients into consumables ──────────────

export function CookingPanel({ facility, onResourceChange }) {
  // Whoever is assigned here is what the player has to beat.
  const staffer = bestAssignedHero(facility)
  const [catalog, setCatalog] = useState([])
  const [busy, setBusy] = useState(false)
  const [msgEl, setMsg] = useMsg()
  // SEASON THE POT minigame — the cook button opens it; skip = NOVICE baseline.
  const [minigameId, setMinigameId] = useState(null)

  useEffect(() => { getDiningCatalog().then(setCatalog).catch(() => {}) }, [])

  function handleCook(id) { setMinigameId(id) }

  async function doCook(id, qualityMult) {
    setMinigameId(null)
    setBusy(true)
    try {
      const res = await cookFood(id, 1, qualityMult)
      if (res.ruined) setMsg(res.message || 'The pot is scorched — nothing served.', true)
      else setMsg(`Cooked ${res.cooked}x ${res.item} (${res.ingredients_spent} ingredients${res.chef_discount ? ', Chef discount!' : ''}${res.cooked > 1 ? ' — the seasoning sang' : ''})`)
      if (onResourceChange) onResourceChange()
    } catch (e) { setMsg(e.message, true) } finally { setBusy(false) }
  }

  if (!catalog.length) return null
  return (
    <div style={panelStyle}>
      <div style={{ color: 'var(--gold)', marginBottom: '0.5rem', fontFamily: 'Cinzel, serif' }}>The Kitchen</div>
      <div className="text-dim text-sm" style={{ marginBottom: '0.5rem' }}>
        Cook Farm ingredients into consumables — equip them on heroes so they can eat mid-climb. A Chef on staff wastes 25% fewer ingredients.
      </div>
      {msgEl}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(190px, 1fr))', gap: '0.5rem' }}>
        {catalog.map(f => (
          <div key={f.id} className="card" style={{ padding: '0.5rem', opacity: f.unlocked ? 1 : 0.5 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
              <GameIcon name={f.id} size={28} />
              <div style={{ fontSize: '0.85rem', fontWeight: 'bold' }}>{f.name}</div>
            </div>
            <div style={{ fontSize: '0.7rem', color: 'var(--text-dim)', margin: '0.2rem 0 0.5rem' }}>{f.desc}</div>
            <button className="btn" onClick={() => handleCook(f.id)} disabled={busy || !f.unlocked}
              style={{ width: '100%', fontSize: '0.75rem', padding: '0.2rem' }}>
              {f.unlocked ? `Cook (${f.ingredients} ✦)` : `Dining Hall Lv.${f.min_level}`}
            </button>
          </div>
        ))}
      </div>

      {minigameId && (
        <MinigameShell
          title="SEASON THE POT"
          heroStar={effectiveStar(staffer)}
          heroName={staffer?.name}
          flavor="The recipe is old and exact. Take the ladle yourself, or let the kitchen keep its rhythm."
          onSkip={(mult) => doCook(minigameId, mult)}
          onResolve={(mult) => doCook(minigameId, mult)}
          game={(difficulty, onDone) => <CookSequence difficulty={difficulty} onDone={onDone} />}
        />
      )}
    </div>
  )
}

// ── Alchemist Lab: refine ingredients + gold into Aether ─────────────

export function RefineAetherPanel({ facility, onResourceChange }) {
  // Whoever is assigned here is what the player has to beat.
  const staffer = bestAssignedHero(facility)
  const [busy, setBusy] = useState(false)
  const [msgEl, setMsg] = useMsg()
  // THE STILL minigame — refining opens it; skip = NOVICE baseline yield.
  const [minigameBatches, setMinigameBatches] = useState(null)

  function handleRefine(batches) { setMinigameBatches(batches) }

  async function doRefine(batches, qualityMult) {
    setMinigameBatches(null)
    setBusy(true)
    try {
      const res = await refineAether(batches, qualityMult)
      if (res.ruined) setMsg(res.message || 'The condenser ruptures — nothing is kept.', true)
      else setMsg(`Distilled ${res.refined} Aether (${res.gold_spent}g + ${res.ingredients_spent} ingredients${res.quality && res.quality !== 1 ? `, distillate ×${res.quality.toFixed(2)}` : ''})`)
      if (onResourceChange) onResourceChange()
    } catch (e) { setMsg(e.message, true) } finally { setBusy(false) }
  }

  return (
    <div style={panelStyle}>
      <div style={{ color: '#8fb8ff', marginBottom: '0.5rem', fontFamily: 'Cinzel, serif' }}>
        <GameIcon name="aether_crystal" size={18} /> Aether Distillation
      </div>
      <div className="text-dim text-sm" style={{ marginBottom: '0.5rem' }}>
        Condense raw ingredients into Aether — the fuel magic battleships burn on raids. 400g + 20 ingredients per batch of ~25; Lab level improves the yield. (The Skydock also condenses a slow trickle for free.)
      </div>
      {msgEl}
      <div style={{ display: 'flex', gap: '0.5rem' }}>
        <button className="btn" disabled={busy} onClick={() => handleRefine(1)} style={{ fontSize: '0.8rem' }}>Refine x1</button>
        <button className="btn" disabled={busy} onClick={() => handleRefine(5)} style={{ fontSize: '0.8rem' }}>Refine x5</button>
      </div>

      {minigameBatches != null && (
        <MinigameShell
          title="THE STILL"
          heroStar={effectiveStar(staffer)}
          heroName={staffer?.name}
          flavor="Raw mana wants to be anything but Aether. Take the valves yourself, or trust the Lab's steady simmer."
          onSkip={(mult) => doRefine(minigameBatches, mult)}
          onResolve={(mult) => doRefine(minigameBatches, mult)}
          game={(difficulty, onDone) => <StillControl difficulty={difficulty} onDone={onDone} />}
        />
      )}
    </div>
  )
}

// ── Shrine: CONDUCT A RITE — daily ceremony (TRACE THE SIGIL minigame) ──

export function ShrineRitePanel({ facility, onResourceChange }) {
  // Whoever is assigned here is what the player has to beat.
  const staffer = bestAssignedHero(facility)
  const [msgEl, setMsg] = useMsg()
  const [showRite, setShowRite] = useState(false)

  async function doRite(mult) {
    setShowRite(false)
    try {
      const res = await shrineRite(mult)
      setMsg(res.message, !!res.soured)
      if (onResourceChange) onResourceChange()
    } catch (e) { setMsg(e.message, true) }
  }

  return (
    <div style={panelStyle}>
      <div style={{ color: 'var(--gold)', marginBottom: '0.5rem', fontFamily: 'Cinzel, serif' }}>Conduct a Rite</div>
      <div className="text-dim text-sm" style={{ marginBottom: '0.5rem' }}>
        Once a day, the Shrine's sigil can be traced by the manager's own hand — a clean rite floods the whole roster with loyalty and eases their minds. A soured one unsettles everyone.
      </div>
      {msgEl}
      <button className="btn" onClick={() => setShowRite(true)} style={{ fontSize: '0.8rem' }}>Light the Candles</button>

      {showRite && (
        <MinigameShell
          title="TRACE THE SIGIL"
          heroStar={effectiveStar(staffer)}
          heroName={staffer?.name}
          flavor="The old pattern waits in the dark. Trace it true, or let the clergy murmur through the standard observance."
          onSkip={(mult) => doRite(mult)}
          onResolve={(mult) => doRite(mult)}
          game={(difficulty, onDone) => <SigilTrace difficulty={difficulty} onDone={onDone} />}
        />
      )}
    </div>
  )
}

// ── Bestiary: captured beasts guard the base ─────────────────────────

export function BestiaryPanel() {
  const [data, setData] = useState(null)
  const [msgEl, setMsg] = useMsg()
  const [showHunt, setShowHunt] = useState(false)

  const refresh = () => getBestiary().then(setData).catch(() => {})
  useEffect(() => { refresh() }, [])

  async function handleRelease(b) {
    try {
      await releaseBeast(b.id)
      setMsg(`${b.name} bounds off into the dark of the Tower.`)
      refresh()
    } catch (e) { setMsg(e.message, true) }
  }

  async function doHunt(mult) {
    setShowHunt(false)
    try {
      const res = await huntBeast(mult)
      setMsg(res.message, !!res.escaped)
      refresh()
    } catch (e) { setMsg(e.message, true) }
  }

  if (!data) return null
  return (
    <div style={panelStyle}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <div style={{ color: 'var(--gold)', fontFamily: 'Cinzel, serif' }}>Monster Pens ({data.beasts.length}/{data.capacity})</div>
        <div className="text-dim text-sm">Base defense from beasts: <span style={{ color: '#9fd68a' }}>+{data.defense_bonus}</span></div>
      </div>
      <div className="text-dim text-sm" style={{ margin: '0.4rem 0' }}>
        Every won fight has a {data.capture_chance_pct}% chance to drag a beaten beast home (bosses and humanoids excepted). Penned beasts add their power to your base's defense rating; release one to free a pen.
      </div>
      {msgEl}
      <button className="btn" onClick={() => setShowHunt(true)} style={{ fontSize: '0.8rem', marginBottom: '0.5rem' }}>Mount a Hunt (daily)</button>
      {showHunt && (
        <MinigameShell
          title="THE HUNT"
          flavor="Something big has been leaving tracks near the base. Read the brush yourself, or let the keepers set the ordinary snares."
          onSkip={(mult) => doHunt(mult)}
          onResolve={(mult) => doHunt(mult)}
          game={(difficulty, onDone) => <HuntGrid difficulty={difficulty} onDone={onDone} />}
        />
      )}
      {data.beasts.length === 0 && <div className="text-dim text-sm" style={{ fontStyle: 'italic' }}>The pens stand empty — go pick a fight with something with claws.</div>}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: '0.5rem' }}>
        {data.beasts.map(b => (
          <div key={b.id} className="card" style={{ padding: '0.5rem' }}>
            <div style={{ fontSize: '0.9rem', fontWeight: 'bold', color: 'var(--text-hi)' }}>{b.name}</div>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>{b.species} · caught on Floor {b.floor_caught}</div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '0.4rem' }}>
              <span style={{ fontSize: '0.8rem', color: '#9fd68a' }}>Power {b.power}</span>
              <button className="btn" onClick={() => handleRelease(b)} style={{ fontSize: '0.7rem', padding: '0.15rem 0.4rem' }}>Release</button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Reliquary: mount boss trophies for global buffs ──────────────────

export function ReliquaryPanel() {
  const [data, setData] = useState(null)
  const [msgEl, setMsg] = useMsg()

  const refresh = () => getReliquary().then(setData).catch(() => {})
  useEffect(() => { refresh() }, [])

  async function handleToggle(t) {
    try {
      await mountTrophy(t.id, !t.is_mounted)
      refresh()
    } catch (e) { setMsg(e.message, true) }
  }

  if (!data) return null
  return (
    <div style={panelStyle}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <div style={{ color: 'var(--gold)', fontFamily: 'Cinzel, serif' }}>
          <GameIcon name="trophy" size={18} /> Trophy Hall ({data.mounted_count}/{data.mount_slots} mounted)
        </div>
      </div>
      <div className="text-dim text-sm" style={{ margin: '0.4rem 0' }}>
        Every 10th-floor Boss drops a Trophy. Mounted trophies grant permanent roster-wide buffs; upgrade the Reliquary for more pedestals.
      </div>
      {msgEl}
      {data.trophies.length === 0 && <div className="text-dim text-sm" style={{ fontStyle: 'italic' }}>No trophies yet — the Tower's guardians still stand.</div>}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
        {data.trophies.map(t => (
          <div key={t.id} style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            padding: '0.4rem 0.6rem', borderRadius: 4,
            background: t.is_mounted ? 'rgba(201,168,76,0.12)' : 'rgba(255,255,255,0.03)',
            border: `1px solid ${t.is_mounted ? 'var(--gold)' : 'var(--border)'}`,
          }}>
            <div>
              <div style={{ fontSize: '0.9rem', color: 'var(--text-hi)' }}>{t.boss_name} <span className="text-dim" style={{ fontSize: '0.75rem' }}>· Floor {t.floor}</span></div>
              <div style={{ fontSize: '0.75rem', color: t.is_mounted ? 'var(--gold)' : 'var(--text-dim)' }}>{t.buff_label}</div>
            </div>
            <button className="btn" onClick={() => handleToggle(t)} style={{ fontSize: '0.75rem', padding: '0.2rem 0.5rem' }}>
              {t.is_mounted ? 'Unmount' : 'Mount'}
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Chronosphere: daily time-skip ────────────────────────────────────

export function ChronospherePanel({ onResourceChange }) {
  const [data, setData] = useState(null)
  const [busy, setBusy] = useState(false)
  const [msgEl, setMsg] = useMsg()

  const refresh = () => getChronosphere().then(setData).catch(() => {})
  useEffect(() => { refresh() }, [])

  async function handleActivate() {
    setBusy(true)
    try {
      const res = await activateChronosphere()
      setMsg(res.message)
      refresh()
      if (onResourceChange) onResourceChange()
    } catch (e) { setMsg(e.message, true) } finally { setBusy(false) }
  }

  if (!data) return null
  const hrs = Math.floor(data.cooldown_remaining / 3600)
  const mins = Math.floor((data.cooldown_remaining % 3600) / 60)
  return (
    <div style={panelStyle}>
      <div style={{ color: '#b09aff', fontFamily: 'Cinzel, serif', marginBottom: '0.4rem' }}>⏳ Temporal Chamber</div>
      <div className="text-dim text-sm" style={{ marginBottom: '0.5rem' }}>
        Once per day, shatter the hourglass: <span style={{ color: 'var(--text-hi)' }}>{data.skip_hours} hours</span> of passive base generation (gold, ingredients, aether, XP, fatigue recovery, brewing) happen instantly. Upgrading adds hours.
      </div>
      {msgEl}
      <button className="btn btn-gold" disabled={busy || !data.ready} onClick={handleActivate} style={{ fontSize: '0.85rem' }}>
        {data.ready ? `Skip ${data.skip_hours} Hours` : `The sands settle… ready in ${hrs}h ${mins}m`}
      </button>
    </div>
  )
}

// ── Transcendence Core: the endgame gold furnace ─────────────────────

export function TranscendencePanel({ gold, onResourceChange }) {
  const [data, setData] = useState(null)
  const [busy, setBusy] = useState(false)
  const [msgEl, setMsg] = useMsg()

  const refresh = () => getTranscendence().then(setData).catch(() => {})
  useEffect(() => { refresh() }, [])

  async function handleInfuse() {
    setBusy(true)
    try {
      const res = await infuseTranscendence()
      setMsg(res.message)
      refresh()
      if (onResourceChange) onResourceChange()
    } catch (e) { setMsg(e.message, true) } finally { setBusy(false) }
  }

  if (!data) return null
  const capped = data.infusions >= data.max_infusions
  return (
    <div style={panelStyle}>
      <div style={{ color: '#e0d3ff', fontFamily: 'Cinzel, serif', marginBottom: '0.4rem' }}>✦ The Core</div>
      <div className="text-dim text-sm" style={{ marginBottom: '0.5rem' }}>
        Feed the Core gold; it feeds your heroes power. Each infusion permanently grants <span style={{ color: 'var(--text-hi)' }}>+1% to ALL stats, roster-wide</span> — and each costs more than the last. The facility's level caps how many infusions it can channel.
      </div>
      <div style={{ display: 'flex', gap: '1.5rem', marginBottom: '0.5rem', fontSize: '0.9rem' }}>
        <span>Infusions: <span style={{ color: 'var(--gold)' }}>{data.infusions}</span> / {data.max_infusions}</span>
        <span>Current bonus: <span style={{ color: '#e0d3ff' }}>+{data.bonus_pct}% all stats</span></span>
      </div>
      {msgEl}
      <button className="btn btn-gold" disabled={busy || capped || (gold != null && gold < data.next_cost)} onClick={handleInfuse} style={{ fontSize: '0.85rem' }}>
        {capped ? `Upgrade the Core to channel infusion ${data.infusions + 1}` : `Infuse (${data.next_cost.toLocaleString()}g)`}
      </button>
    </div>
  )
}
