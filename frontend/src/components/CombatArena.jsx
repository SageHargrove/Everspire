import React, { useState, useEffect, useRef } from 'react'
import { playHitSound, playPhaseHorn } from '../audio'
import Sigil from './Sigil'

// Status-chip palette for the combat rails. Backend emits per-turn labels
// (see combat_service._status_snapshot); `c`/`b` tint them, `icon` is the
// custom Sigil SVG under /public/icons/status/<icon>.svg (currentColor mask,
// so it takes the chip's color). Icon set matches the Sigil Library sheet.
const STATUS_STYLE = {
  BLEED:         { c: '#e08585', b: 'rgba(192,64,64,.5)',   icon: 'BLEED' },
  POISON:        { c: '#8fbf9f', b: 'rgba(74,154,106,.5)',  icon: 'POISON' },
  BURN:          { c: '#e8a34c', b: 'rgba(232,163,76,.5)',  icon: 'BURN' },
  FREEZE:        { c: '#7ecfd8', b: 'rgba(126,207,216,.5)', icon: 'FREEZE' },
  STUN:          { c: '#e08585', b: 'rgba(192,64,64,.5)',   icon: 'STUN' },
  FEAR:          { c: '#e08585', b: 'rgba(192,64,64,.5)',   icon: 'FEAR' },
  'ARMOR BREAK': { c: '#e08585', b: 'rgba(192,64,64,.5)',   icon: 'ARMOR_BREAK' },
  TAUNT:         { c: '#d8bb84', b: 'rgba(216,187,132,.5)', icon: 'TAUNTING' },
  SHIELD:        { c: '#8fbf9f', b: 'rgba(74,154,106,.5)',  icon: 'DMG_SHIELD' },
  ENRAGED:       { c: '#e08585', b: 'rgba(192,64,64,.5)',   icon: 'ENRAGED' },
  HASTE:         { c: '#8fbf9f', b: 'rgba(74,154,106,.5)',  icon: 'HASTE' },
  BLIND:   { c: '#c8a9f5', b: 'rgba(150,110,230,.5)', icon: 'BLIND' },
  SILENCE: { c: '#c8a9f5', b: 'rgba(150,110,230,.5)', icon: 'SILENCE' },
  REGEN:   { c: '#8fbf9f', b: 'rgba(74,154,106,.5)',  icon: 'REGEN' },
  EVASION: { c: '#7ecfd8', b: 'rgba(126,207,216,.5)', icon: 'EVASION' },
  BUFF:    { c: '#8fbf9f', b: 'rgba(74,154,106,.5)' },
  WEAK:    { c: '#d98a8a', b: 'rgba(192,64,64,.4)',   icon: 'WEAK' },
}
function StatusChips({ list }) {
  if (!list || list.length === 0) return null
  return (
    <div className="ilm-unitchips">
      {list.map(s => {
        const st = STATUS_STYLE[s] || { c: 'var(--text-dim)', b: 'var(--border)' }
        return (
          <span key={s} className="ilm-unitchip" style={{ color: st.c, borderColor: st.b }} title={s}>
            {st.icon && <Sigil set="status" name={st.icon} size={11} />}
            {s}
          </span>
        )
      })}
    </div>
  )
}

// Front/back column gap widened from 34%/14% (20% apart) — at the old 1.3x
// hero scale that gap was only a few px wider than the circles themselves
// (confirmed by measuring actual render size), so Front-Top and Back-Top
// visibly overlapped. Now 24% apart, paired with the scale-down below.
const TEAM_POSITIONS = {
  hero: [
    { x: '36%', y: '30%' }, // Front Top
    { x: '36%', y: '70%' }, // Front Bottom
    { x: '12%', y: '15%' }, // Back Top
    { x: '12%', y: '50%' }, // Back Mid
    { x: '12%', y: '85%' }, // Back Bottom
  ],
  enemy: [
    { x: '64%', y: '30%' }, // Front Top
    { x: '64%', y: '70%' }, // Front Bottom
    { x: '88%', y: '15%' }, // Back Top
    { x: '88%', y: '50%' }, // Back Mid
    { x: '88%', y: '85%' }, // Back Bottom
  ]
}

// Solo enemies (elite mobs, minibosses, bosses) read as more threatening when
// rendered bigger than a regular swarm/pack unit — scaled by tier, not just
// "is there one enemy on screen" so a true boss still reads as the biggest
// thing in the room.
const ENEMY_SIZE_TIERS = {
  normal:   { circle: 150, container: 170, icon: '2.8rem', name: '1rem',   pos: null },
  elite:    { circle: 220, container: 240, icon: '3.6rem', name: '1.15rem', pos: { x: '70%', y: '50%' } },
  miniboss: { circle: 320, container: 340, icon: '4.4rem', name: '1.3rem', pos: { x: '73%', y: '50%' } },
  boss:     { circle: 460, container: 480, icon: '5.5rem', name: '1.5rem', pos: { x: '77%', y: '50%' } },
  // Swarms (6+ units on one side) no longer fit the fixed 5-slot formation —
  // they're laid out on a grid (see getGridPosition) and sized down further
  // still as the count climbs, so a 20-rat horde doesn't overlap itself.
  swarm:    { circle: 80,  container: 90,  icon: '1.6rem', name: '0.68rem', pos: null },
  swarmTiny:{ circle: 56,  container: 64,  icon: '1.2rem', name: '0.6rem',  pos: null },
}

// Survival Swarm floors can spawn 30-50 enemies at once server-side — fine
// for the "can't realistically kill them all" combat math, but rendering
// that many sprites reads as a dense unreadable mass rather than "epic".
// Caps how many get an actual sprite; the rest are summarized as an
// overflow badge (see the enemy render block below).
const MAX_VISIBLE_ENEMIES = 16

// TEAM_POSITIONS only has 5 hand-placed slots per side, matching the 5-hero
// team cap — fine for normal encounters, but a swarm (or a hero side padded
// out by a summoned Construct past 5 units) needs a layout that scales with
// however many units actually showed up. Lays units out in an evenly-spaced
// grid within that side's half of the arena instead of hand-placed slots.
function getGridPosition(idx, count, team) {
  const cols = Math.ceil(Math.sqrt(count * 1.4))
  const rows = Math.ceil(count / cols)
  const col = idx % cols
  const row = Math.floor(idx / cols)
  const [xMin, xMax] = team === 'hero' ? [6, 44] : [56, 94]
  const [yMin, yMax] = [8, 92]
  const x = xMin + ((col + 0.5) / cols) * (xMax - xMin)
  const y = rows > 1 ? yMin + ((row + 0.5) / rows) * (yMax - yMin) : 50
  return { x: `${x}%`, y: `${y}%` }
}

function FloatingDamage({ number, isCrit, onComplete }) {
  const [active, setActive] = useState(true)

  useEffect(() => {
    const timer = setTimeout(() => {
      setActive(false)
      if (onComplete) onComplete()
    }, 800)
    return () => clearTimeout(timer)
  }, [onComplete])

  if (!active) return null

  return (
    <div style={{
      position: 'absolute',
      top: '-20px',
      left: '50%',
      transform: 'translate(-50%, -100%)',
      color: isCrit ? '#ff4444' : '#fff',
      fontWeight: 'bold',
      fontSize: isCrit ? '1.8rem' : '1.2rem',
      textShadow: '0 2px 4px rgba(0,0,0,0.8)',
      animation: 'floatUpAndFade 0.8s ease-out forwards',
      zIndex: 100,
      pointerEvents: 'none'
    }}>
      -{number}
      {isCrit && <span style={{ fontSize: '0.8rem', display: 'block' }}>CRIT!</span>}
    </div>
  )
}

// Active skills previously only showed up as combat-log text — this gives
// the caster a visible callout + glow pulse on their own portrait so a
// skill cast actually reads as an event, not just another basic-attack line.
function SkillCallout({ name }) {
  return (
    <div style={{
      position: 'absolute',
      top: '-32px',
      left: '50%',
      transform: 'translate(-50%, -100%)',
      color: '#fff',
      fontWeight: 'bold',
      fontSize: '1.15rem',
      whiteSpace: 'nowrap',
      background: 'rgba(201,168,76,0.25)',
      border: '1px solid var(--gold)',
      borderRadius: '6px',
      padding: '0.15rem 0.7rem',
      textShadow: '0 0 10px rgba(201,168,76,1), 0 2px 4px rgba(0,0,0,0.9)',
      boxShadow: '0 0 16px rgba(201,168,76,0.7)',
      animation: 'skillCalloutPop 1.3s ease-out forwards',
      zIndex: 101,
      pointerEvents: 'none',
      fontFamily: 'Cinzel, serif',
    }}>
      ✦ {name} ✦
    </div>
  )
}

function CombatUnitSprite({ unit, team, position, teamCount = 1, pos: posOverride, isActive, isHit, health, maxHp, mana, maxMana, damageInfo, skillName, tier = 'normal' }) {
  const [imgError, setImgError] = useState(false)
  if (!unit) return null

  const isDead = health <= 0
  const hpPercent = Math.max(0, (health / maxHp) * 100)
  const manaPercent = maxMana > 0 ? Math.max(0, (mana / maxMana) * 100) : 0

  const pos = posOverride || (teamCount > 5 ? getGridPosition(position, teamCount, team) : TEAM_POSITIONS[team][position]) || TEAM_POSITIONS[team][0]
  // Heroes render somewhat larger than the shared enemy-tier sizing so faces
  // and HP/mana bars stay legible — was previously sharing ENEMY_SIZE_TIERS
  // 1:1 with enemies, which is tuned for "boss should look huge," not for
  // a hero player actually needs to read at a glance. Was 1.3x, which (with
  // the border width added on top) was only a few px narrower than the
  // Front/Back column gap at a 5-hero team — visibly overlapped. 1.15x
  // plus the widened columns above gives real clearance.
  const baseSize = ENEMY_SIZE_TIERS[tier] || ENEMY_SIZE_TIERS.normal
  const size = team === 'hero'
    ? { ...baseSize, circle: Math.round(baseSize.circle * 1.15), container: Math.round(baseSize.container * 1.15) }
    : baseSize

  return (
    <div style={{
      position: 'absolute',
      left: pos.x,
      top: pos.y,
      transform: `translate(-50%, -50%) ${isActive ? (team === 'hero' ? 'translateX(15px)' : 'translateX(-15px)') : ''}`,
      transition: 'transform 0.2s ease-out',
      opacity: isDead ? 0.3 : 1,
      filter: isDead ? 'grayscale(100%)' : isHit ? 'brightness(200%)' : 'none',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      gap: '0.7rem',
      width: `${size.container}px`,
      zIndex: tier === 'boss' ? 5 : tier === 'miniboss' ? 4 : tier === 'elite' ? 3 : 1
    }}>
      <div style={{
        width: `${size.circle}px`,
        height: `${size.circle}px`,
        borderRadius: '50%',
        border: `${skillName ? 6 : tier === 'normal' ? 4 : 5}px solid ${skillName ? '#fff' : team === 'hero' ? 'var(--gold)' : '#a44'}`,
        overflow: 'hidden',
        position: 'relative',
        background: '#1a1a24',
        animation: skillName ? 'skillRingPulse 0.6s ease-out 2' : undefined,
        boxShadow: skillName
          ? '0 0 45px 12px rgba(201,168,76,1)'
          : isActive
          ? `0 0 20px ${team === 'hero' ? 'var(--gold)' : '#a44'}`
          : tier !== 'normal' ? `0 0 14px ${team === 'hero' ? 'rgba(201,168,76,0.4)' : 'rgba(170,68,68,0.5)'}, 0 4px 10px rgba(0,0,0,0.5)`
          : '0 4px 10px rgba(0,0,0,0.5)'
      }}>
        {skillName && <SkillCallout name={skillName} />}
        {unit.portrait_path && !imgError ? (
          <img src={`/${unit.portrait_path}`} style={{ width: '100%', height: '100%', objectFit: 'contain', objectPosition: 'center top' }} alt={unit.name} onError={() => setImgError(true)} />
        ) : (
          <div style={{ width: '100%', height: '100%', background: '#333', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: size.icon }}>
            {team === 'hero' ? '✦' : '◆'}
          </div>
        )}
      </div>

      <div style={{
        width: '100%',
        background: '#111',
        height: '10px',
        borderRadius: '5px',
        overflow: 'hidden'
      }}>
        <div style={{
          width: `${hpPercent}%`,
          height: '100%',
          background: team === 'hero' ? '#4a4' : '#e44',
          transition: 'width 0.3s ease-out'
        }} />
      </div>

      {team === 'hero' && maxMana > 0 && (
        <div title={`MP: ${mana} / ${maxMana}`} style={{
          width: '100%',
          background: '#111',
          height: '7px',
          borderRadius: '4px',
          overflow: 'hidden',
          marginTop: '-0.35rem',
        }}>
          <div style={{
            width: `${manaPercent}%`,
            height: '100%',
            background: '#3a7bd5',
            transition: 'width 0.3s ease-out',
          }} />
        </div>
      )}

      <div style={{
        fontSize: size.name,
        background: 'rgba(0,0,0,0.6)',
        padding: '0.15rem 0.6rem',
        borderRadius: '4px',
        whiteSpace: 'nowrap',
        overflow: 'hidden',
        textOverflow: 'ellipsis',
        maxWidth: '100%'
      }}>
        {unit.name}{unit.level ? ` [Lv ${unit.level}]` : ''}
      </div>

      {damageInfo && (
        <FloatingDamage number={damageInfo.amount} isCrit={damageInfo.crit} />
      )}
    </div>
  )
}

export default function CombatArena({ combatData, onComplete, turnNarrations, initialTurnIndex = -1, environment = null }) {
  const [currentTurnIndex, setCurrentTurnIndex] = useState(-1)
  const [playing, setPlaying] = useState(false)
  
  // Local state for Health/Mana tracking
  const [unitHPs, setUnitHPs] = useState({})
  const [unitManas, setUnitManas] = useState({})
  // Persisted across fights (localStorage), not just this component's
  // lifetime — once a player wants 2x, they want it for every fight.
  const [speedMult, setSpeedMult] = useState(() => {
    const v = parseInt(localStorage.getItem('combatSpeed') || '')
    if (v === 1 || v === 2 || v === 4) return v
    return localStorage.getItem('combatSpeed2x') === '1' ? 2 : 1 // legacy key
  })
  function setSpeed(n) {
    localStorage.setItem('combatSpeed', String(n))
    setSpeedMult(n)
  }
  
  const heroes = combatData?.initial_state?.heroes || []
  const enemies = combatData?.initial_state?.enemies || []
  // How many enemies are the targeted-first FRONT LINE — scales with the
  // swarm (backend _enemy_frontline_n). Fallback replicates that formula.
  const enemyFrontN = combatData?.initial_state?.enemy_frontline
    ?? Math.min(6, Math.max(2, Math.round(enemies.length * 0.4)))
  const turns = combatData?.turns || []
  const isBoss = combatData?.initial_state?.is_boss || false
  const isMiniboss = combatData?.initial_state?.is_miniboss || false
  const isSurvivalSwarm = combatData?.initial_state?.is_survival_swarm || false
  const turnLimit = combatData?.initial_state?.turn_limit || null

  // Solo enemies (elite mobs, minibosses, bosses) read as more threatening
  // rendered bigger than a regular swarm/pack unit. A true boss is sized to
  // dominate its entire side of the field. Swarms (6+) drop to a smaller,
  // grid-laid-out size instead — see getGridPosition/ENEMY_SIZE_TIERS.swarm*.
  // isSurvivalSwarm must be checked BEFORE isMiniboss — a Survival Swarm
  // floor is still mechanically flagged is_miniboss at the floor-type
  // level (it's a random alternative rolled *within* a miniboss floor,
  // see SWARM_SURVIVAL_CHANCE), but with 30-50 enemies on screen it must
  // never use the giant 320px miniboss circle size. Confirmed via a
  // direct DOM measurement that this was the actual cause of the dense
  // overlapping mass reported — not just "too many enemies", the count
  // tiers were never being reached at all.
  const enemyTier = isBoss ? 'boss' : isSurvivalSwarm ? (enemies.length > 12 ? 'swarmTiny' : 'swarm') : isMiniboss ? 'miniboss'
    : enemies.length === 1 ? 'elite'
    : enemies.length > 12 ? 'swarmTiny'
    : enemies.length > 5 ? 'swarm'
    : 'normal'
  const heroTier = heroes.length > 5 ? 'swarm' : 'normal'
  const soloEnemyPos = enemies.length === 1 ? ENEMY_SIZE_TIERS[enemyTier].pos : null

  // Hit-sound archetype, reusing the same power_stat/is_ranged fields combat
  // already tracks per-unit instead of a separate per-class sound table —
  // a caster's hits chime, a ranged attacker thwips, melee clangs, enemies
  // get one shared growl.
  function classifyAttacker(unitId) {
    const hero = heroes.find(h => h.id === unitId)
    if (!hero) return 'enemy'
    if (hero.power_stat === 'intelligence') return 'caster'
    if (hero.is_ranged) return 'ranged'
    return 'melee'
  }

  useEffect(() => {
    if (combatData) {
      // Initialize HPs/Manas
      const initialHps = {}
      const initialManas = {}
      heroes.forEach(h => { initialHps[h.id] = h.health; initialManas[h.id] = h.mana })
      enemies.forEach(e => initialHps[e.id] = e.health)

      // Time-skip resume: if the player left the Tower tab mid-fight and
      // came back, TowerPage computes how many turns "should have played"
      // from elapsed real time and hands it in here. Replay every turn up
      // to that point INSTANTLY (no per-turn delay) so HP/mana bars land
      // exactly where they'd be if the player had watched the whole thing,
      // then resume normal timed playback from there.
      const targetIndex = Math.min(initialTurnIndex, turns.length - 1)
      for (let i = 0; i <= targetIndex; i++) {
        const t = turns[i]
        if (t && t.target_id) {
          initialHps[t.target_id] = t.target_hp
          if (t.attacker_mana != null) initialManas[t.attacker_id] = t.attacker_mana
          if (t.target_mana != null) initialManas[t.target_id] = t.target_mana
        }
      }
      setUnitHPs(initialHps)
      setUnitManas(initialManas)
      setCurrentTurnIndex(targetIndex)
      setPlaying(true)
    }
  }, [combatData])

  useEffect(() => {
    if (!playing) return

    if (currentTurnIndex >= turns.length) {
      setPlaying(false)
      setTimeout(() => {
        if (onComplete) onComplete()
      }, 1500 / speedMult)
      return
    }

    if (currentTurnIndex >= 0) {
      const turn = turns[currentTurnIndex]
      if (turn && turn.target_id) {
        setUnitHPs(prev => ({
          ...prev,
          [turn.target_id]: turn.target_hp
        }))
        if (turn.attacker_mana != null || turn.target_mana != null) {
          setUnitManas(prev => ({
            ...prev,
            ...(turn.attacker_mana != null ? { [turn.attacker_id]: turn.attacker_mana } : {}),
            ...(turn.target_mana != null ? { [turn.target_id]: turn.target_mana } : {}),
          }))
        }
        playHitSound(classifyAttacker(turn.attacker_id), turn.is_crit)
      }
    }

    const timer = setTimeout(() => {
      setCurrentTurnIndex(c => c + 1)
    }, 800 / speedMult) // Delay between turns

    return () => clearTimeout(timer)
  }, [currentTurnIndex, playing, turns, onComplete, speedMult])

  const logEndRef = useRef(null)

  // Damage numbers stay on the sprites in the arena itself — this is a
  // separate running feed of the flavor text, building up turn by turn so
  // players can scroll back through what's happened instead of only ever
  // seeing the current turn's line before it's replaced by the next one.
  const revealedLines = []
  for (let i = 0; i <= currentTurnIndex && i < turns.length; i++) {
    revealedLines.push({ key: i, text: turnNarrations?.[i] || turns[i].log, event: turns[i].event })
  }

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ block: 'end' })
  }, [revealedLines.length])

  // The phase horn sounds the moment a PHASE event turn reveals in the replay.
  const hornAt = useRef(-1)
  useEffect(() => {
    const t = currentTurnIndex >= 0 && currentTurnIndex < turns.length ? turns[currentTurnIndex] : null
    if ((t?.event === 'phase' || t?.event === 'wall') && currentTurnIndex > hornAt.current) {
      hornAt.current = currentTurnIndex
      playPhaseHorn()
    }
  }, [currentTurnIndex])

  if (!combatData || combatData.awaiting_choice) return null

  const currentTurn = currentTurnIndex >= 0 && currentTurnIndex < turns.length ? turns[currentTurnIndex] : null

  return (
    <div className="ilm-combat" style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
    {/* combat context strip — floor/turn + ×1/×2/×4 speed */}
    <div className="ilm-combat-topbar">
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <span style={{ width: 9, height: 9, transform: 'rotate(45deg)', background: 'var(--gold)', display: 'inline-block' }} />
        <span style={{ fontFamily: "'Cinzel',serif", fontWeight: 700, letterSpacing: '.24em', fontSize: '0.82rem', color: 'var(--text-hi)' }}>THE FRAY</span>
        {currentTurn?.round != null && <span style={{ fontFamily: "'Cinzel',serif", letterSpacing: '.24em', fontSize: '0.66rem', color: 'var(--gold-hi)' }}>TURN {currentTurn.round}</span>}
      </div>
      <div className="ilm-combat-speed">
        {[1, 2, 4].map(n => (
          <button key={n} className={`ilm-combat-spd ${speedMult === n ? 'active' : ''}`} onClick={() => setSpeed(n)} title={`${n}× playback`}>×{n}</button>
        ))}
      </div>
    </div>
    <div className="ilm-combat-stage" style={environment ? {
      // Vignette instead of a flat dim: the zone art breathes at low opacity
      // mid-stage and falls to ink at the edges (the stage's ::before layer
      // adds the dot-scatter + outer vignette on top).
      backgroundImage: `radial-gradient(115% 95% at 50% 40%, rgba(8,6,14,.58), rgba(8,6,14,.93) 76%), url(${environment})`,
      backgroundSize: 'cover', backgroundPosition: 'center',
    } : undefined}>
      {isSurvivalSwarm && turnLimit && (
        <div className="ilm-combat-survive">SURVIVE · ROUND {Math.min(currentTurn?.round || 1, turnLimit)} / {turnLimit}</div>
      )}

      {/* ══ ALLY FORMATION (left) — a top-down battle layout: REAR GUARD
          column (3) on the outside, VANGUARD column (2) toward the enemies.
          Same shape as the team-setup screen so what you arranged is what
          you fight with. ══ */}
      <div className="ilm-rail left">
        {(() => {
          const renderAllyCard = (hero) => {
            const hp = unitHPs[hero.id] ?? hero.health
            const hpPct = Math.max(0, (hp / hero.max_health) * 100)
            const mp = unitManas[hero.id] ?? hero.mana
            const mpPct = hero.max_mana > 0 ? Math.max(0, (mp / hero.max_mana) * 100) : 0
            const isAtt = currentTurn?.attacker_id === hero.id
            const isTgt = currentTurn?.target_id === hero.id
            const dead = hp <= 0
            const critical = hpPct <= 15 && !dead
            return (
              <div key={hero.id} className={`ilm-combatcard ${isAtt ? 'act' : ''} ${isTgt ? 'hit' : ''} ${dead ? 'dead' : ''} ${critical ? 'low' : ''}`}>
                <span className="ilm-unitface ally" style={{ width: 46, height: 46 }}>
                  {hero.portrait_path
                    ? <img src={`/heroes/${hero.id}/card-image?mini=1`} alt="" draggable={false}
                        onError={e => { if (!e.currentTarget.dataset.fb) { e.currentTarget.dataset.fb = '1'; e.currentTarget.src = `/${hero.portrait_path}` } else { e.currentTarget.style.display = 'none' } }} />
                    : <span className="ilm-unitface-ph">✦</span>}
                </span>
                <div className="ilm-unitbars">
                  <div className="ilm-unitname" style={{ justifyContent: 'center', gap: 5 }}>
                    <span style={{ maxWidth: '100%' }}>{hero.name}</span>
                  </div>
                  <div style={{ textAlign: 'center', marginBottom: 3 }}>
                    <span className="ilm-unitclass" style={dead ? { color: 'var(--red-hi)' } : critical ? { color: 'var(--red-hi)', letterSpacing: '.2em' } : undefined}>
                      {dead ? 'FALLEN' : critical ? 'CRITICAL' : (hero.hero_class || '').toUpperCase()}
                    </span>
                  </div>
                  <div className="ilm-hpbar"><div style={{ width: `${hpPct}%` }} /></div>
                  {hero.max_mana > 0 && <div className="ilm-mpbar"><div style={{ width: `${mpPct}%` }} /></div>}
                  <StatusChips list={currentTurn?.statuses?.[hero.id]} />
                </div>
              </div>
            )
          }
          // Order the formation by team_position so it matches the team-setup
          // screen EXACTLY (that screen sorts by team_position too) — the
          // vanguard is always slots 0-1, rear guard 2+.
          const ordered = [...heroes].sort((a, b) => (a.team_position ?? 99) - (b.team_position ?? 99))
          const front = ordered.slice(0, 2)
          const back = ordered.slice(2)
          const head = (label, color) => (
            <div className="ilm-formhead">
              <span className="d" style={{ background: color }} />
              <span className="t" style={{ color }}>{label}</span>
              <span className="r" style={{ background: `${color}33` }} />
            </div>
          )
          return (
            <div className="ilm-formrow">
              <div className="ilm-formcol">
                {back.length > 0 && head('REAR GUARD', 'var(--lavender)')}
                {back.map(renderAllyCard)}
              </div>
              <div className="ilm-formcol">
                {front.length > 0 && head('VANGUARD', '#ffd88a')}
                <div style={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 9 }}>
                  {front.map(renderAllyCard)}
                </div>
              </div>
            </div>
          )
        })()}
      </div>

      {/* ══ ENEMY FORMATION (right) — mirrors the ally side: the FRONT LINE
          (enemies[:2], whom the party targets first) is a vanguard column
          toward the center; the rest fill the rear grid. Even a big swarm
          stays on one screen. ══ */}
      <div className="ilm-rail right">
        {(() => {
          const renderEnemyCard = (en, i, van) => {
            const hp = unitHPs[en.id] ?? en.health
            const hpPct = Math.max(0, (hp / en.max_health) * 100)
            const isAtt = currentTurn?.attacker_id === en.id
            const isTgt = currentTurn?.target_id === en.id
            const dead = hp <= 0
            const isBossCard = isBoss && i === 0
            const label = isBossCard ? 'BOSS' : (enemyTier === 'elite' || enemyTier === 'miniboss') && i === 0 ? 'ELITE' : ''
            return (
              <div key={en.id} className={`ilm-enemycard ${van ? 'van' : ''} ${isBossCard ? 'boss' : ''} ${isAtt ? 'act' : ''} ${isTgt ? 'hit' : ''} ${dead ? 'dead' : ''}`}>
                <span className="ilm-unitface enemy">
                  {en.portrait_path ? <img src={`/${en.portrait_path}`} alt="" draggable={false} onError={e => { e.target.style.display = 'none' }} /> : <span className="ilm-unitface-ph">☠</span>}
                </span>
                <span className="ec-name">{en.name}</span>
                {label && <span className="ec-label">{label}</span>}
                <div className="ilm-hpbar enemy"><div style={{ width: `${hpPct}%` }} /></div>
                <StatusChips list={currentTurn?.statuses?.[en.id]} />
              </div>
            )
          }
          const shown = enemies.slice(0, 16)
          const front = shown.slice(0, enemyFrontN)   // the party targets these first
          const back = shown.slice(enemyFrontN)
          const head = (label) => (
            <div className="ilm-formhead" style={{ justifyContent: 'flex-end' }}>
              <span className="r" style={{ background: 'rgba(192,64,64,.25)' }} />
              <span className="t" style={{ color: 'var(--red-hi)' }}>{label}</span>
              <span className="d" style={{ background: 'var(--red)' }} />
            </div>
          )
          return (
            <div className="ilm-enemyform">
              {/* vanguard toward the center (left of the enemy area), so the
                  two front lines face each other; the horde fills behind. */}
              <div className="ilm-enemyvan">
                {head('FRONT LINE')}
                {front.map((en, i) => renderEnemyCard(en, i, true))}
              </div>
              {back.length > 0 && (
                <div className="ilm-enemyrear">
                  {head('BACK LINE')}
                  <div className="ilm-enemygrid">
                    {back.map((en, i) => renderEnemyCard(en, i + 2, false))}
                    {enemies.length > 16 && <div className="ilm-rail-more">+{enemies.length - 16} more</div>}
                  </div>
                </div>
              )}
            </div>
          )
        })()}
      </div>

      {/* ══ SKILL CALLOUT SLASH ══ */}
      {currentTurn?.skill_name && (() => {
        const caster = heroes.find(h => h.id === currentTurn.attacker_id) || enemies.find(e => e.id === currentTurn.attacker_id)
        return (
          <div className="ilm-skillslash" key={`sk${currentTurnIndex}`}>
            <span className="ilm-skillslash-dia" />
            <span className="ilm-skillslash-name">{currentTurn.skill_name}</span>
            {caster && <span className="ilm-skillslash-by">{caster.name}{caster.hero_class ? ` · ${String(caster.hero_class).toUpperCase()}` : ''}</span>}
          </div>
        )
      })()}

      {/* ══ FLOATING DAMAGE ══ */}
      {currentTurn?.damage > 0 && currentTurn?.target_id != null && (
        <div key={`dmg${currentTurnIndex}`}
          className={`ilm-floatdmg ${currentTurn.is_crit ? 'crit' : ''}`}
          style={{ left: enemies.some(e => e.id === currentTurn.target_id) ? '66%' : '30%' }}>
          {Number(currentTurn.damage).toLocaleString()}{currentTurn.is_crit && <span className="ilm-floatdmg-tag">CRIT</span>}
        </div>
      )}
    </div>

    {/* ══ THE CHRONICLE (bottom) ══ */}
    <div className="ilm-chronicle horizontal">
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: '0.4rem', flexShrink: 0 }}>
        <span style={{ width: 7, height: 7, transform: 'rotate(45deg)', background: 'var(--gold)', display: 'inline-block' }} />
        <span style={{ fontFamily: "'Cinzel',serif", letterSpacing: '.3em', fontSize: '0.62rem', color: 'var(--gold)' }}>CHRONICLE</span>
        <span style={{ height: 1, flex: 1, background: 'rgba(184,151,98,.2)' }} />
      </div>
      <div className="ilm-chronicle-lines">
        {revealedLines.map(line => (
          line.event ? (
            // Typed EVENT beats — full-width banners so a boss phase or floor
            // condition never reads with the same weight as a basic hit.
            <div key={line.key} style={{
              margin: '4px 0', padding: '5px 12px', textAlign: 'center',
              fontFamily: "'Cinzel',serif", fontWeight: 700, letterSpacing: '.16em', fontSize: '0.72rem',
              color: line.event === 'condition' ? 'var(--lavender)' : 'var(--gold-hi)',
              background: line.event === 'condition'
                ? 'linear-gradient(90deg, transparent, rgba(150,110,230,.16), transparent)'
                : 'linear-gradient(90deg, transparent, rgba(216,187,132,.18), transparent)',
              borderTop: `1px solid ${line.event === 'condition' ? 'rgba(150,110,230,.4)' : 'rgba(216,187,132,.45)'}`,
              borderBottom: `1px solid ${line.event === 'condition' ? 'rgba(150,110,230,.4)' : 'rgba(216,187,132,.45)'}`,
            }}>
              {line.text.toUpperCase()}
            </div>
          ) : (
            <div key={line.key} className="ilm-chronicle-line">{line.text}</div>
          )
        ))}
        <div ref={logEndRef} />
      </div>
    </div>

    <style>{`
      @keyframes skillRingPulse { 0%{transform:scale(1)}50%{transform:scale(1.12)}100%{transform:scale(1)} }
      @keyframes logLineIn { from { opacity:0; transform: translateY(6px) } to { opacity:1; transform: translateY(0) } }
      @keyframes ilm-dmg-rise { 0%{transform:translate(-50%,10px) scale(.7);opacity:0} 18%{opacity:1;transform:translate(-50%,-6px) scale(1.15)} 100%{transform:translate(-50%,-42px) scale(1);opacity:0} }
      @keyframes ilm-slash-in { 0%{opacity:0;transform:rotate(-2.5deg) translateX(-140px);filter:blur(8px)} 55%{opacity:1;transform:rotate(-2.5deg) translateX(8px);filter:blur(0)} 100%{opacity:1;transform:rotate(-2.5deg) translateX(0)} }
    `}</style>
    </div>
  )
}
