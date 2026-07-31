import React, { useState, useEffect } from 'react'
import { listHeroes, revealHeroTalent } from '../api/client'
import MinigameShell, { AUTO_RESOLVE_MULT } from './minigames/MinigameShell'
import MirrorGlimpse from './minigames/MirrorGlimpse'

// Inline panel rendered inside the Mirror of Fate FACILITY card on the
// Base page (it used to be a standalone base-upgrade card). Reveal detail
// scales with the facility's level: Lv1-4 vague tier, Lv5-9 numeric range,
// Lv10+ the exact number — mirrors routers/base.py reveal_hero_talent.
export default function MirrorOfFate({ level, gold, onGoldChange }) {
  const [heroes, setHeroes] = useState([])
  const [loading, setLoading] = useState(true)
  const [selectedId, setSelectedId] = useState('')
  const [revealing, setRevealing] = useState(false)
  const [msg, setMsg] = useState(null)

  useEffect(() => { refresh() }, [])

  async function refresh() {
    setLoading(true)
    try {
      const all = await listHeroes(true)
      setHeroes(all)
    } catch (e) {
      setMsg(e.message)
    } finally {
      setLoading(false)
    }
  }

  const selected = heroes.find(h => h.id === parseInt(selectedId))
  const cost = selected ? (selected.current_star || selected.birth_star) * 500 : 0

  // READ THE GLASS — the reveal opens the recognition minigame; a clean
  // reading discounts the Mirror's price (x3 = a third), a clouded one
  // spends a fifth of it for nothing.
  const [showGlass, setShowGlass] = useState(false)

  function handleReveal() { if (selected) setShowGlass(true) }

  async function doReveal(mult) {
    setShowGlass(false)
    setRevealing(true)
    setMsg(null)
    try {
      const res = await revealHeroTalent(selected.id, mult)
      if (res.clouded) {
        setMsg(res.message || 'The glass clouds over — the offering is spent.')
      } else {
        setHeroes(prev => prev.map(h => h.id === selected.id ? { ...h, talent_reveal: res.talent_reveal } : h))
        if (res.base_cost && res.gold_spent < res.base_cost) setMsg(`A clean reading — the Mirror asked only ${res.gold_spent.toLocaleString()}g of its ${res.base_cost.toLocaleString()}g price.`)
        else if (res.base_cost && res.gold_spent > res.base_cost) setMsg(`A murky reading — the Mirror demanded ${res.gold_spent.toLocaleString()}g for its trouble.`)
      }
      if (onGoldChange) onGoldChange()
    } catch (e) {
      setMsg(e.message)
    } finally {
      setRevealing(false)
    }
  }

  return (
    <div style={{ marginTop: '1rem', background: 'rgba(0,0,0,0.2)', padding: '0.75rem', borderRadius: 6 }}>
      <div className="text-dim text-sm" style={{ marginBottom: '0.75rem', lineHeight: 1.4 }}>
        Pay gold to instantly reveal a hero's hidden Talent.
        {level < 5 && ' Currently reveals a vague tier (Poor/Average/Good/Exceptional) — upgrade to Lv.5 for a numeric range, Lv.10 for the exact number.'}
        {level >= 5 && level < 10 && ' Currently reveals a numeric range — upgrade to Lv.10 for the exact number.'}
        {level >= 10 && ' Reveals the exact number.'}
      </div>

      {msg && <div style={{ color: '#f87', fontSize: '0.85rem', marginBottom: '0.75rem' }}>{msg}</div>}

      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.5rem', alignItems: 'flex-start' }}>
        <select
          value={selectedId}
          onChange={e => setSelectedId(e.target.value)}
          className="input"
          style={{ flex: 1 }}
        >
          <option value="">Select a hero to reveal...</option>
          {heroes.map(h => {
            const displayInfo = h.talent_reveal ? ` - ${h.talent_reveal}` : ' - Unrevealed'
            return <option key={h.id} value={h.id}>{h.name} ({h.class_name}){displayInfo}</option>
          })}
        </select>
        {selected && !selected.talent_reveal && (
           <button className="btn btn-gold" disabled={revealing || gold < cost} onClick={handleReveal}>
              {revealing ? 'Awakening...' : `Awaken (${cost}g)`}
           </button>
        )}
      </div>

      {selected && selected.talent_reveal && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.2rem' }}>
          <div className="text-hi" style={{ fontFamily: 'Cinzel, serif' }}>{selected.name}</div>
          <div style={{ fontSize: '1.1rem', color: 'var(--gold)' }}>{selected.talent_reveal}</div>
          <div className="text-dim text-sm">Already revealed — frozen at the Mirror's level when revealed.</div>
        </div>
      )}

      {showGlass && selected && (
        <MinigameShell
          title="READ THE GLASS"
          flavor={`The Mirror will show ${selected.name}'s truth — for a price the reading itself decides. A clean read pays a fraction; a clouded one pays for nothing.`}
          onSkip={(mult) => doReveal(mult)}
          onResolve={(mult) => doReveal(mult)}
          game={(difficulty, onDone) => <MirrorGlimpse difficulty={difficulty} onDone={onDone} />}
        />
      )}
    </div>
  )
}
