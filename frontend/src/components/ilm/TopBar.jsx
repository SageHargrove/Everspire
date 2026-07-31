/*
 * ILLUMINATED KIT — persistent top bar + global nav.
 *
 * Faithful rebuild of the mockup shell: 58px bar, gold-diamond wordmark, the
 * currency cluster (gold / gems / aether) and the outline-glyph icon cluster
 * (Friends · Mail · Chat · Guild · Menu). Glyphs are the same bordered-span
 * constructs as the .dc.html files — no icon font, no SVG dependency.
 */
import Tip, { TIPS } from '../Tip'
import React from 'react'
import { Diamond } from './Ilm'
import Sigil from '../Sigil'

/* Custom ui/ SVG when present, else the hand-built mockup glyph. The ui set
 * uses lowercase filenames (see icon manifest). currentColor mask, so it
 * inherits the icon button's lit/unlit color exactly like the glyphs do. */
function UiIcon({ name, size = 18, fallback }) {
  return <Sigil set="ui" name={name} size={size} fallback={fallback} />
}

/* ---- outline glyphs (bordered spans, exactly as the mockups) ------------- */

export function FriendsGlyph() {
  return (
    <>
      <span style={{ position: 'absolute', left: 6, top: 6, width: 7, height: 7, borderRadius: '50%', border: '1px solid currentColor' }} />
      <span style={{ position: 'absolute', left: 3, top: 15, width: 13, height: 8, border: '1px solid currentColor', borderBottom: 'none', borderRadius: '7px 7px 0 0' }} />
      <span style={{ position: 'absolute', left: 17, top: 8, width: 6, height: 6, borderRadius: '50%', border: '1px solid var(--text-dim)' }} />
      <span style={{ position: 'absolute', left: 15, top: 16, width: 11, height: 7, border: '1px solid var(--text-dim)', borderBottom: 'none', borderRadius: '6px 6px 0 0' }} />
    </>
  )
}

export function MailGlyph({ dot = false }) {
  return (
    <>
      <span style={{ width: 14, height: 10, border: '1px solid currentColor', display: 'inline-block' }} />
      <span style={{ position: 'absolute', left: 11, top: 5, width: 8, height: 8, borderRight: '1px solid currentColor', borderBottom: '1px solid currentColor', transform: 'rotate(45deg)' }} />
      {dot && <span className="notif-dot" style={{ animation: 'pulse-live 2.5s ease-in-out infinite' }} />}
    </>
  )
}

export function ChatGlyph() {
  return (
    <>
      <span style={{ position: 'absolute', left: 6, top: 8, width: 17, height: 11, border: '1px solid currentColor', borderRadius: 1 }} />
      <span style={{ position: 'absolute', left: 9, top: 17, width: 5, height: 5, borderRight: '1px solid currentColor', borderBottom: '1px solid currentColor', transform: 'rotate(65deg)' }} />
    </>
  )
}

export function GuildGlyph() {
  return (
    <>
      <span style={{ position: 'absolute', left: 9, top: 6, width: 12, height: 17, background: 'currentColor', clipPath: 'polygon(0 0,100% 0,100% 66%,50% 100%,0 66%)' }} />
      <span style={{ position: 'absolute', left: 10, top: 7, width: 10, height: 14, background: '#0d0818', clipPath: 'polygon(0 0,100% 0,100% 64%,50% 100%,0 64%)' }} />
      <span style={{ position: 'absolute', left: 13, top: 11, width: 4, height: 4, transform: 'rotate(45deg)', border: '1px solid currentColor' }} />
    </>
  )
}

export function MenuGlyph() {
  return (
    <span style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 3 }}>
      <span style={{ width: 12, height: 1, background: 'currentColor', display: 'block' }} />
      <span style={{ width: 8, height: 1, background: 'currentColor', display: 'block' }} />
      <span style={{ width: 12, height: 1, background: 'currentColor', display: 'block' }} />
    </span>
  )
}

/* ---- icon-cluster button ------------------------------------------------- */

function IconBtn({ title, onClick, lit, children }) {
  return (
    <button className={`ilm-iconbox ${lit ? 'lit' : ''}`} title={title} onClick={onClick}>
      {children}
    </button>
  )
}

/* ---- the Hearth toggle ----------------------------------------------------
 * Icon-only like its neighbors (a labeled button read as off-model in the
 * cluster) — the double speech bubble + the title tooltip carry the meaning. */
export function HearthGlyph() {
  return (
    <>
      <span style={{ position: 'absolute', left: 5, top: 7, width: 13, height: 9, border: '1px solid currentColor', borderRadius: 1 }} />
      <span style={{ position: 'absolute', left: 11, top: 12, width: 13, height: 9, border: '1px solid currentColor', borderRadius: 1, background: '#0d0818' }} />
    </>
  )
}

/* ---- currency pill ------------------------------------------------------- */

// Spec currency glyphs are the drawn diamonds themselves — gold flat,
// gems glowing. No icon art here; the PNG/SVG versions read as off-model.
function Currency({ value, label, color, glow }) {
  if (value === null || value === undefined) return null
  const tip = { GOLD: TIPS.gold, GEMS: TIPS.gems, AETHER: TIPS.aether }[label]
  return (
    <Tip text={tip} width={230}>
      <span className="resource-pill">
        <Diamond size={9} color={color} glow={glow} />
        <span style={{ color: '#efe8da' }}>{Number(value).toLocaleString()}</span>
        <span className="pill-label">{label}</span>
      </span>
    </Tip>
  )
}

/* ---- the bar ------------------------------------------------------------- */

export default function TopBar({
  profileName, gold, gems, aether = 0,
  onBack, onFriends, onMail, onChat, onGuild, onMenu, onHearth,
  mailDot = false, hearthDot = false, active,
}) {
  return (
    <header className="ilm-topbar ent-fade">
      <div className="ilm-topbar-left">
        <div className="ilm-diamond"><div className="pip" /></div>
        <h1 className="ilm-wordmark">EVERSPIRE</h1>
        {onBack && (
          <button className="ilm-back" title="Back" onClick={onBack}><UiIcon name="back-chevron" size={14} fallback="‹" /></button>
        )}
        {profileName && (
          <>
            <span className="ilm-topbar-div" />
            <span className="ilm-profile-chip">{profileName}</span>
          </>
        )}
      </div>

      <div className="ilm-topbar-right">
        <Currency value={gold} label="GOLD" color="var(--gold)" />
        <Currency value={gems} label="GEMS" color="var(--violet)" glow="var(--violet)" />
        {aether > 0 && <Currency value={aether} label="AETHER" color="var(--lavender)" glow="rgba(200,169,245,.6)" />}
        <span className="ilm-topbar-div" />
        {onHearth && <IconBtn title="The Hearth — hero chatter" onClick={onHearth} lit={active === 'hearth'}><HearthGlyph />{hearthDot && <span className="notif-dot" style={{ animation: 'pulse-live 2.5s ease-in-out infinite' }} />}</IconBtn>}
        {onFriends && <IconBtn title="Allies" onClick={onFriends} lit={active === 'friends'}><UiIcon name="friends" fallback={<FriendsGlyph />} /></IconBtn>}
        {onMail && <IconBtn title="Missives" onClick={onMail} lit={active === 'mail'}><UiIcon name="mail" fallback={<MailGlyph />} />{mailDot && <span className="notif-dot" style={{ animation: 'pulse-live 2.5s ease-in-out infinite' }} />}</IconBtn>}
        {onChat && <IconBtn title="Chat" onClick={onChat} lit={active === 'chat'}><UiIcon name="chat" fallback={<ChatGlyph />} /></IconBtn>}
        {onGuild && <IconBtn title="Guild" onClick={onGuild} lit={active === 'guild'}><UiIcon name="guild-crest" fallback={<GuildGlyph />} /></IconBtn>}
        {onMenu && <IconBtn title="Menu" onClick={onMenu}><UiIcon name="menu" fallback={<MenuGlyph />} /></IconBtn>}
      </div>
    </header>
  )
}

/* ---- global nav band ----------------------------------------------------- */

export function GlobalNav({ tabs, active, onSelect, badges = {}, locked, glow }) {
  return (
    <nav className="tabs ent-fade" style={{ animationDelay: '0.1s' }}>
      {tabs.map(t => {
        const isLocked = locked && locked(t.id)
        const isGlow = glow && glow(t.id)
        return (
          <button
            key={t.id}
            className={`tab-btn ${active === t.id ? 'active' : ''}`}
            disabled={isLocked}
            onClick={() => { if (!isLocked) onSelect(t.id) }}
            style={{ position: 'relative', ...(isLocked ? { opacity: 0.35, cursor: 'not-allowed' } : (isGlow ? { boxShadow: '0 0 10px var(--gold)' } : {})) }}
          >
            {t.label}
            {badges[t.id] > 0 && (
              <span
                title={`${badges[t.id]} ready`}
                style={{
                  position: 'absolute', top: 8, right: 2, width: 8, height: 8, borderRadius: '50%',
                  background: 'var(--gold)', boxShadow: '0 0 6px var(--gold)',
                  animation: 'pulse-live 2s ease-in-out infinite',
                }}
              />
            )}
          </button>
        )
      })}
    </nav>
  )
}
