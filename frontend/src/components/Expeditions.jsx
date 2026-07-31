/*
 * THE SKY CHARTS / Expeditions — live. Dispatch the Skydock hull on timed
 * lanes for offline rewards (/base/expeditions). One hull, one lane at a
 * time; recall early pays half spoils.
 */
import React, { useState, useEffect } from 'react'
import { getExpeditions, dispatchExpedition, collectExpedition, recallExpedition, listHeroes } from '../api/client'
import { emitToast } from '../toastBus'
import MinigameShell, { AUTO_RESOLVE_MULT } from './minigames/MinigameShell'
import HelmGates from './minigames/HelmGates'

const TONE = { violet: 'rgba(150,110,230,.45)', gold: 'rgba(216,187,132,.45)', red: 'rgba(192,64,64,.45)' }
const REWARD_LABEL = { gold: 'Gold · scales with the hull', aether: 'Aether · raid fuel', materials: 'Forge materials · embercores' }

function fmtRemaining(sec) {
  if (sec == null) return ''
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60)
  return `RETURNS ${h}H ${String(m).padStart(2, '0')}M`
}

function rewardToast(name, reward) {
  if (reward.kind === 'materials') {
    const drops = Object.entries(reward.drops).map(([k, v]) => `${k.replace(/_/g, ' ')} ×${v}`).join(', ')
    emitToast(`${name} — ${drops}`, 'success')
  } else {
    emitToast(`${name} — ${reward.amount.toLocaleString()} ${reward.kind}`, 'success')
  }
}

export default function Expeditions({ onClose }) {
  const [status, setStatus] = useState(null)
  const [busy, setBusy] = useState(null)
  const [picking, setPicking] = useState(null)   // lane key while choosing crew
  const [roster, setRoster] = useState([])
  const [crew, setCrew] = useState([])

  async function load() {
    try { setStatus(await getExpeditions()) } catch { /* backend older than /expeditions */ }
  }
  useEffect(() => { load() }, [])

  // tick the countdowns once a minute
  useEffect(() => {
    const t = setInterval(load, 60000)
    return () => clearInterval(t)
  }, [])

  async function openPicker(lane) {
    setPicking(lane.key)
    setCrew([])
    try {
      const hs = await listHeroes(true)
      setRoster(Array.isArray(hs) ? hs : hs.heroes || [])
    } catch { setRoster([]) }
  }

  // Launch opens THE HELM — the steering minigame decides the voyage's
  // spoils multiplier (skip = NOVICE baseline; a botched Legendary run
  // means the hull limps home at half spoils).
  const [showHelm, setShowHelm] = useState(false)

  function launch() { setShowHelm(true) }

  async function doLaunch(qualityMult) {
    setShowHelm(false)
    setBusy(picking)
    try {
      const res = await dispatchExpedition(picking, crew, qualityMult)
      emitToast(res.message, 'success')
      setPicking(null)
      await load()
    } catch (e) { emitToast(e.message, 'error') } finally { setBusy(null) }
  }

  async function act(fn, lane) {
    setBusy(lane.key)
    try {
      const res = await fn(lane.key)
      rewardToast(lane.name, res.reward)
      await load()
    } catch (e) { emitToast(e.message, 'error') } finally { setBusy(null) }
  }

  const capacity = status?.ship?.crew_capacity ?? 0
  const underway = status?.lanes?.filter(l => l.state === 'underway' || l.state === 'ready').length ?? 0

  return (
    <div className="ilm-expeditions">
      <button className="ilm-close" style={{ position: 'absolute', top: 18, right: 24, zIndex: 10 }} onClick={onClose}>✕</button>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 2 }}>
        <span style={{ width: 9, height: 9, transform: 'rotate(45deg)', background: 'var(--gold)', display: 'inline-block' }} />
        <span style={{ fontFamily: "'Cinzel',serif", fontWeight: 600, letterSpacing: '.5em', fontSize: '0.7rem', color: 'var(--gold)' }}>BEYOND THE TOWER</span>
      </div>
      <div style={{ fontFamily: "'Cinzel',serif", fontWeight: 900, fontSize: '2.4rem', color: 'var(--text-hi)', letterSpacing: '.04em', textShadow: '0 6px 40px rgba(124,58,214,.4)' }}>THE SKY CHARTS</div>
      <div style={{ fontStyle: 'italic', color: 'var(--text-dim)', marginTop: 4 }}>Send crewed hulls beyond the Tower — they return with what the sky gives.</div>
      <div className="ilm-micro" style={{ color: 'var(--gold-hi)', marginTop: 10 }}>
        {status?.ship ? `${status.ship.name?.toUpperCase()} · TIER ${status.ship.tier} · ${underway} OF ${status?.lanes?.length ?? 3} LANES UNDERWAY` : 'NO HULL — BUILD ONE AT THE SKYDOCK'}
      </div>

      <div className="ilm-exp-grid">
        {(status?.lanes || []).map(l => (
          <div key={l.key} className="ilm-exp-lane" style={{ borderColor: TONE[l.tone] }}>
            <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between' }}>
              <span style={{ fontFamily: "'Cinzel',serif", fontWeight: 700, fontSize: '1rem', letterSpacing: '.06em', color: 'var(--text-hi)' }}>{l.name}</span>
              <span className="ilm-micro" style={{ color: 'var(--muted)' }}>{l.hours}-HOUR LANE</span>
            </div>
            <div style={{ fontStyle: 'italic', color: 'var(--text-dim)', margin: '8px 0 6px', lineHeight: 1.4 }}>{l.desc}</div>
            <div className="ilm-micro" style={{ color: 'var(--gold-hi)', marginBottom: 12, flex: 1 }}>{REWARD_LABEL[l.reward]}</div>

            {l.state === 'underway' && (
              <>
                <div className="ilm-exp-status"><span className="ilm-livedot" style={{ background: 'var(--green)', boxShadow: '0 0 7px var(--green)' }} /><span className="ilm-micro" style={{ color: 'var(--green-hi)' }}>UNDERWAY</span><span style={{ flex: 1 }} /><span className="ilm-micro" style={{ color: 'var(--gold-hi)' }}>{fmtRemaining(l.returns_in_seconds)}</span></div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, margin: '10px 0' }}>
                  <span className="ilm-social-pennant" style={{ boxShadow: 'inset 0 0 0 1px var(--lavender)' }} />
                  <span style={{ fontFamily: "'Cinzel',serif", fontWeight: 700, fontSize: '0.8rem', color: 'var(--text-hi)' }}>{status?.ship?.name?.toUpperCase()}</span>
                  <span className="ilm-micro">CREW {l.crew_count}/{capacity}</span>
                </div>
                <button className="ilm-btn ilm-btn-ghost ilm-btn-block" disabled={busy === l.key} onClick={() => act(recallExpedition, l)}>RECALL EARLY · HALF SPOILS</button>
              </>
            )}
            {l.state === 'ready' && (
              <>
                <div className="ilm-exp-status"><span className="ilm-livedot" /><span className="ilm-micro" style={{ color: 'var(--gold-hi)' }}>THE HULL HAS RETURNED</span></div>
                <button className="ilm-btn ilm-btn-gold ilm-btn-block" style={{ marginTop: 10 }} disabled={busy === l.key} onClick={() => act(collectExpedition, l)}>UNLOAD THE SPOILS</button>
              </>
            )}
            {l.state === 'open' && (
              <>
                <div className="ilm-micro" style={{ color: 'var(--green-hi)', marginBottom: 8 }}>LANE OPEN</div>
                <button className="ilm-btn ilm-btn-gold ilm-btn-block" onClick={() => openPicker(l)}>CHOOSE A CREW</button>
              </>
            )}
            {l.state === 'no_ship' && (
              <>
                <div className="ilm-micro" style={{ color: 'var(--muted)', marginBottom: 8 }}>THE HULL IS OUT</div>
                <button className="ilm-btn ilm-btn-ghost ilm-btn-block" disabled>AWAITING ITS RETURN</button>
              </>
            )}
            {l.state === 'locked' && (
              <>
                <div className="ilm-micro" style={{ color: 'var(--red-hi)', marginBottom: 8 }}>LOCKED · {l.req}</div>
                <button className="ilm-btn ilm-btn-ghost ilm-btn-block" disabled>REQUIRES A GREATER HULL</button>
              </>
            )}
          </div>
        ))}
      </div>

      {/* crew picker */}
      {picking && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(6,4,12,.78)', zIndex: 60, display: 'flex', alignItems: 'center', justifyContent: 'center' }} onClick={() => setPicking(null)}>
          <div className="ilm-exp-lane" style={{ width: 'min(520px, 92vw)', maxHeight: '80vh', overflowY: 'auto', borderColor: 'var(--gold-dim)' }} onClick={e => e.stopPropagation()}>
            <div style={{ fontFamily: "'Cinzel',serif", fontWeight: 700, fontSize: '1.05rem', letterSpacing: '.06em', color: 'var(--text-hi)' }}>MUSTER A CREW</div>
            <div style={{ fontStyle: 'italic', color: 'var(--text-dim)', margin: '6px 0 12px' }}>
              The {status?.ship?.name} holds {capacity}. A larger crew brings home more.
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 14 }}>
              {roster.map(h => {
                const on = crew.includes(h.id)
                return (
                  <button key={h.id} className="ilm-btn ilm-btn-block" style={{ display: 'flex', justifyContent: 'space-between', border: `1px solid ${on ? 'var(--gold)' : 'var(--line)'}`, background: on ? 'rgba(216,187,132,.12)' : 'transparent' }}
                    onClick={() => setCrew(c => on ? c.filter(x => x !== h.id) : (c.length < capacity ? [...c, h.id] : c))}>
                    <span style={{ color: 'var(--text-hi)' }}>{h.name}</span>
                    <span className="ilm-micro" style={{ color: on ? 'var(--gold-hi)' : 'var(--muted)' }}>{'★'.repeat(h.birth_star || 1)}{on ? ' · ABOARD' : ''}</span>
                  </button>
                )
              })}
              {roster.length === 0 && <div className="ilm-micro" style={{ color: 'var(--muted)' }}>NO LIVING HEROES TO CREW THE HULL</div>}
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button className="ilm-btn ilm-btn-ghost" style={{ flex: 1 }} onClick={() => setPicking(null)}>STAND DOWN</button>
              <button className="ilm-btn ilm-btn-gold" style={{ flex: 2 }} disabled={crew.length === 0 || busy === picking} onClick={launch}>
                {busy === picking ? 'CASTING OFF…' : `CAST OFF · CREW ${crew.length}/${capacity}`}
              </button>
            </div>
          </div>
        </div>
      )}

      {showHelm && (
        <MinigameShell
          title="THE HELM"
          flavor="The hull strains at its moorings. Take the wheel through the departure lanes yourself, or let the crew sail her out."
          onSkip={(mult) => doLaunch(mult)}
          onResolve={(mult) => doLaunch(mult)}
          game={(difficulty, onDone) => <HelmGates difficulty={difficulty} onDone={onDone} />}
        />
      )}
    </div>
  )
}
