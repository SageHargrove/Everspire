/*
 * RIDE THE BLACK WATER — the sea band's traversal minigame.
 *
 * Leviathan's Graveyard is a wreck field. You are not fighting here; you are
 * getting the squad through it intact, and how well you do sets the condition
 * the fight starts in.
 *
 * MOMENTUM, not aim. The current pushes constantly; gaps between hulls open
 * and close on their own rhythm. Holding the line builds speed, and speed is
 * what carries you through a closing gap — but a bad entry kills it and you
 * rebuild from nothing. Chaining clean passages is the whole skill, which is
 * why a steady hand beats a fast one.
 *
 * Score = distance covered against the distance a perfect run would cover,
 * handed back to MinigameShell as 0..1 the same way every other game here does.
 */
import React, { useState, useRef, useEffect } from 'react'
import { playClick, playDeedChime } from '../../audio'

// Higher tiers: gaps are tighter and drift harder, so holding a line costs
// more attention. Speed decay is what punishes a miss — on LEGENDARY a single
// bad passage wipes most of what you'd banked.
const TUNING = {
  novice:     { gap: 0.34, drift: 0.28, decay: 0.55, gapSpeed: 0.55, need: 6 },
  apprentice: { gap: 0.29, drift: 0.36, decay: 0.50, gapSpeed: 0.70, need: 7 },
  adept:      { gap: 0.24, drift: 0.46, decay: 0.44, gapSpeed: 0.85, need: 8 },
  expert:     { gap: 0.19, drift: 0.58, decay: 0.36, gapSpeed: 1.05, need: 9 },
  master:     { gap: 0.15, drift: 0.72, decay: 0.28, gapSpeed: 1.25, need: 10 },
  legendary:  { gap: 0.11, drift: 0.90, decay: 0.18, gapSpeed: 1.5,  need: 12 },
}

const MAX_SPEED = 1.0
const SPEED_GAIN = 0.34          // per clean passage
const RUN_SECONDS = 22

export default function SeaTraversal({ difficulty, onDone }) {
  const t = TUNING[difficulty] || TUNING.adept

  const [boat, setBoat] = useState(0.5)      // 0..1 across the channel
  const [gapCenter, setGapCenter] = useState(0.5)
  const [speed, setSpeed] = useState(0.25)
  const [passed, setPassed] = useState(0)
  const [wrecked, setWrecked] = useState(0)
  const [distance, setDistance] = useState(0)
  const [timeLeft, setTimeLeft] = useState(RUN_SECONDS)
  const [done, setDone] = useState(false)

  // Refs mirror state for the animation loop — reading state inside rAF gets
  // you the value from the frame the closure was made in, not the live one.
  const boatRef = useRef(0.5)
  const gapRef = useRef(0.5)
  const speedRef = useRef(0.25)
  const distRef = useRef(0)
  const heldRef = useRef(0)                  // -1 left, +1 right, 0 released
  const gapPhase = useRef(Math.PI / 3)
  const passLatch = useRef(false)            // one score event per gap crossing
  const raf = useRef(null)
  const doneRef = useRef(false)

  useEffect(() => {
    const onKey = (e, down) => {
      if (e.key === 'ArrowLeft' || e.key === 'a') heldRef.current = down ? -1 : 0
      if (e.key === 'ArrowRight' || e.key === 'd') heldRef.current = down ? 1 : 0
    }
    const kd = (e) => onKey(e, true)
    const ku = (e) => onKey(e, false)
    window.addEventListener('keydown', kd)
    window.addEventListener('keyup', ku)
    return () => { window.removeEventListener('keydown', kd); window.removeEventListener('keyup', ku) }
  }, [])

  useEffect(() => {
    let last = performance.now()
    const start = last

    const tick = (now) => {
      const dt = Math.min(0.05, (now - last) / 1000)
      last = now

      // The gap wanders on its own rhythm — two summed sines so it never
      // settles into a loop the player can memorise instead of read.
      gapPhase.current += dt * t.gapSpeed
      const g = 0.5 + 0.34 * Math.sin(gapPhase.current) + 0.10 * Math.sin(gapPhase.current * 2.3)
      const gc = Math.max(0.12, Math.min(0.88, g))
      gapRef.current = gc
      setGapCenter(gc)

      // Steering fights a constant current. Letting go doesn't hold position;
      // it drifts, which is what makes a long clean line an actual skill.
      const steer = heldRef.current * 0.85
      const current = Math.sin(gapPhase.current * 0.7) * t.drift * 0.35
      let b = boatRef.current + (steer + current) * dt
      b = Math.max(0, Math.min(1, b))
      boatRef.current = b
      setBoat(b)

      // Crossing the gap line: score once per crossing.
      const offset = Math.abs(b - gc)
      const inGap = offset <= t.gap / 2
      if (!passLatch.current && inGap) {
        passLatch.current = true
        // Dead-centre passages bank more speed than scraping the edge.
        const quality = 1 - (offset / (t.gap / 2))
        speedRef.current = Math.min(MAX_SPEED, speedRef.current + SPEED_GAIN * (0.45 + 0.55 * quality))
        setSpeed(speedRef.current)
        setPassed((p) => p + 1)
        try { playClick() } catch {}
      } else if (passLatch.current && offset > t.gap * 0.9) {
        passLatch.current = false
      }

      // Off the line entirely — you're grinding a hull. Bleed speed.
      if (offset > t.gap) {
        const before = speedRef.current
        speedRef.current = Math.max(0.05, speedRef.current - t.decay * dt)
        setSpeed(speedRef.current)
        if (before > 0.4 && speedRef.current <= 0.4) setWrecked((w) => w + 1)
      }

      distRef.current += speedRef.current * dt
      setDistance(distRef.current)

      const elapsed = (now - start) / 1000
      setTimeLeft(Math.max(0, RUN_SECONDS - elapsed))
      if (elapsed >= RUN_SECONDS) return finish()

      raf.current = requestAnimationFrame(tick)
    }

    const finish = () => {
      if (doneRef.current) return
      doneRef.current = true
      setDone(true)
      // A perfect run holds MAX_SPEED throughout. Scoring against that rather
      // than against a fixed target means the tuning table only has to make
      // holding the line harder — it never has to restate what "good" is.
      const perfect = MAX_SPEED * RUN_SECONDS
      const raw = distRef.current / perfect
      const score = Math.max(0, Math.min(1, raw))
      try { if (score >= 0.7) playDeedChime() } catch {}
      setTimeout(() => onDone(score), 650)
    }

    raf.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf.current)
  }, [t])

  const press = (dir) => { heldRef.current = dir }
  const release = () => { heldRef.current = 0 }

  const gapLeft = Math.max(0, gapCenter - t.gap / 2)
  const gapWidth = t.gap
  const onLine = Math.abs(boat - gapCenter) <= t.gap / 2

  return (
    <div style={{ marginTop: 18 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontFamily: "'Cinzel',serif", fontSize: 10, letterSpacing: '.16em', color: 'var(--muted)' }}>
        <span>PASSAGES {passed}{t.need ? ` / ${t.need}` : ''}</span>
        <span style={{ color: speed > 0.7 ? 'var(--green-hi)' : speed < 0.3 ? 'var(--red-hi)' : 'var(--muted)' }}>
          WAY {Math.round(speed * 100)}%
        </span>
        <span>{timeLeft.toFixed(1)}s</span>
      </div>

      {/* The channel. The lit band is the gap between hulls; the marker is you. */}
      <div style={{ position: 'relative', height: 92, marginTop: 8, background: 'linear-gradient(180deg, #05040c, #0b0a1c)', border: '1px solid rgba(184,151,98,.3)', overflow: 'hidden' }}>
        <div style={{ position: 'absolute', inset: 0, background: 'repeating-linear-gradient(90deg, rgba(120,150,200,.05) 0 2px, transparent 2px 26px)' }} />
        <div style={{ position: 'absolute', top: 0, bottom: 0, left: `${gapLeft * 100}%`, width: `${gapWidth * 100}%`, background: onLine ? 'rgba(80,200,160,.20)' : 'rgba(150,110,230,.13)', borderLeft: '1px solid rgba(150,190,230,.45)', borderRight: '1px solid rgba(150,190,230,.45)', transition: 'background .12s' }} />
        <div style={{ position: 'absolute', top: '50%', left: `${boat * 100}%`, width: 12, height: 30, transform: 'translate(-50%,-50%) rotate(45deg)', background: onLine ? 'var(--green-hi)' : 'var(--gold-hi)', boxShadow: onLine ? '0 0 14px rgba(80,200,160,.7)' : '0 0 10px rgba(184,151,98,.5)' }} />
        <div style={{ position: 'absolute', left: 0, right: 0, bottom: 0, height: 3, background: 'rgba(184,151,98,.2)' }}>
          <div style={{ height: '100%', width: `${Math.min(100, (distance / (MAX_SPEED * RUN_SECONDS)) * 100)}%`, background: 'var(--gold-hi)' }} />
        </div>
      </div>

      <div style={{ display: 'flex', gap: 10, marginTop: 12 }}>
        <button className="btn" style={{ flex: 1, padding: '14px 0', fontSize: 20, cursor: 'pointer' }}
          onMouseDown={() => press(-1)} onMouseUp={release} onMouseLeave={release}
          onTouchStart={(e) => { e.preventDefault(); press(-1) }} onTouchEnd={release}>◀</button>
        <button className="btn" style={{ flex: 1, padding: '14px 0', fontSize: 20, cursor: 'pointer' }}
          onMouseDown={() => press(1)} onMouseUp={release} onMouseLeave={release}
          onTouchStart={(e) => { e.preventDefault(); press(1) }} onTouchEnd={release}>▶</button>
      </div>

      <div className="text-dim" style={{ fontSize: '.7rem', fontStyle: 'italic', marginTop: 8, textAlign: 'center' }}>
        {done ? 'The wreck field falls behind.'
              : wrecked > 0 ? 'Hulls scrape. Hold the line — speed is what carries you through.'
              : 'Hold the lit water. Momentum builds while you stay on it.'}
      </div>
    </div>
  )
}
