/*
 * HERO DETAIL — the Illuminated three-column dossier (mockup
 * "Infirmary - Illuminated.dc.html"). Left: identity + full-body portrait.
 * Middle: vitals, core stats, state of mind, aptitudes. Right: skills,
 * equipment, career, actions. Bottom: chronicle. Collapsible sections
 * mirror the mockup's chevrons. Data-only component — mutations arrive
 * through props from HeroesPage (equipment modal, gift, ascend cluster).
 */
import React, { useState, useEffect } from 'react'
import Sigil from './Sigil'
import { classSigil, classFamily } from '../classSigils'
import GameIcon from './GameIcon'
import { toggleFavorite, regenerateProfile, getHeroDeeds } from '../api/client'
import Tip, { TIPS } from './Tip'
import { emitToast } from '../toastBus'

const RARITY_COLORS = { F: '#8a8a96', E: '#8a8a96', D: '#9fb59f', C: '#8fbf9f', B: '#7fb2d9', 'B+': '#7fb2d9', A: '#c8a9f5', S: '#ffd88a', SS: '#ffb35c', SSS: '#7ecfd8' }
const SLOT_ORDER = ['Weapon', 'Armor', 'Ring', 'Accessory']
const APTS = ['Combat', 'Tactical', 'Survival', 'Mental', 'Leadership', 'Diligence']
const ROMAN = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X', 'XI', 'XII']
const STAR_ACCENT = { 1: '#9aa0ad', 2: '#8fbf9f', 3: '#1e90ff', 4: '#b84dff', 5: '#ffb300', 6: '#ff3333', 7: '#e0aaff' }

function rarityColor(r) {
  return RARITY_COLORS[r] || RARITY_COLORS[(r || '').replace(/[+-]$/, '')] || 'var(--muted)'
}

function StarRow({ count }) {
  if (count >= 7) return <span className="rainbow-text" style={{ fontSize: 13, letterSpacing: '.14em' }}>★★★★★★★</span>
  const accent = STAR_ACCENT[count] || '#9aa0ad'
  return (
    <span style={{ fontSize: 13, letterSpacing: '.14em' }}>
      <span style={{ color: accent, textShadow: `0 0 6px ${accent}99` }}>{'★'.repeat(count)}</span>
      <span style={{ color: '#453c5c' }}>{'★'.repeat(Math.max(0, 7 - count))}</span>
    </span>
  )
}

// Section header per spec — diamond bullet, letterspaced label, hairline, chevron.
// When onToggle is omitted the section is fixed-open — no chevron, no pointer
// (used for CORE STATS, which the user wants always visible).
function SectionHead({ label, right, open, onToggle, violet }) {
  const c = violet ? 'var(--lavender)' : 'var(--gold)'
  return (
    <div onClick={onToggle} style={{ cursor: onToggle ? 'pointer' : 'default', display: 'flex', alignItems: 'center', gap: 10 }}>
      <span style={{ width: 7, height: 7, transform: 'rotate(45deg)', background: violet ? 'var(--violet)' : 'var(--gold)', display: 'inline-block', flex: 'none' }} />
      <span style={{ fontFamily: "'Cinzel',serif", letterSpacing: '.28em', fontSize: 10, color: c }}>{label}</span>
      <span style={{ height: 1, flex: 1, background: violet ? 'rgba(150,110,230,.25)' : 'rgba(184,151,98,.2)' }} />
      {right}
      {onToggle && <span style={{ fontSize: 11, color: c, width: 12, textAlign: 'center' }}>{open ? '▾' : '▸'}</span>}
    </div>
  )
}

export default function HeroDetail({ hero, onManageEquipment, onManageConsumable, onAutoEquip, onGift, onPrev, onNext, actions, onChanged }) {
  // Anti-overload: the dossier is TABBED (STATS / SKILLS & GEAR / INSIGHT),
  // opening on STATS so HP/MANA + the six CORE STATS are what you see first.
  // Sections within a tab stay expanded (the chevron is a bonus, not the main
  // mechanism) so no tab ever reads as empty.
  const [tab, setTab] = useState('stats')
  const [open, setOpen] = useState({ mind: true, apt: true, skills: true, gear: true })
  const [fullChronicle, setFullChronicle] = useState(false)
  // Deeds — permanent accomplishment records mined from real fights.
  const [deeds, setDeeds] = useState([])
  useEffect(() => {
    let live = true
    if (hero?.id) getHeroDeeds(hero.id).then(d => { if (live) setDeeds(d || []) }).catch(() => {})
    return () => { live = false }
  }, [hero?.id])
  const [fav, setFav] = useState(!!hero?.is_favorite)
  const [regenning, setRegenning] = useState(false)
  const toggle = k => setOpen(o => ({ ...o, [k]: !o[k] }))

  if (!hero) return null
  const dead = !hero.is_alive
  const star = hero.current_star || hero.birth_star || 1
  const skills = (() => { try { return JSON.parse(hero.skills || '[]') } catch { return [] } })()
  const traits = (() => { try { return JSON.parse(hero.traits || '[]') } catch { return [] } })()
  const equipment = hero.equipment || []
  const heroSigil = classSigil(hero.hero_class)
  const revealedApts = APTS.filter(a => hero[`apt_${a.toLowerCase()}`] != null)
  const pronouns = hero.gender === 'male' ? 'he/him' : hero.gender === 'female' ? 'she/her' : 'they/them'
  const portraitSrc = hero.portrait_path && !hero.portrait_path.includes('default_')
    ? `/${hero.portrait_path}` : `/heroes/${hero.id}/card-image?mini=false`
  const backstory = hero.backstory || ''
  const loyalty = hero.affinity ?? 0
  const xpMax = Math.max(1, (hero.level || 1) * 100)
  const moraleState = (hero.morale_state || 'steady').toUpperCase()
  const moraleBad = /FEARFUL|BROKEN/.test(moraleState)

  async function heartClick() {
    setFav(f => !f)
    try { await toggleFavorite(hero.id); onChanged?.() } catch { setFav(f => !f) }
  }

  const panelStyle = {
    border: '1px solid rgba(184,151,98,.35)', background: 'rgba(12,7,24,.5)', padding: '14px 16px',
    clipPath: 'polygon(0 0,100% 0,100% 100%,10px 100%)', marginBottom: 14,
  }

  return (
    <div>
      {/* breadcrumb row */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 12, fontFamily: "'Cinzel',serif", letterSpacing: '.24em', fontSize: 12 }}>
        <span style={{ color: 'var(--muted)' }}>HEROES</span>
        <span style={{ color: '#6f628c' }}>/</span>
        <span style={{ color: 'var(--text-hi)', fontWeight: 700 }}>{hero.name?.toUpperCase()}</span>
        <span style={{ flex: 1 }} />
        {onPrev && <button onClick={onPrev} style={{ background: 'none', border: 'none', cursor: 'pointer', fontFamily: "'Cinzel',serif", letterSpacing: '.2em', fontSize: 11, color: 'var(--muted)' }}>‹ PREV HERO</button>}
        {onNext && <button onClick={onNext} style={{ background: 'none', border: 'none', cursor: 'pointer', fontFamily: "'Cinzel',serif", letterSpacing: '.2em', fontSize: 11, color: 'var(--muted)', marginRight: 46 }}>NEXT HERO ›</button>}
      </div>

      <div style={{ display: 'flex', gap: 22, flexWrap: 'wrap', alignItems: 'flex-start' }}>
        {/* ══ LEFT: identity + portrait ══ */}
        <div style={{ flex: '1 1 300px', minWidth: 0, maxWidth: 380 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <span style={{ fontFamily: "'Cinzel',serif", fontWeight: 900, fontSize: (hero.name || '').length > 13 ? 30 : (hero.name || '').length > 10 ? 34 : 40, lineHeight: 1, color: 'var(--text-hi)', textShadow: '0 4px 30px rgba(124,58,214,.5)', wordBreak: 'break-word', minWidth: 0 }}>
              {hero.name?.toUpperCase()}
            </span>
            {!!hero.is_team_leader && (
              <span title="Team Leader" style={{ width: 24, height: 24, transform: 'rotate(45deg)', background: 'linear-gradient(135deg,#c8a9f5,#8b46d6)', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', flex: 'none', boxShadow: '0 0 10px rgba(139,70,214,.5)' }}>
                <span style={{ transform: 'rotate(-45deg)', fontFamily: "'Cinzel',serif", fontWeight: 900, fontSize: 12, color: '#0a0710' }}>♛</span>
              </span>
            )}
            <span style={{ flex: 1 }} />
            <button onClick={heartClick} title={fav ? 'Unfavorite' : 'Favorite'}
              style={{ background: 'none', border: 'none', cursor: 'pointer', flex: 'none', lineHeight: 0, filter: fav ? 'drop-shadow(0 0 8px rgba(232,98,138,.8))' : 'none', transition: 'filter .2s' }}>
              <svg width="25" height="25" viewBox="0 0 24 24" fill={fav ? '#e8628a' : 'none'} stroke="#e8628a" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 20.5 C12 20.5 4.5 14.3 4.5 9 C4.5 6.6 6.4 5 8.4 5 C10.1 5 11.4 6.1 12 7.2 C12.6 6.1 13.9 5 15.6 5 C17.6 5 19.5 6.6 19.5 9 C19.5 14.3 12 20.5 12 20.5 Z" />
              </svg>
            </button>
          </div>
          <div style={{ fontSize: 16, fontStyle: 'italic', color: 'var(--muted)', marginTop: 3 }}>
            {hero.title ? `"${hero.title}"` : 'Unnamed'} · {pronouns}{!!hero.is_team_leader && ' · Team Leader'}
            {dead && <span style={{ color: '#d98a8a' }}> · FALLEN</span>}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 6 }}>
            <StarRow count={star} />
            {(hero.ascension_star || 0) > 0 && (
              <span style={{ fontFamily: "'Cinzel',serif", fontSize: 10, letterSpacing: '.18em', color: 'var(--gold-hi)' }}>ASC {'✦'.repeat(hero.ascension_star)}</span>
            )}
          </div>

          {/* class row */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 6, flexWrap: 'wrap' }}>
            <span style={{ width: 22, height: 22, transform: 'rotate(45deg)', flex: 'none', border: '1px solid rgba(181,123,239,.5)', background: 'linear-gradient(135deg,#1c1030,#0e0918)', display: 'flex', alignItems: 'center', justifyContent: 'center' }} title={`${hero.hero_class} sigil`}>
              <Sigil set={heroSigil.set} name={heroSigil.name} size={14} color="var(--violet)" style={{ transform: 'rotate(-45deg)' }}
                fallback={<Sigil set="class-base" name="CLASSLESS" size={14} color="var(--violet)" style={{ transform: 'rotate(-45deg)' }} />} />
            </span>
            <span style={{ fontFamily: "'Cinzel',serif", letterSpacing: '.28em', fontSize: 12, color: 'var(--violet)' }}>{(hero.hero_class || 'CLASSLESS').toUpperCase()}</span>
            <span style={{ fontFamily: "'Cinzel',serif", letterSpacing: '.16em', fontSize: 10, color: '#7c6f92' }}>
              {hero.hidden_class ? 'EVOLUTION · HIDDEN — ?' : `${(familyLabel(hero.hero_class) || '').toUpperCase()}`}
            </span>
            {hero.ego_type && hero.ego_type.toLowerCase() !== 'null' && (
              <span style={{ fontFamily: "'Cinzel',serif", letterSpacing: '.16em', fontSize: 10, color: '#e8a34c' }} title={`Patience ${hero.ego_patience ?? 100}/100`}>
                EGO · {hero.ego_type.toUpperCase()}
              </span>
            )}
          </div>

          {/* loyalty: front and center */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 12 }}>
            <span title="Loyalty — an oath of allegiance" style={{ width: 26, height: 26, transform: 'rotate(45deg)', flex: 'none', border: '1px solid rgba(216,187,132,.55)', background: 'linear-gradient(135deg,#241a10,#120d08)', display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 0 12px rgba(184,151,98,.3)' }}>
              <svg width="14" height="14" viewBox="0 0 24 24" style={{ transform: 'rotate(-45deg)' }} fill="none" stroke="#d8bb84" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 3 L19 6 L19 12 C19 16.5 16 19.5 12 21 C8 19.5 5 16.5 5 12 L5 6 Z" /><path d="M9.2 11.5 L11 13.3 L15 9" />
              </svg>
            </span>
            <span style={{ fontFamily: "'Cinzel',serif", letterSpacing: '.26em', fontSize: 10, color: 'var(--gold-hi)' }}>LOYALTY</span>
            <div style={{ flex: 1, height: 6, background: 'rgba(0,0,0,.5)', border: '1px solid rgba(184,151,98,.45)' }}>
              <div style={{ width: `${Math.min(100, loyalty)}%`, height: '100%', background: 'linear-gradient(90deg,#8b46d6,#d8bb84)', boxShadow: '0 0 8px rgba(184,151,98,.4)' }} />
            </div>
            <span style={{ fontFamily: "'Cormorant Garamond',serif", fontWeight: 700, fontSize: 17, color: 'var(--gold-hi)' }}>{loyalty}<span style={{ fontSize: 12, color: 'var(--muted)' }}>/100</span></span>
          </div>

          {/* level + xp */}
          <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginTop: 12 }}>
            <span style={{ fontFamily: "'Cinzel',serif", letterSpacing: '.28em', fontSize: 11, color: 'var(--gold)' }}>LEVEL {hero.level || 1}</span>
            <span style={{ fontFamily: "'Cinzel',serif", fontSize: 10, letterSpacing: '.14em', color: 'var(--muted)' }}>{(hero.xp ?? 0).toLocaleString()} / {xpMax.toLocaleString()} XP</span>
          </div>
          <div style={{ height: 5, background: 'rgba(124,58,214,.15)', border: '1px solid rgba(184,151,98,.3)', marginTop: 5 }}>
            <div style={{ width: `${Math.min(100, ((hero.xp ?? 0) / xpMax) * 100)}%`, height: '100%', background: 'linear-gradient(90deg,#8b46d6,#d8bb84)' }} />
          </div>

          {/* portrait — the dossier's visual anchor: taller frame, stronger
              bloom, corner ticks. Fills the left column like the landing
              page's hero cutout rather than sitting as a thumbnail. */}
          <div style={{ position: 'relative', marginTop: 12, minHeight: 300 }}>
            <div style={{ position: 'absolute', inset: -10, background: 'radial-gradient(62% 55% at 50% 38%, rgba(140,70,214,.42), rgba(140,70,214,.12) 55%, rgba(0,0,0,0) 74%)', animation: 'toe-glow 6s ease-in-out infinite' }} />
            <span className="ilm-corner" />
            <span className="ilm-corner ilm-corner-r" />
            <span className="ilm-corner ilm-corner-bl" />
            <span className="ilm-corner ilm-corner-br" />
            <img src={portraitSrc} alt={hero.name} style={{ position: 'relative', width: '100%', maxHeight: 430, objectFit: 'contain', filter: dead ? 'grayscale(1) brightness(.6)' : 'none' }} />
            <div style={{ position: 'absolute', left: 0, right: 0, bottom: 0, height: 90, pointerEvents: 'none', background: 'linear-gradient(rgba(8,6,14,0),#08060e)' }} />
          </div>
          {!dead && (
            <button disabled={regenning}
              onClick={async () => {
                setRegenning(true)
                try { await regenerateProfile(hero.id); emitToast('The Mirror repaints them — a new portrait is being drawn.', 'success'); onChanged?.() }
                catch (e) { emitToast(e.message, 'error') } finally { setRegenning(false) }
              }}
              style={{ width: '100%', marginTop: 6, background: 'none', border: '1px dashed rgba(150,110,230,.35)', cursor: 'pointer', fontFamily: "'Cinzel',serif", fontSize: 9, letterSpacing: '.2em', color: 'var(--muted)', padding: '6px 0' }}>
              {regenning ? 'REPAINTING…' : 'REGENERATE PORTRAIT'}
            </button>
          )}
        </div>

        {/* ══ RIGHT: tabbed dossier — opens on STATS (HP/MANA + the six), with
            SKILLS & GEAR and INSIGHT one click away, so it never reads as a
            wall of data. The portrait/identity column on the left is constant. ══ */}
        <div style={{ flex: '1.5 1 380px', minWidth: 0, display: 'flex', flexDirection: 'column' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 26, borderBottom: '1px solid rgba(184,151,98,.22)', marginBottom: 18 }}>
            {[['stats', 'STATS'], ['gear', 'SKILLS & GEAR'], ['insight', 'INSIGHT']].map(([id, label]) => (
              <button key={id} onClick={() => setTab(id)}
                style={{ background: 'none', border: 'none', cursor: 'pointer', fontFamily: "'Cinzel',serif", letterSpacing: '.22em', fontSize: 11.5, fontWeight: tab === id ? 700 : 500, color: tab === id ? 'var(--text-hi)' : 'var(--muted)', borderBottom: tab === id ? '2px solid var(--gold)' : '2px solid transparent', padding: '0 0 9px' }}>
                {label}
              </button>
            ))}
          </div>

          {/* ── STATS ── */}
          {tab === 'stats' && (<div>
          {/* vitals side by side */}
          <div style={{ display: 'flex', gap: 16, marginBottom: 16 }}>
            <div style={{ flex: 1 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 4 }}>
                <span style={{ fontFamily: "'Cinzel',serif", letterSpacing: '.22em', fontSize: 9, color: 'var(--muted)' }}>HEALTH</span>
                <span style={{ fontFamily: "'Cormorant Garamond',serif", fontWeight: 700, fontSize: 16, color: 'var(--text-hi)' }}>{(hero.health ?? 0).toLocaleString()} / {(hero.max_health ?? 0).toLocaleString()}</span>
              </div>
              <div style={{ height: 6, background: 'rgba(0,0,0,.5)', border: '1px solid rgba(192,64,64,.4)' }}>
                <div style={{ width: `${hero.max_health ? Math.min(100, (hero.health / hero.max_health) * 100) : 0}%`, height: '100%', background: 'linear-gradient(90deg,#7a3030,#c04040)' }} />
              </div>
            </div>
            {hero.max_mana != null && (
              <div style={{ flex: 1 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 4 }}>
                  <span style={{ fontFamily: "'Cinzel',serif", letterSpacing: '.22em', fontSize: 9, color: 'var(--muted)' }}>MANA</span>
                  <span style={{ fontFamily: "'Cormorant Garamond',serif", fontWeight: 700, fontSize: 16, color: '#8fb8ff' }}>{(hero.mana ?? hero.max_mana).toLocaleString()} / {hero.max_mana.toLocaleString()}</span>
                </div>
                <div style={{ height: 6, background: 'rgba(0,0,0,.5)', border: '1px solid rgba(74,122,170,.4)' }}>
                  <div style={{ width: `${Math.min(100, ((hero.mana ?? hero.max_mana) / hero.max_mana) * 100)}%`, height: '100%', background: '#3a7bd5' }} />
                </div>
              </div>
            )}
          </div>

          {/* the seven */}
          <div style={panelStyle}>
            <SectionHead label="CORE STATS"
              right={<span style={{ fontFamily: "'Cinzel',serif", fontSize: 9, letterSpacing: '.14em', color: 'var(--lavender)' }}>POWER · {powerStat(hero)}</span>} />
            {(
              <div style={{ marginTop: 10 }}>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: '10px 12px' }}>
                  {[['STR', hero.strength, TIPS.strength], ['INT', hero.intelligence, TIPS.intelligence], ['AGI', hero.agility, TIPS.agility], ['END', hero.endurance, TIPS.endurance], ['WIL', hero.willpower, TIPS.willpower], ['LCK', hero.luck, TIPS.luck, 'var(--gold-hi)']].map(([k, v, tip, c]) => (
                    <div key={k}>
                      <Tip text={tip}>
                        <div style={{ fontFamily: "'Cinzel',serif", letterSpacing: '.24em', fontSize: 9, color: k === powerStat(hero) ? 'var(--gold-hi)' : 'var(--muted)' }}>{k}</div>
                      </Tip>
                      <div style={{ fontFamily: "'Cormorant Garamond',serif", fontWeight: 700, fontSize: 22, color: c || 'var(--text-hi)', lineHeight: 1.1 }}>{Math.round(v ?? 0)}</div>
                    </div>
                  ))}
                </div>
                <div style={{ display: 'flex', gap: 7, marginTop: 12, flexWrap: 'wrap' }}>
                  {/* DEF removed — 'defense' is a legacy/inert stat; endurance
                      replaced it (mitigation + drives max_health), so it reads
                      as out of place next to the six real attributes. */}
                  {!!hero.crit_chance && <span style={{ fontFamily: "'Cinzel',serif", fontSize: 9, letterSpacing: '.12em', color: '#c9bfa8', border: '1px solid rgba(184,151,98,.35)', padding: '2px 8px' }}>CRIT {Math.round(hero.crit_chance * 100)}%</span>}
                  {!!hero.dodge_chance && <span style={{ fontFamily: "'Cinzel',serif", fontSize: 9, letterSpacing: '.12em', color: '#c9bfa8', border: '1px solid rgba(184,151,98,.35)', padding: '2px 8px' }}>DODGE {Math.round(hero.dodge_chance * 100)}%</span>}
                  {!!hero.dmg_reduction_pct && <span style={{ fontFamily: "'Cinzel',serif", fontSize: 9, letterSpacing: '.12em', color: '#c9bfa8', border: '1px solid rgba(184,151,98,.35)', padding: '2px 8px' }}>DR {Math.round(hero.dmg_reduction_pct * 100)}%</span>}
                  {hero.can_pilot === 1 && <span style={{ fontFamily: "'Cinzel',serif", fontSize: 9, letterSpacing: '.12em', color: '#c8a9f5', border: '1px solid rgba(150,110,230,.4)', padding: '2px 8px' }}>PILOT</span>}
                </div>
              </div>
            )}
          </div>
          </div>)}

          {/* ── INSIGHT ── */}
          {tab === 'insight' && (<div>
          {/* psyche */}
          <div style={panelStyle}>
            <SectionHead label="STATE OF MIND" open={open.mind} onToggle={() => toggle('mind')}
              right={<span style={{ fontFamily: "'Cinzel',serif", fontSize: 9, letterSpacing: '.2em', color: moraleBad ? '#e08585' : '#8fbf9f', border: `1px solid ${moraleBad ? 'rgba(192,64,64,.45)' : 'rgba(74,154,106,.45)'}`, padding: '2px 8px' }}>{moraleState}</span>} />
            {open.mind && (
              <div style={{ marginTop: 10 }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {[['MORALE', hero.morale ?? 100, '#4a9a6a', 'rgba(74,154,106,.35)', '#8fbf9f', TIPS.morale], ['STRESS', hero.stress ?? 0, '#c9a84c', 'rgba(184,151,98,.3)', '#d8bb84', TIPS.stress], ['TRAUMA', hero.trauma ?? 0, '#c04040', 'rgba(192,64,64,.3)', '#d98a8a', TIPS.trauma]].map(([k, v, bar, border, valc, tip]) => (
                    <div key={k} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <Tip text={tip}><span style={{ fontFamily: "'Cinzel',serif", letterSpacing: '.2em', fontSize: 9, color: 'var(--muted)', width: 52, display: 'inline-block' }}>{k}</span></Tip>
                      <div style={{ flex: 1, height: 4, background: 'rgba(0,0,0,.5)', border: `1px solid ${border}` }}>
                        <div style={{ width: `${Math.min(100, v)}%`, height: '100%', background: bar }} />
                      </div>
                      <span style={{ fontFamily: "'Cormorant Garamond',serif", fontWeight: 700, fontSize: 15, color: valc, width: 30, textAlign: 'right' }}>{v}</span>
                    </div>
                  ))}
                </div>
                <div style={{ display: 'flex', gap: 7, marginTop: 11, flexWrap: 'wrap' }}>
                  <Tip text={TIPS.fatigue}><span style={{ fontFamily: "'Cinzel',serif", fontSize: 9, letterSpacing: '.14em', color: 'var(--gold-hi)', border: '1px solid rgba(184,151,98,.4)', padding: '2px 8px' }}>FATIGUE {hero.fatigue ?? 0}/10</span></Tip>
                  {hero.condition && <span style={{ fontFamily: "'Cinzel',serif", fontSize: 9, letterSpacing: '.14em', color: '#c9bfa8', border: '1px solid rgba(184,151,98,.35)', padding: '2px 8px' }}>{hero.condition.toUpperCase()}</span>}
                  {traits.map(t => (
                    <span key={t.id || t.name} title={t.desc} style={{ fontFamily: "'Cinzel',serif", fontSize: 9, letterSpacing: '.14em', color: '#c8a9f5', border: '1px solid rgba(150,110,230,.4)', padding: '2px 8px', cursor: 'help' }}>{(t.name || '').toUpperCase()}</span>
                  ))}
                  {hero.battle_tendency && <span style={{ fontFamily: "'Cinzel',serif", fontSize: 9, letterSpacing: '.14em', color: 'var(--muted)', border: '1px dashed rgba(150,110,230,.3)', padding: '2px 8px' }}>{hero.battle_tendency.toUpperCase()}</span>}
                </div>
              </div>
            )}
          </div>

          {/* aptitudes: hidden until the Mirror of Fate */}
          <div style={{ marginTop: 14 }}>
            <SectionHead violet label="APTITUDES" open={open.apt} onToggle={() => toggle('apt')}
              right={<span style={{ fontFamily: "'Cinzel',serif", fontSize: 9, letterSpacing: '.16em', color: 'var(--muted)' }}>{revealedApts.length} OF 6 REVEALED</span>} />
            {open.apt && (
              <div style={{ display: 'flex', gap: 12, marginTop: 12, flexWrap: 'wrap' }}>
                {APTS.map(a => {
                  const v = hero[`apt_${a.toLowerCase()}`]
                  return (
                    <div key={a} style={{ textAlign: 'center' }}>
                      {v != null ? (
                        <div style={{ width: 38, height: 38, transform: 'rotate(45deg)', border: '1px solid #d8bb84', background: 'linear-gradient(135deg,#2a1650,#140b22)', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto', boxShadow: '0 0 10px rgba(184,151,98,.3)' }}>
                          <span style={{ transform: 'rotate(-45deg)', fontFamily: "'Cormorant Garamond',serif", fontWeight: 700, fontSize: 15, color: 'var(--text-hi)' }}>{v}</span>
                        </div>
                      ) : (
                        <div style={{ width: 38, height: 38, transform: 'rotate(45deg)', border: '1px dashed rgba(150,110,230,.5)', background: 'rgba(12,7,24,.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto' }}>
                          <span style={{ transform: 'rotate(-45deg)', fontFamily: "'Cinzel',serif", fontSize: 13, color: 'var(--lavender)' }}>?</span>
                        </div>
                      )}
                      <Tip text={TIPS[`apt_${a.toLowerCase()}`]} width={240}>
                        <div style={{ fontFamily: "'Cinzel',serif", fontSize: 8, letterSpacing: '.14em', color: v != null ? 'var(--gold-hi)' : 'var(--muted)', marginTop: 9 }}>{a.toUpperCase()}</div>
                      </Tip>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
          </div>)}

          {/* ── SKILLS & GEAR ── */}
          {tab === 'gear' && (<div>
          {/* skills */}
          <SectionHead label="SKILLS" open={open.skills} onToggle={() => toggle('skills')}
            right={<span style={{ fontFamily: "'Cinzel',serif", fontSize: 9, letterSpacing: '.16em', color: 'var(--muted)' }}>{skills.length} KNOWN</span>} />
          {open.skills && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 7, marginTop: 10, maxHeight: 250, overflowY: 'auto' }}>
              {skills.length === 0 && <div style={{ fontStyle: 'italic', color: 'var(--muted)', fontSize: 13 }}>No skills learned.</div>}
              {skills.map((s, i) => {
                const active = s.type === 'active'
                const featured = s.rarity === 'epic' || s.rarity === 'legendary'
                return (
                  <div key={i} title={s.desc} style={{
                    display: 'flex', alignItems: 'center', gap: 12, padding: '8px 12px',
                    border: featured ? '1px solid rgba(150,110,230,.45)' : '1px solid rgba(184,151,98,.3)',
                    background: featured ? 'linear-gradient(90deg,rgba(124,58,214,.16),rgba(12,7,24,.5))' : 'rgba(12,7,24,.5)',
                  }}>
                    <span style={{ fontFamily: "'Cinzel',serif", fontSize: 10, color: featured ? '#c8a9f5' : 'var(--gold-hi)', width: 16, flex: 'none' }}>{ROMAN[i] || i + 1}</span>
                    <span style={{ fontFamily: "'Cinzel',serif", fontWeight: 700, fontSize: 12, letterSpacing: '.08em', color: 'var(--text-hi)', flex: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{(s.name || '').toUpperCase()}</span>
                    <span style={{ fontFamily: "'Cinzel',serif", fontSize: 8, letterSpacing: '.16em', color: active ? '#8fb8ff' : '#8fbf9f', flex: 'none' }}>
                      {active ? `${s.effect?.mana_cost ?? 25} MP` : 'PASSIVE'}
                    </span>
                  </div>
                )
              })}
            </div>
          )}

          {/* equipment */}
          <div style={{ margin: '16px 0 10px' }}>
            <SectionHead label="EQUIPMENT" open={open.gear} onToggle={() => toggle('gear')}
              right={<span style={{ fontFamily: "'Cinzel',serif", fontSize: 9, letterSpacing: '.16em', color: 'var(--muted)' }}>{equipment.length}/4</span>} />
          </div>
          {open.gear && (
            <>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                {SLOT_ORDER.map(slot => {
                  const eq = equipment.find(e => e.type === slot || (slot === 'Armor' && /armor/i.test(e.type || '')))
                  if (!eq) {
                    return (
                      <button key={slot} onClick={() => onManageEquipment?.(hero, slot.toLowerCase(), null)} disabled={dead}
                        style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', border: '1px dashed rgba(150,110,230,.35)', background: 'rgba(12,7,24,.3)', padding: '8px 10px', cursor: dead ? 'default' : 'pointer', minHeight: 48 }}>
                        <span style={{ fontFamily: "'Cinzel',serif", fontSize: 9, letterSpacing: '.2em', color: 'var(--muted)' }}>{slot.toUpperCase()} —</span>
                      </button>
                    )
                  }
                  const c = rarityColor(eq.rarity)
                  return (
                    <button key={slot} onClick={() => onManageEquipment?.(hero, slot.toLowerCase(), eq)} disabled={dead} title={eq.name}
                      style={{ display: 'flex', alignItems: 'center', gap: 10, border: `1px solid ${c}73`, background: 'rgba(12,7,24,.4)', padding: '8px 10px', cursor: dead ? 'default' : 'pointer', textAlign: 'left', minHeight: 48 }}>
                      <span style={{ width: 30, height: 30, border: `1px solid ${c}80`, background: 'repeating-linear-gradient(135deg,#150d20 0 5px,#100a18 5px 10px)', flex: 'none' }} />
                      <span style={{ minWidth: 0 }}>
                        <span style={{ display: 'block', fontFamily: "'Cinzel',serif", fontWeight: 700, fontSize: 11, letterSpacing: '.06em', color: 'var(--text-hi)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{eq.name?.toUpperCase()}</span>
                        <span style={{ display: 'block', fontFamily: "'Cinzel',serif", fontSize: 8, letterSpacing: '.14em', color: c }}>{eq.rarity} · {slot.toUpperCase()}</span>
                      </span>
                    </button>
                  )
                })}
              </div>
              <div style={{ display: 'flex', gap: 6, marginTop: 8 }}>
                {onAutoEquip && !dead && (
                  <>
                    <button onClick={() => onAutoEquip(hero, 'auto')} style={{ flex: 1, background: 'none', border: '1px solid rgba(184,151,98,.35)', cursor: 'pointer', fontFamily: "'Cinzel',serif", fontSize: 8, letterSpacing: '.16em', color: '#c9bfa8', padding: '5px 4px' }}>AUTO-EQUIP</button>
                    <button onClick={() => onAutoEquip(hero, 'unequip')} style={{ flex: 1, background: 'none', border: '1px solid rgba(184,151,98,.35)', cursor: 'pointer', fontFamily: "'Cinzel',serif", fontSize: 8, letterSpacing: '.16em', color: '#c9bfa8', padding: '5px 4px' }}>UNEQUIP ALL</button>
                  </>
                )}
                {onManageConsumable && !dead && (
                  <button onClick={() => onManageConsumable(hero)} style={{ flex: 1, background: 'none', border: '1px solid rgba(184,151,98,.35)', cursor: 'pointer', fontFamily: "'Cinzel',serif", fontSize: 8, letterSpacing: '.16em', color: hero.equipped_consumable ? 'var(--gold-hi)' : '#c9bfa8', padding: '5px 4px' }}>
                    {hero.equipped_consumable ? 'CONSUMABLE ◆' : 'CONSUMABLE'}
                  </button>
                )}
              </div>
            </>
          )}

          {/* career */}
          <div style={{ marginTop: 14 }}>
            <div style={{ display: 'flex', gap: 20, fontFamily: "'Cinzel',serif", fontSize: 10, letterSpacing: '.16em', color: 'var(--muted)' }}>
              <span>KILLS <span style={{ color: 'var(--text-hi)' }}>{hero.lifetime_kills ?? hero.kills ?? 0}</span></span>
              <span>FLOORS <span style={{ color: 'var(--text-hi)' }}>{hero.floors_survived ?? 0}</span></span>
              <span>MISSIONS <span style={{ color: 'var(--text-hi)' }}>{hero.missions_completed ?? 0}</span></span>
            </div>
          </div>
          </div>)}

          {/* footer — actions stay reachable on every tab */}
          {!dead && onGift && (
            <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
              <button onClick={() => onGift(hero)}
                style={{ flex: 1, textAlign: 'center', cursor: 'pointer', fontFamily: "'Cinzel',serif", fontWeight: 700, letterSpacing: '.16em', fontSize: 11, color: '#0a0710', background: 'linear-gradient(120deg,#c8a9f5,#8b46d6)', border: 'none', padding: '10px 0', clipPath: 'polygon(8px 0,100% 0,calc(100% - 8px) 100%,0 100%)' }}>
                GIVE GIFT
              </button>
            </div>
          )}
          {actions && <div style={{ marginTop: 10 }}>{actions}</div>}

          {/* chronicle — revealed sentence by sentence as the hero ascends:
              revealed = round(total × star/7), min 1, everything at 7★. The
              sealed remainder is named so the player knows more awaits. */}
          {backstory && (() => {
            const sentences = backstory.match(/[^.!?]+[.!?]+["”']?\s*/g) || [backstory]
            const revealedCount = star >= 7 ? sentences.length : Math.max(1, Math.round(sentences.length * star / 7))
            const revealed = sentences.slice(0, revealedCount).join('').trim()
            const sealed = sentences.length - revealedCount
            return (
              <div style={{ marginTop: 18, borderTop: '1px solid rgba(184,151,98,.2)', paddingTop: 14 }}>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, marginBottom: 8 }}>
                  <span style={{ fontFamily: "'Cinzel',serif", letterSpacing: '.28em', fontSize: 10, color: 'var(--gold)' }}>CHRONICLE</span>
                  <span style={{ fontFamily: "'Cinzel',serif", letterSpacing: '.14em', fontSize: 9, color: 'var(--muted)' }}>{revealedCount} OF {sentences.length} PASSAGES</span>
                </div>
                <div style={{ fontSize: 15, fontStyle: 'italic', color: 'var(--muted)', lineHeight: 1.55 }}>
                  {fullChronicle || revealed.length <= 300 ? revealed : `${revealed.slice(0, 300)}…`}
                  {revealed.length > 300 && (
                    <button onClick={() => setFullChronicle(f => !f)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--gold-hi)', fontStyle: 'normal', fontFamily: "'Cinzel',serif", fontSize: 10, letterSpacing: '.2em', marginLeft: 8 }}>
                      {fullChronicle ? '‹ LESS' : 'READ MORE ›'}
                    </button>
                  )}
                </div>
                {sealed > 0 && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 10 }}>
                    <span style={{ width: 7, height: 7, transform: 'rotate(45deg)', border: '1px solid rgba(150,110,230,.5)', display: 'inline-block', flex: 'none' }} />
                    <span style={{ fontFamily: "'Cinzel',serif", letterSpacing: '.14em', fontSize: 10, color: 'var(--lavender)' }}>
                      {sealed} PASSAGE{sealed === 1 ? '' : 'S'} REMAIN{sealed === 1 ? 'S' : ''} SEALED — ASCEND THEM TO REMEMBER MORE
                    </span>
                  </div>
                )}
              </div>
            )
          })()}

          {/* deeds — the record of what they've actually DONE. Written by the
              combat engine at dramatic moments; survives the hero's death. */}
          {deeds.length > 0 && (
            <div style={{ marginTop: 18, borderTop: '1px solid rgba(184,151,98,.2)', paddingTop: 14 }}>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, marginBottom: 10 }}>
                <span style={{ fontFamily: "'Cinzel',serif", letterSpacing: '.28em', fontSize: 10, color: 'var(--gold)' }}>DEEDS</span>
                <span style={{ fontFamily: "'Cinzel',serif", letterSpacing: '.14em', fontSize: 9, color: 'var(--muted)' }}>{deeds.length} RECORDED</span>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
                {(fullChronicle ? deeds : deeds.slice(0, 5)).map((d, i) => (
                  <div key={i} style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
                    <span style={{ width: 6, height: 6, transform: 'rotate(45deg)', background: 'var(--gold-dim)', display: 'inline-block', flex: 'none', position: 'relative', top: -1 }} />
                    <span style={{ fontSize: 14.5, fontStyle: 'italic', color: '#d8cbb0', lineHeight: 1.4 }}>{d.deed}</span>
                  </div>
                ))}
              </div>
              {deeds.length > 5 && !fullChronicle && (
                <button onClick={() => setFullChronicle(true)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--gold-hi)', fontFamily: "'Cinzel',serif", fontSize: 10, letterSpacing: '.2em', marginTop: 8, padding: 0 }}>
                  ALL {deeds.length} DEEDS ›
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// Highest of the six — which stat this hero's power leans on.
function powerStat(hero) {
  const pairs = [['STR', hero.strength], ['INT', hero.intelligence], ['AGI', hero.agility], ['END', hero.endurance], ['WIL', hero.willpower], ['LCK', hero.luck]]
  return pairs.reduce((best, p) => (p[1] ?? 0) > (best[1] ?? 0) ? p : best, pairs[0])[0]
}

// "THIEF EVOLUTION" flavor line — base class family the current class grew from.
function familyLabel(cls) {
  if (!cls) return ''
  return `${classFamily(cls)} line`
}
