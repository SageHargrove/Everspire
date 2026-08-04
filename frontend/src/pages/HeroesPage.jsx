import React, { useState, useEffect } from 'react'
import { listHeroes, setTeam, removeHeroFromTeam, reorderTeam, dismissHero, dismissHeroesBulk, synthesizeHero, ascendHero, getAscensionInfo, promoteHero, getEvolutionInfo, regeneratePortraits, evolveHero, listEquipment, equipItem, unequipItem, autoEquipHero, unequipAllHero, egoAutoTeam, getEgoRecommendation, assignTeamLeader, getBonds, equipConsumable, getInventory, getBase, toggleFavorite } from '../api/client'
import { playTakeover } from '../audio'
import { emitToast } from '../toastBus'
import { CLASS_FAMILIES, FRONTLINE_FAMILIES } from '../components/HeroCard'
import HeroDetail from '../components/HeroDetail'
import ClassEvolutionModal from '../components/ClassEvolutionModal'
import { HeroCompareModal, TeamCompareModal } from '../components/CompareModal'
import { confirmDialog } from '../components/DialogHost'
import SynthesisChamber from '../components/SynthesisChamber'
import GiftModal from '../components/GiftModal'
import { HeartIcon } from '../components/ActionIcons'
import Sigil from '../components/Sigil'
import { classSigil } from '../classSigils'

// Small % rolls are real now (a D-tier ring's 1.4% crit matters at that
// level) — toFixed(0) rendered anything under 0.5% as a nonsense "+0%",
// so keep one decimal for sub-10% values.
function formatPct(v) {
  const pct = v * 100
  return `+${pct < 10 ? pct.toFixed(1).replace(/\.0$/, '') : pct.toFixed(0)}%`
}

function formatEquipmentStats(eq) {
  const parts = []
  if (eq.base_str > 0) parts.push(`STR +${eq.base_str}`)
  if (eq.base_int > 0) parts.push(`INT +${eq.base_int}`)
  if (eq.base_end > 0) parts.push(`END +${eq.base_end}`)
  if (eq.base_hlt > 0) parts.push(`Health +${eq.base_hlt}`)
  if (eq.base_agi > 0) parts.push(`AGI +${eq.base_agi}`)
  if (eq.base_wil > 0) parts.push(`WIL +${eq.base_wil}`)
  if (eq.base_luck > 0) parts.push(`Luck +${eq.base_luck}`)
  if (eq.str_pct > 0) parts.push(`STR ${formatPct(eq.str_pct)}`)
  if (eq.int_pct > 0) parts.push(`INT ${formatPct(eq.int_pct)}`)
  if (eq.hlt_pct > 0) parts.push(`Health ${formatPct(eq.hlt_pct)}`)
  if (eq.agi_pct > 0) parts.push(`AGI ${formatPct(eq.agi_pct)}`)
  if (eq.crit_chance > 0) parts.push(`Crit ${formatPct(eq.crit_chance)}`)
  if (eq.dodge_chance > 0) parts.push(`Dodge ${formatPct(eq.dodge_chance)}`)
  if (eq.armor_pen > 0) parts.push(`ArmorPen ${formatPct(eq.armor_pen)}`)
  if (eq.dmg_reduction_pct > 0) parts.push(`DR ${formatPct(eq.dmg_reduction_pct)}`)
  return parts.length ? parts.join(' ') : 'No bonus stats'
}

// ── Squad Overview spec vocabulary ─────────────────────────────────────────
const ROMAN = { 1: 'I', 2: 'II', 3: 'III', 4: 'IV', 5: 'V' }

// Teams carry NAMES (the mock's "TEAM · ECHO") — renameable, kept per
// browser until teams live server-side. Defaults are the design's cadence.
const DEFAULT_TEAM_NAMES = { 1: 'ECHO', 2: 'EMBER', 3: 'ONYX', 4: 'GALE', 5: 'VOW' }
function loadTeamNames() {
  try { return { ...DEFAULT_TEAM_NAMES, ...JSON.parse(localStorage.getItem('toe_team_names') || '{}') } }
  catch { return { ...DEFAULT_TEAM_NAMES } }
}
const RANK_LETTER = ['', 'E', 'D', 'C', 'B', 'A', 'S', 'SS']
// Star rarity accents from the mockup: 1 gray → 6 red; 7★ renders rainbow.
const STAR_ACCENT = { 1: '#9aa0ad', 2: '#8fbf9f', 3: '#1e90ff', 4: '#b84dff', 5: '#ffb300', 6: '#ff3333', 7: '#e0aaff' }

function familyOf(cls) {
  for (const [fam, d] of Object.entries(CLASS_FAMILIES)) if (d.members.includes(cls)) return fam
  return 'Classless'
}
function sigilNameOf(cls) {
  const fam = familyOf(cls)
  return fam === 'Magic Engineer' ? 'M_ENGINEER' : fam.toUpperCase().replace(/ /g, '_')
}

function StarSpan({ count, size = 10 }) {
  if (count >= 7) {
    return <span className="rainbow-text" style={{ fontSize: size, letterSpacing: '.12em' }}>★★★★★★★</span>
  }
  const accent = STAR_ACCENT[count] || '#9aa0ad'
  return (
    <span style={{ fontSize: size }}>
      <span style={{ color: accent, textShadow: `0 0 5px ${accent}99`, letterSpacing: '.12em' }}>{'★'.repeat(count)}</span>
      <span style={{ color: '#453c5c', letterSpacing: '.12em' }}>{'★'.repeat(Math.max(0, 7 - count))}</span>
    </span>
  )
}

// Rotated-diamond portrait (the mockup's roster monogram) that prefers the
// hero's own art: backend composite → raw portrait → accent monogram.
function DiamondArt({ hero, size = 38 }) {
  const [stage, setStage] = useState(0)
  const star = hero.current_star || hero.birth_star || 1
  const accent = STAR_ACCENT[Math.min(star, 7)] || '#9aa0ad'
  const hasArt = hero.portrait_path && !hero.portrait_path.includes('default_')
  return (
    <span style={{
      position: 'relative', width: size, height: size, transform: 'rotate(45deg)', flex: 'none',
      border: `1px solid ${accent}`, background: 'linear-gradient(135deg,#1c1030,#0c0718)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      // soft violet halo so faces read at a glance instead of spreadsheet lines
      boxShadow: '0 0 16px rgba(139,70,214,.4), 0 0 5px rgba(0,0,0,.5)', overflow: 'hidden',
    }}>
      {hasArt && stage < 2 ? (
        <img
          src={stage === 0 ? `/heroes/${hero.id}/card-image?mini=1` : `/${hero.portrait_path}`}
          alt={hero.name} draggable={false} onError={() => setStage(s => s + 1)}
          // top-anchored: the face sits at the top of the mini crop, and a
          // centered cover-crop was slicing off the top of some heads (Torsten)
          style={{ width: '142%', height: '142%', objectFit: 'cover', objectPosition: 'center', transform: 'rotate(-45deg)', flex: 'none' }}
        />
      ) : (
        <span style={{ transform: 'rotate(-45deg)', fontFamily: "'Cinzel',serif", fontWeight: 700, fontSize: Math.round(size * 0.34), color: accent }}>
          {(hero.name || '?')[0]}
        </span>
      )}
    </span>
  )
}

// Rectangular art for the party cards. Uses the RAW portrait only — NEVER the
// backend card-image, which is a fully composited card (frame + name + stars +
// class all baked in). Rendering that composite behind our own name plate/stars
// double-stamped everything and, at panel size, overflowed the screen (the
// "INCREDIBLY wrong" leader card). Raw portrait → class-icon fallback.
function PanelArt({ hero, style }) {
  const [failed, setFailed] = useState(false)
  const hasArt = hero.portrait_path && !hero.portrait_path.includes('default_')
  if (!hasArt || failed) {
    return (
      <div style={{ ...style, display: 'flex', alignItems: 'center', justifyContent: 'center', opacity: .3 }}>
        <Sigil set={classSigil(hero.hero_class).set} name={classSigil(hero.hero_class).name} size={52} color="var(--lavender)"
          fallback={<Sigil set="class-base" name="CLASSLESS" size={52} color="var(--lavender)" />} />
      </div>
    )
  }
  return (
    <img
      src={`/${hero.portrait_path}`}
      alt={hero.name} draggable={false} onError={() => setFailed(true)}
      style={{ objectFit: 'cover', ...style }}
    />
  )
}

// A hero's rough power score — used for the team summary strip (mock: "POWER
// 21,430"). Cheap sum of the seven plus a level weight; not combat-exact,
// just a single legible number that grows sensibly.
function heroPower(h) {
  const stats = (h.strength || 0) + (h.intelligence || 0) + (h.endurance || 0) + (h.agility || 0) + (h.willpower || 0) + (h.luck || 0)
  return Math.round((h.level || 1) * 40 + stats * 12 + (h.max_health || 0) * 1.5)
}

const chipStyle = (color, border) => ({
  cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 7,
  fontFamily: "'Cinzel',serif", fontSize: 9, letterSpacing: '.16em',
  color, border: `1px solid ${border}`, background: 'none', padding: '5px 12px',
})
const menuItemStyle = (active) => ({
  cursor: 'pointer', fontFamily: "'Cinzel',serif", letterSpacing: '.14em', fontSize: 9,
  padding: '8px 14px', color: active ? '#ffd88a' : '#c9bfa8',
  background: active ? 'rgba(184,151,98,.12)' : 'transparent',
  borderBottom: '1px solid rgba(184,151,98,.12)', whiteSpace: 'nowrap',
})

const FILTERS = [
  ['ALL', 'ALL HEROES'],
  ['DEPLOYED', 'DEPLOYED'],
  ['AVAILABLE', 'AVAILABLE'],
  ['R5', '5★ AND UP'],
  ['R4', '4★ AND UP'],
  ['MELEE', 'MELEE (STR)'],
  ['RANGED', 'RANGED / ARCANE'],
]
const SORTS = [['rarity', 'RARITY'], ['level', 'LEVEL'], ['name', 'A–Z']]

export default function HeroesPage({ onNavigate }) {
  const [heroes, setHeroes] = useState([])
  const [selected, setSelected] = useState(new Set())
  const [activeTab, setActiveTab] = useState('all') // 'all' | 'favorites' | 1 | 2 | ... | 5
  const isTeamTab = typeof activeTab === 'number'
  const [assignTargetTeam, setAssignTargetTeam] = useState(1)
  const [searchQuery, setSearchQuery] = useState('')

  const [teamNames, setTeamNames] = useState(loadTeamNames)
  function renameTeam(id) {
    const next = window.prompt('Name this team', teamNames[id] || '')
    if (next == null || !next.trim()) return
    const updated = { ...teamNames, [id]: next.trim().toUpperCase().slice(0, 14) }
    setTeamNames(updated)
    try { localStorage.setItem('toe_team_names', JSON.stringify(updated)) } catch {}
  }

  const [filterBy, setFilterBy] = useState('ALL')
  const [sortBy, setSortBy] = useState('rarity')
  // Roster pagination (no page scrolling — overflow becomes pages, paged
  // from the footer bar). Page size is MEASURED: however many 4-wide rows
  // the grid area actually fits, so big screens hold more heroes.
  const ROSTER_ROW_H = 112, ROSTER_GAP = 12
  const gridRef = React.useRef(null)
  const [gridH, setGridH] = useState(0)
  useEffect(() => {
    const el = gridRef.current
    if (!el) return
    const ro = new ResizeObserver(entries => setGridH(entries[0]?.contentRect?.height || 0))
    ro.observe(el)
    return () => ro.disconnect()
  }, [activeTab])
  const rosterRows = Math.max(2, Math.floor((gridH + ROSTER_GAP) / (ROSTER_ROW_H + ROSTER_GAP)) || 6)
  const pageSize = rosterRows * 4
  const [rosterPage, setRosterPage] = useState(0)
  useEffect(() => { setRosterPage(0) }, [filterBy, searchQuery, activeTab, sortBy])
  const [sortOpen, setSortOpen] = useState(false)
  const [filterOpen, setFilterOpen] = useState(false)
  const [assignOpen, setAssignOpen] = useState(false)

  const [expandedId, setExpandedId] = useState(null)
  // Team-view spotlight: which hero the right panel renders full-body.
  // null = the team leader (the default).
  const [spotlightId, setSpotlightId] = useState(null)
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState(null)
  const [egoPreview, setEgoPreview] = useState(null)
  const [eqModal, setEqModal] = useState(null)
  const [allEq, setAllEq] = useState([])
  const [evoModal, setEvoModal] = useState(null)
  // FORCE-EVO-PICK (support revamp leftover): the backend already holds a
  // hero's level at 30/60 until a path is chosen — this surfaces it. Any
  // gated hero auto-opens the evolution modal on page load; closing without
  // choosing snoozes that hero for this visit only (the gate itself never
  // releases until they pick).
  const evoSnoozedRef = React.useRef(new Set())
  useEffect(() => {
    if (evoModal) return
    const gated = heroes.find(h =>
      h.evolution_options?.length > 0 &&
      (h.level === 30 || h.level === 60) &&
      !evoSnoozedRef.current.has(h.id))
    if (gated) setEvoModal({ hero: gated, forced: true })
  }, [heroes, evoModal])
  const [consModal, setConsModal] = useState(null)
  const [consOptions, setConsOptions] = useState([])

  const [synthChamberOpen, setSynthChamberOpen] = useState(false)
  const [giftHero, setGiftHero] = useState(null)

  // Ascension & Promotion state
  const [ascending, setAscending] = useState(false)
  const [promoting, setPromoting] = useState(false)
  const [evolving, setEvolving] = useState(false)

  // Comparison — reuses the `selected` checkbox set for Hero vs Hero;
  // Team vs Team is a standalone picker since it compares whole rosters.
  const [compareHeroesOpen, setCompareHeroesOpen] = useState(false)
  const [compareTeamsOpen, setCompareTeamsOpen] = useState(false)
  const [compareTeamsResultOpen, setCompareTeamsResultOpen] = useState(false)
  const [compareTeamA, setCompareTeamA] = useState(1)
  const [compareTeamB, setCompareTeamB] = useState(2)

  useEffect(() => { load() }, [])

  async function load() {
    const data = await listHeroes(true)
    try {
      // Attach each hero's own bonds so the bond-driven combat stat boost
      // (1% per total bond level shared with current teammates, see
      // bonds_service.py) can show real data in the detail view.
      const allBonds = await getBonds()
      data.forEach(h => {
        h.bonds = allBonds.filter(b => b.hero_a_id === h.id || b.hero_b_id === h.id)
      })
    } catch (e) {}
    setHeroes(data)
    try {
      const eqData = await listEquipment()
      setAllEq(eqData.unequipped || [])
    } catch(e) {}
    try {
      const [inv, base] = await Promise.all([getInventory(), getBase()])
      const opts = inv.filter(i => i.item_type === 'potion' || i.item_type === 'scroll')
        .map(i => ({ item_name: i.item_name, item_type: i.item_type, quantity: i.quantity }))
      const materials = base.materials ? JSON.parse(base.materials) : {}
      if (materials.Bandage > 0) opts.unshift({ item_name: 'Bandage', item_type: 'bandage', quantity: materials.Bandage })
      setConsOptions(opts)
    } catch (e) {}
  }

  function toggleSelect(id) {
    setSelected(prev => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      return next
    })
    setMsg(null)
  }

  async function saveTeamFromAll(team = assignTargetTeam) {
    setSaving(true)
    try {
      const currentTeam = heroes.filter(h => h.is_on_team === team).map(h => h.id)
      const toAdd = Array.from(selected).filter(id => !currentTeam.includes(id))
      const nextTeam = [...currentTeam, ...toAdd]

      if (nextTeam.length > 5) {
        setMsg(`Cannot assign. Team ${team} would exceed 5 heroes (currently ${currentTeam.length}, adding ${toAdd.length}).`)
        setSaving(false)
        return
      }

      await setTeam(team, nextTeam)
      setMsg(`Added ${toAdd.length} heroes to Team ${team}.`)
      setSelected(new Set())
      await load()
    } catch (e) {
      setMsg(e.message)
    } finally {
      setSaving(false)
    }
  }

  async function removeFromTeam() {
    setSaving(true)
    try {
      const currentTeam = heroes.filter(h => h.is_on_team === activeTab).map(h => h.id)
      const nextTeam = currentTeam.filter(id => !selected.has(id))

      await setTeam(activeTab, nextTeam)
      setMsg(`Removed ${selected.size} heroes from Team ${activeTab}.`)
      setSelected(new Set())
      await load()
    } catch (e) {
      setMsg(e.message)
    } finally {
      setSaving(false)
    }
  }

  // Selected heroes here can be on any (or no) team — unlike removeFromTeam
  // above, which only makes sense within a single team's tab.
  async function removeFromTeamFromAll() {
    setSaving(true)
    try {
      const ids = [...selected]
      await Promise.all(ids.map(id => removeHeroFromTeam(id)))
      setMsg(`Removed ${ids.length} heroes from their teams.`)
      setSelected(new Set())
      await load()
    } catch (e) {
      setMsg(e.message)
    } finally {
      setSaving(false)
    }
  }

  // --- Dismiss Selected ---
  async function handleDismissSelected() {
    if (selected.size === 0) return

    const selectedHeroes = heroes.filter(h => selected.has(h.id))
    const highestStar = Math.max(...selectedHeroes.map(h => h.current_star || h.birth_star))

    if (highestStar >= 6) {
      if (!(await confirmDialog(`CRITICAL WARNING: You have selected a ${highestStar}★ hero for dismissal! This action is PERMANENT. Are you absolutely sure?`))) return
    } else if (highestStar >= 4) {
      if (!(await confirmDialog(`Warning: You have selected a high rank (${highestStar}★) hero for dismissal. Are you sure?`))) return
    } else {
      if (!(await confirmDialog(`Dismiss ${selected.size} selected heroes permanently?`))) return
    }

    setSaving(true)
    try {
      const res = await dismissHeroesBulk(selectedHeroes.map(h => h.id))
      setMsg(`Dismissed ${res.deleted_count} heroes.`)
      setSelected(new Set())
      await load()
    } catch (e) {
      setMsg(`Bulk dismiss failed: ${e.message}`)
      console.error(e)
    } finally {
      setSaving(false)
    }
  }

  // --- Dismiss Filtered ---
  async function handleDismissFiltered() {
    if (displayHeroes.length === 0) return

    const highestStar = Math.max(...displayHeroes.map(h => h.current_star || h.birth_star))

    if (highestStar >= 6) {
      if (!(await confirmDialog(`CRITICAL WARNING: The current filter includes a ${highestStar}★ hero! This action will dismiss ALL ${displayHeroes.length} heroes displayed. This is PERMANENT. Are you absolutely sure?`))) return
    } else if (highestStar >= 4) {
      if (!(await confirmDialog(`Warning: The current filter includes a high rank (${highestStar}★) hero. Are you sure you want to dismiss ALL ${displayHeroes.length} displayed heroes?`))) return
    } else {
      if (!(await confirmDialog(`Dismiss ALL ${displayHeroes.length} currently displayed heroes permanently?`))) return
    }

    setSaving(true)
    try {
      const res = await dismissHeroesBulk(displayHeroes.map(h => h.id))
      setMsg(`Dismissed ${res.deleted_count} heroes.`)
      setSelected(new Set())
      await load()
    } catch (e) {
      setMsg(`Bulk dismiss failed: ${e.message}`)
      console.error(e)
    } finally {
      setSaving(false)
    }
  }

  // --- Ascension ---
  async function handleAscend(heroId, e) {
    e.stopPropagation()
    try {
      const info = await getAscensionInfo(heroId)
      const costStr = Object.entries(info.materials_required || {}).map(([m, q]) => `${q} ${m}`).join(', ')
      const pct = Math.round((info.fail_chance || 0) * 100)
      if (!(await confirmDialog(`Ascend this hero? Costs ${costStr}.\nThis ritual has a ${pct}% chance to fail — materials are consumed either way.`))) return
    } catch (e) {
      // If the info lookup fails, fall through to attempting the ascend anyway — the
      // endpoint itself validates materials/level and will surface a clear error.
    }
    setAscending(true)
    try {
      const result = await ascendHero(heroId)
      if (result.failed) {
        setMsg(`Ascension failed! ${result.message || ''}`)
      } else {
        playTakeover('ascension')  // the game's peak — full ceremony seizes the audio
        setMsg(`Ascension successful! ${result.message || ''}`)
      }
      await load()
    } catch (e) {
      setMsg(e.message)
    } finally {
      setAscending(false)
    }
  }

  // --- Promotion (Evolution) ---
  async function handlePromote(heroId, e) {
    e.stopPropagation()
    try {
      const info = await getEvolutionInfo(heroId)
      const costStr = Object.entries(info.materials_required || {}).map(([m, q]) => `${q} ${m}`).join(', ')
      if (!(await confirmDialog(`Evolve this hero to ${info.current_star + 1}★? Costs ${info.gold_cost} gold + ${costStr}.`))) return
    } catch (e) {
      // If the info lookup fails, fall through to attempting the promote anyway — the
      // endpoint itself validates floor gate/materials/level and will surface a clear error.
    }
    setPromoting(true)
    try {
      const result = await promoteHero(heroId)
      setMsg(result.message || 'Evolution successful!')
      // A star rose — a new Chronicle passage unseals (see HeroDetail).
      const promoted = heroes.find(x => x.id === heroId)
      if (promoted) emitToast(`A memory returns to ${promoted.name} — a new Chronicle passage is revealed.`, 'success')
      await load()
    } catch (e) {
      setMsg(e.message)
    } finally {
      setPromoting(false)
    }
  }

  async function handleAssignLeader(heroId, e) {
    if (e) e.stopPropagation()
    try {
      const result = await assignTeamLeader(heroId)
      setMsg(result.message || '')
      await load()
    } catch (e) {
      setMsg(e.message)
    }
  }

  // --- Drag and Drop (team tabs reorder frontline/backline) ---
  const [draggedHeroId, setDraggedHeroId] = useState(null)
  const [dragOverHeroId, setDragOverHeroId] = useState(null)
  const [dragOverLeader, setDragOverLeader] = useState(false)

  function handleDragStart(e, heroId) {
    if (!isTeamTab) return;
    setDraggedHeroId(heroId);
  }

  function handleDragOver(e, heroId) {
    e.preventDefault();
    if (!isTeamTab || heroId === draggedHeroId) return;
    setDragOverHeroId(heroId);
  }

  async function handleDrop(e, targetHeroId) {
    e.preventDefault();
    if (!isTeamTab) return;
    if (draggedHeroId && draggedHeroId !== targetHeroId) {
      const currentTeam = [...displayHeroes];
      const draggedIdx = currentTeam.findIndex(h => h.id === draggedHeroId);
      const targetIdx = currentTeam.findIndex(h => h.id === targetHeroId);
      const [dragged] = currentTeam.splice(draggedIdx, 1);
      currentTeam.splice(targetIdx, 0, dragged);
      const newIds = currentTeam.map(h => h.id);

      try {
        await reorderTeam(activeTab, newIds);
        await load();
      } catch (e) {
        setMsg(e.message)
      }
    }
    setDraggedHeroId(null);
    setDragOverHeroId(null);
  }

  const STAR_CAPS = { 1: 10, 2: 20, 3: 40, 4: 60, 5: 80, 6: 99, 7: 120 }

  const baseHeroes = heroes.filter(h => h.is_alive)

  // Filter by Tab
  let displayHeroes = baseHeroes
  if (isTeamTab) {
    displayHeroes = displayHeroes.filter(h => h.is_on_team === activeTab)
  } else if (activeTab === 'favorites') {
    displayHeroes = displayHeroes.filter(h => h.is_favorite)
  }

  // Spec filter menu: DEPLOYED / AVAILABLE / rarity floors / MELEE / RANGED
  if (!isTeamTab) {
    if (filterBy === 'DEPLOYED') displayHeroes = displayHeroes.filter(h => h.is_on_team > 0)
    else if (filterBy === 'AVAILABLE') displayHeroes = displayHeroes.filter(h => !h.is_on_team)
    else if (filterBy === 'R5') displayHeroes = displayHeroes.filter(h => (h.current_star || h.birth_star) >= 5)
    else if (filterBy === 'R4') displayHeroes = displayHeroes.filter(h => (h.current_star || h.birth_star) >= 4)
    else if (filterBy === 'MELEE') displayHeroes = displayHeroes.filter(h => FRONTLINE_FAMILIES.includes(familyOf(h.hero_class)))
    else if (filterBy === 'RANGED') displayHeroes = displayHeroes.filter(h => !FRONTLINE_FAMILIES.includes(familyOf(h.hero_class)))
  }

  if (searchQuery.trim()) {
    const q = searchQuery.toLowerCase()
    displayHeroes = displayHeroes.filter(h =>
      h.name.toLowerCase().includes(q) ||
      h.hero_class.toLowerCase().includes(q) ||
      (h.synergy_group && h.synergy_group.toLowerCase().includes(q))
    )
  }

  // Sort
  if (isTeamTab) {
    displayHeroes.sort((a, b) => (a.team_position || 0) - (b.team_position || 0))
  } else {
    displayHeroes.sort((a, b) => {
      if (sortBy === 'rarity') return ((b.current_star || b.birth_star) - (a.current_star || a.birth_star)) || (b.level - a.level)
      if (sortBy === 'level') return b.level - a.level
      if (sortBy === 'name') return a.name.localeCompare(b.name)
      return 0
    })
  }

  // Slice the roster into measured pages so the grid always fits the screen.
  const totalRosterPages = Math.max(1, Math.ceil(displayHeroes.length / pageSize))
  const safeRosterPage = Math.min(rosterPage, totalRosterPages - 1)
  const pagedHeroes = displayHeroes.slice(safeRosterPage * pageSize, (safeRosterPage + 1) * pageSize)

  async function handleToggleFavorite(heroId, e) {
    e.stopPropagation()
    // Optimistic flip — the roster reload would make the heart feel laggy.
    setHeroes(hs => hs.map(h => h.id === heroId ? { ...h, is_favorite: h.is_favorite ? 0 : 1 } : h))
    try { await toggleFavorite(heroId) } catch { load() }
  }

  // ── Compact roster row-card (the mockup's 4-column list tile) ────────────
  function renderRosterRow(hero) {
    const star = hero.current_star || hero.birth_star || 1
    const accent = STAR_ACCENT[Math.min(star, 7)] || '#9aa0ad'
    const sel = selected.has(hero.id)
    const deployed = hero.is_on_team > 0

    return (
      <div key={hero.id}
        onClick={() => setExpandedId(hero.id)}
        className={dragOverHeroId === hero.id ? 'dragover' : ''}
        style={{
          cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 16, padding: '16px 18px',
          border: sel ? '1px solid #c8a9f5' : (deployed ? '1px solid rgba(216,187,132,.5)' : '1px solid rgba(184,151,98,.25)'),
          background: sel ? 'linear-gradient(90deg,rgba(124,58,214,.2),rgba(12,7,24,.5))' : (deployed ? 'linear-gradient(90deg,rgba(184,151,98,.1),rgba(12,7,24,.5))' : 'rgba(12,7,24,.45)'),
          boxShadow: sel ? '0 0 14px rgba(124,58,214,.3)' : 'none',
          opacity: hero.condition === 'Retired' ? .6 : 1,
        }}>
        <DiamondArt hero={hero} size={76} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
            <span style={{ fontFamily: "'Cinzel',serif", fontWeight: 700, fontSize: 16, letterSpacing: '.06em', color: 'var(--text-hi)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{hero.name}</span>
            <span style={{ flex: 1 }} />
            <span style={{ fontFamily: "'Cinzel',serif", fontSize: 10, letterSpacing: '.1em', color: '#c9bfa8' }}>LV {hero.level}</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 6 }}>
            <span style={{ width: 22, height: 22, transform: 'rotate(45deg)', flex: 'none', border: `1px solid ${accent}66`, background: 'linear-gradient(135deg,#1c1030,#0e0918)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Sigil set="class-base" name={sigilNameOf(hero.hero_class)} size={14} color={accent} style={{ transform: 'rotate(-45deg)' }}
                fallback={<span style={{ transform: 'rotate(-45deg)', fontSize: 8, color: accent }}>{(hero.hero_class || '?').slice(0, 2).toUpperCase()}</span>} />
            </span>
            <span style={{ fontFamily: "'Cinzel',serif", letterSpacing: '.2em', fontSize: 9.5, color: 'var(--muted)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{(hero.hero_class || '').toUpperCase()}</span>
            {!!hero.is_team_leader && <span title="Team Leader" style={{ fontSize: 10, color: '#ffd88a' }}>♛</span>}
          </div>
          <div style={{ marginTop: 6 }}><StarSpan count={star} size={11} /></div>
        </div>
        <button
          title={hero.is_favorite ? 'Remove from Favorites' : 'Add to Favorites'}
          onClick={(e) => handleToggleFavorite(hero.id, e)}
          style={{ width: 20, height: 20, flex: 'none', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'none', border: 'none', cursor: 'pointer', color: hero.is_favorite ? '#e0708a' : 'rgba(154,134,184,.35)' }}>
          <HeartIcon size={14} filled={!!hero.is_favorite} />
        </button>
        <button
          title={sel ? 'Deselect' : 'Select'}
          onClick={(e) => { e.stopPropagation(); toggleSelect(hero.id) }}
          style={{
            width: 22, height: 22, flex: 'none', display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 11, cursor: 'pointer', color: sel ? '#0a0710' : '#8fbf9f',
            background: sel ? '#c8a9f5' : 'transparent',
            border: sel ? '1px solid #c8a9f5' : '1px solid rgba(154,134,184,.25)',
            borderRadius: sel ? 2 : '50%',
          }}>
          {sel ? '✓' : (deployed ? '●' : '')}
        </button>
      </div>
    )
  }

  // ── ALL HEROES / FAVORITES view ───────────────────────────────────────────
  function renderAllView() {
    const filterLabel = (FILTERS.find(f => f[0] === filterBy) || FILTERS[0])[1]
    const sortLabel = (SORTS.find(x => x[0] === sortBy) || SORTS[0])[1]
    const one = selected.size === 1 ? [...selected][0] : null
    return (
      <>
        {/* header — the new Squad mock: ROSTER over ghost LEGION, souls sworn.
            position/zIndex here keeps its dropdowns above the roster grid: the
            ent-* entrance animations end on transform:translateY(0), so every
            ent-* block is its own stacking context — without this the later
            grid (.ent-2) painted over this header's menus. */}
        <div className="ent-1" style={{ position: 'relative', zIndex: 20, marginBottom: 12 }}>
          {/* ROW 1 — identity + the always-present sort/filter/search. Nothing
              here appears or disappears, so this row never moves. */}
          <div style={{ display: 'flex', alignItems: 'flex-end', gap: 18, flexWrap: 'wrap' }}>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 2 }}>
                <span style={{ width: 9, height: 9, transform: 'rotate(45deg)', background: 'var(--gold)', display: 'inline-block' }} />
                <span style={{ fontFamily: "'Cinzel',serif", fontWeight: 600, letterSpacing: '.5em', fontSize: 13, color: 'var(--gold)' }}>SQUAD OVERVIEW</span>
                <span style={{ fontFamily: "'Cinzel',serif", letterSpacing: '.22em', fontSize: 11, color: 'var(--muted)' }}>
                  {baseHeroes.length} SOULS SWORN
                </span>
              </div>
              <div className="ilm-title-stack">
                <div className="ghost">{activeTab === 'favorites' ? 'BELOVED' : 'LEGION'}</div>
                <div className="solid">{activeTab === 'favorites' ? 'FAVORITES' : 'ROSTER'}</div>
              </div>
            </div>
            <span style={{ flex: 1 }} />
            <div style={{ position: 'relative' }}>
              <button onClick={() => { setSortOpen(o => !o); setFilterOpen(false); setAssignOpen(false) }} style={chipStyle('#c9bfa8', 'rgba(184,151,98,.35)')}>
                SORT · {sortLabel} <span style={{ fontSize: 8, color: 'var(--muted)' }}>▾</span>
              </button>
              {sortOpen && (
                <div style={{ position: 'absolute', right: 0, top: 28, zIndex: 9, border: '1px solid rgba(184,151,98,.45)', background: '#140b22', boxShadow: '0 12px 30px rgba(0,0,0,.6)', minWidth: 130 }}>
                  {SORTS.map(([k, label]) => (
                    <div key={k} style={menuItemStyle(k === sortBy)} onClick={() => { setSortBy(k); setSortOpen(false) }}>{label}</div>
                  ))}
                </div>
              )}
            </div>
            <div style={{ position: 'relative' }}>
              <button onClick={() => { setFilterOpen(o => !o); setSortOpen(false); setAssignOpen(false) }} style={chipStyle('#c9bfa8', 'rgba(184,151,98,.35)')}>
                FILTER · {filterLabel} <span style={{ fontSize: 8, color: 'var(--muted)' }}>▾</span>
              </button>
              {filterOpen && (
                <div style={{ position: 'absolute', right: 0, top: 28, zIndex: 9, border: '1px solid rgba(184,151,98,.45)', background: '#140b22', boxShadow: '0 12px 30px rgba(0,0,0,.6)', minWidth: 150 }}>
                  {FILTERS.map(([k, label]) => (
                    <div key={k} style={menuItemStyle(k === filterBy)} onClick={() => { setFilterBy(k); setFilterOpen(false) }}>{label}</div>
                  ))}
                  <div style={{ ...menuItemStyle(false), color: '#e08585', borderBottom: 'none' }}
                    onClick={() => { setFilterOpen(false); handleDismissFiltered() }}>
                    ✕ DISMISS ALL SHOWN ({displayHeroes.length})
                  </div>
                </div>
              )}
            </div>
            <input
              type="text"
              placeholder="Search…"
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              style={{ width: 130, fontFamily: "'Cormorant Garamond',serif", fontStyle: 'italic', fontSize: 14, color: 'var(--text-hi)', background: 'rgba(12,7,24,.5)', border: '1px solid rgba(184,151,98,.35)', padding: '4px 10px', outline: 'none' }}
            />
          </div>

          {/* ROW 2 — action bar. A fixed min-height reserves the space whether
              or not any heroes are selected, so the contextual tools (compare,
              assign, remove…) fade in on the RIGHT without ever reflowing the
              roster grid below. Synthesis anchors the left as the primary act. */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, minHeight: 40, marginTop: 12, flexWrap: 'nowrap' }}>
            <button onClick={() => setSynthChamberOpen(true)} title="Fuse two heroes into a stronger one"
              style={{
                cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 9, flex: 'none',
                fontFamily: "'Cinzel',serif", fontWeight: 700, fontSize: 11, letterSpacing: '.2em',
                color: '#f2dede', background: 'linear-gradient(120deg, rgba(192,64,64,.30), rgba(120,40,40,.14))',
                border: '1px solid rgba(224,133,133,.55)', padding: '10px 22px',
                clipPath: 'polygon(8px 0,100% 0,calc(100% - 8px) 100%,0 100%)',
              }}>
              ⚗ SYNTHESIS <span style={{ opacity: .55, fontSize: 13 }}>›</span>
            </button>
            <span style={{ flex: 1 }} />

            {selected.size > 0 && (
              <>
                <span style={{ fontFamily: "'Cinzel',serif", fontSize: 9, letterSpacing: '.14em', color: '#8fbf9f' }}>{selected.size} SELECTED</span>
                {selected.size === 2 && (
                  <button onClick={() => setCompareHeroesOpen(true)} style={chipStyle('#c9bfa8', 'rgba(184,151,98,.35)')}>⇄ COMPARE</button>
                )}
                {one && heroes.find(h => h.id === one)?.is_on_team > 0 && (
                  <button onClick={(e) => handleAssignLeader(one, e)}
                    style={{ ...chipStyle('#ffd88a', 'rgba(255,216,138,.5)'), fontWeight: 600, letterSpacing: '.14em' }}>
                    ★ SET LEADER
                  </button>
                )}
                <div style={{ position: 'relative' }}>
                  <button onClick={() => { setAssignOpen(o => !o); setSortOpen(false); setFilterOpen(false) }} disabled={saving}
                    style={{ cursor: 'pointer', fontFamily: "'Cinzel',serif", fontWeight: 700, fontSize: 9, letterSpacing: '.14em', color: '#0a0710', background: 'linear-gradient(120deg,#c8a9f5,#8b46d6)', border: 'none', padding: '6px 14px', clipPath: 'polygon(6px 0,100% 0,calc(100% - 6px) 100%,0 100%)' }}>
                    {saving ? 'ASSIGNING…' : `ASSIGN TO TEAM ${ROMAN[assignTargetTeam]} ▾`}
                  </button>
                  {assignOpen && (
                    <div style={{ position: 'absolute', right: 0, top: 28, zIndex: 9, border: '1px solid rgba(184,151,98,.45)', background: '#140b22', boxShadow: '0 12px 30px rgba(0,0,0,.6)', minWidth: 130 }}>
                      {[1, 2, 3, 4, 5].map(t => (
                        <div key={t} style={menuItemStyle(t === assignTargetTeam)}
                          onClick={() => { setAssignOpen(false); setAssignTargetTeam(t); saveTeamFromAll(t) }}>
                          TEAM {ROMAN[t]}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
                <button onClick={removeFromTeamFromAll} disabled={saving} style={chipStyle('#e08585', 'rgba(192,64,64,.4)')}>REMOVE</button>
                <button onClick={handleDismissSelected} disabled={saving} style={chipStyle('#e08585', 'rgba(192,64,64,.4)')}>✕ DISMISS</button>
              </>
            )}
          </div>

          {/* status line — reserved height so a message never nudges the grid. */}
          <div style={{ minHeight: 20, marginTop: 6, fontStyle: 'italic', fontSize: 14, color: /saved|complete|Added|Removed|successful|Dismissed|cleared|leader/i.test(msg || '') ? '#8fbf9f' : '#e08585' }}>
            {msg}
          </div>
        </div>

        {/* roster grid — the spec's 4-column compact rows. Paged, never
            scrolled: overflow past PAGE_SIZE becomes numbered pages below. */}
        <div ref={gridRef} className="ent-2 ilm-page-weave" style={{ flex: 1, minHeight: 0, overflow: 'hidden', display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: '9px 12px', alignContent: 'start' }}>
          {displayHeroes.length === 0 && (
            <div className="empty-state" style={{ gridColumn: '1 / -1' }}>
              <div className="empty-state-icon">{activeTab === 'favorites' ? '♡' : <Sigil set="ui" name="sparkle" size={46} color="var(--gold-dim)" fallback={<span style={{ color: 'var(--gold-dim)' }}>✦</span>} />}</div>
              <div className="empty-state-title">
                {activeTab === 'favorites' ? 'No Favorites Yet' : heroes.length === 0 ? 'No Heroes Yet' : 'No Heroes Match These Filters'}
              </div>
              <div className="empty-state-hint">
                {activeTab === 'favorites'
                  ? "Click the ♡ on any hero's row to pin them here."
                  : heroes.length === 0
                    ? 'Visit the Summoning Gate to call your first heroes into the Tower.'
                    : 'Try clearing the search or the filter.'}
              </div>
            </div>
          )}
          {pagedHeroes.map(hero => renderRosterRow(hero))}
        </div>
      </>
    )
  }

  // ── Formation face tile (team view) — FACES ONLY here (Liam: full body
  // lives solely in Hero Detail and the spotlight panel). Click = spotlight
  // the hero on the right; ♛ pip = crown; drag = reorder positions. ─────────
  function renderFaceTile(hero, isSpotlit) {
    const star = hero.current_star || hero.birth_star || 1
    const accent = STAR_ACCENT[Math.min(star, 7)] || '#9aa0ad'
    const hasArt = hero.portrait_path && !hero.portrait_path.includes('default_')
    return (
      <div key={hero.id}
        draggable
        onDragStart={(e) => handleDragStart(e, hero.id)}
        onDragOver={(e) => handleDragOver(e, hero.id)}
        onDrop={(e) => handleDrop(e, hero.id)}
        onDragEnd={() => { setDraggedHeroId(null); setDragOverHeroId(null) }}
        onClick={() => setSpotlightId(hero.id)}
        title={`${hero.name} — click to inspect, drag to reposition`}
        style={{
          position: 'relative', display: 'flex', alignItems: 'center', gap: 15, width: 248, flex: 'none', cursor: 'grab', padding: '13px 14px',
          border: `1px solid ${isSpotlit ? 'var(--gold-hi)' : `${accent}55`}`,
          background: isSpotlit ? 'linear-gradient(120deg,rgba(184,151,98,.14),rgba(12,7,24,.6))' : 'rgba(12,7,24,.5)',
          boxShadow: isSpotlit ? '0 0 14px rgba(184,151,98,.3)' : 'none',
          transform: dragOverHeroId === hero.id ? 'scale(1.04)' : 'none',
          filter: draggedHeroId === hero.id ? 'brightness(1.2)' : 'none',
        }}>
        {/* diamond portrait — same size + centered crop as the roster's DiamondArt */}
        <span style={{ position: 'relative', width: 74, height: 74, transform: 'rotate(45deg)', flex: 'none', border: `1px solid ${accent}`, background: 'linear-gradient(135deg,#1a0f2e,#0c0718)', overflow: 'hidden', boxShadow: '0 0 16px rgba(139,70,214,.4), 0 0 5px rgba(0,0,0,.5)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          {hasArt ? (
            <img src={`/heroes/${hero.id}/card-image?mini=1`} alt={hero.name} draggable={false}
              onError={(e) => { if (!e.currentTarget.dataset.fb) { e.currentTarget.dataset.fb = '1'; e.currentTarget.src = `/${hero.portrait_path}` } }}
              style={{ width: '142%', height: '142%', objectFit: 'cover', objectPosition: 'center', transform: 'rotate(-45deg)', flex: 'none', pointerEvents: 'none' }} />
          ) : (
            <span style={{ transform: 'rotate(-45deg)', display: 'flex', alignItems: 'center', justifyContent: 'center', width: '100%', height: '100%', opacity: .5 }}>
              <Sigil set="class-base" name={sigilNameOf(hero.hero_class)} size={30} color="var(--lavender)"
                fallback={<span style={{ color: 'var(--lavender)', fontFamily: "'Cinzel',serif", fontSize: 22 }}>{hero.name?.[0]}</span>} />
            </span>
          )}
        </span>
        {/* text column */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
            <span style={{ fontFamily: "'Cinzel',serif", fontWeight: 700, fontSize: 14, letterSpacing: '.06em', color: 'var(--text-hi)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{hero.name?.toUpperCase()}</span>
            <span style={{ flex: 1 }} />
            <span style={{ fontFamily: "'Cinzel',serif", fontSize: 10, letterSpacing: '.1em', color: '#c9bfa8', flex: 'none' }}>LV {hero.level}</span>
          </div>
          <div style={{ marginTop: 6 }}><StarSpan count={star} size={11} /></div>
          <div style={{ fontFamily: "'Cinzel',serif", letterSpacing: '.18em', fontSize: 9, color: 'var(--muted)', marginTop: 6, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{(hero.hero_class || '').toUpperCase()}</div>
        </div>
        {/* crown pip — bottom-right corner so it never overlaps the LV text */}
        <button
          title={hero.is_team_leader ? 'Team Leader' : `Make ${hero.name} the leader`}
          onClick={(e) => { e.stopPropagation(); if (!hero.is_team_leader) handleAssignLeader(hero.id, e) }}
          style={{ position: 'absolute', bottom: 4, right: 4, width: 20, height: 20, padding: 0, display: 'flex', alignItems: 'center', justifyContent: 'center',
            background: hero.is_team_leader ? 'linear-gradient(135deg,#241a10,#120d08)' : 'rgba(10,7,16,.6)',
            border: `1px solid ${hero.is_team_leader ? 'var(--gold-hi)' : 'rgba(184,151,98,.3)'}`,
            cursor: hero.is_team_leader ? 'default' : 'pointer' }}>
          <span style={{ fontSize: 11, color: hero.is_team_leader ? '#ffd88a' : 'rgba(201,191,168,.45)', textShadow: hero.is_team_leader ? '0 0 6px rgba(255,216,138,.7)' : 'none' }}>♛</span>
        </button>
      </div>
    )
  }

  // ── Leader panel (team view) — the VESPER-style spotlight (mock parity):
  // a stats column | vertical divider | full-body render. Name wraps (never
  // truncates), the tendency is a short chip (not the long personality blurb).
  function renderLeaderPanel(leader) {
    const star = leader.current_star || leader.birth_star || 1
    const hpPct = leader.max_health ? Math.max(0, Math.min(100, (leader.health / leader.max_health) * 100)) : 100
    const manaPct = leader.max_mana ? Math.max(0, Math.min(100, ((leader.mana ?? leader.max_mana) / leader.max_mana) * 100)) : 0
    const fmt = n => (n ?? 0).toLocaleString()
    const condition = (leader.condition || 'Steady').toUpperCase()
    const condBad = /INJUR|CRITICAL|BROKEN|SICK/.test(condition)
    const hasArt = leader.portrait_path && !leader.portrait_path.includes('default_')
    const name = (leader.name || '').toUpperCase()
    // Size the name to fit without truncating (it used to clip to "ORION SH…").
    const nameSize = name.length > 15 ? 30 : name.length > 11 ? 36 : 44
    const tendency = leader.battle_tendency || (Array.isArray(leader.traits) ? leader.traits[0]?.name : null)
    // No box — the leader floats on the page ink like the mock; only the
    // vertical divider separates the stats from the render. It's ALSO a drop
    // target: drag any party card onto it to crown that hero the leader.
    return (
      <div className="ent-3"
        onDragOver={(e) => { if (draggedHeroId) { e.preventDefault(); setDragOverLeader(true) } }}
        onDragLeave={() => setDragOverLeader(false)}
        onDrop={(e) => { e.preventDefault(); setDragOverLeader(false); const id = draggedHeroId; setDraggedHeroId(null); setDragOverHeroId(null); if (id && id !== leader.id) handleAssignLeader(id) }}
        style={{ position: 'relative', display: 'flex', flex: '1 1 620px', minWidth: 540, minHeight: 440, overflow: 'hidden',
          outline: dragOverLeader ? '2px dashed var(--gold-hi)' : 'none', outlineOffset: -4,
          background: dragOverLeader ? 'radial-gradient(60% 60% at 50% 40%, rgba(184,151,98,.12), transparent 70%)' : 'none',
          transition: 'outline-color .12s' }}>
        {/* drag-to-crown hint */}
        {dragOverLeader && (
          <div style={{ position: 'absolute', inset: 0, zIndex: 5, display: 'flex', alignItems: 'center', justifyContent: 'center', pointerEvents: 'none' }}>
            <span style={{ fontFamily: "'Cinzel',serif", fontWeight: 700, letterSpacing: '.24em', fontSize: 15, color: '#ffd88a', background: 'rgba(10,7,16,.85)', border: '1px solid var(--gold-hi)', padding: '10px 20px', clipPath: 'polygon(10px 0,100% 0,calc(100% - 10px) 100%,0 100%)' }}>♛ CROWN AS LEADER</span>
          </div>
        )}
        {/* ── stats column ── */}
        <div style={{ flex: '1.15 1 320px', minWidth: 300, padding: '24px 24px 22px', display: 'flex', flexDirection: 'column' }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
            <span style={{ fontFamily: "'Cinzel',serif", fontSize: 11, letterSpacing: '.32em', color: 'var(--gold)' }}>LV {leader.level}</span>
            <span style={{ height: 1, flex: 1, background: 'rgba(184,151,98,.4)' }} />
            <span style={{ fontFamily: "'Cinzel',serif", fontSize: 11, letterSpacing: '.24em', color: 'var(--muted)' }}>RANK</span>
            {/* star-ranked — the diamond shows the star tier, not a letter grade */}
            <span style={{ width: 28, height: 28, transform: 'rotate(45deg)', background: star >= 7 ? 'linear-gradient(135deg,#fff,#c8a9f5)' : `linear-gradient(135deg,${STAR_ACCENT[Math.min(star, 7)]},#0c0718)`, border: `1px solid ${STAR_ACCENT[Math.min(star, 7)]}`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <span className={star >= 7 ? 'rainbow-text' : undefined} style={{ transform: 'rotate(-45deg)', fontFamily: "'Cinzel',serif", fontWeight: 900, fontSize: 13, color: star >= 7 ? undefined : '#f3ecdd' }}>{star}★</span>
            </span>
          </div>
          <div style={{ fontFamily: "'Cinzel',serif", fontWeight: 900, fontSize: nameSize, letterSpacing: '.02em', lineHeight: 1, color: 'var(--text-hi)', marginTop: 8, textShadow: '0 4px 30px rgba(124,58,214,.5)', wordBreak: 'break-word' }}>
            {name}
          </div>
          {leader.title && <div style={{ fontSize: 15, fontStyle: 'italic', color: 'var(--muted)', marginTop: 3 }}>"{leader.title}"</div>}
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 6, flexWrap: 'wrap' }}>
            <StarSpan count={star} size={13} />
            <span style={{ fontFamily: "'Cinzel',serif", letterSpacing: '.3em', fontSize: 12, color: 'var(--violet)' }}>{(leader.hero_class || '').toUpperCase()}</span>
            {tendency && <span style={{ fontFamily: "'Cinzel',serif", letterSpacing: '.16em', fontSize: 10, color: '#7c6f92' }}>{String(tendency).toUpperCase()}</span>}
          </div>
          {/* vitals */}
          <div style={{ marginTop: 16 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 3 }}>
              <span style={{ fontFamily: "'Cinzel',serif", letterSpacing: '.24em', fontSize: 9, color: 'var(--muted)' }}>HEALTH</span>
              <span style={{ fontFamily: "'Cormorant Garamond',serif", fontWeight: 700, fontSize: 15, color: 'var(--text-hi)' }}>{fmt(leader.health)} / {fmt(leader.max_health)}</span>
            </div>
            <div style={{ height: 6, background: 'rgba(0,0,0,.5)', border: '1px solid rgba(192,64,64,.4)' }}>
              <div style={{ width: `${hpPct}%`, height: '100%', background: 'linear-gradient(90deg,#7a3030,#c04040)' }} />
            </div>
            {leader.max_mana != null && (
              <>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', margin: '8px 0 3px' }}>
                  <span style={{ fontFamily: "'Cinzel',serif", letterSpacing: '.24em', fontSize: 9, color: 'var(--muted)' }}>MANA</span>
                  <span style={{ fontFamily: "'Cormorant Garamond',serif", fontWeight: 700, fontSize: 15, color: '#8fb8ff' }}>{fmt(leader.mana ?? leader.max_mana)} / {fmt(leader.max_mana)}</span>
                </div>
                <div style={{ height: 6, background: 'rgba(0,0,0,.5)', border: '1px solid rgba(74,122,170,.4)' }}>
                  <div style={{ width: `${manaPct}%`, height: '100%', background: '#3a7bd5' }} />
                </div>
              </>
            )}
          </div>
          {/* the seven */}
          <div style={{ marginTop: 16, display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '10px 14px', borderTop: '1px solid rgba(184,151,98,.2)', paddingTop: 14 }}>
            {[['STR', leader.strength], ['INT', leader.intelligence], ['AGI', leader.agility], ['END', leader.endurance], ['WIL', leader.willpower], ['LCK', leader.luck, 'var(--gold-hi)']].map(([k, v, c]) => (
              <div key={k}>
                <div style={{ fontFamily: "'Cinzel',serif", letterSpacing: '.26em', fontSize: 9, color: 'var(--muted)' }}>{k}</div>
                <div style={{ fontFamily: "'Cormorant Garamond',serif", fontWeight: 700, fontSize: 21, color: c || 'var(--text-hi)', lineHeight: 1.1 }}>{Math.round(v ?? 0)}</div>
              </div>
            ))}
          </div>
          {/* state chips */}
          <div style={{ display: 'flex', gap: 7, marginTop: 14, flexWrap: 'wrap' }}>
            <span style={{ fontFamily: "'Cinzel',serif", fontSize: 9, letterSpacing: '.16em', color: condBad ? '#e08585' : '#8fbf9f', border: `1px solid ${condBad ? 'rgba(192,64,64,.45)' : 'rgba(74,154,106,.45)'}`, padding: '2px 8px' }}>{condition}</span>
            {leader.fatigue != null && (
              <span style={{ fontFamily: "'Cinzel',serif", fontSize: 9, letterSpacing: '.16em', color: 'var(--gold-hi)', border: '1px solid rgba(184,151,98,.45)', padding: '2px 8px' }}>FATIGUE {leader.fatigue}/10</span>
            )}
            {tendency && (
              <span style={{ fontFamily: "'Cinzel',serif", fontSize: 9, letterSpacing: '.16em', color: 'var(--lavender)', border: '1px solid rgba(150,110,230,.45)', padding: '2px 8px' }}>{String(tendency).toUpperCase()}</span>
            )}
          </div>
          <span style={{ flex: 1, minHeight: 12 }} />
          {/* leader badge / crown + REMOVE FROM TEAM (Liam QoL) */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
            {leader.is_team_leader ? (
              <div style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '7px 14px', border: '1px solid rgba(255,216,138,.5)', background: 'rgba(184,151,98,.1)', clipPath: 'polygon(8px 0,100% 0,calc(100% - 8px) 100%,0 100%)' }}>
                <span style={{ color: '#ffd88a', fontSize: 13, textShadow: '0 0 8px rgba(255,216,138,.7)' }}>♛</span>
                <span style={{ fontFamily: "'Cinzel',serif", fontWeight: 700, letterSpacing: '.2em', fontSize: 10, color: '#ffd88a' }}>TEAM LEADER</span>
              </div>
            ) : (
              <button onClick={(e) => handleAssignLeader(leader.id, e)}
                style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '7px 14px', cursor: 'pointer', border: '1px solid rgba(184,151,98,.45)', background: 'rgba(12,7,24,.5)', clipPath: 'polygon(8px 0,100% 0,calc(100% - 8px) 100%,0 100%)' }}>
                <span style={{ color: 'rgba(255,216,138,.7)', fontSize: 13 }}>♛</span>
                <span style={{ fontFamily: "'Cinzel',serif", fontWeight: 700, letterSpacing: '.2em', fontSize: 10, color: '#c9bfa8' }}>CROWN AS LEADER</span>
              </button>
            )}
            <button onClick={async () => {
              try { await removeHeroFromTeam(leader.id); setSpotlightId(null); setMsg(`${leader.name} stood down from Team ${ROMAN[activeTab]}.`); await load() }
              catch (err) { setMsg(err.message) }
            }} title={`Remove ${leader.name} from this team`}
              style={{ display: 'inline-flex', alignItems: 'center', gap: 7, padding: '7px 14px', cursor: 'pointer', border: '1px solid rgba(192,64,64,.4)', background: 'rgba(12,7,24,.5)' }}>
              <span style={{ color: '#e08585', fontSize: 12 }}>✕</span>
              <span style={{ fontFamily: "'Cinzel',serif", fontWeight: 700, letterSpacing: '.2em', fontSize: 10, color: '#e08585' }}>REMOVE FROM TEAM</span>
            </button>
          </div>
        </div>

        {/* ── vertical divider ── */}
        <div style={{ width: 1, alignSelf: 'stretch', margin: '22px 0', background: 'linear-gradient(rgba(150,110,230,0),rgba(150,110,230,.4),rgba(150,110,230,0))', flex: 'none' }} />

        {/* ── full-body render ── */}
        <div onClick={() => setExpandedId(leader.id)} title={`Inspect ${leader.name}`}
          style={{ flex: '1 1 300px', minWidth: 220, position: 'relative', overflow: 'hidden', cursor: 'pointer' }}>
          <div style={{ position: 'absolute', inset: 0, background: 'radial-gradient(65% 60% at 55% 44%, rgba(140,70,214,.3), rgba(0,0,0,0) 72%)', animation: 'toe-glow 6s ease-in-out infinite' }} />
          {hasArt ? (
            <PanelArt hero={leader} style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'contain', objectPosition: 'center bottom' }} />
          ) : (
            <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 8, opacity: .55 }}>
              <span style={{ width: 34, height: 34, border: '1px solid rgba(200,169,245,.4)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--lavender)', fontSize: 18 }}>▤</span>
              <span style={{ fontFamily: 'monospace', fontSize: 11, color: '#7a6f92' }}>full-body leader render</span>
            </div>
          )}
          <div style={{ position: 'absolute', left: 0, right: 0, bottom: 0, height: 120, pointerEvents: 'none', background: 'linear-gradient(rgba(9,6,15,0),#0b0716)' }} />
        </div>
      </div>
    )
  }

  // ── TEAM view — left column (title, DEPLOY/MANAGE, the formation as
  // compact FACE tiles, left→right: rear guard | vanguard) + the spotlight
  // panel on the right (full body — defaults to the leader, or whichever
  // face was clicked). Full-body art appears NOWHERE else on this screen. ───
  function renderTeamView() {
    const teamHeroes = displayHeroes
    const leader = teamHeroes.find(h => h.is_team_leader) || teamHeroes[0] || null
    // Positions 0-1 are the frontline (team_position order), 2-4 the back.
    const front = teamHeroes.slice(0, 2)
    const back = teamHeroes.slice(2, 5)
    const spotlight = teamHeroes.find(h => h.id === spotlightId) || leader
    const goManage = () => { setAssignTargetTeam(activeTab); setActiveTab('all'); setFilterBy('AVAILABLE') }

    const emptySlotTile = (key) => (
      <div key={key} onClick={goManage}
        style={{ position: 'relative', display: 'flex', alignItems: 'center', gap: 15, width: 248, flex: 'none', cursor: 'pointer', padding: '13px 14px', border: '1px dashed rgba(150,110,230,.4)', background: 'rgba(12,7,24,.3)' }}>
        <span style={{ width: 74, height: 74, transform: 'rotate(45deg)', flex: 'none', border: '1px dashed rgba(200,169,245,.5)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <span style={{ transform: 'rotate(-45deg)', color: 'var(--lavender)', fontFamily: "'Cinzel',serif" }}>+</span>
        </span>
        <span style={{ fontFamily: "'Cinzel',serif", fontSize: 10, letterSpacing: '.22em', color: '#6f628c' }}>ASSIGN</span>
      </div>
    )
    const clusterHead = (label, color) => (
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
        <span style={{ width: 7, height: 7, transform: 'rotate(45deg)', background: color, display: 'inline-block' }} />
        <span style={{ fontFamily: "'Cinzel',serif", letterSpacing: '.26em', fontSize: 10, color, whiteSpace: 'nowrap' }}>{label}</span>
        <span style={{ height: 1, flex: 1, minWidth: 10, background: `${color}44` }} />
      </div>
    )

    return (
      <div className="ent-1" style={{ display: 'flex', gap: 26, alignItems: 'stretch', flexWrap: 'wrap' }}>
        {/* ── LEFT: title + actions + party cards ── */}
        <div style={{ flex: '1 1 620px', minWidth: 0, display: 'flex', flexDirection: 'column' }}>
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: 22, flexWrap: 'wrap' }}>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 6 }}>
                <span style={{ width: 9, height: 9, transform: 'rotate(45deg)', background: 'var(--gold)', display: 'inline-block' }} />
                <span style={{ fontFamily: "'Cinzel',serif", fontWeight: 600, letterSpacing: '.5em', fontSize: 13, color: 'var(--gold)' }}>SQUAD OVERVIEW · TEAM</span>
              </div>
              <div className="ilm-title-stack">
                <div className="ghost">FORMATION</div>
                <div className="solid">{teamNames[activeTab] || `TEAM ${ROMAN[activeTab]}`}</div>
              </div>
              <button onClick={() => renameTeam(activeTab)} title="Rename this team"
                style={{ background: 'none', border: 'none', cursor: 'pointer', fontFamily: "'Cinzel',serif", fontSize: 9, letterSpacing: '.2em', color: 'var(--muted)', padding: 0, marginTop: 2 }}>
                TEAM {ROMAN[activeTab]} · ✎ RENAME
              </button>
            </div>
            <span style={{ flex: 1 }} />
            {/* Arranging happens in-place (drag, crown, click-to-inspect);
                "go fight" is the Tower nav tab. The one action worth a button
                is comparing this team against another. */}
            <button onClick={() => { setCompareTeamB(activeTab === 1 ? 2 : 1); setCompareTeamA(activeTab); setCompareTeamsOpen(true) }}
              title="Compare this team's totals against another"
              style={{ cursor: 'pointer', fontFamily: "'Cinzel',serif", fontWeight: 600, letterSpacing: '.24em', fontSize: 13, color: '#cdbfe4', background: 'none', border: '1px solid rgba(150,110,230,.4)', padding: '10px 20px', clipPath: 'polygon(10px 0,100% 0,calc(100% - 10px) 100%,0 100%)' }}>
              ⇄ COMPARE TEAMS
            </button>
          </div>

          {msg && <div style={{ fontStyle: 'italic', fontSize: 14, marginTop: 8, color: '#8fbf9f' }}>{msg}</div>}
          <div style={{ fontStyle: 'italic', color: 'var(--muted)', fontSize: 13, marginTop: 12 }}>
            {teamHeroes.length > 0
              ? 'Click a face to inspect them on the right. Drag between positions — the vanguard takes the hits. ♛ crowns the leader.'
              : `Team ${ROMAN[activeTab]} is empty. Click any slot below to draw heroes from the roster.`}
          </div>

          {/* the formation — a top-down battle layout: REAR GUARD column
              (3 stacked) on the left, VANGUARD column (2 stacked) on the
              right toward the enemy. Same shape the combat screen uses.
              Row stretches so the vanguard's 2 tiles center against the 3. */}
          <div style={{ display: 'flex', gap: 20, marginTop: 28, alignItems: 'stretch' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {clusterHead('REAR GUARD', 'var(--lavender)')}
              {[0, 1, 2].map(i => back[i] ? renderFaceTile(back[i], spotlight?.id === back[i].id) : emptySlotTile(`back-empty-${i}`))}
            </div>
            <div style={{ width: 1, background: 'linear-gradient(rgba(184,151,98,0),rgba(184,151,98,.35),rgba(184,151,98,0))' }} />
            <div style={{ display: 'flex', flexDirection: 'column' }}>
              {clusterHead('VANGUARD', '#ffd88a')}
              <div style={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 10 }}>
                {[0, 1].map(i => front[i] ? renderFaceTile(front[i], spotlight?.id === front[i].id) : emptySlotTile(`front-empty-${i}`))}
              </div>
            </div>
          </div>
        </div>

        {/* ── RIGHT: the spotlight — leader by default, or the clicked face ── */}
        {spotlight ? renderLeaderPanel(spotlight) : (
          <div className="ent-3" style={{ flex: '1 1 460px', minWidth: 420, minHeight: 440, border: '1px dashed rgba(150,110,230,.35)', background: 'rgba(12,7,24,.3)', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 12 }}>
            <span style={{ width: 40, height: 40, transform: 'rotate(45deg)', border: '1px dashed rgba(200,169,245,.4)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <span style={{ transform: 'rotate(-45deg)', color: 'var(--lavender)', fontSize: 18 }}>♛</span>
            </span>
            <span style={{ fontFamily: "'Cinzel',serif", letterSpacing: '.24em', fontSize: 12, color: 'var(--muted)' }}>NO LEADER YET</span>
            <span style={{ fontStyle: 'italic', fontSize: 13, color: 'var(--text-dim)' }}>Assign heroes, then crown one to lead.</span>
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="page" style={{ display: 'flex', flexDirection: 'column' }}>
      {isTeamTab ? renderTeamView() : renderAllView()}

      {synthChamberOpen && (
        <SynthesisChamber
          heroes={heroes}
          onClose={() => setSynthChamberOpen(false)}
          onComplete={() => load()}
        />
      )}

      {giftHero && (
        <GiftModal
          hero={giftHero}
          onClose={() => setGiftHero(null)}
          onGifted={() => load()}
        />
      )}

      {expandedId && (
        // Zoom-safe modal scroll: align-items:flex-start keeps the top reachable
        // and overflow-y:auto scrolls the scrim (a centered oversized modal
        // clips its top otherwise). The modal's max-width:100% (containing-block
        // relative, NOT vw) can't overflow under the app's root zoom.
        <div className="ilm-modal-scrim" style={{ zIndex: 100, alignItems: 'flex-start', justifyContent: 'center', overflowY: 'hidden', padding: '28px' }} onClick={() => setExpandedId(null)}>
          <div className="ilm-herodetail" onClick={e => e.stopPropagation()}>
            <span className="ilm-corner" />
            <span className="ilm-corner ilm-corner-r" />
            {/* no bottom-left tick — that corner is the clip-path notch */}
            <span className="ilm-corner ilm-corner-br" />
            <button className="ilm-close" style={{ position: 'absolute', top: 14, right: 14, zIndex: 20 }} onClick={() => setExpandedId(null)}>✕</button>
            <HeroDetail
              hero={heroes.find(h => h.id === expandedId)}
              onChanged={() => load()}
              onManageEquipment={(h, s, e) => setEqModal({ hero: h, slot: s, currentEq: e })}
              onManageConsumable={(h) => setConsModal({ hero: h })}
              onAutoEquip={async (h, mode) => {
                try {
                  if (mode === 'auto') await autoEquipHero(h.id)
                  else await unequipAllHero(h.id)
                  load()
                } catch (e) {
                  emitToast({ title: 'Equipment Error', lines: [{ label: e.message, value: '' }], borderColor: 'var(--red)' })
                }
              }}
              onGift={(h) => setGiftHero(h)}
              onPrev={(() => {
                const idx = displayHeroes.findIndex(h => h.id === expandedId)
                return idx > 0 ? () => setExpandedId(displayHeroes[idx - 1].id) : null
              })()}
              onNext={(() => {
                const idx = displayHeroes.findIndex(h => h.id === expandedId)
                return idx >= 0 && idx < displayHeroes.length - 1 ? () => setExpandedId(displayHeroes[idx + 1].id) : null
              })()}
              actions={heroes.find(h => h.id === expandedId)?.is_alive && (
                <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end', alignItems: 'center' }}>
                  {typeof activeTab === 'number' && heroes.find(h => h.id === expandedId)?.ego_type && (
                    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '0.3rem' }}>
                      {egoPreview && egoPreview.heroId === expandedId && (
                        <div className="text-dim" style={{ fontSize: '0.7rem', textAlign: 'right', maxWidth: '260px' }}>
                          Wants: {egoPreview.recommended_team.map(h => h.name).join(', ')}
                        </div>
                      )}
                      <div style={{ display: 'flex', gap: '0.4rem' }}>
                        <button className="btn" style={{ border: '1px solid #ff8888', color: '#ff8888', background: 'rgba(255,100,100,0.05)', fontFamily: 'Cinzel, serif', padding: '0.3rem 0.6rem', fontSize: '0.7rem', borderRadius: 4 }} onClick={async (e) => {
                          e.stopPropagation();
                          try {
                            const rec = await getEgoRecommendation(expandedId);
                            setEgoPreview({ heroId: expandedId, ...rec });
                          } catch (err) { setMsg(err.message) }
                        }}>
                          Preview Wishes
                        </button>
                        <button className="btn" style={{ border: '1px solid #ff8888', color: '#ff8888', background: 'rgba(255,100,100,0.1)', fontFamily: 'Cinzel, serif', padding: '0.3rem 0.8rem', fontSize: '0.75rem', borderRadius: 4 }} onClick={async (e) => {
                          e.stopPropagation();
                          try {
                            await egoAutoTeam(activeTab, expandedId);
                            await load();
                            setExpandedId(null);
                            setEgoPreview(null);
                          } catch (err) { setMsg(err.message) }
                        }}>
                          Let {heroes.find(h => h.id === expandedId)?.name} form Team {activeTab}
                        </button>
                      </div>
                    </div>
                  )}
                  {(heroes.find(h => h.id === expandedId)?.ascension_star || 0) < 7 && (
                    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end' }}>
                      <button className="btn" style={{ border: '1px solid var(--gold)', color: 'var(--gold)', background: 'rgba(201,168,76,0.1)', fontFamily: 'Cinzel, serif', padding: '0.3rem 0.8rem', fontSize: '0.75rem', borderRadius: 4 }} onClick={(e) => handleAscend(expandedId, e)} disabled={ascending || promoting || evolving}>
                        {ascending ? '...' : `◆ Ascend`}
                      </button>
                      <div className="text-dim" style={{ fontSize: '0.6rem', marginTop: '0.2rem' }}>{(heroes.find(h => h.id === expandedId)?.birth_star || 1) * 1000} Gold</div>
                    </div>
                  )}
                  {heroes.find(h => h.id === expandedId)?.evolution_options?.length > 0 && (() => {
                    const h = heroes.find(x => x.id === expandedId)
                    // Level holds at 30/60 until a path is chosen (backend
                    // evolution gate) — XP banks, so say so.
                    const gated = h.level === 30 || h.level === 60
                    if (gated) import('../codexBus').then(c => c.unlockCodex('crossroads', 'THE CROSSROADS')).catch(() => {})
                    return (
                      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', marginLeft: '1rem' }}>
                        <button className="btn" style={{ border: '1px solid #9d4edd', color: '#e0aaff', background: 'rgba(157, 78, 221, 0.1)', fontFamily: 'Cinzel, serif', padding: '0.4rem 1rem', fontSize: '0.85rem', borderRadius: 4, boxShadow: '0 0 8px rgba(157,78,221,0.5)' }} onClick={(e) => { e.preventDefault(); e.stopPropagation(); setEvoModal({ hero: h }); }} disabled={evolving || ascending || promoting}>
                          Class Advancement Available
                        </button>
                        {gated && (
                          <div style={{ fontSize: '0.6rem', marginTop: '0.2rem', color: '#e0aaff', fontFamily: 'Cinzel, serif', letterSpacing: '.08em' }}>
                            LEVEL HELD AT {h.level} — XP BANKS UNTIL A PATH IS CHOSEN
                          </div>
                        )}
                      </div>
                    )
                  })()}
                  {heroes.find(h => h.id === expandedId)?.level >= STAR_CAPS[heroes.find(h => h.id === expandedId)?.current_star || heroes.find(h => h.id === expandedId)?.birth_star] && (heroes.find(h => h.id === expandedId)?.current_star || heroes.find(h => h.id === expandedId)?.birth_star) < 7 && (
                    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end' }}>
                      <button className="btn" style={{ border: '1px solid var(--star5)', color: 'var(--star5)', background: 'rgba(201,168,76,0.1)', fontFamily: 'Cinzel, serif', padding: '0.3rem 0.8rem', fontSize: '0.75rem', boxShadow: '0 0 5px var(--star5)', borderRadius: 4 }} onClick={(e) => handlePromote(expandedId, e)} disabled={ascending || promoting}>
                        {promoting ? '...' : `★ Promote`}
                      </button>
                      <div className="text-dim" style={{ fontSize: '0.6rem', marginTop: '0.2rem' }}>{(heroes.find(h => h.id === expandedId)?.current_star || heroes.find(h => h.id === expandedId)?.birth_star) * 5000} Gold</div>
                    </div>
                  )}
                </div>
              )}
            />
          </div>
        </div>
      )}

      {/* Equipment Modal */}
      {eqModal && (
        <div className="ilm-modal-scrim" style={{ zIndex: 200 }} onClick={() => setEqModal(null)}>
          <div className="ilm-featmodal" style={{ width: 500, maxWidth: '90vw', maxHeight: '80vh', overflowY: 'auto' }} onClick={e => e.stopPropagation()}>
            <span className="ilm-corner" /><span className="ilm-corner ilm-corner-r" />
            <button className="ilm-close" style={{ position: 'absolute', top: 14, right: 14 }} onClick={() => setEqModal(null)}>✕</button>
            <div className="ilm-micro" style={{ color: 'var(--gold-hi)' }}>ARSENAL · {eqModal.slot?.toUpperCase()}</div>
            <div style={{ fontFamily: "'Cinzel',serif", fontWeight: 900, fontSize: '1.3rem', color: 'var(--text-hi)', marginTop: 2, marginBottom: 12 }}>
              {eqModal.hero.name?.toUpperCase()}
            </div>

            {eqModal.currentEq && (
              <div style={{ marginBottom: 16, padding: '12px 14px', background: 'rgba(184,151,98,.06)', border: '1px solid rgba(184,151,98,.35)' }}>
                <div className="ilm-micro" style={{ color: 'var(--muted)', marginBottom: 6 }}>CURRENTLY BORNE</div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10 }}>
                  <div>
                    <div style={{ color: 'var(--gold-hi)', fontFamily: "'Cinzel',serif" }}>{eqModal.currentEq.name}</div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>
                      {eqModal.currentEq.rarity} · Lv {eqModal.currentEq.level} · {formatEquipmentStats(eqModal.currentEq)}
                    </div>
                  </div>
                  <button className="ilm-btn ilm-btn-danger" onClick={async () => {
                    await unequipItem(eqModal.currentEq.id);
                    setEqModal(null);
                    load();
                  }}>UNEQUIP</button>
                </div>
              </div>
            )}

            <div className="ilm-micro" style={{ color: 'var(--muted)', marginBottom: 8 }}>IN STORAGE</div>
            {allEq.filter(e => e.type?.toLowerCase() === eqModal.slot).length === 0 ? (
              <div style={{ fontStyle: 'italic', color: 'var(--text-dim)', fontSize: '0.85rem' }}>No unequipped {eqModal.slot}s available.</div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8, maxHeight: 300, overflowY: 'auto', paddingRight: 6 }}>
                {allEq.filter(e => e.type?.toLowerCase() === eqModal.slot)
                  .sort((a, b) => {
                    const tiers = ["F-", "F", "F+", "E-", "E", "E+", "D-", "D", "D+", "C-", "C", "C+", "B-", "B", "B+", "A-", "A", "A+", "S-", "S", "S+", "SS", "SSS", "Z"];
                    return tiers.indexOf(b.rarity) - tiers.indexOf(a.rarity);
                  })
                  .map(eq => (
                  <div key={eq.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10, padding: '10px 12px', background: 'rgba(12,7,24,.5)', border: '1px solid rgba(184,151,98,.25)' }}>
                    <div>
                      <div style={{ color: 'var(--text-hi)', fontFamily: "'Cinzel',serif" }}>{eq.name}</div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>
                        {eq.rarity} · Lv {eq.level} · {formatEquipmentStats(eq)}
                      </div>
                    </div>
                    <button className="ilm-btn ilm-btn-gold" onClick={async () => {
                      try {
                        await equipItem(eq.id, eqModal.hero.id);
                        setEqModal(null);
                        load();
                      } catch (e) {
                        emitToast({ title: 'Cannot Equip', lines: [{ label: e.message, value: '' }], borderColor: 'var(--red)' });
                      }
                    }}>EQUIP</button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Consumable Modal */}
      {consModal && (
        <div className="ilm-modal-scrim" style={{ zIndex: 200 }} onClick={() => setConsModal(null)}>
          <div className="ilm-featmodal" style={{ width: 500, maxWidth: '90vw', maxHeight: '80vh', overflowY: 'auto' }} onClick={e => e.stopPropagation()}>
            <span className="ilm-corner" /><span className="ilm-corner ilm-corner-r" />
            <button className="ilm-close" style={{ position: 'absolute', top: 14, right: 14 }} onClick={() => setConsModal(null)}>✕</button>
            <div className="ilm-micro" style={{ color: 'var(--gold-hi)' }}>PROVISIONS</div>
            <div style={{ fontFamily: "'Cinzel',serif", fontWeight: 900, fontSize: '1.3rem', color: 'var(--text-hi)', marginTop: 2 }}>
              {consModal.hero.name?.toUpperCase()}
            </div>
            <div style={{ fontStyle: 'italic', color: 'var(--text-dim)', fontSize: '0.85rem', margin: '8px 0 14px', lineHeight: 1.5 }}>
              What this hero carries into the tower and drinks/uses when hurt. Bandages heal pre-fight; Potions/Scrolls heal mid-fight. The item still comes from the same shared stock — this just decides who's allowed to reach for it.
            </div>

            {consModal.hero.equipped_consumable && (
              <div style={{ marginBottom: 16, padding: '12px 14px', background: 'rgba(184,151,98,.06)', border: '1px solid rgba(184,151,98,.35)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div style={{ color: 'var(--gold-hi)', fontFamily: "'Cinzel',serif" }}>{consModal.hero.equipped_consumable}</div>
                <button className="ilm-btn ilm-btn-danger" onClick={async () => {
                  await equipConsumable(consModal.hero.id, null)
                  setConsModal(null)
                  load()
                }}>UNEQUIP</button>
              </div>
            )}

            <div className="ilm-micro" style={{ color: 'var(--muted)', marginBottom: 8 }}>IN STORAGE</div>
            {consOptions.length === 0 ? (
              <div style={{ fontStyle: 'italic', color: 'var(--text-dim)', fontSize: '0.85rem' }}>No Bandages, Potions, or Scrolls in storage.</div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8, maxHeight: 300, overflowY: 'auto', paddingRight: 6 }}>
                {consOptions.map(opt => (
                  <div key={opt.item_name} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 12px', background: 'rgba(12,7,24,.5)', border: '1px solid rgba(184,151,98,.25)' }}>
                    <div>
                      <div style={{ color: 'var(--text-hi)', fontFamily: "'Cinzel',serif" }}>{opt.item_name}</div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>Owned: {opt.quantity}</div>
                    </div>
                    <button className="ilm-btn ilm-btn-gold" onClick={async () => {
                      try {
                        await equipConsumable(consModal.hero.id, opt.item_name)
                        setConsModal(null)
                        load()
                      } catch (e) {
                        setMsg(e.message)
                      }
                    }}>EQUIP</button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Evolution Modal */}
      {evoModal && (
        <ClassEvolutionModal
          hero={evoModal.hero}
          forced={!!evoModal.forced}
          onClose={() => {
            if (evoModal.forced) evoSnoozedRef.current.add(evoModal.hero.id)
            setEvoModal(null)
          }}
          onEvolve={(newClass) => {
            setMsg(`Hero evolved to ${newClass}!`)
            import('../audio').then(a => a.playEvolveSurge()).catch(() => {})
            load()
          }}
        />
      )}

      {compareHeroesOpen && (
        <HeroCompareModal
          heroes={heroes.filter(h => selected.has(h.id))}
          onClose={() => setCompareHeroesOpen(false)}
        />
      )}

      {compareTeamsOpen && (
        <div className="ilm-modal-scrim" style={{ zIndex: 100 }} onClick={() => setCompareTeamsOpen(false)}>
          <div className="ilm-featmodal" style={{ width: 400, maxWidth: '90vw' }} onClick={e => e.stopPropagation()}>
            <span className="ilm-corner" /><span className="ilm-corner ilm-corner-r" />
            <button className="ilm-close" style={{ position: 'absolute', top: 14, right: 14 }} onClick={() => setCompareTeamsOpen(false)}>✕</button>
            <div className="ilm-micro" style={{ color: 'var(--gold-hi)' }}>WAR COUNCIL</div>
            <div style={{ fontFamily: "'Cinzel',serif", fontWeight: 900, fontSize: '1.3rem', color: 'var(--text-hi)', marginTop: 2, marginBottom: 14 }}>COMPARE TEAMS</div>
            <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 16 }}>
              <select className="input" value={compareTeamA} onChange={e => setCompareTeamA(Number(e.target.value))} style={{ flex: 1, fontFamily: "'Cinzel',serif", fontSize: '0.75rem', letterSpacing: '.1em' }}>
                {[1, 2, 3, 4, 5].map(t => <option key={t} value={t}>TEAM {ROMAN[t]}</option>)}
              </select>
              <span style={{ fontFamily: "'Cinzel',serif", fontSize: 10, letterSpacing: '.2em', color: 'var(--muted)' }}>VS</span>
              <select className="input" value={compareTeamB} onChange={e => setCompareTeamB(Number(e.target.value))} style={{ flex: 1, fontFamily: "'Cinzel',serif", fontSize: '0.75rem', letterSpacing: '.1em' }}>
                {[1, 2, 3, 4, 5].map(t => <option key={t} value={t}>TEAM {ROMAN[t]}</option>)}
              </select>
            </div>
            <div style={{ display: 'flex', gap: 10 }}>
              <button className="ilm-btn ilm-btn-violet" style={{ flex: 1.4 }} onClick={() => { setCompareTeamsOpen(false); setCompareTeamsResultOpen(true) }} disabled={compareTeamA === compareTeamB}>
                COMPARE
              </button>
              <button style={{ flex: 0.7, background: 'none', border: 'none', cursor: 'pointer', fontFamily: "'Cinzel',serif", fontWeight: 500, letterSpacing: '.2em', fontSize: '0.68rem', color: 'var(--text-dim)' }} onClick={() => setCompareTeamsOpen(false)}>CANCEL</button>
            </div>
            {compareTeamA === compareTeamB && <div style={{ color: '#e08585', fontSize: '0.8rem', fontStyle: 'italic', marginTop: 8 }}>Pick two different teams.</div>}
          </div>
        </div>
      )}

      {compareTeamsResultOpen && (
        <TeamCompareModal
          teamA={{ label: compareTeamA, heroes: heroes.filter(h => h.is_on_team === compareTeamA) }}
          teamB={{ label: compareTeamB, heroes: heroes.filter(h => h.is_on_team === compareTeamB) }}
          onClose={() => setCompareTeamsResultOpen(false)}
        />
      )}

      {/* ── bottom team nav (Squad Overview spec) ── */}
      <div style={{ position: 'sticky', bottom: 0, marginTop: 'auto', display: 'flex', alignItems: 'center', gap: 26,
        padding: '14px 8px 12px', borderTop: '1px solid rgba(184,151,98,.28)',
        background: 'linear-gradient(rgba(11,7,20,0), #0b0714)', zIndex: 20 }}>
        {[
          { id: 'all', label: 'ALL HEROES' },
          { id: 1, label: 'TEAM I' }, { id: 2, label: 'TEAM II' }, { id: 3, label: 'TEAM III' },
          { id: 4, label: 'TEAM IV' }, { id: 5, label: 'TEAM V' },
          { id: 'favorites', label: '♥ FAVORITES' },
        ].map(t => {
          const active = activeTab === t.id
          return (
            <span key={t.id} onClick={() => { setActiveTab(t.id); setSelected(new Set()); setMsg(null); setSpotlightId(null) }}
              style={{ cursor: 'pointer', fontFamily: 'Cinzel, serif', fontWeight: active ? 700 : 500,
                letterSpacing: '.28em', fontSize: 13, textTransform: 'uppercase',
                color: active ? 'var(--text-hi)' : (t.id === 'favorites' ? '#e0708a' : 'var(--text-dim)'),
                borderBottom: active ? '2px solid var(--gold)' : '2px solid transparent', paddingBottom: 3 }}>
              {t.label}
            </span>
          )
        })}
        <span style={{ flex: 1 }} />
        {/* roster page controls — footer-resident, only when the roster overflows */}
        {!isTeamTab && totalRosterPages > 1 && (
          <span style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <button onClick={() => setRosterPage(Math.max(0, safeRosterPage - 1))} disabled={safeRosterPage === 0}
              style={{ background: 'none', border: 'none', cursor: safeRosterPage === 0 ? 'default' : 'pointer', fontFamily: 'Cinzel, serif', fontSize: 15, color: safeRosterPage === 0 ? 'rgba(154,134,184,.3)' : '#c9bfa8', padding: '0 4px' }}>‹</button>
            {totalRosterPages <= 9 ? (
              Array.from({ length: totalRosterPages }, (_, i) => {
                const active = i === safeRosterPage
                return (
                  <span key={i} onClick={() => setRosterPage(i)}
                    style={{ cursor: 'pointer', width: 20, height: 20, transform: 'rotate(45deg)', flex: 'none',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      border: `1px solid ${active ? 'var(--gold-hi)' : 'rgba(184,151,98,.35)'}`,
                      background: active ? 'linear-gradient(135deg,#241a10,#120d08)' : 'rgba(12,7,24,.5)',
                      boxShadow: active ? '0 0 8px rgba(184,151,98,.35)' : 'none' }}>
                    <span style={{ transform: 'rotate(-45deg)', fontFamily: "'Cinzel',serif", fontWeight: active ? 700 : 500, fontSize: 9, color: active ? '#ffd88a' : 'var(--text-dim)' }}>{i + 1}</span>
                  </span>
                )
              })
            ) : (
              <span style={{ fontFamily: 'Cinzel, serif', letterSpacing: '.2em', fontSize: 11, color: 'var(--text-dim)' }}>
                PAGE <span style={{ color: '#ffd88a' }}>{safeRosterPage + 1}</span> / {totalRosterPages}
              </span>
            )}
            <button onClick={() => setRosterPage(Math.min(totalRosterPages - 1, safeRosterPage + 1))} disabled={safeRosterPage >= totalRosterPages - 1}
              style={{ background: 'none', border: 'none', cursor: safeRosterPage >= totalRosterPages - 1 ? 'default' : 'pointer', fontFamily: 'Cinzel, serif', fontSize: 15, color: safeRosterPage >= totalRosterPages - 1 ? 'rgba(154,134,184,.3)' : '#c9bfa8', padding: '0 4px' }}>›</button>
            <span style={{ width: 1, height: 16, background: 'rgba(184,151,98,.3)', margin: '0 6px' }} />
          </span>
        )}
        <span style={{ fontFamily: 'Cinzel, serif', letterSpacing: '.24em', fontSize: 12, color: 'var(--muted)' }}>
          {heroes.filter(h => h.is_alive).length} HEROES · <span style={{ color: 'var(--gold-hi)' }}>{heroes.filter(h => h.is_alive && h.is_on_team).length} DEPLOYED</span>
        </span>
      </div>
    </div>
  )
}
