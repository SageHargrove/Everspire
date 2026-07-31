/*
 * MINIGAME FRAMEWORK — the shared shell every facility minigame runs in.
 *
 * Design rules (Liam, final 2026-07-11):
 *  - SIX Skyrim-style difficulties; NOVICE is the auto-resolve baseline, so
 *    skipping the minigame is never a punishment — mastering it is a bonus.
 *  - Higher tiers multiply the reward, topping out ×3 on LEGENDARY — where
 *    a bad enough run RUINS the work outright.
 *  - Gating comes from the ACTIVITY's own resource (crafting spends
 *    materials, brewing spends ingredients), never a minigame-only cap.
 *
 * Usage:
 *  <MinigameShell title="STRIKE THE STEEL" onResolve={(mult) => craft(mult)}
 *    onSkip={(mult) => craft(mult)} heroStar={smith.birth_star} heroName={smith.name}
 *    game={(difficulty, onDone) => <ForgeTiming .../>} />
 *
 *  onSkip is HANDED the assigned hero's baseline — it is no longer a flat 1.0.
 *  Omitting heroStar falls back to 1.0, so an un-migrated caller keeps its
 *  old behaviour rather than breaking.
 *
 * The child game reports a raw SCORE 0..1; the shell converts it to the
 * final multiplier: baseline + (ceiling - baseline) * score, where a
 * botched run on higher tiers can dip slightly below baseline (risk).
 */
import React, { useState, useEffect } from 'react'
import { playDeedChime, playDefeatToll } from '../../audio'

// Skyrim's ladder (user call): NOVICE is the auto-resolve baseline (×1.0 —
// no tier below it, skipping IS novice), LEGENDARY tops out ×3 but is meant
// to be INCREDIBLY difficult — and botching it can RUIN the work outright
// (materials wasted, nothing made). Floors dip under 1.0 from ADEPT up:
// taking the hammer is a wager, not a free upgrade.
export const DIFFICULTIES = [
  { key: 'novice',     label: 'NOVICE',     desc: 'the steady baseline — auto-resolve matches this', floor: 0.9,  ceil: 1.1 },
  { key: 'apprentice', label: 'APPRENTICE', desc: 'a little nerve',        floor: 0.85, ceil: 1.25 },
  { key: 'adept',      label: 'ADEPT',      desc: 'real craft',            floor: 0.8,  ceil: 1.5 },
  { key: 'expert',     label: 'EXPERT',     desc: 'few hands qualify',     floor: 0.7,  ceil: 1.9 },
  { key: 'master',     label: 'MASTER',     desc: 'the Tower is watching', floor: 0.6,  ceil: 2.4 },
  { key: 'legendary',  label: 'LEGENDARY',  desc: 'perfection — or the work is RUINED', floor: 0.3, ceil: 3.0, ruin: 0.2 },
]
export const AUTO_RESOLVE_MULT = 1.0  // legacy default when no hero is assigned

// ── the hero's own hands ────────────────────────────────────────────────────
//
// Skipping used to be a flat ×1.0 no matter who was assigned, so a 1-star and
// a 7-star Blacksmith produced identical work the moment you declined to play.
// The star now sets the BASELINE — what that hero achieves unsupervised.
//
// The ceiling is untouched and stays player-only. A 7-star gives you a high
// floor that is genuinely hard to beat, but LEGENDARY's ×3 is not reachable by
// any hero at any rarity — that tier is for the player, permanently, and can't
// be power-crept away by rarity. Recruiting well buys you a good result;
// only you can buy a great one.
export const HERO_BASELINE_BY_STAR = {
  1: 0.85,   // barely competent — taking over is almost always worth it
  2: 0.95,
  3: 1.05,
  4: 1.15,
  5: 1.30,
  6: 1.45,
  7: 1.60,   // genuinely good — you need ADEPT+ and a clean run to beat them
}

export function heroBaseline(star) {
  return HERO_BASELINE_BY_STAR[star] ?? AUTO_RESOLVE_MULT
}

// The hero a facility's minigame is actually judged against: whoever assigned
// there is best. Ties break on level, so two 5-stars aren't picked by row
// order. Returns null when nothing is assigned, which the shell reads as
// "no one is minding this" and falls back to the flat baseline.
export function bestAssignedHero(facility) {
  const staff = facility?.heroes || []
  if (!staff.length) return null
  return staff.reduce((best, h) => {
    const star = (h.ascension_star || 0) > 0 ? h.ascension_star : (h.birth_star || 1)
    const bStar = (best.ascension_star || 0) > 0 ? best.ascension_star : (best.birth_star || 1)
    if (star !== bStar) return star > bStar ? h : best
    return (h.level || 0) > (best.level || 0) ? h : best
  })
}

export function effectiveStar(hero) {
  if (!hero) return null
  return (hero.ascension_star || 0) > 0 ? hero.ascension_star : (hero.birth_star || 1)
}

// score 0..1 -> reward multiplier. On tiers with a `ruin` threshold, a score
// below it returns 0 — the caller treats 0 as CATASTROPHE (work destroyed).
export function scoreToMult(diff, score) {
  const d = DIFFICULTIES.find(x => x.key === diff) || DIFFICULTIES[0]
  const s = Math.max(0, Math.min(1, score))
  if (d.ruin != null && s < d.ruin) return 0
  return Math.round((d.floor + (d.ceil - d.floor) * s) * 100) / 100
}

export default function MinigameShell({ title, flavor, onResolve, onSkip, game,
                                        heroStar = null, heroName = null }) {
  // What the assigned hero manages alone. Falls back to the old flat baseline
  // when a caller hasn't been taught to pass a hero yet, so nothing breaks
  // while the facilities are migrated one at a time.
  const baseline = heroStar ? heroBaseline(heroStar) : AUTO_RESOLVE_MULT
  const [phase, setPhase] = useState('pick')   // pick -> play -> done
  const [diff, setDiff] = useState('adept')
  const [result, setResult] = useState(null)

  function handleDone(score) {
    const mult = scoreToMult(diff, score)
    setResult({ score, mult })
    setPhase('done')
    try { mult === 0 ? playDefeatToll() : mult >= 1.1 ? playDeedChime() : null } catch {}
  }

  return (
    <div className="ilm-modal-scrim" style={{ padding: 28 }}>
      <div style={{ position: 'relative', width: 560, maxWidth: '100%', background: 'linear-gradient(160deg, #160d27, #0b0716)', border: '1px solid rgba(184,151,98,.55)', clipPath: 'polygon(0 0, 100% 0, 100% 100%, 18px 100%)', boxShadow: '0 30px 90px rgba(0,0,0,.8)', padding: '24px 30px 28px' }}>
        <span className="ilm-corner" /><span className="ilm-corner ilm-corner-r" />
        <div className="ilm-micro" style={{ color: 'var(--gold-hi)', letterSpacing: '.3em' }}>THE MANAGER'S HAND</div>
        <div style={{ fontFamily: "'Cinzel',serif", fontWeight: 900, fontSize: '1.6rem', color: 'var(--text-hi)', marginTop: 2 }}>{title}</div>
        {flavor && <div style={{ fontStyle: 'italic', color: 'var(--text-dim)', fontSize: '0.9rem', marginTop: 4 }}>{flavor}</div>}

        {phase === 'pick' && (
          <>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 7, marginTop: 18 }}>
              {DIFFICULTIES.map(d => (
                <button key={d.key} onClick={() => setDiff(d.key)}
                  style={{ display: 'flex', alignItems: 'baseline', gap: 12, textAlign: 'left', cursor: 'pointer', padding: '9px 14px', background: diff === d.key ? 'rgba(184,151,98,.14)' : 'rgba(12,7,24,.5)', border: `1px solid ${diff === d.key ? 'var(--gold)' : 'rgba(184,151,98,.25)'}` }}>
                  <span style={{ fontFamily: "'Cinzel',serif", fontWeight: 700, letterSpacing: '.16em', fontSize: 12, color: diff === d.key ? 'var(--gold-hi)' : 'var(--text-dim)', width: 110 }}>{d.label}</span>
                  <span style={{ fontStyle: 'italic', fontSize: 13, color: 'var(--muted)', flex: 1 }}>{d.desc}</span>
                  <span style={{ fontFamily: "'Cinzel',serif", fontSize: 10, letterSpacing: '.1em', color: d.ceil > 1.1 ? 'var(--gold-hi)' : 'var(--muted)' }}>UP TO ×{d.ceil}</span>
                  {/* A tier that can't beat the assigned hero is worth saying
                      out loud — otherwise you take over, play well, and are
                      quietly worse off than doing nothing. */}
                  {d.ceil <= baseline && (
                    <span title="This hero already does better than this tier's best outcome"
                      style={{ fontFamily: "'Cinzel',serif", fontSize: 9, letterSpacing: '.1em', color: 'var(--red-hi)' }}>BELOW THEM</span>
                  )}
                </button>
              ))}
            </div>
            <div style={{ display: 'flex', gap: 10, marginTop: 18 }}>
              <button className="btn" style={{ flex: 1, padding: '11px 0', fontFamily: "'Cinzel',serif", letterSpacing: '.18em', border: '1px solid rgba(150,110,230,.45)', color: '#cdbfe4', background: 'none', cursor: 'pointer' }}
                onClick={() => onSkip(baseline)}>
                {heroName ? `LET ${heroName.toUpperCase()} WORK` : 'LET THE HANDS WORK'} · ×{baseline.toFixed(2)}
              </button>
              <button className="btn btn-primary" style={{ flex: 1, padding: '11px 0', letterSpacing: '.18em' }} onClick={() => setPhase('play')}>
                TAKE OVER
              </button>
            </div>
          </>
        )}

        {phase === 'play' && game(diff, handleDone)}

        {phase === 'done' && result && (
          <div style={{ textAlign: 'center', marginTop: 22 }}>
            {result.mult === 0 ? (
              <>
                <div style={{ fontFamily: "'Cinzel',serif", letterSpacing: '.26em', fontSize: 11, color: 'var(--red-hi)' }}>CATASTROPHE</div>
                <div style={{ fontFamily: "'Cormorant Garamond',serif", fontWeight: 700, fontSize: 40, color: 'var(--red-hi)', lineHeight: 1.15 }}>RUINED</div>
                <div style={{ fontStyle: 'italic', fontSize: 13, color: 'var(--muted)', marginTop: 6 }}>Legendary work forgives nothing. What was spent is gone.</div>
              </>
            ) : (
              <>
                <div style={{ fontFamily: "'Cinzel',serif", letterSpacing: '.26em', fontSize: 11, color: 'var(--muted)' }}>
                  {result.score >= 0.95 ? 'FLAWLESS' : result.score >= 0.7 ? 'MASTERFUL' : result.score >= 0.4 ? 'STEADY' : 'SLOPPY'} WORK
                </div>
                <div style={{ fontFamily: "'Cormorant Garamond',serif", fontWeight: 700, fontSize: 52, color: result.mult >= 1.1 ? 'var(--gold-hi)' : 'var(--text-hi)', lineHeight: 1.1 }}>
                  ×{result.mult.toFixed(2)}
                </div>
              </>
            )}
            <button className="btn btn-primary" style={{ marginTop: 16, padding: '11px 42px', letterSpacing: '.2em' }} onClick={() => onResolve(result.mult)}>
              {result.mult === 0 ? 'ACCEPT THE LOSS' : 'SEAL THE WORK'}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
