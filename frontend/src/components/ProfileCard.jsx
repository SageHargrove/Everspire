/*
 * PROFILE CARD — how the Tower sees you (mockup "Reliquary - Illuminated").
 * Identity modal: standard (Pennant), master name + base name (both
 * editable via existing endpoints), deepest climb / roster might / heroes,
 * and the Face of the Band — a chosen hero whose portrait fronts the card.
 * Face + motto persist per-profile in localStorage until profiles go social.
 */
import React, { useState, useEffect } from 'react'
import { getBase, setMasterName, getBanner, listHeroes } from '../api/client'
import Pennant from './Pennant'
import { emitToast } from '../toastBus'

const LS_FACE = 'profileFaceHero'
const LS_MOTTO = 'profileMotto'

export default function ProfileCard({ onClose }) {
  const [base, setBase] = useState(null)
  const [banner, setBanner] = useState(null)
  const [heroes, setHeroes] = useState([])
  const [faceId, setFaceId] = useState(() => Number(localStorage.getItem(LS_FACE)) || null)
  const [motto, setMotto] = useState(() => localStorage.getItem(LS_MOTTO) || '')

  useEffect(() => {
    getBase().then(setBase).catch(() => {})
    getBanner().then(setBanner).catch(() => {})
    listHeroes(true).then(hs => setHeroes(Array.isArray(hs) ? hs : hs.heroes || [])).catch(() => {})
  }, [])

  const power = heroes.reduce((s, h) => s + (h.strength || 0) + (h.intelligence || 0) + (h.agility || 0) + (h.endurance || 0), 0)

  // The band is your STRONGEST five — leader first (they front the card by
  // default), then the four mightiest of the rest.
  const might = h => (h.strength || 0) + (h.intelligence || 0) + (h.agility || 0) + (h.endurance || 0)
  const alive = heroes.filter(h => h.is_alive)
  const leader = alive.find(h => h.is_team_leader) || [...alive].sort((a, b) => might(b) - might(a))[0]
  const band = leader
    ? [leader, ...alive.filter(h => h.id !== leader.id).sort((a, b) => might(b) - might(a)).slice(0, 4)]
    : []
  const face = band.find(h => h.id === faceId) || leader
  const faceRow = band

  async function editUser() {
    const next = window.prompt('Choose a name for the Master of the base', base?.master_name || '')
    if (!next || !next.trim()) return
    try { await setMasterName(next.trim()); setBase(b => ({ ...b, master_name: next.trim() })) }
    catch (e) { emitToast(e.message, 'error') }
  }

  function editMotto() {
    const next = window.prompt('A line for the Tower to remember you by', motto)
    if (next == null) return
    setMotto(next.trim())
    localStorage.setItem(LS_MOTTO, next.trim())
  }

  function pickFace(id) {
    setFaceId(id)
    localStorage.setItem(LS_FACE, String(id))
  }

  function shareProfile() {
    const payload = { master: base?.master_name, base: base?.name, floor: base?.highest_floor, power, heroes: heroes.length }
    navigator.clipboard?.writeText(`TOE-PROFILE:${btoa(JSON.stringify(payload))}`)
    emitToast('Profile card copied — share it with the Tower.', 'success')
  }

  const pencil = { cursor: 'pointer', width: 20, height: 20, border: '1px solid rgba(184,151,98,.4)', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: 10, color: 'var(--gold-hi)', flex: 'none', background: 'none' }

  return (
    <div className="ilm-modal-scrim" style={{ zIndex: 330 }} onClick={onClose}>
      <div className="ilm-featmodal" style={{ width: 660, maxWidth: '94vw', padding: 0, clipPath: 'polygon(0 0,100% 0,100% 100%,18px 100%)' }} onClick={e => e.stopPropagation()}>
        <span className="ilm-corner" style={{ zIndex: 9 }} />
        <span className="ilm-corner ilm-corner-r" style={{ zIndex: 9 }} />
        {/* no bottom-left tick — that corner is the clip-path notch */}
        <span className="ilm-corner ilm-corner-br" style={{ zIndex: 9 }} />
        <button className="ilm-close" style={{ position: 'absolute', top: 10, right: 12, zIndex: 10 }} onClick={onClose}>✕</button>

        <div style={{ position: 'relative', display: 'flex', gap: 22, padding: '26px 28px 22px', flexWrap: 'wrap' }}>
          {/* standard */}
          <div style={{ width: 86, flex: 'none' }}>
            <div style={{ width: 76, margin: '2px auto 0', animation: 'banner-sway 7s ease-in-out infinite', transformOrigin: 'top center' }}>
              <Pennant
                cloth={banner?.cloth || '#7a3df0'}
                cut={banner?.cut || 'swallow'}
                frameTier={banner?.frame_tier || 1}
                sigil={banner?.sigil || null}
                emblem={banner?.emblem || null}
                paint={banner?.paint || null}
                width={76}
              />
            </div>
            <div style={{ textAlign: 'center', marginTop: 10, fontFamily: "'Cinzel',serif", fontSize: '0.5rem', letterSpacing: '.16em', color: 'var(--lavender)' }}>YOUR STANDARD</div>
          </div>

          {/* identity */}
          <div style={{ flex: 1, minWidth: 260 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
              <span style={{ fontFamily: "'Cinzel',serif", fontWeight: 600, letterSpacing: '.28em', fontSize: '0.72rem', color: 'var(--lavender)', textTransform: 'uppercase' }}>
                {base?.master_name || 'UNNAMED MASTER'}
              </span>
              <button title="Change name" style={{ ...pencil, color: 'var(--lavender)', borderColor: 'rgba(150,110,230,.4)' }} onClick={editUser}>✎</button>
              <span style={{ flex: 1 }} />
              <span style={{ fontFamily: "'Cinzel',serif", fontSize: '0.56rem', letterSpacing: '.14em', color: '#ffd88a', border: '1px solid rgba(255,216,138,.5)', padding: '3px 9px', flex: 'none' }}>
                FLOOR {base?.highest_floor ?? 0}
              </span>
            </div>
            {/* World name is granted by the Tower, not chosen — no rename here */}
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
              <div style={{ fontFamily: "'Cinzel',serif", fontWeight: 900, fontSize: '1.7rem', lineHeight: 1, color: 'var(--text-hi)', textShadow: '0 4px 24px rgba(124,58,214,.45)', textTransform: 'uppercase' }}>
                {base?.name || '…'}
              </div>
              <span title="Every Master's world is named by the Tower itself" style={{ fontFamily: "'Cinzel',serif", fontSize: '0.52rem', letterSpacing: '.2em', color: 'var(--muted)', textTransform: 'uppercase' }}>
                Your World
              </span>
            </div>
            <button onClick={editMotto} style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer', fontSize: '0.82rem', fontStyle: 'italic', fontFamily: 'inherit', color: 'var(--muted)', marginTop: 6, textAlign: 'left' }}>
              {motto ? `"${motto}"` : 'Tap to set a line the Tower remembers you by…'}
            </button>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8, marginTop: 14 }}>
              <div className="ilm-guild-stat"><span className="ilm-micro">DEEPEST</span><b>Floor {base?.highest_floor ?? 0}</b></div>
              <div className="ilm-guild-stat"><span className="ilm-micro">MIGHT</span><b style={{ color: 'var(--gold-hi)' }}>{power.toLocaleString()}</b></div>
              <div className="ilm-guild-stat"><span className="ilm-micro">HEROES</span><b style={{ color: 'var(--lavender)' }}>{heroes.length}</b></div>
            </div>
          </div>

          {/* face of the band */}
          <div style={{ width: 150, flex: 'none', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 9 }}>
            <div style={{ width: 118, height: 118, position: 'relative' }}>
              <span style={{ position: 'absolute', inset: 8, transform: 'rotate(45deg)', border: '1px solid var(--lavender)', background: 'linear-gradient(135deg,#1c1030,#0c0718)', overflow: 'hidden', boxShadow: '0 0 26px rgba(0,0,0,.5), 0 0 18px rgba(150,110,230,.27)' }}>
                {face?.portrait_path && !face.portrait_path.includes('default_') && (
                  <img src={`/heroes/${face.id}/card-image?mini=1`} alt=""
                    onError={(e) => { if (!e.currentTarget.dataset.fb) { e.currentTarget.dataset.fb = '1'; e.currentTarget.src = `/${face.portrait_path}` } }}
                    style={{ position: 'absolute', width: '141%', height: '141%', left: '50%', top: '50%', transform: 'translate(-50%,-50%) rotate(-45deg)', objectFit: 'cover', objectPosition: 'top' }} />
                )}
              </span>
              {(!face?.portrait_path || face.portrait_path.includes('default_')) && (
                <span style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: "'Cinzel',serif", fontWeight: 900, fontSize: '2.4rem', color: 'var(--lavender)' }}>
                  {face?.name?.[0] || '?'}
                </span>
              )}
            </div>
            <div style={{ fontFamily: "'Cinzel',serif", fontSize: '0.5rem', letterSpacing: '.16em', color: 'var(--muted)' }}>FACE OF THE BAND</div>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', justifyContent: 'center' }}>
              {faceRow.map(h => {
                const on = face?.id === h.id
                return (
                  <button key={h.id} title={h.name} onClick={() => pickFace(h.id)} style={{ cursor: 'pointer', width: 26, height: 26, transform: 'rotate(45deg)', flex: 'none', border: on ? '1px solid #ffd88a' : '1px solid rgba(154,134,184,.5)', background: on ? 'rgba(184,151,98,.14)' : '#140b22', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <span style={{ transform: 'rotate(-45deg)', fontFamily: "'Cinzel',serif", fontSize: '0.56rem', color: on ? '#ffd88a' : 'var(--lavender)' }}>{h.name[0]}</span>
                  </button>
                )
              })}
            </div>
          </div>
        </div>

        {/* footer */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '14px 28px', borderTop: '1px solid rgba(184,151,98,.2)' }}>
          <span style={{ fontSize: '0.78rem', fontStyle: 'italic', color: 'var(--muted)' }}>This is how the Tower sees you — tap ✎ to change your name.</span>
          <span style={{ flex: 1 }} />
          <button className="ilm-btn ilm-btn-gold" onClick={shareProfile}>SHARE PROFILE</button>
        </div>
      </div>
    </div>
  )
}
