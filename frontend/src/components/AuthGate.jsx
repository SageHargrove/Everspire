import React, { useEffect, useState } from 'react'
import { authLogin, authRegister, authMe, authGoogle, authDiscord, getArenaToken, clearArenaSession } from '../api/arenaServerClient'
import { switchProfile, setMasterName, listProfiles } from '../api/client'

// The title screen — account gate + entry, replacing the old profile-select
// screen entirely. One account = one save: the local profile is derived from
// the world display name (or a single shared "offline" save). Flow:
//   sign in / create account / play offline  ->  "Press to Ascend"  ->  game.
// A stored valid token skips straight to the ascend step, greeting the
// player by display name. Server unreachable -> offline is offered inline.
//
// NOTE (Liam, 2026-07-12): "Play Offline" is a DEV/TESTING affordance only —
// remove it (and the offline identity path) before launch; accounts will be
// mandatory.
export default function AuthGate({ onEnter }) {
  const [phase, setPhase] = useState('checking')      // checking | form | ready
  const [mode, setMode] = useState('login')           // login | register
  const [identity, setIdentity] = useState(null)      // { online, username }
  const [identifier, setIdentifier] = useState('')
  const [email, setEmail] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [serverDown, setServerDown] = useState(false)

  useEffect(() => {
    (async () => {
      if (getArenaToken()) {
        try {
          const me = await authMe()
          setIdentity({ online: true, username: me.username })
          setPhase('ready')
          return
        } catch (e) {
          if (String(e.message || '').match(/fetch|network|Failed/i)) setServerDown(true)
          clearArenaSession()
        }
      }
      setPhase('form')
    })()
  }, [])

  function fail(err) {
    if (String(err.message || '').match(/fetch|network|Failed/i)) {
      setServerDown(true)
      setError('World server unreachable — you can still play offline below.')
    } else {
      setError(err.message)
    }
    setBusy(false)
  }

  async function submit(e) {
    e.preventDefault()
    setBusy(true); setError(null)
    try {
      const data = mode === 'register'
        ? await authRegister(email.trim(), username.trim(), password)
        : await authLogin(identifier.trim(), password)
      setIdentity({ online: true, username: data.username })
      setBusy(false)
      setPhase('ready')
    } catch (err) { fail(err) }
  }

  async function google() {
    setBusy(true); setError(null)
    try { await authGoogle() } catch (err) {
      setError(err.message || 'Google sign-in is not available yet')
      setBusy(false)
    }
  }

  async function discord() {
    setBusy(true); setError(null)
    try { await authDiscord() } catch (err) {
      setError(err.message || 'Discord sign-in is not available yet')
      setBusy(false)
    }
  }

  function goOffline() {
    setIdentity({ online: false, username: null })
    setPhase('ready')
    setError(null)
  }

  async function ascend() {
    setBusy(true); setError(null)
    const ident = identity || { online: false, username: null }
    // one save per account: profile name = world display name; offline
    // players share a single local "offline" save (alts = other accounts).
    const profile = ident.online ? ident.username : 'offline'
    try {
      const existing = await listProfiles().then(d => d.profiles || []).catch(() => [])
      const isNew = !existing.includes(profile)
      await switchProfile(profile, 'normal')
      if (ident.online && isNew) {
        try { await setMasterName(ident.username) } catch {}
      }
      onEnter({ ...ident, profile })
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }

  return (
    <div className="ilm-title-screen">
      <div className="ilm-title-scrim" />
      <span className="ilm-title-glyph" style={{ left: '16%', top: '22%', animationDelay: '0s' }}>◆</span>
      <span className="ilm-title-glyph" style={{ left: '82%', top: '18%', animationDelay: '1.2s' }}>✧</span>
      <span className="ilm-title-glyph" style={{ left: '76%', top: '46%', animationDelay: '.5s' }}>❡</span>

      <div className="ilm-title-wordmark">
        <div className="ilm-diamond" style={{ width: 44, height: 44, margin: '0 auto', boxShadow: '0 0 24px rgba(184,151,98,.4)', background: 'rgba(10,7,19,.6)' }}>
          <div className="pip" style={{ width: 14, height: 14 }} />
        </div>
        <div className="ilm-title-stackword">
          {/* ghost deliberately differs from the solid word — the faded echo
              beneath the title. (Same-word echo read as a duplicate once the
              title became one word.) */}
          <span className="ghost">ASCEND</span>
          <span className="solid">EVERSPIRE</span>
        </div>
        <div className="ilm-title-tagline">
          <span className="rule" /><span>Heroes die. Legacies do not.</span><span className="rule" />
        </div>
      </div>

      <div className="ilm-title-profiles">
        {phase === 'checking' && (
          <div className="ilm-title-selecthead">REACHING THE WORLD SERVER…</div>
        )}

        {phase === 'form' && (
          <>
            <div className="ilm-title-selecthead">
              {mode === 'login' ? 'SIGN IN TO THE WORLD SERVER' : 'CREATE YOUR WORLD ACCOUNT'}
            </div>
            {error && <div style={{ color: 'var(--red-hi)', fontSize: '0.85rem', textAlign: 'center', marginBottom: '0.6rem' }}>{error}</div>}

            <form onSubmit={submit} style={{ width: 360, maxWidth: '90vw', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 10 }}>
              {mode === 'register' ? (
                <>
                  <input type="email" className="input" placeholder="Email" value={email} onChange={e => setEmail(e.target.value)} autoFocus
                    style={{ width: '100%', fontSize: '1rem', padding: '0.65rem 0.85rem' }} />
                  <input type="text" className="input" placeholder="Display name — how the World knows you" value={username} onChange={e => setUsername(e.target.value)}
                    style={{ width: '100%', fontSize: '1rem', padding: '0.65rem 0.85rem' }} />
                </>
              ) : (
                <input type="text" className="input" placeholder="Email or display name" value={identifier} onChange={e => setIdentifier(e.target.value)} autoFocus
                  style={{ width: '100%', fontSize: '1rem', padding: '0.65rem 0.85rem' }} />
              )}
              <input type="password" className="input" placeholder="Password" value={password} onChange={e => setPassword(e.target.value)}
                style={{ width: '100%', fontSize: '1rem', padding: '0.65rem 0.85rem' }} />

              <button type="submit" className="btn btn-gold" disabled={busy} style={{ padding: '0.8rem 0', letterSpacing: '.18em', fontSize: '0.95rem' }}>
                {busy ? '…' : mode === 'login' ? 'SIGN IN' : 'CREATE ACCOUNT'}
              </button>
              <div style={{ display: 'flex', gap: 8 }}>
                <button type="button" className="btn" onClick={google} disabled={busy} title="Available once Google sign-in is enabled on the server"
                  style={{ padding: '0.65rem 0', flex: 1 }}>
                  <b>G</b>&nbsp;&nbsp;Google
                </button>
                <button type="button" className="btn" onClick={discord} disabled={busy} title="Available once Discord sign-in is enabled on the server"
                  style={{ padding: '0.65rem 0', flex: 1 }}>
                  <b>D</b>&nbsp;&nbsp;Discord
                </button>
              </div>
              <div style={{ textAlign: 'center', fontSize: '0.85rem', color: 'var(--muted)', marginTop: 2 }}>
                {mode === 'login'
                  ? <>No account? <a style={{ color: 'var(--gold-hi)', cursor: 'pointer', textDecoration: 'underline' }} onClick={() => { setMode('register'); setError(null) }}>Create one</a></>
                  : <>Already climbing? <a style={{ color: 'var(--gold-hi)', cursor: 'pointer', textDecoration: 'underline' }} onClick={() => { setMode('login'); setError(null) }}>Sign in</a></>}
              </div>
            </form>

            {/* DEV ONLY — remove before launch (accounts become mandatory) */}
            <div className="ilm-title-actions" style={{ marginTop: '1.4rem' }}>
              <button className="btn" onClick={goOffline} style={{ padding: '0.7rem 1.8rem', border: '1px dashed rgba(184,151,98,.4)' }}>
                {serverDown ? 'World server unreachable — ' : ''}Play Offline
              </button>
            </div>
            <div style={{ textAlign: 'center', fontSize: '0.72rem', fontStyle: 'italic', color: 'var(--muted)', marginTop: 8, opacity: .8 }}>
              Offline keeps your full tower — arena, guilds and the wire stay dark until you sign in.
            </div>
          </>
        )}

        {phase === 'ready' && (
          <>
            <div className="ilm-title-selecthead">
              {identity?.online ? 'THE WORLD REMEMBERS' : 'CLIMBING ALONE'}
            </div>
            <div style={{ textAlign: 'center', margin: '0.4rem 0 1.4rem' }}>
              <span style={{ fontFamily: "'Cinzel',serif", fontWeight: 700, fontSize: '1.5rem', letterSpacing: '.12em', color: 'var(--text-hi)' }}>
                {identity?.online ? identity.username.toUpperCase() : 'OFFLINE CLIMBER'}
              </span>
              {!identity?.online && (
                <div style={{ fontSize: '0.8rem', fontStyle: 'italic', color: 'var(--muted)', marginTop: 6 }}>
                  World features stay dark. Your climb is your own.
                </div>
              )}
            </div>
            {error && <div style={{ color: 'var(--red-hi)', fontSize: '0.85rem', textAlign: 'center', marginBottom: '0.6rem' }}>{error}</div>}
            <div className="ilm-title-actions">
              <button className="btn btn-gold" disabled={busy} style={{ padding: '0.9rem 2.6rem', letterSpacing: '.24em', fontSize: '1rem' }} onClick={ascend}>
                {busy ? '…' : 'Press to Ascend'}
              </button>
              <button className="btn" disabled={busy} onClick={() => { clearArenaSession(); setIdentity(null); setPhase('form') }}>
                {identity?.online ? 'Log Out' : 'Sign In Instead'}
              </button>
            </div>
          </>
        )}

        <div className="ilm-title-version">EVERSPIRE · PRE-ALPHA</div>
      </div>
    </div>
  )
}
