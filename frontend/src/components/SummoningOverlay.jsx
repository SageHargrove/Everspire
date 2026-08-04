import React, { useState, useEffect, useCallback } from 'react'
import HeroCard from './HeroCard'
import { EquipmentTypeIcon } from './EquipmentTypeIcon'
import { playClick, playFlip, playRevealStinger, playArrayThud, playTakeover } from '../audio'

// ── Rarity → the RGB the revealed face is tinted with (mirrors index.css
// --star*; the card back is uniform, so rarity lives ONLY on the flipped face).
const STAR_RGB = {
  1: '255,255,255', 2: '77,255,77', 3: '30,144,255', 4: '184,77,255',
  5: '255,179,0', 6: '255,92,92', 7: '0,229,255',
}
// Equipment 24-letter grades → 8 tiers (D … Z). E/F are non-droppable starters.
function equipTier(rarity) {
  const r = rarity || 'D'
  if (r === 'Z') return 8
  if (r.startsWith('SSS')) return 7
  if (r.startsWith('SS')) return 6
  if (r.startsWith('S')) return 5
  if (r.startsWith('A')) return 4
  if (r.startsWith('B')) return 3
  if (r.startsWith('C')) return 2
  return 1
}
const EQUIP_RGB = {
  1: '216,216,216', 2: '77,192,106', 3: '79,146,232', 4: '160,90,238',
  5: '242,166,60', 6: '255,68,68', 7: '0,229,255', 8: '255,48,221',
}

function itemTier(item) {
  return item.is_equipment ? equipTier(item.rarity) : (item.birth_star || 1)
}
// A hero's 1-7 star tier is what drives the "how dramatic is the flip" scale.
// Equipment maps its 8 grade-tiers down onto the same 1-7 spin ladder.
function spinTier(item) {
  if (!item.is_equipment) return Math.min(7, Math.max(1, item.birth_star || 1))
  return Math.min(7, equipTier(item.rarity))  // Z(8) shares the 7-tier drama
}
function itemRGB(item) {
  return item.is_equipment ? (EQUIP_RGB[equipTier(item.rarity)] || '255,255,255')
                           : (STAR_RGB[item.birth_star] || '255,255,255')
}
// Is this the rainbow, mythic top grade? (hero 7★ / equipment Z)
function isMythic(item) {
  return item.is_equipment ? equipTier(item.rarity) === 8 : (item.birth_star || 1) >= 7
}

// The per-tier flip choreography the user asked for: 1-4★ all spin the SAME,
// then 5 / 6 / 7 each spin a little more dramatically than the last — more
// rotations, a longer, bouncier settle, a louder aura, and (7 only) a rainbow.
function flipFx(item) {
  const t = spinTier(item)
  const mythic = isMythic(item)
  // rotations: 1-4 → 540°, 5 → 720°, 6 → 900°, 7 → 1080°
  const spins = t <= 4 ? 540 : t === 5 ? 720 : t === 6 ? 900 : 1080
  const dur = t <= 4 ? 0.7 : t === 5 ? 1.0 : t === 6 ? 1.3 : 1.6
  // aura strength grows with tier; commons barely glow.
  const auraOpacity = t >= 4 ? 1 : t >= 2 ? 0.5 : 0.22
  const showRings = t >= 4  // orbiting reveal rings for the good pulls
  const rgb = itemRGB(item)
  return { t, mythic, spins, dur, auraOpacity, showRings, rgb }
}

// Card-back suite: ONE uniform back for every card (design: gold diamond over
// a violet hatch) — the FACE never leaks rarity. (For 5★+ a soft rarity glow
// deliberately bleeds from the card's EDGES before the flip — anticipation,
// see FlipCard — but the printed back itself stays identical for every pull.)
// Rendered from parts so it needs no art asset.
function CardBack() {
  return (
    <>
      <div style={{ position: 'absolute', inset: 6, border: '1px solid rgba(150,110,230,.35)', background: 'repeating-linear-gradient(45deg, rgba(150,110,230,.07) 0 10px, transparent 10px 20px)' }} />
      {/* soft light pooling high on the card — reads as lacquer, not flat ink */}
      <div style={{ position: 'absolute', inset: 6, pointerEvents: 'none', background: 'radial-gradient(70% 45% at 50% 24%, rgba(216,187,132,.1), transparent 70%)' }} />
      {/* embossed diamond sigil — nested outline + lit pip, stamped shadows */}
      <div style={{ position: 'relative', width: '30%', aspectRatio: '1', maxWidth: 54, transform: 'rotate(45deg)', border: '1px solid #b89762', boxShadow: 'inset 1px 1px 0 rgba(255,224,160,.28), inset -1px -1px 0 rgba(0,0,0,.55), 0 0 14px rgba(184,151,98,.22)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div style={{ position: 'absolute', inset: '14%', border: '1px solid rgba(184,151,98,.5)' }} />
        <div style={{ width: '30%', aspectRatio: '1', background: '#b89762', boxShadow: '0 0 8px rgba(216,187,132,.55)' }} />
      </div>
      {/* slow light band drifting across the whole back */}
      <div style={{ position: 'absolute', inset: 0, pointerEvents: 'none', background: 'linear-gradient(115deg, transparent 42%, rgba(216,187,132,.12) 50%, transparent 58%) 0 0 / 240% 100%', animation: 'sheen-sweep 5.5s linear infinite' }} />
    </>
  )
}

// Ember drift behind 7★/Z flips — hand-placed offsets (deterministic; a
// render-time random would reshuffle every re-render).
const EMBERS = [
  { left: '12%', dur: 2.6, delay: 0.0 }, { left: '30%', dur: 3.1, delay: 0.9 },
  { left: '46%', dur: 2.4, delay: 1.6 }, { left: '58%', dur: 3.4, delay: 0.4 },
  { left: '72%', dur: 2.8, delay: 2.1 }, { left: '86%', dur: 3.2, delay: 1.2 },
  { left: '22%', dur: 3.6, delay: 2.7 }, { left: '64%', dur: 2.5, delay: 3.1 },
]

// The revealed face — built from the design's anatomy: rarity-tinted frame,
// a "hero art" slot (real portrait when we have one), then stars + NAME + CLASS
// stacked at the foot. Equipment swaps stars for its grade letter.
function RevealedFace({ item, fx }) {
  const { rgb, mythic } = fx
  const frame = `rgba(${rgb},.85)`
  const cls = item.is_equipment ? (item.equipment_type || item.type || 'ARMAMENT') : (item.hero_class || '')
  const grade = item.is_equipment ? String(item.rarity || '') : null
  const stars = mythic ? '★★★★★★★' : '★'.repeat(spinTier(item))
  const starStyle = mythic
    ? { backgroundImage: 'linear-gradient(90deg,#ff5c5c,#ffb300,#4dff4d,#00e5ff,#b84dff,#ff5c5c)', backgroundSize: '200% auto', WebkitBackgroundClip: 'text', backgroundClip: 'text', color: 'transparent', animation: 'star-rainbow-slide 3s linear infinite' }
    : { color: `rgb(${rgb})`, textShadow: `0 0 9px rgba(${rgb},.7)` }
  return (
    <div style={{ position: 'absolute', inset: 0, border: `1px solid ${frame}`, background: 'linear-gradient(160deg,#1a1130,#0d0818)', boxShadow: fx.t >= 5 ? `0 0 26px rgba(${rgb},.5), inset 0 0 16px rgba(${rgb},.22)` : `inset 0 0 12px rgba(${rgb},.18)`, overflow: 'hidden' }}>
      {/* rainbow border for the mythic grade only */}
      {mythic && <div style={{ position: 'absolute', inset: -2, pointerEvents: 'none', background: 'conic-gradient(from 0deg,#ff5c5c,#ffb300,#4dff4d,#00e5ff,#b84dff,#ff5c5c)', animation: 'ov-hue 4s linear infinite' }} />}
      {mythic && <div style={{ position: 'absolute', inset: 1, background: 'linear-gradient(160deg,#1a1130,#0d0818)' }} />}
      <div style={{ position: 'absolute', inset: 5, border: `1px solid rgba(${rgb},.35)`, pointerEvents: 'none' }} />
      {/* rarity-tinted corner ticks framing the reveal */}
      <span className="ilm-corner" style={{ borderColor: `rgba(${rgb},.8)` }} />
      <span className="ilm-corner ilm-corner-r" style={{ borderColor: `rgba(${rgb},.8)` }} />
      <span className="ilm-corner ilm-corner-bl" style={{ borderColor: `rgba(${rgb},.8)` }} />
      <span className="ilm-corner ilm-corner-br" style={{ borderColor: `rgba(${rgb},.8)` }} />

      {/* art slot — fills the whole card (300×448 ≈ 2:3, matching the
          portrait) so the hero art is large; the name plate overlays the
          faded bottom instead of sitting below a big empty gap (Liam). */}
      <div style={{ position: 'absolute', left: 6, right: 6, top: 6, bottom: 6, overflow: 'hidden' }}>
        {item.is_equipment ? (
          <div style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', background: `radial-gradient(60% 55% at 50% 45%, rgba(${rgb},.18), rgba(0,0,0,0) 75%)` }}>
            <EquipmentTypeIcon item={item} fontSize="2.4rem" />
          </div>
        ) : item.portrait_path ? (
          <img src={`/${item.portrait_path}`} draggable={false} alt=""
            onError={(e) => { e.target.style.display = 'none' }}
            style={{ width: '100%', height: '100%', objectFit: 'cover', objectPosition: 'center top' }} />
        ) : (
          <div style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', background: `radial-gradient(60% 50% at 50% 40%, rgba(${rgb},.16), rgba(0,0,0,0) 75%)` }}>
            <span style={{ fontFamily: 'monospace', fontSize: '0.55rem', color: '#7a6f92' }}>hero art</span>
          </div>
        )}
        <div style={{ position: 'absolute', left: 0, right: 0, bottom: 0, height: '32%', background: 'linear-gradient(rgba(13,8,24,0),#150e28)' }} />
      </div>

      {/* stars / grade + name + class */}
      <div style={{ position: 'absolute', left: 4, right: 4, bottom: 8, textAlign: 'center' }}>
        {grade !== null ? (
          <div style={{ fontFamily: "'Cinzel',serif", fontWeight: 900, fontSize: '1rem', letterSpacing: '.1em', ...starStyle }}>{grade}</div>
        ) : (
          <div style={{ fontSize: '0.72rem', letterSpacing: '.12em', ...starStyle }}>{stars}</div>
        )}
        <div style={{ fontFamily: "'Cinzel',serif", fontWeight: 700, fontSize: '0.68rem', letterSpacing: '.05em', color: '#f3ecdd', marginTop: 3, lineHeight: 1.1 }}>{item.name}</div>
        <div style={{ fontFamily: "'Cinzel',serif", fontSize: '0.5rem', letterSpacing: '.2em', color: '#9a86b8', marginTop: 1 }}>{String(cls).toUpperCase()}</div>
      </div>
    </div>
  )
}

// A single 3D flip card. The rarity glow lives on a WRAPPER aura layer + the
// revealed face's box-shadow, NEVER a filter on the transformed card itself —
// a filter on the 3D element flattens preserve-3d and kills the flip.
// backface-visibility keeps the down/up faces from bleeding through.
function FlipCard({ item, flipped, onFlip, onInspect, width, height }) {
  const fx = flipFx(item)
  return (
    <div
      style={{ position: 'relative', width, height, perspective: 900, cursor: !flipped || onInspect ? 'pointer' : 'default' }}
      onClick={!flipped ? onFlip : onInspect}
      title={flipped && onInspect ? `Inspect ${item.name}` : undefined}
    >
      {/* pre-flip anticipation — for 5★+ the rarity glow leaks softly from the
          card's edges BEFORE the turn (the printed back stays uniform). */}
      {!flipped && fx.t >= 5 && (
        <div style={{ position: 'absolute', inset: -10, pointerEvents: 'none', background: `radial-gradient(62% 58% at 50% 50%, rgba(${fx.rgb},.26), rgba(0,0,0,0) 72%)`, animation: 'ov-aura 2.6s ease-in-out infinite' }} />
      )}
      {/* ember drift behind the mythic reveal */}
      {flipped && fx.mythic && EMBERS.map((e, i) => (
        <span key={`em${i}`} style={{ position: 'absolute', left: e.left, bottom: 4, width: 4, height: 4, borderRadius: '50%', background: '#ffd88a', boxShadow: '0 0 9px #e8a34c', opacity: 0, pointerEvents: 'none', animation: `ember-rise ${e.dur}s linear ${e.delay}s infinite` }} />
      ))}
      {/* reveal aura — fades in behind the card once flipped */}
      <div style={{ position: 'absolute', inset: -16, pointerEvents: 'none', opacity: flipped ? fx.auraOpacity : 0, transition: 'opacity .5s ease .3s', background: `radial-gradient(60% 55% at 50% 50%, rgba(${fx.rgb},${fx.t >= 5 ? 0.5 : 0.3}), rgba(0,0,0,0) 70%)`, animation: `ov-aura 3s ease-in-out infinite${fx.mythic ? ', ov-hue 5s linear infinite' : ''}` }} />
      {/* orbiting reveal rings for tier 4+ */}
      {flipped && fx.showRings && (
        <>
          <div style={{ position: 'absolute', left: '50%', top: '50%', width: height ? height * 0.78 : 168, height: height ? height * 0.78 : 168, borderRadius: '50%', pointerEvents: 'none', border: `1px solid rgba(${fx.rgb},.55)`, animation: `ov-ping 2.8s ease-out infinite${fx.mythic ? ', ov-hue 5s linear infinite' : ''}` }} />
          <div style={{ position: 'absolute', left: '50%', top: '50%', width: height ? height * 0.78 : 168, height: height ? height * 0.78 : 168, borderRadius: '50%', pointerEvents: 'none', border: `1px solid rgba(${fx.rgb},.55)`, animation: `ov-ping 2.8s ease-out 1.4s infinite${fx.mythic ? ', ov-hue 5s linear infinite' : ''}` }} />
        </>
      )}
      <div style={{
        position: 'relative', width: '100%', height: '100%', transformStyle: 'preserve-3d',
        transition: `transform ${fx.dur}s cubic-bezier(.3,1.2,.4,1)`,
        transform: flipped ? `rotateY(${fx.spins}deg)` : 'rotateY(0deg)',
      }}>
        {/* face-down — uniform, no rarity */}
        <div style={{ position: 'absolute', inset: 0, backfaceVisibility: 'hidden', WebkitBackfaceVisibility: 'hidden', border: '1px solid rgba(184,151,98,.6)', background: 'linear-gradient(160deg,#171028,#0c0716)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <CardBack />
        </div>
        {/* revealed */}
        <div style={{ position: 'absolute', inset: 0, backfaceVisibility: 'hidden', WebkitBackfaceVisibility: 'hidden', transform: 'rotateY(180deg)' }}>
          <RevealedFace item={item} fx={fx} />
        </div>
      </div>
    </div>
  )
}

// Single-pull reveal: one large card, auto-flips after a beat. Stays until NEXT.
function SingleReveal({ item, onDone, onInspect }) {
  const [flipped, setFlipped] = useState(false)
  const flip = useCallback(() => {
    setFlipped(f => { if (!f) { playFlip(); playRevealStinger(itemTier(item)) } return true })
  }, [item])
  useEffect(() => {
    if (!flipped) { const t = setTimeout(flip, 2200); return () => clearTimeout(t) }
  }, [flipped, flip])

  return (
    <div style={{ margin: 'auto', textAlign: 'center' }}>
      <FlipCard
        item={item}
        flipped={flipped}
        onFlip={flip}
        onInspect={!item.is_equipment && onInspect ? () => onInspect(item) : undefined}
        width={300}
        height={448}
      />
      {!flipped ? (
        <div className="tarot-hint" style={{ marginTop: '0.9rem' }}>Click to reveal</div>
      ) : (
        <div style={{ marginTop: '1.1rem', display: 'flex', flexDirection: 'column', gap: '0.5rem', alignItems: 'center' }}>
          {!item.is_equipment && (
            <div className="text-dim" style={{ fontSize: '0.72rem', fontFamily: 'Cinzel, serif', letterSpacing: '0.1em' }}>Click the card to inspect</div>
          )}
          <button className="ilm-btn ilm-btn-gold" onClick={onDone}>NEXT ›</button>
        </div>
      )}
    </div>
  )
}

// Multi-pull spread: every card dealt face-down in a 5-across grid. Click each
// or Reveal All. NEXT (gold) appears once every card is turned.
function TarotSpread({ results, onComplete, onInspect }) {
  const [flipped, setFlipped] = useState(() => new Set())
  useEffect(() => { playArrayThud() }, [])

  const keyOf = (item, i) => item.id ?? `i${i}`
  const allFlipped = flipped.size >= results.length
  const cols = Math.min(5, results.length)

  function flipOne(key, item) {
    playFlip(); playRevealStinger(itemTier(item))
    setFlipped(prev => new Set(prev).add(key))
  }
  function revealAll() {
    playFlip(); playRevealStinger(Math.max(...results.map(itemTier)))
    // stagger the turns so the array ripples open rather than snapping flat
    results.forEach((item, i) => setTimeout(() => setFlipped(prev => new Set(prev).add(keyOf(item, i))), i * 90))
  }

  return (
    <div style={{ position: 'relative', width: '100%', minHeight: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
      {/* header */}
      <div style={{ position: 'relative', zIndex: 2, textAlign: 'center', marginBottom: '1.4rem' }}>
        <div style={{ fontFamily: "'Cinzel',serif", letterSpacing: '.5em', fontSize: '0.66rem', color: 'var(--gold-hi)' }}>
          THE RITE IS CAST · ×{results.length}
        </div>
        <div style={{ fontFamily: "'Cinzel',serif", fontWeight: 900, fontSize: '1.9rem', color: 'var(--text-hi)', marginTop: 6 }}>
          TURN THE CARDS
        </div>
      </div>

      {/* 5-across grid */}
      <div style={{ display: 'grid', gridTemplateColumns: `repeat(${cols}, 150px)`, gap: '22px 18px', justifyContent: 'center', position: 'relative', zIndex: 2, padding: '0.5rem' }}>
        {results.map((item, i) => {
          const key = keyOf(item, i)
          return (
            <div key={key} style={{ animation: `ov-deal .5s cubic-bezier(.2,.9,.3,1) ${(0.06 + i * 0.05).toFixed(2)}s both` }}>
              <FlipCard
                item={item}
                flipped={flipped.has(key)}
                onFlip={() => flipOne(key, item)}
                onInspect={!item.is_equipment && onInspect ? () => onInspect(item) : undefined}
                width={150}
                height={224}
              />
            </div>
          )
        })}
      </div>

      {/* actions */}
      <div style={{ position: 'relative', zIndex: 2, marginTop: '1.5rem', display: 'flex', gap: '0.9rem', alignItems: 'center' }}>
        {!allFlipped ? (
          <>
            <button className="ilm-btn ilm-btn-violet" onClick={revealAll}>REVEAL ALL</button>
            {flipped.size > 0 && <button className="ilm-btn ilm-btn-ghost" onClick={() => setFlipped(new Set())}>RESET</button>}
            <span className="text-dim" style={{ fontFamily: "'Cinzel',serif", letterSpacing: '0.14em', fontSize: '0.78rem' }}>{flipped.size} / {results.length} REVEALED</span>
          </>
        ) : (
          <>
            <button className="ilm-btn ilm-btn-ghost" onClick={() => setFlipped(new Set())}>RESET</button>
            <button className="ilm-btn ilm-btn-gold" onClick={onComplete}>NEXT ›</button>
          </>
        )}
      </div>
    </div>
  )
}

export default function SummoningOverlay({ results, onComplete }) {
  const isSpread = results.length > 1
  const [inspectHero, setInspectHero] = useState(null)

  // MUSICAL TAKEOVER: if this batch's best pull is 6★+ (hero) / top-grade
  // equipment, the full hype track seizes the audio for the whole reveal —
  // one per event, persists even if the player navigates away.
  useEffect(() => {
    if (results?.length && Math.max(...results.map(itemTier)) >= 6) playTakeover('6_star_pull')
  }, [])

  return (
    <div style={{
      position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
      background:
        'radial-gradient(80% 70% at 50% 30%, rgba(96,42,168,.3), rgba(0,0,0,0) 60%),' +
        'radial-gradient(140% 120% at 50% 120%, #0d0818, #08060e 72%)',
      backgroundColor: '#08060e', zIndex: 9999,
      display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
      overflowY: 'auto', padding: '2rem 0',
    }}>
      <button className="ilm-btn ilm-btn-ghost" onClick={onComplete} style={{ position: 'absolute', top: 20, right: 20, zIndex: 10000 }}>
        SKIP ALL ⏭
      </button>

      {isSpread ? (
        <TarotSpread results={results} onComplete={onComplete} onInspect={setInspectHero} />
      ) : results.length === 1 ? (
        <SingleReveal item={results[0]} onDone={onComplete} onInspect={setInspectHero} />
      ) : null}

      {inspectHero && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.88)', zIndex: 10001, display: 'flex', alignItems: 'center', justifyContent: 'center', backdropFilter: 'blur(4px)' }} onClick={() => setInspectHero(null)}>
          <div style={{ width: 1000, maxWidth: '95vw', maxHeight: '90vh', overflowY: 'auto', borderRadius: 8 }} onClick={e => e.stopPropagation()}>
            <HeroCard hero={inspectHero} showFull={true} />
          </div>
        </div>
      )}

      <style>{`
        @keyframes ov-aura { 0%,100% { opacity:.55; transform:scale(1) } 50% { opacity:1; transform:scale(1.07) } }
        @keyframes ov-ping { 0% { transform:translate(-50%,-50%) scale(.5); opacity:.75 } 100% { transform:translate(-50%,-50%) scale(1.22); opacity:0 } }
        @keyframes ov-hue { to { filter:hue-rotate(360deg) } }
        @keyframes ov-deal { from { opacity:0; transform:translateY(26px) rotate(3deg) } to { opacity:1; transform:translateY(0) rotate(0) } }
        @keyframes star-rainbow-slide { from { background-position:0% center } to { background-position:-200% center } }
        .tarot-hint { text-align:center; font-family:'Cinzel',serif; font-size:0.75rem; letter-spacing:0.2em; color:rgba(255,255,255,0.75); animation: ov-hint 1.6s ease-in-out infinite; }
        @keyframes ov-hint { 0%,100% { opacity:0.5 } 50% { opacity:1 } }
      `}</style>
    </div>
  )
}
