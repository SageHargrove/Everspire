import React, { useState, useEffect } from 'react'
import { listProfiles, switchProfile, renameProfile, deleteProfile, setMasterName } from '../api/client'
import { confirmDialog } from './DialogHost'


export default function ProfileSelect({ onSelect }) {
  const [profiles, setProfiles] = useState([])
  const [loading, setLoading] = useState(true)
  const [newProfile, setNewProfile] = useState('')
  const [selectedProfile, setSelectedProfile] = useState(null)
  const [msg, setMsg] = useState(null)
  // Difficulty is locked in at creation — see backend/services/difficulty_service.py
  const [pendingNewName, setPendingNewName] = useState(null)

  useEffect(() => { load() }, [])

  async function load() {
    setLoading(true)
    try {
      const data = await listProfiles()
      setProfiles(data.profiles)
      if (selectedProfile && !data.profiles.includes(selectedProfile)) setSelectedProfile(null)
    } catch (e) {
      setMsg(e.message)
    } finally {
      setLoading(false)
    }
  }

  async function handleLoadSelected() {
    if (!selectedProfile) return
    try {
      setLoading(true)
      await switchProfile(selectedProfile)
      onSelect(selectedProfile)
    } catch (e) { setMsg(e.message); setLoading(false) }
  }

  function handleCreate(e) {
    e.preventDefault()
    const name = newProfile.trim()
    if (!name) return
    setPendingNewName(name)
  }

  async function confirmCreate() {
    const name = pendingNewName
    setPendingNewName(null)
    try {
      setLoading(true)
      await switchProfile(name, 'normal')
      try { await setMasterName(name) } catch(e) {}
      onSelect(name)
    } catch (e) { setMsg(e.message); setLoading(false) }
  }

  async function handleRename() {
    if (!selectedProfile) return
    const newName = prompt(`Rename "${selectedProfile}" to:`, selectedProfile)
    if (!newName || newName === selectedProfile) return
    try {
      setLoading(true)
      await renameProfile(selectedProfile, newName)
      setSelectedProfile(newName)
      await load()
      setMsg(`Renamed to ${newName}`)
    } catch(e) { setMsg(e.message); setLoading(false) }
  }

  async function handleDelete() {
    if (!selectedProfile) return
    if (!(await confirmDialog(`Permanently delete "${selectedProfile}"?`))) return
    try {
      setLoading(true)
      await deleteProfile(selectedProfile)
      setSelectedProfile(null)
      await load()
      setMsg('Profile deleted.')
    } catch(e) { setMsg(e.message); setLoading(false) }
  }

  if (loading && profiles.length === 0) return (
    <div style={{ position: 'fixed', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#08060e', color: '#fff', fontFamily: 'Cinzel, serif' }}>
      Loading...
    </div>
  )

  return (
    <div className="ilm-title-screen">
      {/* No tower key-art — the ambient gradient background carries the screen.
          A soft violet scrim keeps the wordmark legible. */}
      <div className="ilm-title-scrim" />

      {/* drifting glyphs */}
      <span className="ilm-title-glyph" style={{ left: '16%', top: '22%', animationDelay: '0s' }}>◆</span>
      <span className="ilm-title-glyph" style={{ left: '82%', top: '18%', animationDelay: '1.2s' }}>✧</span>
      <span className="ilm-title-glyph" style={{ left: '76%', top: '46%', animationDelay: '.5s' }}>❡</span>

      {/* ── wordmark ── */}
      <div className="ilm-title-wordmark">
        <div className="ilm-diamond" style={{ width: 44, height: 44, margin: '0 auto', boxShadow: '0 0 24px rgba(184,151,98,.4)', background: 'rgba(10,7,19,.6)' }}>
          <div className="pip" style={{ width: 14, height: 14 }} />
        </div>
        <div className="ilm-title-stackword">
          {/* ghost = ASCEND on purpose — see AuthGate title block */}
          <span className="ghost">ASCEND</span>
          <span className="solid">GILTGRAVE</span>
        </div>
        <div className="ilm-title-tagline">
          <span className="rule" /><span>Heroes die. Legacies do not.</span><span className="rule" />
        </div>
      </div>

      {/* ── profile select ── */}
      <div className="ilm-title-profiles">
        <div className="ilm-title-selecthead">SELECT YOUR PROFILE</div>
        {msg && <div style={{ color: 'var(--red-hi)', fontSize: '0.85rem', textAlign: 'center', marginBottom: '0.6rem' }}>{msg}</div>}

        <div className="ilm-title-cardrow">
          {profiles.map((p, i) => {
            const sel = selectedProfile === p
            return (
              <button
                key={p}
                className={`ilm-profile-card ${sel ? 'sel' : ''}`}
                onClick={() => setSelectedProfile(p)}
                style={{ clipPath: 'polygon(0 0,100% 0,100% 100%,12px 100%)' }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                  <span style={{ fontFamily: "'Cinzel',serif", fontWeight: 700, fontSize: '1.2rem', letterSpacing: '.08em', color: sel ? 'var(--text-hi)' : 'var(--text)' }}>{p}</span>
                  {i === 0 && <span style={{ fontFamily: "'Cinzel',serif", fontSize: '0.58rem', letterSpacing: '.2em', color: 'var(--gold-hi)' }}>LAST&nbsp;PLAYED</span>}
                </div>
                <div className="ilm-title-cardhint">Enter the Tower and climb on.</div>
              </button>
            )
          })}

          {/* new-profile card */}
          <form onSubmit={handleCreate} className="ilm-profile-card new">
            <input
              type="text"
              className="input"
              placeholder="New profile name…"
              value={newProfile}
              onChange={e => setNewProfile(e.target.value)}
              style={{ width: '100%', fontSize: '1rem', padding: '0.6rem 0.8rem' }}
            />
            <button type="submit" className="btn btn-gold" disabled={!newProfile.trim()} style={{ marginTop: 12, width: '100%', padding: '0.7rem 0', fontSize: '0.9rem' }}>
              + New Profile
            </button>
          </form>
        </div>

        {/* actions for the selected profile */}
        <div className="ilm-title-actions" style={{ opacity: selectedProfile ? 1 : 0.25, pointerEvents: selectedProfile ? 'auto' : 'none' }}>
          <button className="btn btn-gold" style={{ padding: '0.9rem 2.6rem', letterSpacing: '.24em', fontSize: '1rem' }} onClick={handleLoadSelected}>
            Press to Ascend
          </button>
          <button className="btn" onClick={handleRename}>Rename</button>
          <button className="btn btn-danger" onClick={handleDelete}>Delete</button>
        </div>

        <div className="ilm-title-version">GILTGRAVE · PRE-ALPHA</div>
      </div>

      {/* confirm manager name */}
      {pendingNewName && (
        <div className="ilm-modal-scrim" style={{ zIndex: 50 }} onClick={() => setPendingNewName(null)}>
          <div className="ilm-confirm-panel ent-fade" onClick={e => e.stopPropagation()}>
            <span className="ilm-corner" />
            <span className="ilm-corner ilm-corner-r" />
            <div style={{ fontFamily: "'Cinzel',serif", letterSpacing: '.3em', fontSize: '0.56rem', color: 'var(--gold-hi)', textAlign: 'center' }}>THE WORLD SERVER REMEMBERS</div>
            <div style={{ fontFamily: "'Cinzel',serif", fontWeight: 900, fontSize: '1.3rem', color: 'var(--text-hi)', textAlign: 'center', marginTop: 6 }}>
              CONFIRM MANAGER NAME
            </div>
            <div style={{ fontSize: '0.95rem', fontStyle: 'italic', color: '#c8b8dd', textAlign: 'center', margin: '0.8rem 0 1.4rem', lineHeight: 1.5 }}>
              You will be known as “{pendingNewName}” on the World server. This cannot be changed later.
            </div>
            <button className="btn btn-primary" style={{ width: '100%', padding: '0.75rem' }} onClick={() => confirmCreate()}>
              Begin the Climb
            </button>
            <button className="btn" style={{ width: '100%', marginTop: '0.8rem' }} onClick={() => setPendingNewName(null)}>
              Never Mind
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
