import React, { useState, useEffect } from 'react'
import { pullHeroes, getOdds, getEquipmentOdds, getBase, getPityInfo, redeemSpark, redeemEquipSpark, pullEquipment, getSparkWishlist, getFreePullStatus, freePull, getSeason, getGenerationEnabled } from '../api/client'
import SummoningOverlay from '../components/SummoningOverlay'
import FairyTip from '../components/FairyTip'
import { confirmDialog } from '../components/DialogHost'
import { Diamond, Meter } from '../components/ilm/Ilm'
import SparkWishlist from '../components/SparkWishlist'
import { EquipmentTypeIcon } from '../components/EquipmentTypeIcon'

// Mirrors backend services/class_service.py's is_combat_class() exclusion list.
const NON_COMBAT_CLASSES = ['Chef', 'Blacksmith', 'Quartermaster', 'Alchemist', 'Priest']

// Rarity string → 1..7 (matches SummoningOverlay).
function equipTier(r = '') {
  r = String(r).toUpperCase()
  if (r.startsWith('Z')) return 7
  if (r.startsWith('SSS')) return 7
  if (r.startsWith('SS')) return 6
  if (r.startsWith('S')) return 5
  if (r.startsWith('A')) return 4
  if (r.startsWith('B')) return 3
  if (r.startsWith('C')) return 2
  return 1
}
function tierOf(item) {
  return item.is_equipment ? equipTier(item.rarity) : (item.birth_star || 1)
}
const STAR_COLOR = n => `var(--star${Math.min(7, Math.max(1, n))})`

// Reveal accents are raw hex (they get concatenated with alpha suffixes for
// glows), unlike STAR_COLOR's CSS vars which are only ever used bare.
const HERO_ACCENT = { 1: '#9aa0ad', 2: '#8fbf9f', 3: '#1e90ff', 4: '#b84dff', 5: '#ffb300', 6: '#ff3333', 7: '#c8a9f5' }
const EQUIP_ACCENT = { 1: '#d8d8d8', 2: '#4dc06a', 3: '#4f92e8', 4: '#a05aee', 5: '#f2a63c', 6: '#ff4444', 7: '#00e5ff' }
function REVEAL_ACCENT(item, isEquip) {
  return isEquip ? (EQUIP_ACCENT[equipTier(item.rarity)] || '#e8a34c')
                 : (HERO_ACCENT[Math.min(7, Math.max(1, item.birth_star || 1))] || '#c8a9f5')
}
// Forge-word for an equipment rank plaque ("RANK Z · MYTHFORGED").
function RANK_WORD(rarity = '') {
  const r = String(rarity).toUpperCase()
  if (r === 'Z') return 'MYTHFORGED'
  if (r.startsWith('SSS')) return 'GODFORGED'
  if (r.startsWith('SS')) return 'LEGENDFORGED'
  if (r.startsWith('S')) return 'MASTERWORK'
  if (r.startsWith('A')) return 'ARTIFICED'
  if (r.startsWith('B')) return 'TEMPERED'
  if (r.startsWith('C')) return 'FORGED'
  return 'ROUGH-HEWN'
}
// The headline stat line for a revealed weapon ("GREATSWORD · ATK +812").
const _EQ_STAT_LABEL = { base_str: 'ATK', base_int: 'MAG', base_hlt: 'HP', base_def: 'DEF', base_end: 'END', base_agi: 'AGI', base_wil: 'WIL', base_luck: 'LCK' }
function equipHeadline(item) {
  let bestK = null, bestV = 0
  for (const k in _EQ_STAT_LABEL) { const v = Number(item[k]) || 0; if (v > bestV) { bestV = v; bestK = k } }
  const type = String(item.equipment_type || item.type || 'ARMAMENT').toUpperCase()
  return bestK ? `${type} · ${_EQ_STAT_LABEL[bestK]} +${bestV}` : type
}

// Banner definitions per mode. `banner` is the backend calling id ('standard'
// or 'seasonal'); `cur` is the currency the pull is charged in. The seasonal
// entry is only shown while a season is live (see `banners` in render).
const SEASON_STRIP = 'linear-gradient(#ffd88a,#e8a34c)'
// SEASONAL BANNERS ARE PARKED (Liam 2026-07-12): a rate-up banner doesn't
// mean much when every hero is procedurally random — pulled from the UI
// until a seasonal design that fits that (themed generation, seasonal
// synergy court, etc.) gets approved. The backend season machinery
// (season_service, banner='seasonal' pulls) stays intact for that day.
const HERO_BANNERS = {
  gem:  { key: 'gem',  banner: 'standard', label: 'GEM SUMMON',   strip: 'linear-gradient(#c8a9f5,#8b46d6)', border: 'rgba(184,151,98,.55)', wash: 'linear-gradient(120deg,rgba(124,58,214,.22),rgba(12,7,24,.6))', tint: 'var(--lavender)', blurb: 'Premium odds · every pull builds Sparks', c1: 100, c10: 1000, cur: 'gem' },
  gold: { key: 'gold', banner: 'standard', label: 'GOLD SUMMON',  strip: 'linear-gradient(#d8bb84,#7a6030)', border: 'rgba(184,151,98,.28)', wash: 'rgba(12,7,24,.4)', tint: 'var(--gold-hi)', blurb: 'Reliable calls · soft currency', c1: 500, c10: 5000, cur: 'gold' },
}
const EQUIP_BANNERS = {
  gem:  { key: 'gem',  banner: 'standard', label: 'GEM FORGE',    strip: 'linear-gradient(#c8a9f5,#8b46d6)', border: 'rgba(184,151,98,.55)', wash: 'linear-gradient(120deg,rgba(124,58,214,.22),rgba(12,7,24,.6))', tint: 'var(--lavender)', blurb: 'B-rank and above guaranteed', c1: 75, c10: 750, cur: 'gem' },
  gold: { key: 'gold', banner: 'standard', label: 'GOLD FORGE',   strip: 'linear-gradient(#d8bb84,#7a6030)', border: 'rgba(184,151,98,.28)', wash: 'rgba(12,7,24,.4)', tint: 'var(--gold-hi)', blurb: 'Reliable arms · soft currency', c1: 250, c10: 2500, cur: 'gold' },
}

function BannerCard({ b, active, onClick, days }) {
  return (
    <div onClick={onClick} className="ilm-banner-card" style={{
      border: `1px solid ${active ? (b.seasonal ? '#ffd88a' : '#ffd88a') : b.border}`,
      background: active ? b.wash : (b.seasonal ? 'linear-gradient(120deg,rgba(122,64,22,.14),rgba(12,7,24,.5))' : 'rgba(12,7,24,.4)'),
      boxShadow: active ? '0 0 16px rgba(184,151,98,.2)' : 'none',
    }}>
      <span className="ilm-banner-strip" style={{ background: b.strip }} />
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 8 }}>
        <span style={{ fontFamily: "'Cinzel',serif", fontWeight: 700, letterSpacing: '.18em', fontSize: '0.82rem', color: b.seasonal ? '#ffd88a' : (active ? b.tint : 'var(--muted)') }}>{b.label}</span>
        {b.seasonal && days != null && (
          <span style={{ fontFamily: "'Cinzel',serif", fontSize: '0.6rem', letterSpacing: '.2em', color: '#e8a34c', flex: 'none' }}>{days} DAYS</span>
        )}
      </div>
      <div style={{ fontSize: '0.82rem', fontStyle: 'italic', color: b.seasonal ? '#d8c3a8' : (active ? '#c8b8dd' : 'var(--text-dim)'), marginTop: 2 }}>{b.blurb}</div>
    </div>
  )
}

export default function SummonPage({ onGoldChange }) {
  const [activeTab, setActiveTab] = useState('heroes')
  const [banner, setBanner] = useState('gem')
  const [gold, setGold] = useState(0)
  const [gems, setGems] = useState(0)
  const [odds, setOdds] = useState(null)
  const [goldOdds, setGoldOdds] = useState(null)
  const [equipGoldOdds, setEquipGoldOdds] = useState(null)
  const [equipGemOdds, setEquipGemOdds] = useState(null)
  const [pityInfo, setPityInfo] = useState(null)
  const [pulling, setPulling] = useState(false)
  const [showWishlist, setShowWishlist] = useState(false)
  const [wishlistCount, setWishlistCount] = useState(0)
  const [redeeming, setRedeeming] = useState(false)
  const [redeemingEquip, setRedeemingEquip] = useState(false)
  const [heroResults, setHeroResults] = useState([])
  const [equipResults, setEquipResults] = useState([])
  const [showOdds, setShowOdds] = useState(false)
  const [error, setError] = useState(null)
  const [showAnimation, setShowAnimation] = useState(false)
  const [fairyGender, setFairyGender] = useState('female')
  const [fairyTip, setFairyTip] = useState({ show: false, message: '' })
  const [freeStatus, setFreeStatus] = useState(null)
  const [season, setSeason] = useState(null)
  // Base-gallery notice: shown until an API key is set (personal hero gen)
  // or the player dismisses it for this browser.
  const [genOn, setGenOn] = useState(true)
  const [galleryChipDismissed, setGalleryChipDismissed] = useState(
    () => localStorage.getItem('base_gallery_chip_dismissed') === 'true'
  )
  // LAST GRANTED HERE — the gate's five most recent grants, kept PER BANNER
  // (design chat: it's the history of *this* calling, not a global feed).
  const grantKey = `toe_last_granted_${activeTab}_${banner}`
  const [lastGranted, setLastGranted] = useState([])
  useEffect(() => {
    try { setLastGranted(JSON.parse(localStorage.getItem(grantKey) || '[]')) } catch { setLastGranted([]) }
  }, [grantKey])
  function recordGranted(items) {
    const tiers = items.map(tierOf)
    setLastGranted(prev => {
      const next = [...tiers, ...prev].slice(0, 5)
      try { localStorage.setItem(grantKey, JSON.stringify(next)) } catch {}
      return next
    })
  }

  useEffect(() => {
    refreshData()
    const poll = setInterval(() => {
      getBase().then(b => { setGold(b.gold); setGems(b.gems || 0) }).catch(() => {})
    }, 4000)
    return () => clearInterval(poll)
  }, [])

  async function refreshData() {
    getBase().then(b => { setGold(b.gold); setGems(b.gems || 0); setFairyGender(b.fairy_gender) })
    getOdds().then(setOdds)
    getOdds('gold').then(setGoldOdds)
    getEquipmentOdds('gold').then(setEquipGoldOdds)
    getEquipmentOdds('gem').then(setEquipGemOdds)
    getPityInfo().then(setPityInfo)
    getSparkWishlist().then(d => setWishlistCount((d.classes || []).length)).catch(() => {})
    getFreePullStatus().then(setFreeStatus).catch(() => {})
    getSeason().then(setSeason).catch(() => setSeason(null))
    getGenerationEnabled().then(r => setGenOn(!!r?.enabled)).catch(() => {})
  }

  async function doFreePull() {
    setPulling(true); setError(null); setHeroResults([])
    try {
      const data = await freePull()
      setHeroResults(data.pulled)
      setShowAnimation(true)
      recordGranted(data.pulled)
      await refreshData(); if (onGoldChange) onGoldChange()
    } catch (e) { setError(e.message) } finally { setPulling(false) }
  }

  async function doPull(count, bd) {
    const currency = bd.cur
    setPulling(true); setError(null); setHeroResults([])
    try {
      const data = await pullHeroes(count, true, currency, bd.banner)
      setHeroResults(data.pulled)
      recordGranted(data.pulled)
      const cost = count === 10 ? bd.c10 : bd.c1
      if (currency === 'gold') setGold(g => g - cost); else setGems(g => g - cost)
      setShowAnimation(true)
      if (!localStorage.getItem('seen_noncombat_tip')) {
        const noncombat = data.pulled.find(h => NON_COMBAT_CLASSES.includes(h.hero_class))
        if (noncombat) {
          localStorage.setItem('seen_noncombat_tip', 'true')
          setFairyTip({ show: true, message: `${noncombat.name} is a ${noncombat.hero_class} — not a combat class! Assign them to a Facility back at your Base instead of deploying them to the Tower.` })
          setTimeout(() => setFairyTip(t => ({ ...t, show: false })), 12000)
        }
      }
      await refreshData(); if (onGoldChange) onGoldChange()
    } catch (e) { setError(e.message) } finally { setPulling(false) }
  }

  async function doPullEquipment(count, bd) {
    const currency = bd.cur
    setPulling(true); setError(null); setEquipResults([])
    try {
      const data = await pullEquipment(count, currency, bd.banner)
      const tagged = data.results.map(e => ({ ...e, is_equipment: true }))
      setEquipResults(tagged)
      recordGranted(tagged)
      setShowAnimation(true)
      const cost = count === 10 ? bd.c10 : bd.c1
      if (currency === 'gem') setGems(g => g - cost); else setGold(g => g - cost)
      await refreshData(); if (onGoldChange) onGoldChange()
    } catch (e) { setError(e.message) } finally { setPulling(false) }
  }

  async function doSpark() {
    if (!(await confirmDialog(`Redeem ${pityInfo.spark_threshold} sparks for a guaranteed 5★ hero?`))) return
    setRedeeming(true); setError(null)
    try { const data = await redeemSpark(); setHeroResults([data.hero]); setShowAnimation(true); await refreshData() }
    catch (e) { setError(e.message) } finally { setRedeeming(false) }
  }
  async function doEquipSpark() {
    if (!(await confirmDialog(`Redeem ${pityInfo.equip_spark_threshold} sparks for a guaranteed A-tier item?`))) return
    setRedeemingEquip(true); setError(null)
    try { const data = await redeemEquipSpark(); setEquipResults([{ ...data.equipment, is_equipment: true }]); setShowAnimation(true); await refreshData() }
    catch (e) { setError(e.message) } finally { setRedeemingEquip(false) }
  }

  const isEquip = activeTab === 'equipment'
  const banners = isEquip ? EQUIP_BANNERS : HERO_BANNERS
  const seasonActive = !!season?.active
  // Seasonal only appears while a season is live; otherwise fall back to gem.
  const bannerList = Object.values(banners).filter(bd => !bd.seasonal || seasonActive)
  const b = (banners[banner] && (!banners[banner].seasonal || seasonActive)) ? banners[banner] : banners.gem
  const results = isEquip ? equipResults : heroResults
  const balance = b.cur === 'gem' ? gems : gold
  const short1 = balance < b.c1
  const short10 = balance < b.c10

  const sparkPts = isEquip ? (pityInfo?.equip_spark_points ?? 0) : (pityInfo?.spark_points ?? 0)
  const sparkMax = isEquip ? (pityInfo?.equip_spark_threshold ?? 90) : (pityInfo?.spark_threshold ?? 90)
  const sparkReady = sparkPts >= sparkMax

  // Featured reveal — the best unit from the last rite, unless the player
  // clicks a specific card in the THIS RITE spread below.
  const [featuredIdx, setFeaturedIdx] = useState(null)
  const autoFeatured = results.length
    ? results.reduce((best, x) => (tierOf(x) > tierOf(best) ? x : best), results[0])
    : null
  const featured = (featuredIdx != null && results[featuredIdx]) ? results[featuredIdx] : autoFeatured
  const featTier = featured ? tierOf(featured) : 0

  // THE ODDS tracks the SELECTED calling (Liam) — no separate filter.
  const oddsCurrency = b.cur === 'gold' ? 'gold' : 'gem'
  const oddsTable = isEquip
    ? (oddsCurrency === 'gold' ? equipGoldOdds : equipGemOdds)
    : (oddsCurrency === 'gold' ? goldOdds : odds)

  // Condensed odds for the altar's THE ODDS panel (full table lives behind ›).
  const oddsSummary = (() => {
    if (isEquip || !oddsTable) return null
    let p5 = 0, p4 = 0
    for (const [star, d] of Object.entries(oddsTable)) {
      const n = Number(star); const p = Number(d.percent) || 0
      if (n >= 5) p5 += p; else if (n === 4) p4 += p
    }
    return { p5, p4, rest: Math.max(0, 100 - p5 - p4) }
  })()

  const dormant = !featured

  return (
    <div className="page ilm-summon">
      <FairyTip show={fairyTip.show} message={fairyTip.message} fairyGender={fairyGender}
        onDismiss={() => setFairyTip(t => ({ ...t, show: false }))} />

      {showAnimation && results.length > 0 && (
        <SummoningOverlay results={results} onComplete={() => setShowAnimation(false)} />
      )}

      {!genOn && !galleryChipDismissed && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap',
          background: 'rgba(168,139,224,0.08)', border: '1px solid rgba(168,139,224,0.4)',
          borderRadius: 8, padding: '0.55rem 0.9rem', marginBottom: 14,
        }}>
          <span style={{ fontSize: '0.82rem', color: '#cfc4ea' }}>
            <b style={{ color: '#a88be0' }}>SHARED GALLERY</b> — your summons draw from the Tower's base art.
            Turn on portrait generation and the Gate forges heroes that exist only for you.
          </span>
          <button className="btn" style={{ fontSize: '0.78rem', padding: '0.3rem 0.8rem' }}
            onClick={() => window.dispatchEvent(new CustomEvent('toe-open-settings'))}>
            Turn On
          </button>
          <button className="btn" style={{ fontSize: '0.78rem', padding: '0.3rem 0.6rem', opacity: 0.6 }}
            onClick={() => { localStorage.setItem('base_gallery_chip_dismissed', 'true'); setGalleryChipDismissed(true) }}>
            ✕
          </button>
        </div>
      )}

      <div className={dormant ? undefined : 'ilm-summon-grid'} style={dormant ? { display: 'flex', gap: 26, alignItems: 'stretch', flexWrap: 'wrap' } : undefined}>
        {/* ============ LEFT CONSOLE ============ */}
        <div className="ilm-summon-left ent-1" style={dormant ? { width: 340, flex: '1 1 300px', maxWidth: 380 } : undefined}>
          {/* Step 1 shows the dormant altar title; after a rite the Gate takes
              its true name (the mockups' three-step flow). */}
          {dormant ? (
            <div className="ilm-title-stack">
              <div className="ghost">{isEquip ? 'FORGE' : 'GATE'}</div>
              <div className="solid">SUMMON</div>
            </div>
          ) : (
            <div className="ilm-summon-title">{isEquip ? <>THE<br />ARMORY GATE</> : <>THE<br />SOUL GATE</>}</div>
          )}
          <div className="ilm-summon-flavor">
            {dormant
              ? 'The Gate lies dormant. Choose a calling, and wake it.'
              : isEquip
                ? 'The Forge tempers chance itself — every tenth strike burns brighter.'
                : 'The Gate weighs every soul it grants — the tenth calling always answers louder.'}
          </div>

          {/* mode tabs */}
          <div className="ilm-summon-modetabs">
            {[['heroes', 'HEROES'], ['equipment', 'EQUIPMENT']].map(([id, label]) => (
              <span key={id} onClick={() => setActiveTab(id)}
                className={`ilm-summon-modetab ${activeTab === id ? 'active' : ''}`}>{label}</span>
            ))}
          </div>

          {/* banner cards */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 7, marginTop: 4 }}>
            {bannerList.map(bd => (
              <BannerCard key={bd.key} b={bd} active={b.key === bd.key} onClick={() => setBanner(bd.key)} days={season?.days_left} />
            ))}
          </div>

          {/* spark / strike meter — the Forge tempers with STRIKES, the Gate with SPARKS */}
          <div style={{ marginTop: 10 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 7 }}>
              <span style={{ fontFamily: "'Cinzel',serif", letterSpacing: '.24em', fontSize: '0.62rem', color: 'var(--muted)' }}>{isEquip ? 'STRIKES TO GUARANTEE' : 'SPARKS TO GUARANTEE'}</span>
              <span style={{ fontFamily: "'Cinzel',serif", fontSize: '0.78rem', color: isEquip ? '#e8a34c' : 'var(--violet)' }}>{sparkPts}<span style={{ color: '#6a6a82' }}>/{sparkMax}</span></span>
            </div>
            <Meter pct={(sparkPts / sparkMax) * 100} from="var(--violet-deep)" to={isEquip ? '#e8a34c' : 'var(--violet)'} height={6} glow />
          </div>

          {/* pull buttons */}
          <div style={{ marginTop: 12, display: 'flex', gap: 10 }}>
            <button className="btn btn-primary" style={{ flex: 1.5, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, padding: '13px 4px', fontSize: '0.78rem', opacity: short10 ? 0.5 : 1 }}
              disabled={pulling || short10}
              onClick={() => { setFeaturedIdx(null); (isEquip ? doPullEquipment(10, b) : doPull(10, b)) }}>
              <span>{pulling ? 'SUMMONING…' : 'SUMMON ×10'}</span>
              <span style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: '0.72rem' }}><Diamond size={7} color="#0a0710" />{b.c10.toLocaleString()}</span>
            </button>
            <button className="btn" style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6, padding: '13px 4px', fontSize: '0.78rem', opacity: short1 ? 0.5 : 1 }}
              disabled={pulling || short1}
              onClick={() => (isEquip ? doPullEquipment(1, b) : doPull(1, b))}>
              <span>×1</span><span style={{ fontSize: '0.72rem', color: 'var(--muted)' }}>{b.c1.toLocaleString()}</span>
            </button>
          </div>
          {(short1) && (
            <div className="text-dim" style={{ fontSize: '0.78rem', fontStyle: 'italic', marginTop: 8 }}>
              Not enough {b.cur === 'gem' ? 'gems' : 'gold'} — claim Achievement rewards and set new floor records to earn more.
            </div>
          )}

          {/* wishlist row (heroes mode) — mockup's gold strip below the pull buttons */}
          {!isEquip && (
            <button onClick={() => setShowWishlist(true)} style={{
              marginTop: 8, display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer',
              border: '1px solid rgba(184,151,98,.4)',
              background: 'linear-gradient(120deg,rgba(122,64,22,.16),rgba(12,7,24,.5))',
              padding: '8px 14px', clipPath: 'polygon(10px 0,100% 0,calc(100% - 10px) 100%,0 100%)',
              color: 'inherit', textAlign: 'left', width: '100%',
            }}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" style={{ flex: 'none' }}>
                <path d="M12 20 C6 15.5 4 12.5 4 9 C4 6.5 6 5 8 5 C10 5 12 7 12 7 C12 7 14 5 16 5 C18 5 20 6.5 20 9 C20 12.5 18 15.5 12 20 Z" stroke="#d8bb84" strokeWidth="1.4" strokeLinejoin="round" />
              </svg>
              <span style={{ fontFamily: "'Cinzel',serif", fontWeight: 700, letterSpacing: '.2em', fontSize: '0.72rem', color: '#e7ddc9' }}>WISHLIST</span>
              <span style={{ flex: 1 }} />
              <span style={{ fontFamily: "'Cinzel',serif", fontSize: '0.66rem', letterSpacing: '.1em', color: 'var(--green-hi)' }}>
                {wishlistCount > 0 ? `${wishlistCount} PINNED` : 'NONE PINNED'}
              </span>
              <span style={{ fontFamily: "'Cinzel',serif", fontSize: '0.82rem', color: 'var(--text-dim)' }}>›</span>
            </button>
          )}

          {/* spark redeem */}
          <button
            className="btn"
            style={{ marginTop: 10, width: '100%', padding: '0.7rem', letterSpacing: '.14em',
              color: sparkReady ? 'var(--star5)' : 'var(--text-dim)',
              borderColor: sparkReady ? 'var(--star5)' : 'var(--border)',
              boxShadow: sparkReady ? '0 0 14px rgba(255,179,0,.3)' : 'none' }}
            onClick={isEquip ? doEquipSpark : doSpark}
            disabled={pulling || redeeming || redeemingEquip || !sparkReady}>
            {sparkReady ? `Redeem ${isEquip ? 'A-Tier Item' : '5★ Hero'} · ${sparkMax} Sparks` : `Sparks ${sparkPts}/${sparkMax}`}
          </button>

          {error && <div className="text-red" style={{ marginTop: 10, fontSize: '0.95rem' }}>{error}</div>}
        </div>

        {/* ============ CENTER: THE GATE ============ */}
        {/* FIXED height in dormant mode (not stretch): the left rail's height
            changes per banner (extra hint lines etc.), and a stretched column
            let the gate drift vertically when switching callings. */}
        <div className="ilm-summon-center ent-2" style={dormant ? { flex: '1.4 1 380px', height: 620, alignSelf: 'flex-start' } : undefined}>
          {/* The 7/Z watermark belongs to a top-grade granting only — never ambient. */}
          {featTier === 7 && <div className="ilm-gate-watermark" style={{ color: 'transparent', WebkitTextStroke: isEquip ? '1px rgba(232,163,76,.16)' : '1px rgba(150,110,230,.14)' }}>{isEquip ? 'Z' : '7'}</div>}
          {!featured && <div className="ilm-gate-ring outer" />}
          {!featured && <div className="ilm-gate-ring inner" />}

          {featured ? (
            <div style={{ position: 'relative', zIndex: 2, textAlign: 'center', width: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
              {/* rarity / rank plaque */}
              {isEquip ? (
                <div style={{ display: 'inline-flex', alignItems: 'center', gap: 10, padding: '5px 18px', border: `1px solid ${REVEAL_ACCENT(featured, isEquip)}`, background: 'rgba(70,40,10,.4)', boxShadow: `0 0 24px ${REVEAL_ACCENT(featured, isEquip)}66`, clipPath: 'polygon(10px 0,100% 0,calc(100% - 10px) 100%,0 100%)' }}>
                  <span className={featTier >= 7 ? 'rainbow-text' : undefined} style={{ fontFamily: "'Cinzel',serif", fontWeight: 900, letterSpacing: '.3em', fontSize: '0.86rem', color: featTier >= 7 ? undefined : REVEAL_ACCENT(featured, isEquip), textShadow: featTier >= 7 ? undefined : `0 0 10px ${REVEAL_ACCENT(featured, isEquip)}` }}>
                    RANK {featured.rarity} · {RANK_WORD(featured.rarity)}
                  </span>
                </div>
              ) : featTier === 7 ? (
                <div style={{ display: 'inline-flex', alignItems: 'center', gap: 10, padding: '5px 18px', border: `1px solid ${STAR_COLOR(7)}`, background: 'rgba(0,40,50,.35)', boxShadow: `0 0 24px ${STAR_COLOR(7)}66`, clipPath: 'polygon(10px 0,100% 0,calc(100% - 10px) 100%,0 100%)' }}>
                  <span className="rainbow-text" style={{ fontFamily: "'Cinzel',serif", fontWeight: 900, letterSpacing: '.3em', fontSize: '0.9rem' }}>
                    ★★★★★★★ MYTHIC
                  </span>
                </div>
              ) : (
                <div style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '4px 16px', border: `1px solid ${STAR_COLOR(featTier)}`, background: 'rgba(12,7,24,.5)', clipPath: 'polygon(10px 0,100% 0,calc(100% - 10px) 100%,0 100%)' }}>
                  <span style={{ fontFamily: "'Cinzel',serif", fontWeight: 700, letterSpacing: '.22em', fontSize: '0.76rem', color: STAR_COLOR(featTier) }}>{'★'.repeat(featTier)}</span>
                </div>
              )}

              {/* the radiant art — hero portrait / weapon icon on a bloom */}
              <div style={{ position: 'relative', width: 260, height: 300, marginTop: 14 }}>
                <div style={{ position: 'absolute', inset: -24, background: `radial-gradient(50% 55% at 50% 42%, ${REVEAL_ACCENT(featured, isEquip)}55, ${REVEAL_ACCENT(featured, isEquip)}18 55%, transparent 72%)`, animation: 'toe-glow 6s ease-in-out infinite' }} />
                {isEquip ? (
                  <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <EquipmentTypeIcon item={featured} fontSize="6rem" />
                  </div>
                ) : featured.portrait_path ? (
                  <img src={`/${featured.portrait_path}`} draggable={false} alt=""
                    onError={(e) => { e.target.style.display = 'none' }}
                    style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'contain' }} />
                ) : null}

              </div>

              <div style={{ fontFamily: "'Cinzel',serif", fontWeight: 900, fontSize: '3.1rem', letterSpacing: '.04em', color: 'var(--text-hi)', textShadow: `0 0 30px ${REVEAL_ACCENT(featured, isEquip)}88`, marginTop: 6, lineHeight: 1 }}>
                {featured.name}
              </div>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 14, marginTop: 8 }}>
                <span style={{ height: 1, width: 56, background: `linear-gradient(90deg, transparent, ${REVEAL_ACCENT(featured, isEquip)}cc)` }} />
                <span style={{ fontFamily: "'Cinzel',serif", letterSpacing: '.28em', fontSize: '0.82rem', color: REVEAL_ACCENT(featured, isEquip) }}>
                  {isEquip ? equipHeadline(featured) : (featured.hero_class || '')}
                </span>
                <span style={{ height: 1, width: 56, background: `linear-gradient(90deg, ${REVEAL_ACCENT(featured, isEquip)}cc, transparent)` }} />
              </div>
            </div>
          ) : (
            /* the dormant gate — a dark diamond inside the rings */
            <div style={{ position: 'relative', zIndex: 2, textAlign: 'center', width: '100%' }}>
              <div style={{ position: 'relative', width: 300, height: 300, margin: '0 auto' }}>
                <div style={{ position: 'absolute', inset: 0, borderRadius: '50%', background: 'radial-gradient(closest-side, rgba(96,42,168,.4), rgba(96,42,168,.12) 60%, transparent)', animation: 'toe-glow 6s ease-in-out infinite' }} />
                <div style={{ position: 'absolute', inset: 26, border: '1px solid rgba(150,110,230,.3)', borderRadius: '50%' }} />
                <div style={{ position: 'absolute', inset: 58, border: '1px dashed rgba(150,110,230,.2)', borderRadius: '50%' }} />
                {/* compass diamonds */}
                <span style={{ position: 'absolute', left: '50%', top: -6, transform: 'translateX(-50%) rotate(45deg)', width: 11, height: 11, background: 'var(--gold)' }} />
                <span style={{ position: 'absolute', left: '50%', bottom: -6, transform: 'translateX(-50%) rotate(45deg)', width: 11, height: 11, background: 'var(--violet)', boxShadow: '0 0 8px var(--violet)' }} />
                <span style={{ position: 'absolute', left: -6, top: '50%', transform: 'translateY(-50%) rotate(45deg)', width: 10, height: 10, border: '1px solid rgba(216,187,132,.6)' }} />
                <span style={{ position: 'absolute', right: -6, top: '50%', transform: 'translateY(-50%) rotate(45deg)', width: 10, height: 10, border: '1px solid rgba(200,169,245,.6)' }} />
                {/* the gate itself */}
                <div style={{ position: 'absolute', left: '50%', top: '50%', width: 128, height: 128, transform: 'translate(-50%,-50%) rotate(45deg)', background: 'linear-gradient(150deg,#1a0f2e,#0a0712)', border: '1px solid rgba(150,110,230,.45)', boxShadow: '0 0 40px rgba(96,42,168,.5)' }} />
                <span style={{ position: 'absolute', left: '50%', top: '50%', transform: 'translate(-50%,-50%)', color: '#c8a9f5', fontSize: 18, textShadow: '0 0 14px rgba(200,169,245,.9)', animation: 'toe-glow 4s ease-in-out infinite' }}>✦</span>
              </div>
              <div style={{ fontFamily: "'Cinzel',serif", letterSpacing: '.4em', fontSize: 15, color: 'var(--text-hi)', marginTop: 26 }}>THE GATE AWAITS</div>
              <div style={{ fontStyle: 'italic', fontSize: 15, color: 'var(--muted)', marginTop: 8 }}>
                An ember-wind stirs beyond the rings. The Gate is generous — for now.
              </div>
            </div>
          )}
        </div>

        {/* ============ RIGHT RAIL (dormant altar only) ============ */}
        {dormant && (
          <div className="ent-3" style={{ width: 300, flex: '1 1 280px', maxWidth: 340, display: 'flex', flexDirection: 'column', gap: 14 }}>
            {/* no soul is promised */}
            <div style={{ border: '1px solid rgba(150,110,230,.35)', background: 'rgba(12,7,24,.45)', padding: '22px 18px 18px', textAlign: 'center' }}>
              <div style={{ position: 'relative', width: 64, height: 64, margin: '0 auto' }}>
                <div style={{ position: 'absolute', inset: 6, transform: 'rotate(45deg)', background: 'linear-gradient(150deg,#2a1650,#140b22)', border: '1px solid rgba(200,169,245,.55)', boxShadow: '0 0 22px rgba(150,110,230,.5)' }} />
                <span style={{ position: 'absolute', left: '50%', top: '50%', transform: 'translate(-50%,-50%)', fontFamily: "'Cinzel',serif", fontWeight: 900, fontSize: 20, color: '#c8a9f5' }}>?</span>
              </div>
              <div style={{ fontFamily: "'Cinzel',serif", letterSpacing: '.26em', fontSize: 10, color: 'var(--muted)', marginTop: 14 }}>NO SOUL IS PROMISED</div>
            </div>

            {/* the calling */}
            <div style={{ border: '1px solid rgba(184,151,98,.35)', background: 'rgba(12,7,24,.45)', padding: '14px 16px' }}>
              <div style={{ fontFamily: "'Cinzel',serif", fontWeight: 700, letterSpacing: '.1em', fontSize: 14, color: 'var(--text-hi)' }}>
                THE {b.label.split(' ')[0]} CALLING
              </div>
              <div style={{ fontStyle: 'italic', fontSize: 14.5, color: 'var(--muted)', marginTop: 6, lineHeight: 1.5 }}>
                {isEquip
                  ? 'The Forge answers with arms, not souls. What it tempers is never yours to choose.'
                  : 'The Gate grants souls as it pleases. Who steps through is never yours to choose.'}
              </div>
              <div style={{ fontFamily: "'Cinzel',serif", letterSpacing: '.22em', fontSize: 9, color: 'var(--gold-hi)', margin: '12px 0 8px' }}>LAST GRANTED HERE</div>
              <div style={{ display: 'flex', gap: 10 }}>
                {lastGranted.length === 0 && <span style={{ fontStyle: 'italic', fontSize: 13, color: 'var(--muted)' }}>The Gate has granted nothing yet.</span>}
                {lastGranted.slice(0, 5).map((t, i) => (
                  <span key={i} style={{ width: 34, height: 34, transform: 'rotate(45deg)', flex: 'none', border: `1px solid ${STAR_COLOR(t)}`, boxShadow: `0 0 10px ${STAR_COLOR(t)}55`, background: '#140b22', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <span className={t === 7 ? 'rainbow-text' : undefined} style={{ transform: 'rotate(-45deg)', fontFamily: "'Cinzel',serif", fontWeight: 700, fontSize: 13, color: t === 7 ? undefined : STAR_COLOR(t) }}>{t}</span>
                  </span>
                ))}
              </div>
            </div>

            {/* the odds */}
            <div style={{ border: '1px solid rgba(184,151,98,.35)', background: 'rgba(12,7,24,.45)', padding: '12px 16px' }}>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
                <span style={{ width: 7, height: 7, transform: 'rotate(45deg)', background: 'var(--gold)', display: 'inline-block', alignSelf: 'center' }} />
                <span style={{ fontFamily: "'Cinzel',serif", letterSpacing: '.24em', fontSize: 10, color: 'var(--gold)' }}>THE ODDS</span>
                <span style={{ flex: 1 }} />
                <button onClick={() => setShowOdds(o => !o)} style={{ background: 'none', border: 'none', cursor: 'pointer', fontFamily: "'Cinzel',serif", fontSize: 9, letterSpacing: '.16em', color: 'var(--muted)' }}>FULL TABLE ›</button>
              </div>
              {oddsSummary && !showOdds ? (
                <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 4 }}>
                  {[[`5★ ${isEquip ? '' : 'HERO'}`, oddsSummary.p5, 'var(--star5)'], [`4★ ${isEquip ? '' : 'HERO'}`, oddsSummary.p4, 'var(--star4)'], ['3★ & BELOW', oddsSummary.rest, 'var(--star3)']].map(([k, v, c]) => (
                    <div key={k} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                      <span style={{ fontFamily: "'Cinzel',serif", fontSize: 10, letterSpacing: '.12em', color: c }}>{k}</span>
                      <span style={{ fontFamily: "'Cormorant Garamond',serif", fontWeight: 700, fontSize: 15, color: 'var(--text-hi)' }}>{Number(v).toFixed(1)}%</span>
                    </div>
                  ))}
                </div>
              ) : !showOdds ? (
                <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 4 }}>
                  {(oddsTable || []).slice(0, 3).map((tier, i) => (
                    <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                      <span style={{ fontFamily: "'Cinzel',serif", fontSize: 10, letterSpacing: '.12em', color: 'var(--gold-hi)' }}>{tier.grades[Math.floor(tier.grades.length / 2)]}-TIER</span>
                      <span style={{ fontFamily: "'Cormorant Garamond',serif", fontWeight: 700, fontSize: 15, color: 'var(--text-hi)' }}>{tier.percent.toFixed(1)}%</span>
                    </div>
                  ))}
                </div>
              ) : (
                /* the full table, expanded in place — the ONLY odds readout on
                   the page. No currency toggle: the table tracks whichever
                   calling is selected on the left (Liam). */
                <div style={{ marginTop: 8 }}>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                    {isEquip
                      ? (oddsTable || []).map((tier, i) => {
                          const mid = tier.grades[Math.floor(tier.grades.length / 2)]
                          return (
                            <div key={i} style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', padding: '2px 0' }}>
                              <span className="text-hi">{mid}-Tier</span>
                              <span className="text-dim" style={{ fontFamily: 'monospace' }}>{tier.percent.toFixed(2)}%</span>
                            </div>
                          )
                        })
                      : Object.entries(oddsTable || {}).map(([star, d]) => {
                          const n = Number(star)
                          return (
                            <div key={star} style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', padding: '2px 0' }}>
                              <span className={n === 7 ? 'rainbow-text' : undefined} style={{ color: n === 7 ? undefined : STAR_COLOR(n), textShadow: n >= 5 ? '0 0 5px currentColor' : 'none' }}>{'★'.repeat(n)}</span>
                              <span className="text-dim" style={{ fontFamily: 'monospace' }}>{Number(d.percent).toFixed(3)}%</span>
                            </div>
                          )
                        })}
                  </div>
                </div>
              )}
            </div>

            {/* free daily calling — one soul, on the house, resets at dawn */}
            <button onClick={doFreePull} disabled={pulling || !freeStatus?.available}
              style={{ border: '1px solid rgba(74,154,106,.4)', background: 'linear-gradient(160deg,rgba(36,80,58,.18),rgba(12,7,24,.5))', padding: '12px 16px', display: 'flex', alignItems: 'center', gap: 12, textAlign: 'left', width: '100%', cursor: freeStatus?.available ? 'pointer' : 'default', opacity: freeStatus?.available ? 1 : 0.65 }}>
              <span style={{ width: 26, height: 26, transform: 'rotate(45deg)', flex: 'none', border: '1px solid rgba(143,191,159,.6)', background: '#122016', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <span style={{ transform: 'rotate(-45deg)', color: '#8fbf9f', fontSize: 11 }}>✦</span>
              </span>
              <div style={{ flex: 1 }}>
                <div style={{ fontFamily: "'Cinzel',serif", fontWeight: 700, letterSpacing: '.14em', fontSize: 11, color: '#8fbf9f' }}>FREE DAILY CALLING</div>
                <div style={{ fontStyle: 'italic', fontSize: 13, color: 'var(--muted)', marginTop: 2 }}>
                  {freeStatus?.available
                    ? 'One soul, on the house — take it before dawn.'
                    : `The Gate's charity is spent — resets in ${Math.floor((freeStatus?.resets_in_seconds ?? 0) / 3600)}h.`}
                </div>
              </div>
              <span style={{ width: 7, height: 7, borderRadius: '50%', flex: 'none',
                background: freeStatus?.available ? '#4a9a6a' : 'rgba(143,191,159,.3)',
                boxShadow: freeStatus?.available ? '0 0 8px #4a9a6a' : 'none',
                animation: freeStatus?.available ? 'pulse-live 2s ease-in-out infinite' : 'none' }} />
            </button>
          </div>
        )}
      </div>

      {/* ============ BOTTOM: THIS RITE SPREAD ============ */}
      {results.length > 0 && !showAnimation && (
        <div className="ilm-rite-spread ent-3">
          <span style={{ fontFamily: "'Cinzel',serif", letterSpacing: '.24em', fontSize: '0.6rem', color: 'var(--muted)', writingMode: 'vertical-rl', transform: 'rotate(180deg)' }}>THIS RITE</span>
          {results.map((it, i) => {
            const t = tierOf(it)
            const accent = REVEAL_ACCENT(it, isEquip)
            const top = t >= 7
            const isFeatured = featured === it
            return (
              <div key={i} className="ilm-rite-card" onClick={() => setFeaturedIdx(i)}
                style={{ cursor: 'pointer', borderColor: isFeatured ? 'var(--gold-hi)' : accent, boxShadow: t >= 4 ? `inset 0 0 12px ${accent}55${top ? `, 0 0 16px ${accent}66` : ''}` : 'none', transform: top ? 'translateY(-4px) scale(1.06)' : 'none' }} title={it.name}>
                {/* face thumbnail — backend mini (square, face-centered crop) */}
                {!isEquip && it.portrait_path && (
                  <div style={{ width: '100%', height: 44, overflow: 'hidden', display: 'flex', justifyContent: 'center', flex: 'none' }}>
                    <img src={`/heroes/${it.id}/card-image?mini=1`} draggable={false} alt=""
                      onError={(e) => { if (!e.currentTarget.dataset.fb) { e.currentTarget.dataset.fb = '1'; e.currentTarget.src = `/${it.portrait_path}` } else { e.currentTarget.style.display = 'none' } }}
                      style={{ width: '100%', height: '100%', objectFit: 'cover', objectPosition: 'center' }} />
                  </div>
                )}
                {/* equipment leads with its type; heroes lead with the name */}
                <span style={{ fontFamily: 'monospace', fontSize: '0.5rem', color: '#7a6f92', textAlign: 'center', lineHeight: 1.3, textTransform: isEquip ? 'lowercase' : 'none' }}>{isEquip ? String(it.type || it.equipment_type || '') : it.name}</span>
                {isEquip ? (
                  <span className={top ? 'rainbow-text' : undefined} style={{ fontFamily: "'Cinzel',serif", fontWeight: 700, fontSize: '0.7rem', color: top ? undefined : accent }}>{it.rarity}</span>
                ) : (
                  <span className={top ? 'rainbow-text' : undefined} style={{ fontSize: '0.6rem', color: top ? undefined : accent }}>{'★'.repeat(t)}</span>
                )}
              </div>
            )
          })}
          {/* step-3 actions — summon again or lay the rite to rest */}
          <span style={{ flex: 1 }} />
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8, flex: 'none', paddingRight: 6 }}>
            <button className="btn btn-primary" disabled={pulling || short10}
              onClick={() => (isEquip ? doPullEquipment(10, b) : doPull(10, b))}
              style={{ padding: '11px 22px', fontSize: '0.78rem', letterSpacing: '.18em', display: 'flex', alignItems: 'center', gap: 8, opacity: short10 ? 0.5 : 1 }}>
              SUMMON ×10 <span style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: '0.7rem' }}><Diamond size={7} color="#0a0710" />{b.c10.toLocaleString()}</span>
            </button>
            <button onClick={() => { setFeaturedIdx(null); (isEquip ? setEquipResults([]) : setHeroResults([])) }}
              style={{ background: 'none', border: 'none', cursor: 'pointer', fontFamily: "'Cinzel',serif", fontWeight: 500, letterSpacing: '.24em', fontSize: '0.7rem', color: 'var(--text-dim)' }}>
              DONE
            </button>
          </div>
        </div>
      )}

      {showWishlist && <SparkWishlist onClose={() => { setShowWishlist(false); getSparkWishlist().then(d => setWishlistCount((d.classes || []).length)).catch(() => {}) }} />}
    </div>
  )
}
