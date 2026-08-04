/*
 * ILLUMINATED KIT — per-page background ornaments.
 *
 * MODEST + VARIED (per feedback). A single faint diagonal hairline wash sets
 * the manuscript tone; on top of it a SMALL, seeded scatter of mixed motifs —
 * a couple of rotated diamonds, an upright square or two, a few ✦ sparkles, a
 * lone accent hairline — gives each screen some life without turning into a
 * dense lattice. Low counts, low alpha; the point is variety, not volume.
 */
import React, { useMemo } from 'react'

// Tiny deterministic PRNG (mulberry32) seeded from a string.
function rng(seedStr) {
  let h = 1779033703 ^ seedStr.length
  for (let i = 0; i < seedStr.length; i++) {
    h = Math.imul(h ^ seedStr.charCodeAt(i), 3432918353)
    h = (h << 13) | (h >>> 19)
  }
  let a = h >>> 0
  return () => {
    a |= 0; a = (a + 0x6D2B79F5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

const GOLD = a => `rgba(184,151,98,${a})`
const VIOLET = a => `rgba(150,110,230,${a})`

// Background variants for Liam to A/B live (Settings → BACKGROUND). The
// sparkles + diagonal lines are loved and stay in every variant; what
// changes is the "shapes" layer he isn't sold on.
//   manuscript    — the current look: big diamond/square outlines
//   starfield     — no shapes at all, just a denser sparkle scatter
//   constellation — sparkle clusters joined by faint hairlines
//   pips          — tiny filled diamond pips (brand-mark motif), no outlines
//   watermark     — one enormous ghost outline WORD per screen, bled off the
//                   bottom-right (same stroke language as the title stacks and
//                   the summon gate's 7/Z watermark)
//   rings         — concentric nested-diamond rings anchored in the dead
//                   corners; the gate's ring motif as page furniture
export const BG_VARIANTS = [
  ['manuscript', 'MANUSCRIPT'],
  ['starfield', 'STARFIELD'],
  ['constellation', 'CONSTELLATION'],
  ['pips', 'PIPS'],
  ['watermark', 'WATERMARK'],
  ['rings', 'RINGS'],
]

// The ghost word each screen carries. Echoes the word already sitting behind
// that page's own title stack (ROSTER over LEGION, VAULT over ARSENAL…), so
// the watermark reads as the same voice rather than a new label.
const WATERMARK_WORDS = {
  summon: 'GATE', heroes: 'LEGION', inventory: 'ARSENAL', tower: 'ASCENT',
  arena: 'WORLD', achievements: 'DEEDS', base: 'HAVEN', more: 'ARCHIVE',
  log: 'CHRONICLE',
}

export default function Ornaments({ seed = 'page', variant = 'manuscript' }) {
  const bits = useMemo(() => {
    const r = rng(seed + ':' + variant)
    const pick = arr => arr[Math.floor(r() * arr.length)]
    const spread = () => ({ left: `${Math.round(6 + r() * 86)}%`, top: `${Math.round(6 + r() * 84)}%` })

    const mkSpark = () => ({
      ...spread(), char: pick(['✦', '✧', '✦']), size: Math.round(9 + r() * 9),
      color: (r() < 0.5 ? 'rgba(200,169,245,' : 'rgba(216,187,132,') + (0.3 + r() * 0.25) + ')',
      dur: (3.5 + r() * 3).toFixed(1), delay: (r() * 3).toFixed(1),
    })
    const mkLine = () => ({
      ...spread(), len: Math.round(120 + r() * 220), rot: Math.round(-70 + r() * 40),
      color: (r() < 0.5 ? GOLD : VIOLET)(0.1 + r() * 0.06),
    })

    let diamonds = [], squares = [], pips = [], constellations = []
    let watermark = null, ringSets = []
    let sparkCount = 4
    let lineCount = 1 + Math.floor(r() * 2)

    if (variant === 'manuscript') {
      // 2-3 rotated diamond outlines — large, faint, spread; ~half nested.
      diamonds = Array.from({ length: 2 + Math.floor(r() * 2) }, () => {
        const size = Math.round(180 + r() * 300)
        return { ...spread(), size, nested: r() < 0.45, color: (r() < 0.5 ? GOLD : VIOLET)(0.05 + r() * 0.04) }
      })
      // 1-2 upright squares (axis-aligned) — a different shape for variety.
      squares = Array.from({ length: 1 + Math.floor(r() * 2) }, () => {
        const size = Math.round(90 + r() * 150)
        return { ...spread(), size, color: (r() < 0.5 ? GOLD : VIOLET)(0.045 + r() * 0.035) }
      })
    } else if (variant === 'starfield') {
      sparkCount = 11
      lineCount = 2
    } else if (variant === 'constellation') {
      // 3 clusters of 3-4 stars, each joined by faint hairlines.
      sparkCount = 3
      constellations = Array.from({ length: 3 }, () => {
        const cx = 10 + r() * 76, cy = 10 + r() * 74
        const stars = Array.from({ length: 3 + Math.floor(r() * 2) }, () => ({
          x: cx + (r() - 0.5) * 16, y: cy + (r() - 0.5) * 14,
          size: Math.round(8 + r() * 8),
          color: (r() < 0.5 ? 'rgba(200,169,245,' : 'rgba(216,187,132,') + (0.35 + r() * 0.25) + ')',
          dur: (3.5 + r() * 3).toFixed(1), delay: (r() * 3).toFixed(1),
        }))
        return { stars, lineColor: (r() < 0.5 ? GOLD : VIOLET)(0.14 + r() * 0.06) }
      })
    } else if (variant === 'pips') {
      sparkCount = 5
      pips = Array.from({ length: 8 }, () => ({
        ...spread(), size: Math.round(4 + r() * 6),
        color: (r() < 0.5 ? GOLD : VIOLET)(0.14 + r() * 0.12),
      }))
    } else if (variant === 'watermark') {
      // One huge stroked word sitting in the BOTTOM BAND. That band is the
      // only region empty on every screen — the vault/base/social pages all
      // carry a full-height panel on the right, so a corner-anchored mark
      // just hides behind it. Stroke-only, so it can't fight the wash.
      sparkCount = 5
      watermark = { word: WATERMARK_WORDS[seed] || 'GILTGRAVE', size: 210 }
    } else if (variant === 'rings') {
      // A horizon of nested-diamond arcs rising out of the bottom edge —
      // one great crown flanked by two satellites, all anchored below 100%
      // so only their upper arcs show. Reads as a fragment of something
      // larger under the floor rather than a logo dropped on the page.
      sparkCount = 5
      lineCount = 1
      // Alpha runs well above the manuscript diamonds' 0.05-0.09: those sit
      // mid-canvas where the violet bloom lifts them, while these arcs cross
      // the darkest part of the page gradient and vanish at that alpha.
      ringSets = [
        { left: '50%', top: '117%', size: 1120, rings: 5, pip: false, color: GOLD(0.26) },
        { left: '15%', top: '112%', size: 440, rings: 3, pip: false, color: VIOLET(0.24) },
        { left: '85%', top: '112%', size: 440, rings: 3, pip: false, color: VIOLET(0.24) },
      ]
    }

    const sparks = Array.from({ length: sparkCount }, mkSpark)
    const lines = Array.from({ length: lineCount }, mkLine)
    return { diamonds, squares, pips, constellations, sparks, lines, watermark, ringSets }
  }, [seed, variant])

  return (
    <div aria-hidden style={{ position: 'fixed', inset: 0, pointerEvents: 'none', overflow: 'hidden', zIndex: 0 }}>
      {/* faint single-direction diagonal wash — the quiet base tone */}
      <div style={{
        position: 'absolute', inset: 0,
        background: 'repeating-linear-gradient(64deg, rgba(184,151,98,.028) 0 1px, transparent 1px 190px)',
      }} />
      {/* enormous ghost word across the bottom band */}
      {bits.watermark && (
        <div style={{
          position: 'absolute', left: '50%', bottom: 54, transform: 'translateX(-50%)',
          fontFamily: "'Cinzel', serif", fontWeight: 900,
          fontSize: bits.watermark.size, lineHeight: 0.78, letterSpacing: '0.16em',
          color: 'transparent', WebkitTextStroke: '1px rgba(150,110,230,.17)',
          whiteSpace: 'nowrap', userSelect: 'none',
        }}>{bits.watermark.word}</div>
      )}
      {/* concentric nested-diamond rings */}
      {bits.ringSets.map((rs, i) => (
        <div key={`rg${i}`} style={{
          position: 'absolute', left: rs.left, top: rs.top,
          width: rs.size, height: rs.size,
          transform: 'translate(-50%,-50%) rotate(45deg)',
        }}>
          {Array.from({ length: rs.rings }).map((_, k) => (
            <div key={k} style={{ position: 'absolute', inset: Math.round(rs.size * 0.115 * k), border: `1px solid ${rs.color}` }} />
          ))}
          {rs.pip && (
            <div style={{
              position: 'absolute', left: '50%', top: '50%', width: 12, height: 12,
              transform: 'translate(-50%,-50%)', background: rs.color,
            }} />
          )}
        </div>
      ))}
      {/* rotated diamond outlines */}
      {bits.diamonds.map((d, i) => (
        <div key={`d${i}`} style={{ position: 'absolute', left: d.left, top: d.top, width: d.size, height: d.size, transform: 'rotate(45deg)', border: `1px solid ${d.color}` }}>
          {d.nested && <div style={{ position: 'absolute', inset: Math.round(d.size * 0.08), border: `1px solid ${d.color}` }} />}
        </div>
      ))}
      {/* upright squares */}
      {bits.squares.map((s, i) => (
        <div key={`q${i}`} style={{ position: 'absolute', left: s.left, top: s.top, width: s.size, height: s.size, border: `1px solid ${s.color}` }} />
      ))}
      {/* filled diamond pips (pips variant) */}
      {bits.pips.map((p, i) => (
        <div key={`p${i}`} style={{ position: 'absolute', left: p.left, top: p.top, width: p.size, height: p.size, transform: 'rotate(45deg)', background: p.color }} />
      ))}
      {/* constellation clusters (constellation variant) */}
      {bits.constellations.map((c, ci) => (
        <React.Fragment key={`c${ci}`}>
          {c.stars.map((s, si) => {
            const next = c.stars[si + 1]
            return (
              <React.Fragment key={si}>
                {next && (() => {
                  const dx = next.x - s.x, dy = next.y - s.y
                  // % coords → approximate px angle/length on a 16:9 canvas
                  const lenPct = Math.sqrt(dx * dx * 1 + dy * dy * (9 / 16) * (9 / 16))
                  const ang = Math.atan2(dy * (9 / 16), dx) * 180 / Math.PI
                  return <div style={{ position: 'absolute', left: `${s.x}%`, top: `${s.y}%`, width: `${lenPct}%`, height: 1, transform: `rotate(${ang}deg)`, transformOrigin: 'left center', background: `linear-gradient(90deg,transparent,${c.lineColor},transparent)` }} />
                })()}
                <span style={{ position: 'absolute', left: `${s.x}%`, top: `${s.y}%`, fontSize: s.size, lineHeight: 1, transform: 'translate(-50%,-50%)', color: s.color, animation: `orn-twinkle ${s.dur}s ease-in-out ${s.delay}s infinite` }}>✦</span>
              </React.Fragment>
            )
          })}
        </React.Fragment>
      ))}
      {/* accent hairlines on top of the wash */}
      {bits.lines.map((l, i) => (
        <div key={`l${i}`} style={{ position: 'absolute', left: l.left, top: l.top, width: l.len, height: 1, transform: `rotate(${l.rot}deg)`, transformOrigin: 'left center', background: `linear-gradient(90deg,transparent,${l.color},transparent)` }} />
      ))}
      {/* twinkling sparkles */}
      {bits.sparks.map((s, i) => (
        <span key={`s${i}`} style={{ position: 'absolute', left: s.left, top: s.top, fontSize: s.size, lineHeight: 1, color: s.color, animation: `orn-twinkle ${s.dur}s ease-in-out ${s.delay}s infinite` }}>{s.char}</span>
      ))}
      <style>{`
        @keyframes orn-twinkle {
          0%, 100% { opacity: .35; transform: scale(.9); }
          50%      { opacity: 1; transform: scale(1.15); }
        }
      `}</style>
    </div>
  )
}
