import React, { useState, useEffect } from 'react'
import { getLore } from '../api/client'
import Sigil from './Sigil'

// Renders as either an inline section (inline=true, for BasePage tab) or
// a modal overlay (default, for any direct call with onClose).
export default function LoreJournal({ onClose, inline = false }) {
  const [entries, setEntries] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    getLore().then(res => setEntries(res.entries)).catch(e => setError(e.message))
  }, [])

  const content = (
    <div style={inline ? {} : { position: 'relative', background: 'linear-gradient(160deg,#160d27,#0b0716)', border: '1px solid rgba(184,151,98,.55)', clipPath: 'polygon(0 0,100% 0,100% 100%,16px 100%)', padding: '1.5rem', maxWidth: '90vw', maxHeight: '85vh', overflow: 'auto', minWidth: '500px', width: '620px', boxShadow: '0 30px 90px rgba(0,0,0,.75)' }}>
      {!inline && (
        <>
          <span className="ilm-corner" /><span className="ilm-corner ilm-corner-r" />
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.2rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <span style={{ width: 7, height: 7, transform: 'rotate(45deg)', background: 'var(--gold)', display: 'inline-block' }} />
              <span style={{ fontFamily: "'Cinzel',serif", fontWeight: 900, fontSize: '1.2rem', letterSpacing: '.08em', color: 'var(--text-hi)' }}>THE LORE JOURNAL</span>
            </div>
            <button className="ilm-close" onClick={onClose}>✕</button>
          </div>
        </>
      )}

      {error && <div className="text-dim" style={{ color: 'var(--red)' }}>{error}</div>}

      {entries === null && !error && (
        <div className="text-dim" style={{ fontStyle: 'italic' }}>Reading...</div>
      )}

      {entries && entries.length === 0 && (
        <div className="empty-state" style={{ padding: '3rem 2rem' }}>
          <div className="empty-state-icon"><Sigil set="ui" name="codex" size={40} color="var(--gold-dim)" fallback={<span style={{ color: 'var(--gold-dim)' }}>✦</span>} /></div>
          <div className="empty-state-title">The Journal Is Blank</div>
          <div className="empty-state-hint">
            A new page is written every 10 floors, drawn from what your team actually fought
            and chose along the way. Clear Floor 10 to unlock the first entry.
          </div>
        </div>
      )}

      {entries && entries.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.2rem' }}>
          {entries.slice().reverse().map(e => (
            <div key={e.milestone} style={{
              background: 'linear-gradient(160deg, rgba(201,168,76,0.06), rgba(12,7,24,0.5))',
              border: '1px solid rgba(184,151,98,0.28)',
              borderLeft: '2px solid var(--gold)',
              clipPath: 'polygon(0 0,100% 0,100% 100%,12px 100%)',
              padding: '1.3rem 1.5rem',
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: '0.7rem' }}>
                <div style={{ fontFamily: 'Cinzel, serif', fontWeight: 700, color: 'var(--gold-hi)', fontSize: '1.1rem', letterSpacing: '0.04em' }}>{e.title}</div>
                <div style={{ fontFamily: "'Cinzel',serif", fontSize: '0.56rem', color: '#120c04', background: 'var(--gold)', padding: '0.15rem 0.7rem', letterSpacing: '0.14em', textTransform: 'uppercase', whiteSpace: 'nowrap', clipPath: 'polygon(5px 0,100% 0,calc(100% - 5px) 100%,0 100%)' }}>
                  Floor {e.milestone}
                </div>
              </div>
              <div style={{ lineHeight: 1.75, fontStyle: 'italic', color: 'var(--text-hi)', fontSize: '1.02rem' }}>{e.text}</div>
              <div style={{ textAlign: 'center', color: 'var(--gold-dim)', marginTop: '0.9rem', fontSize: '0.9rem' }}>❦</div>
            </div>
          ))}
        </div>
      )}
    </div>
  )

  if (inline) return content

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.75)', zIndex: 100, display: 'flex', alignItems: 'center', justifyContent: 'center' }} onClick={onClose}>
      <div onClick={e => e.stopPropagation()}>{content}</div>
    </div>
  )
}
