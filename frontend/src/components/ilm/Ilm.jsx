/*
 * ILLUMINATED KIT — shared design-layer primitives.
 *
 * Extracted faithfully from the "Illuminated" .dc.html mockups so every screen
 * inherits the same top bar, panels, buttons, diamonds and titles. Pure
 * presentational React; no game state or API calls live here. The supporting
 * classes are in index.css under the "ILLUMINATED KIT" banner.
 */
import React from 'react'

/* ---- small shapes -------------------------------------------------------- */

// 45°-rotated square used as bullet / currency glyph / badge.
export function Diamond({ size = 9, color = 'var(--gold)', glow = false, style, ...rest }) {
  return (
    <span
      style={{
        width: size, height: size, transform: 'rotate(45deg)', display: 'inline-block',
        flex: 'none', background: color,
        boxShadow: glow ? `0 0 8px ${typeof glow === 'string' ? glow : color}` : 'none',
        ...style,
      }}
      {...rest}
    />
  )
}

// Diamond monogram: rotated frame with a counter-rotated letter sitting upright.
export function Mono({ letter, color = 'var(--gold-hi)', size = 34, border, bg, style }) {
  return (
    <span
      className="ilm-mono"
      style={{
        width: size, height: size,
        borderColor: border || color,
        background: bg || 'linear-gradient(135deg,#1c1030,#0c0718)',
        ...style,
      }}
    >
      <span style={{ color, fontSize: Math.round(size * 0.4) }}>{letter}</span>
    </span>
  )
}

// Four gold L-ticks marking the corners of a plate/modal. Parent must be
// position:relative (all the ilm modal frames already are).
export function CornerTicks() {
  return (
    <>
      <span className="ilm-corner" />
      <span className="ilm-corner ilm-corner-r" />
      <span className="ilm-corner ilm-corner-bl" />
      <span className="ilm-corner ilm-corner-br" />
    </>
  )
}

/* ---- titles -------------------------------------------------------------- */

export function Eyebrow({ children, style }) {
  return <div className="ilm-eyebrow" style={style}>{children}</div>
}

// Ornate trailing rule — double hairline with a centered diamond, matching the
// landing tagline rules. Drop-in for the flat `height:1` span in headers on
// the money screens (Summon / Tower / Base).
export function OrnateRule({ color = 'rgba(216,187,132,.55)', dot = 'var(--gold)', style }) {
  return (
    <span style={{ flex: 1, display: 'flex', alignItems: 'center', gap: 8, minWidth: 24, ...style }}>
      <span style={{ height: 1, flex: 1, background: `linear-gradient(90deg, transparent, ${color})` }} />
      <span style={{ width: 5, height: 5, transform: 'rotate(45deg)', background: dot, flex: 'none', opacity: 0.9 }} />
      <span style={{ height: 1, flex: 1, background: `linear-gradient(90deg, ${color}, transparent)` }} />
    </span>
  )
}

// Two-layer screen title: a ghost outline word behind a solid word.
export function StackedTitle({ eyebrow, ghost, solid, height = 96, solidSize, ghostSize, style }) {
  return (
    <div style={style}>
      {eyebrow && <Eyebrow style={{ marginBottom: 2 }}>{eyebrow}</Eyebrow>}
      <div className="ilm-title-stack" style={{ height }}>
        <div className="ghost" style={ghostSize ? { fontSize: ghostSize } : undefined}>{ghost}</div>
        <div className="solid" style={solidSize ? { fontSize: solidSize } : undefined}>{solid}</div>
      </div>
    </div>
  )
}

// Diamond + label + hairline rule. `right` renders trailing content (e.g. count).
// `ornate` swaps the flat hairline for the double-rule-with-diamond (major screens).
export function SectionHeader({ children, right, color = 'var(--gold)', dotColor, ornate = false, style }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12, ...style }}>
      <Diamond size={7} color={dotColor || color} />
      <span style={{
        fontFamily: "'Cinzel',serif", letterSpacing: '0.3em',
        fontSize: '0.68rem', color, textTransform: 'uppercase',
      }}>{children}</span>
      {ornate ? <OrnateRule /> : <span style={{ height: 1, flex: 1, background: 'rgba(184,151,98,.2)' }} />}
      {right}
    </div>
  )
}

/* ---- surfaces ------------------------------------------------------------ */

// Notched ink panel. `notch` clips the bottom-left corner; `corner` draws the
// gold L-tick; `accent` washes a faint radial in a corner; `glow` adds a soft
// box-shadow. `as` lets it render as a button/link when needed.
export function Panel({
  children, notch = true, corner = false, cornerRight = false, glow = false,
  accent, tone = 'ink', className = '', style, as: Tag = 'div', ...rest
}) {
  const tones = {
    ink: 'rgba(12,7,24,.5)',
    violet: 'linear-gradient(160deg,rgba(42,22,80,.28),rgba(12,7,24,.6))',
    gold: 'linear-gradient(160deg,rgba(122,74,22,.2),rgba(12,7,24,.6))',
    green: 'linear-gradient(160deg,rgba(40,80,54,.2),rgba(12,7,24,.6))',
    danger: 'linear-gradient(160deg,rgba(80,20,26,.3),rgba(12,7,24,.65))',
  }
  return (
    <Tag
      className={`ilm-panel ${className}`}
      style={{
        position: 'relative',
        border: '1px solid var(--border)',
        background: tones[tone] || tone,
        clipPath: notch ? 'polygon(0 0,100% 0,100% 100%,14px 100%)' : undefined,
        boxShadow: glow ? '0 0 26px rgba(216,187,132,.22)' : undefined,
        ...style,
      }}
      {...rest}
    >
      {corner && <span className="ilm-corner" />}
      {cornerRight && <span className="ilm-corner ilm-corner-r" />}
      {accent && (
        <span style={{
          position: 'absolute', inset: 0, pointerEvents: 'none',
          background: `radial-gradient(70% 60% at 20% 0%, ${accent}, transparent 70%)`,
        }} />
      )}
      {children}
    </Tag>
  )
}

/* ---- buttons ------------------------------------------------------------- */

// Parallelogram CTA. variant: gold | violet | ghost | danger | green.
export function IlmButton({ variant = 'ghost', children, className = '', style, block, ...rest }) {
  return (
    <button
      className={`ilm-btn ilm-btn-${variant} ${block ? 'ilm-btn-block' : ''} ${className}`}
      style={style}
      {...rest}
    >
      {children}
    </button>
  )
}

/* ---- meters + stats ------------------------------------------------------ */

export function StatTile({ label, value, accent = 'var(--text-hi)', sub, style }) {
  return (
    <div style={{
      border: '1px solid var(--border)', background: 'rgba(12,7,24,.5)',
      padding: '8px 11px', ...style,
    }}>
      <div style={{
        fontFamily: "'Cinzel',serif", fontSize: '0.5rem', letterSpacing: '0.18em',
        color: 'var(--muted)', textTransform: 'uppercase',
      }}>{label}</div>
      <div style={{ fontWeight: 700, fontSize: '1.15rem', color: accent, lineHeight: 1.1, marginTop: 2 }}>
        {value}
      </div>
      {sub && <div className="ilm-micro" style={{ marginTop: 2 }}>{sub}</div>}
    </div>
  )
}

// Tier pips (diamonds), `filled` lit, remainder hollow.
export function Pips({ filled = 0, total = 5, color = 'var(--gold-hi)', size = 12, gap = 4 }) {
  return (
    <span style={{ display: 'flex', gap, flexWrap: 'wrap' }}>
      {Array.from({ length: total }).map((_, i) => (
        <span key={i} style={{
          width: size, height: size, transform: 'rotate(45deg)',
          background: i < filled ? color : 'transparent',
          border: `1px solid ${i < filled ? color : 'rgba(184,151,98,.3)'}`,
          boxShadow: i < filled ? `0 0 6px ${color}88` : 'none',
        }} />
      ))}
    </span>
  )
}

// Slim gradient progress bar. Full meters get a slow sheen sweep — a light
// band drifting across the fill so "ready" states read alive in stills.
export function Meter({ pct = 0, from = 'var(--violet-deep)', to = 'var(--gold-hi)', height = 5, border = 'rgba(184,151,98,.3)', glow = false }) {
  const full = pct >= 100
  return (
    <div style={{ height, background: 'rgba(124,58,214,.15)', border: `1px solid ${border}` }}>
      <div style={{
        width: `${Math.max(0, Math.min(100, pct))}%`, height: '100%',
        background: full
          ? `linear-gradient(100deg, transparent 38%, rgba(255,255,255,.3) 50%, transparent 62%) 0 0 / 240% 100%, linear-gradient(90deg,${from},${to})`
          : `linear-gradient(90deg,${from},${to})`,
        boxShadow: glow || full ? `0 0 10px ${to}88` : 'none',
        animation: full ? 'sheen-sweep 3.4s linear infinite' : 'none',
      }} />
    </div>
  )
}

// Rarity stars 1–7 (7 rendered rainbow via .rainbow-text).
export function StarRow({ rarity = 1, max = 7, size = '0.8rem', style }) {
  return (
    <span className={`stars birth-star-${rarity}`} style={{ fontSize: size, ...style }}>
      <span className={rarity >= 7 ? 'rainbow-text' : undefined}>{'★'.repeat(rarity)}</span>
      <span style={{ color: '#453c5c' }}>{'★'.repeat(Math.max(0, max - rarity))}</span>
    </span>
  )
}

export default {
  Diamond, Mono, CornerTicks, Eyebrow, StackedTitle, SectionHeader, OrnateRule,
  Panel, IlmButton, StatTile, Pips, Meter, StarRow,
}
