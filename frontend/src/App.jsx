import React, { useState, useEffect } from 'react'
import GameIcon from './components/GameIcon'
import SummonPage from './pages/SummonPage'
import HeroesPage from './pages/HeroesPage'
import TowerPage from './pages/TowerPage'
import BasePage from './pages/BasePage'
import LogPage from './pages/LogPage'
import MoreHub from './components/MoreHub'
import InventoryPage from './pages/InventoryPage'
import ArenaPage from './pages/ArenaPage'
import AchievementsPage from './pages/AchievementsPage'
import HeraldWire from './components/HeraldWire'
import ToastContainer from './components/ToastContainer'
import ErrorBoundary from './components/ErrorBoundary'
import TutorialOverlay from './components/TutorialOverlay'
import TabTourOverlay from './components/TabTourOverlay'
import FairyChoice from './components/FairyChoice'
import AuthGate from './components/AuthGate'
import TopBar, { GlobalNav } from './components/ilm/TopBar'
import Ornaments, { BG_VARIANTS } from './components/ilm/Ornaments'
import Mailbox from './components/Mailbox'
import HearthDrawer from './components/HearthDrawer'
import GuildHall from './components/GuildHall'
import Social from './components/Social'
import ProfileCard from './components/ProfileCard'
import { emitToast } from './toastBus'
import { getBase, grantResources, clearDevInventory, setDevLevel, grantInventoryItem, listHeroes, getAchievements, getMailList, getChatLogs, getApiKeyStatus, setApiKey, getGenerationEnabled, setGenerationEnabled, getGenerationInstallStatus, startGenerationInstall } from './api/client'
import { confirmDialog, alertDialog } from './components/DialogHost'
import { initAudio, setSoundEnabled, isSoundEnabled, playClick, setBgmVolume, setSfxVolume, setBgmScene } from './audio'

const TABS = [
  { id: 'summon', label: 'Summon' },
  { id: 'heroes', label: 'Heroes' },
  { id: 'inventory', label: 'Vault' },
  { id: 'tower',  label: 'Tower' },
  { id: 'arena',  label: 'World' },
  { id: 'achievements', label: 'Achievements' },
  { id: 'base',   label: 'Base' },
  { id: 'more',   label: 'Archive' },
]

// Runs once per browser after the intro TutorialOverlay finishes (or, for
// existing profiles that already finished it before this feature shipped,
// the first time they load in). Walks every top-level tab plus the two
// Base sub-tabs worth calling out specifically — see TabTourOverlay.jsx.
const TAB_TOUR_STEPS = [
  { tab: 'summon', label: 'Summon', title: 'The Summoning Gate',
    body: "This is where you call new heroes into the Tower — spend Gold or Gems to pull. Every hero's stats, class, and face are unique." },
  { tab: 'heroes', label: 'Heroes', title: 'Your Roster',
    body: "Every hero you've ever summoned lives here. Set your active Tower team, check stats, manage equipment, and assign a team leader." },
  { tab: 'inventory', label: 'Items', title: 'Items',
    body: "Potions, scrolls, and crafting materials you've picked up sit here, ready to use on a hero or save for crafting." },
  { tab: 'tower', label: 'Tower', title: 'The Tower',
    body: "The main event. Send your team up floor by floor — each one's a fight, sometimes worse. Climb as high as you can." },
  { tab: 'arena', label: 'World', title: 'The World',
    body: "Everything beyond your Tower: PvP arenas, leaderboards, and (soon) base raids and server-wide tournaments. Never touches your real save, and heroes never actually die here." },
  { tab: 'base', subTab: 'lobby', label: 'Base', title: 'Home Base',
    body: "Rest your heroes here between runs, watch your gold and ingredient income, and manage Legacies." },
  { tab: 'base', subTab: 'facilities', label: 'Facilities', title: 'Facilities',
    body: "Build and staff facilities like the Forge, Dining Hall, and Infirmary — station a support-class hero (Blacksmith, Chef, Medic...) in their own facility and their COMPANY BOON rides with every climb: feasts, field surgery, opening gambits. Their evolution branch decides the boon; their star and growth decide its strength." },
]

export default function App() {
  const [activeProfile, setActiveProfile] = useState(null)
  // Account gate: null until the player signs in or picks offline.
  // { online: bool, username: string|null } — world identity for the session.
  const [account, setAccount] = useState(null)
  const [tab, setTab] = useState('summon')
  const [gold, setGold] = useState(null)
  const [ingredients, setIngredients] = useState(null)
  const [aether, setAether] = useState(null)
  const [gems, setGems] = useState(null)
  const [tutorialComplete, setTutorialComplete] = useState(true)
  const [fairyGender, setFairyGender] = useState('female')
  const [fairyChosen, setFairyChosen] = useState(true)
  const [showSettings, setShowSettings] = useState(false)
  // Bring-your-own-key AI generation setting (masked status + input buffer)
  const [apiKeyStatus, setApiKeyStatus] = useState(null)
  const [apiKeyInput, setApiKeyInput] = useState('')
  const [apiKeySaving, setApiKeySaving] = useState(false)
  const [genEnabled, setGenEnabled] = useState(false)
  const [genSaving, setGenSaving] = useState(false)
  // Live status of the one-click generation setup (null until it has anything
  // to say). Polled rather than pushed so closing Settings — or the whole
  // window — can't strand a 9GB download.
  const [genInstall, setGenInstall] = useState(null)
  const [soundOn, setSoundOn] = useState(localStorage.getItem('soundEnabled') !== 'false')
  // Background ornament style — live A/B from Settings, persisted per install
  const [bgVariant, setBgVariant] = useState(localStorage.getItem('toe_bg_variant') || 'starfield')
  const changeBgVariant = (v) => { setBgVariant(v); try { localStorage.setItem('toe_bg_variant', v) } catch {} }
  const [bgmVol, setBgmVol] = useState(parseFloat(localStorage.getItem('bgmVolume') || '0.5') * 100)
  const [sfxVol, setSfxVol] = useState(parseFloat(localStorage.getItem('sfxVolume') || '0.5') * 100)
  const [devHeroes, setDevHeroes] = useState([])
  const [devHeroId, setDevHeroId] = useState('')
  const [devLevel, setDevLevel_] = useState(10)
  const [devItemName, setDevItemName] = useState('')
  const [devItemType, setDevItemType] = useState('material')
  const [devItemQty, setDevItemQty] = useState(5)
  const [devBusy, setDevBusy] = useState(false)
  const [tourActive, setTourActive] = useState(false)
  const [tourStepIndex, setTourStepIndex] = useState(0)
  const [tourTabEntered, setTourTabEntered] = useState(false)
  const [baseSubTab, setBaseSubTab] = useState('lobby')
  // Notification design: exactly ONE kind of dot, for finite, claimable,
  // always-good actions (unclaimed achievement rewards). Deliberately NOT
  // "you can afford an upgrade" — gold fluctuates constantly and that dot
  // would never turn off, which trains players to ignore it.
  const [claimableAchievements, setClaimableAchievements] = useState(0)
  // Top-bar icon cluster overlays.
  const [showMail, setShowMail] = useState(false)
  const [showChat, setShowChat] = useState(false)
  const [showGuild, setShowGuild] = useState(false)
  const [showSocial, setShowSocial] = useState(false)
  const [showProfileCard, setShowProfileCard] = useState(false)
  const [mailDot, setMailDot] = useState(false)
  // The Hearth (global hero chatter drawer) — toggleable from any screen.
  const [showHearth, setShowHearth] = useState(false)
  const [hearthDot, setHearthDot] = useState(false)
  // Global UI scale. The UI is authored around a ~1600px-wide design; this
  // zooms the whole page (via <html> zoom, Chromium webview) so it fills the
  // window on 1080p / 1440p / 4K rather than sitting tiny in the middle.
  // uiScale is the player's manual multiplier on top of the auto fit.
  const [uiScale, setUiScale] = useState(() => {
    const v = parseFloat(localStorage.getItem('uiScale') || '1')
    return Number.isFinite(v) && v > 0 ? v : 1
  })

  useEffect(() => {
    function applyScale() {
      const auto = Math.min(1.9, Math.max(0.8, window.innerWidth / 1600))
      document.documentElement.style.zoom = String((auto * uiScale).toFixed(3))
    }
    applyScale()
    window.addEventListener('resize', applyScale)
    return () => window.removeEventListener('resize', applyScale)
  }, [uiScale])

  function changeUiScale(v) {
    const clamped = Math.min(1.5, Math.max(0.7, v))
    localStorage.setItem('uiScale', String(clamped))
    setUiScale(clamped)
  }

  useEffect(() => {
    if (showSettings) {
      getApiKeyStatus().then(setApiKeyStatus).catch(() => {})
      getGenerationEnabled().then(r => setGenEnabled(!!r.enabled)).catch(() => {})
      // Pick up an install that's still running from an earlier session —
      // the download survives the game being closed, so the UI has to be able
      // to rejoin one in progress rather than only tracking ones it started.
      getGenerationInstallStatus().then(st => {
        if (st && st.state !== 'idle') setGenInstall(st)
      }).catch(() => {})
    }
  }, [showSettings])

  // Poll only while something is actually installing. Stops on its own at
  // done/error so a finished setup isn't hitting the API forever.
  useEffect(() => {
    if (genInstall?.state !== 'running') return
    const id = setInterval(() => {
      getGenerationInstallStatus().then(setGenInstall).catch(() => {})
    }, 1500)
    return () => clearInterval(id)
  }, [genInstall?.state])

  useEffect(() => {
    // Global click listener for buttons to play sound
    const handleGlobalClick = (e) => {
      if (e.target.closest('button')) {
        playClick()
      }
    }
    document.addEventListener('click', handleGlobalClick)
    return () => document.removeEventListener('click', handleGlobalClick)
  }, [])

  useEffect(() => {
    // Pages deep-link into settings (e.g. SummonPage's "Attune Key" chip).
    const openSettings = () => setShowSettings(true)
    window.addEventListener('toe-open-settings', openSettings)
    return () => window.removeEventListener('toe-open-settings', openSettings)
  }, [])

  async function refreshResources() {
    if (!activeProfile) return
    try {
      const data = await getBase()
      setGold(data.gold)
      setIngredients(data.ingredients)
      setAether(data.aether)
      setGems(data.gems || 0)
      setTutorialComplete(!!data.tutorial_complete)
      setFairyGender(data.fairy_gender || 'female')
      setFairyChosen(!!data.fairy_gender)
      maybeStartTabTour(!!data.tutorial_complete)
    } catch {}
    getAchievements()
      .then(r => setClaimableAchievements((r.achievements || []).filter(a => a.complete && !a.claimed).length))
      .catch(() => {})
    getMailList()
      .then(rows => {
        const list = Array.isArray(rows) ? rows : (rows.mail || [])
        setMailDot(list.some(m => !m.is_read))
      })
      .catch(() => {})
  }

  // Covers returning profiles that finished the intro tutorial before this
  // tour existed — they still get it once. Brand-new profiles get it via
  // handleTutorialComplete below instead (refreshResources never observes
  // tutorial_complete flip true->true for them in time).
  function maybeStartTabTour(introDone) {
    if (introDone && !tourActive && localStorage.getItem('tab_tour_complete') !== 'true') {
      setTourStepIndex(0)
      setTourActive(true)
    }
  }

  function handleTutorialComplete(gemsGranted) {
    setTutorialComplete(true)
    if (gemsGranted > 0) setGems(g => (g || 0) + gemsGranted)
    setTab('summon')
    maybeStartTabTour(true)
  }

  // Re-evaluates whenever the active tab, Base's internal sub-tab, or the
  // current tour step changes — covers both "just clicked the target tab"
  // and "advanced to a step whose target tab I was already sitting on"
  // (the lobby -> facilities step, both inside the already-open Base tab).
  useEffect(() => {
    if (!tourActive) return
    const step = TAB_TOUR_STEPS[tourStepIndex]
    if (!step) return
    setTourTabEntered(tab === step.tab && (!step.subTab || baseSubTab === step.subTab))
  }, [tab, baseSubTab, tourActive, tourStepIndex])

  function finishTabTour() {
    localStorage.setItem('tab_tour_complete', 'true')
    setTourActive(false)
  }

  function handleTourNext() {
    if (tourStepIndex + 1 >= TAB_TOUR_STEPS.length) {
      finishTabTour()
    } else {
      setTourStepIndex(i => i + 1)
    }
  }

  useEffect(() => {
    if (activeProfile) refreshResources()
    if (activeProfile && activeProfile.toLowerCase().startsWith('test')) {
      listHeroes(true).then(setDevHeroes).catch(() => {})
    }
  }, [activeProfile])

  // Hearth notification dot: lights up when a chat log newer than the last
  // one seen in the drawer exists. Opening the drawer marks everything seen
  // (HearthDrawer writes hearthSeenAt on every load).
  useEffect(() => {
    if (!activeProfile) return
    const check = () => {
      getChatLogs(1).then(logs => {
        const newest = logs?.[0]?.created_at
        if (!newest) return setHearthDot(false)
        setHearthDot(!showHearth && newest !== localStorage.getItem('hearthSeenAt'))
      }).catch(() => {})
    }
    check()
    const iv = setInterval(check, 30000)
    return () => clearInterval(iv)
  }, [activeProfile, showHearth])

  async function handleDevClearInventory() {
    if (!(await confirmDialog('Wipe all equipment, materials, potions, and scrolls on this profile?'))) return
    setDevBusy(true)
    try {
      await clearDevInventory()
      alertDialog('Inventory cleared.')
    } catch (e) { alertDialog(e.message) } finally { setDevBusy(false) }
  }

  async function handleDevSetLevel() {
    if (!devHeroId) return
    setDevBusy(true)
    try {
      const res = await setDevLevel(Number(devHeroId), Number(devLevel))
      alertDialog(`Set to level ${res.level}${res.capped ? ' (capped by star)' : ''}.`)
    } catch (e) { alertDialog(e.message) } finally { setDevBusy(false) }
  }

  async function handleDevGrantItem() {
    if (!devItemName.trim()) return
    setDevBusy(true)
    try {
      await grantInventoryItem(devItemName.trim(), devItemType, Number(devItemQty))
      alertDialog(`Granted ${devItemQty}x ${devItemName}.`)
    } catch (e) { alertDialog(e.message) } finally { setDevBusy(false) }
  }

  async function handleGrantResources(gold, gems, ingredients, aether) {
    try {
      await grantResources(gold, gems, ingredients, aether)
      refreshResources()
    } catch (e) {
      alertDialog(e.message)
    }
  }

  function toggleSound() {
    initAudio()
    const next = !soundOn
    setSoundOn(next)
    setSoundEnabled(next)
  }

  // Coarse per-screen BGM routing. Deeper screens (TowerPage combat/boss,
  // ArenaPage matches, dedicated facilities) override this from their own
  // components; leaving the tab re-asserts the tab's scene here. Same-scene
  // calls are no-ops in the manager, so this never restarts a running track.
  useEffect(() => {
    if (!account || !activeProfile) { setBgmScene('title'); return }
    const SCENE_FOR_TAB = {
      summon: 'summon', heroes: 'hub', inventory: 'hub',
      tower: 'towerAscent', arena: 'world', achievements: 'hub',
      base: 'hub', more: 'hub',
    }
    setBgmScene(SCENE_FOR_TAB[tab] || 'hub')
  }, [tab, baseSubTab, account, activeProfile, soundOn])

  // AuthGate is the whole front door now: account sign-in (or offline) and
  // save selection are one step — one account, one save. ProfileSelect is
  // retired from the flow.
  if (!account || !activeProfile) {
    return <AuthGate onEnter={(ident) => {
      initAudio()
      setAccount(ident)
      setActiveProfile(ident.profile)
    }} />
  }

  const pages = {
    summon: <SummonPage onGoldChange={refreshResources} />,
    heroes: <HeroesPage onNavigate={setTab} />,
    inventory: <InventoryPage />,
    tower:  <TowerPage onGoldChange={refreshResources} onNavigate={setTab} />,
    arena:  <ArenaPage />,
    achievements: <AchievementsPage onGoldChange={refreshResources} />,
    base:   <BasePage onGoldChange={refreshResources} onSubTabChange={setBaseSubTab}
               tourTargetSubTab={tourActive && TAB_TOUR_STEPS[tourStepIndex]?.tab === 'base' ? TAB_TOUR_STEPS[tourStepIndex].subTab : null} />,
    more:   <MoreHub />,
    log:    <LogPage />,
  }

  return (
    <div className="app">
      <Ornaments seed={tab} variant={bgVariant} />
      <TopBar
        profileName={activeProfile}
        gold={gold} gems={gems} aether={aether}
        mailDot={mailDot}
        hearthDot={hearthDot}
        active={showHearth ? 'hearth' : (showMail ? 'mail' : (showChat ? 'chat' : (showSocial ? 'friends' : null)))}
        onHearth={() => { setShowHearth(v => !v); setHearthDot(false) }}
        onFriends={() => setShowSocial(true)}
        onMail={() => setShowMail(true)}
        onChat={() => setShowChat(v => !v)}
        onGuild={() => setShowGuild(true)}
        onMenu={() => setShowSettings(true)}
      />

      <GlobalNav
        tabs={TABS}
        active={tab}
        badges={{ achievements: claimableAchievements }}
        locked={id => tourActive && id !== TAB_TOUR_STEPS[tourStepIndex]?.tab}
        glow={id => tourActive && id === TAB_TOUR_STEPS[tourStepIndex]?.tab}
        onSelect={id => { setTab(id); if (id === 'base' || id === 'summon' || id === 'tower' || id === 'achievements') refreshResources() }}
      />

      <main className="main-content">
        <ErrorBoundary resetKey={tab}>
          {pages[tab]}
        </ErrorBoundary>
      </main>

      {activeProfile && activeProfile.toLowerCase().startsWith('test') && (
        <div style={{
          position: 'fixed', top: '50%', right: 0, transform: 'translateY(-50%)',
          zIndex: 500, background: 'rgba(20,10,10,0.92)', border: '1px solid rgba(255,100,100,0.4)',
          borderRight: 'none', borderRadius: '8px 0 0 8px', padding: '1rem',
          display: 'flex', flexDirection: 'column', gap: '0.5rem', width: '230px',
          maxHeight: '90vh', overflowY: 'auto',
          boxShadow: '-4px 0 12px rgba(0,0,0,0.4)'
        }}>
          <div style={{ fontFamily: 'Cinzel, serif', fontSize: '1rem', color: '#ff8080' }}>✦ Dev Tools</div>
          <div className="text-dim" style={{ fontSize: '0.7rem', marginBottom: '0.3rem' }}>
            Profile "{activeProfile}" only
          </div>
          <button className="btn" style={{ fontSize: '0.85rem' }} onClick={() => handleGrantResources(10000, 0, 0)}>+10,000 Gold</button>
          <button className="btn" style={{ fontSize: '0.85rem' }} onClick={() => handleGrantResources(0, 500, 0)}>+500 Gems</button>
          <button className="btn" style={{ fontSize: '0.85rem' }} onClick={() => handleGrantResources(0, 0, 500)}>+500 Ingredients</button>
          <button className="btn" style={{ fontSize: '0.85rem' }} onClick={() => handleGrantResources(0, 0, 0, 500)}>+500 Aether</button>

          <div style={{ borderTop: '1px solid rgba(255,100,100,0.25)', marginTop: '0.4rem', paddingTop: '0.5rem' }}>
            <button className="btn" style={{ fontSize: '0.8rem', width: '100%', color: '#ff8080' }} disabled={devBusy} onClick={handleDevClearInventory}>
              ⚠ Clear Inventory
            </button>
          </div>

          <div style={{ borderTop: '1px solid rgba(255,100,100,0.25)', marginTop: '0.4rem', paddingTop: '0.5rem', display: 'flex', flexDirection: 'column', gap: '0.3rem' }}>
            <div className="text-dim" style={{ fontSize: '0.7rem' }}>Set Hero Level</div>
            <select className="input" style={{ fontSize: '0.75rem', padding: '0.3rem' }} value={devHeroId} onChange={e => setDevHeroId(e.target.value)}>
              <option value="">Select hero...</option>
              {devHeroes.map(h => <option key={h.id} value={h.id}>{h.name} (Lv.{h.level})</option>)}
            </select>
            <div style={{ display: 'flex', gap: '0.3rem' }}>
              <input type="number" className="input" style={{ fontSize: '0.75rem', padding: '0.3rem', flex: 1 }} value={devLevel} onChange={e => setDevLevel_(e.target.value)} />
              <button className="btn" style={{ fontSize: '0.75rem' }} disabled={devBusy || !devHeroId} onClick={handleDevSetLevel}>Set</button>
            </div>
          </div>

          <div style={{ borderTop: '1px solid rgba(255,100,100,0.25)', marginTop: '0.4rem', paddingTop: '0.5rem', display: 'flex', flexDirection: 'column', gap: '0.3rem' }}>
            <div className="text-dim" style={{ fontSize: '0.7rem' }}>Grant Item</div>
            <input type="text" className="input" placeholder="Item name" style={{ fontSize: '0.75rem', padding: '0.3rem' }} value={devItemName} onChange={e => setDevItemName(e.target.value)} />
            <div style={{ display: 'flex', gap: '0.3rem' }}>
              <select className="input" style={{ fontSize: '0.75rem', padding: '0.3rem', flex: 1 }} value={devItemType} onChange={e => setDevItemType(e.target.value)}>
                <option value="material">Material</option>
                <option value="potion">Potion</option>
                <option value="scroll">Scroll</option>
              </select>
              <input type="number" className="input" style={{ fontSize: '0.75rem', padding: '0.3rem', width: '50px' }} value={devItemQty} onChange={e => setDevItemQty(e.target.value)} />
            </div>
            <button className="btn" style={{ fontSize: '0.75rem' }} disabled={devBusy || !devItemName.trim()} onClick={handleDevGrantItem}>Grant</button>
          </div>
        </div>
      )}



      {showSettings && (
        <div style={{
          position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
          background: 'rgba(0,0,0,0.85)', zIndex: 1000,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          backdropFilter: 'blur(5px)'
        }} onClick={() => setShowSettings(false)}>
          <div className="ilm-settings-panel" onClick={e => e.stopPropagation()}>
            <div className="ilm-corner" />
            <div className="ilm-corner ilm-corner-r" />

            {/* header */}
            <div className="ilm-settings-head">
              <span style={{ fontFamily: "'Cinzel',serif", fontWeight: 900, fontSize: '1.3rem', color: 'var(--text-hi)', letterSpacing: '.06em' }}>SETTINGS</span>
              <button className="ilm-close" onClick={() => setShowSettings(false)}>✕</button>
            </div>

            <div style={{ padding: '1.1rem 1.4rem 1.3rem' }}>
              {/* sound master toggle */}
              <div className="ilm-settings-row">
                <span className="ilm-settings-k">SOUND</span>
                <button className="ilm-toggle" onClick={toggleSound} aria-pressed={soundOn}>
                  <span className="ilm-toggle-label" style={{ color: soundOn ? 'var(--green-hi)' : 'var(--muted)' }}>{soundOn ? 'ON' : 'OFF'}</span>
                  <span className={`ilm-toggle-track ${soundOn ? 'on' : ''}`}><span className="ilm-toggle-knob" /></span>
                </button>
              </div>

              {/* music */}
              <div className="ilm-slider" style={{ marginTop: '1.1rem' }}>
                <div className="ilm-slider-head"><span className="ilm-settings-k">MUSIC</span><span className="ilm-slider-val">{bgmVol}</span></div>
                <div className="ilm-slider-track">
                  <div className="ilm-slider-fill" style={{ width: `${bgmVol}%` }} />
                  <span className="ilm-slider-knob" style={{ left: `${bgmVol}%` }} />
                  <input type="range" min="0" max="100" value={bgmVol} onChange={(e) => { const v = parseInt(e.target.value); setBgmVol(v); setBgmVolume(v / 100) }} />
                </div>
              </div>

              {/* effects */}
              <div className="ilm-slider" style={{ marginTop: '1.1rem' }}>
                <div className="ilm-slider-head"><span className="ilm-settings-k">EFFECTS</span><span className="ilm-slider-val">{sfxVol}</span></div>
                <div className="ilm-slider-track">
                  <div className="ilm-slider-fill" style={{ width: `${sfxVol}%` }} />
                  <span className="ilm-slider-knob" style={{ left: `${sfxVol}%` }} />
                  <input type="range" min="0" max="100" value={sfxVol} onChange={(e) => { const v = parseInt(e.target.value); setSfxVol(v); setSfxVolume(v / 100) }} />
                </div>
              </div>

              {/* ui scale */}
              <div className="ilm-slider" style={{ marginTop: '1.1rem' }}>
                <div className="ilm-slider-head"><span className="ilm-settings-k">UI SCALE</span><span className="ilm-slider-val">{Math.round(uiScale * 100)}%</span></div>
                <div className="ilm-slider-track">
                  <div className="ilm-slider-fill" style={{ width: `${(uiScale * 100 - 70) / 0.8}%` }} />
                  <span className="ilm-slider-knob" style={{ left: `${(uiScale * 100 - 70) / 0.8}%` }} />
                  <input type="range" min="70" max="150" step="5" value={Math.round(uiScale * 100)} onChange={(e) => changeUiScale(parseInt(e.target.value) / 100)} />
                </div>
                <div className="text-dim" style={{ fontSize: '0.7rem', fontStyle: 'italic', marginTop: 4 }}>On top of the automatic fit — higher = larger UI on big screens.</div>
              </div>

              {/* background ornament style — live A/B (Liam is picking a favorite) */}
              <div style={{ marginTop: '1.4rem' }}>
                <div className="ilm-settings-row" style={{ marginBottom: 6 }}>
                  <span className="ilm-settings-k">BACKGROUND</span>
                </div>
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                  {BG_VARIANTS.map(([id, label]) => (
                    <button key={id} onClick={() => changeBgVariant(id)}
                      style={{ flex: '1 1 40%', padding: '8px 6px', cursor: 'pointer', fontFamily: "'Cinzel',serif", fontSize: '0.6rem', letterSpacing: '.14em',
                        border: `1px solid ${bgVariant === id ? 'var(--gold-hi)' : 'rgba(184,151,98,.3)'}`,
                        background: bgVariant === id ? 'rgba(184,151,98,.18)' : 'rgba(12,7,24,.5)',
                        color: bgVariant === id ? '#ffd88a' : 'var(--text-dim)' }}>
                      {label}
                    </button>
                  ))}
                </div>
                <div className="text-dim" style={{ fontSize: '0.7rem', fontStyle: 'italic', marginTop: 4 }}>
                  Changes the faint shapes behind every page — the sparkles and diagonal lines stay.
                </div>
              </div>

              {/* AI — Claude key (text) + image generation toggle */}
              <div style={{ marginTop: '1.4rem' }}>
                <div className="ilm-settings-row" style={{ marginBottom: 6 }}>
                  <span className="ilm-settings-k">CLAUDE API KEY</span>
                  <span style={{ fontSize: '.72rem', color: apiKeyStatus?.set ? 'var(--green-hi)' : 'var(--muted)' }}>
                    {apiKeyStatus?.set ? (apiKeyStatus.env ? 'FROM ENV' : `SET (${apiKeyStatus.masked})`) : 'NOT SET'}
                  </span>
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                  <input
                    type="password"
                    placeholder={apiKeyStatus?.set ? 'Enter a new key to replace…' : 'Paste your Claude API key…'}
                    value={apiKeyInput}
                    onChange={e => setApiKeyInput(e.target.value)}
                    style={{ flex: 1, background: 'rgba(8,6,14,0.9)', border: '1px solid rgba(184,151,98,.3)', borderRadius: 6, color: 'var(--text-hi)', padding: '9px 10px', fontSize: '.85rem' }}
                  />
                  <button
                    disabled={apiKeySaving || (!apiKeyInput.trim() && !apiKeyStatus?.set)}
                    onClick={async () => {
                      setApiKeySaving(true)
                      try {
                        const res = await setApiKey(apiKeyInput.trim())
                        setApiKeyStatus(res.set ? await getApiKeyStatus() : { set: false, masked: null })
                        setApiKeyInput('')
                      } catch (e) { emitToast(e.message, 'error') }
                      setApiKeySaving(false)
                    }}
                    style={{ padding: '9px 14px', cursor: 'pointer', border: '1px solid rgba(184,151,98,.4)', background: 'rgba(184,151,98,.15)', color: 'var(--text-hi)', borderRadius: 6, fontSize: '.8rem', letterSpacing: '.05em' }}
                  >{apiKeySaving ? '…' : apiKeyInput.trim() ? 'SAVE' : 'CLEAR'}</button>
                </div>
                <div className="text-dim" style={{ fontSize: '0.7rem', fontStyle: 'italic', marginTop: 4 }}>
                  Powers all written content — hero names, backstories, dialogue, and the appearance descriptions used for portraits. Your key stays on this machine.
                </div>

                {/* Image generation on/off (independent of the key) */}
                <div className="ilm-settings-row" style={{ marginTop: '1.1rem', marginBottom: 6 }}>
                  <span className="ilm-settings-k">HERO PORTRAIT GENERATION</span>
                  <button
                    disabled={genSaving}
                    onClick={async () => {
                      setGenSaving(true)
                      try {
                        const res = await setGenerationEnabled(!genEnabled)
                        setGenEnabled(!!res.enabled)
                        // Turning it on with nothing installed starts the ~9GB
                        // setup here rather than sending the player off to run
                        // a .bat. The backend reports needs_install so a big
                        // download is never a silent side effect of a toggle.
                        if (res.enabled && res.needs_install) {
                          const st = await getGenerationInstallStatus()
                          if (!st.gpu) {
                            emitToast('No NVIDIA GPU detected — heroes will keep using the built-in art.', 'error')
                          } else {
                            setGenInstall(await startGenerationInstall())
                          }
                        }
                      } catch (e) { emitToast(e.message, 'error') }
                      setGenSaving(false)
                    }}
                    style={{
                      padding: '5px 14px', cursor: 'pointer', borderRadius: 20, fontSize: '.72rem', letterSpacing: '.08em',
                      border: `1px solid ${genEnabled ? 'var(--green-hi)' : 'rgba(184,151,98,.4)'}`,
                      background: genEnabled ? 'rgba(80,200,120,.15)' : 'rgba(12,7,24,.5)',
                      color: genEnabled ? 'var(--green-hi)' : 'var(--muted)',
                    }}
                  >{genSaving ? '…' : genEnabled ? 'ON' : 'OFF'}</button>
                </div>
                <div className="text-dim" style={{ fontSize: '0.7rem', fontStyle: 'italic', marginTop: 4 }}>
                  When ON, your summons render unique portraits on this machine's GPU. Needs an NVIDIA card — the first time you switch it on, the game downloads what it needs (~9GB) by itself. When OFF, heroes use the built-in art pool. Turn it off anytime to free up your GPU mid-session.
                </div>

                {/* Setup progress. Only rendered while an install is live or
                    has something to report — a finished install just leaves
                    the toggle ON with no leftover UI. */}
                {genInstall && ['running', 'error', 'no_gpu'].includes(genInstall.state) && (
                  <div style={{
                    marginTop: 10, padding: '10px 12px', borderRadius: 6,
                    border: '1px solid rgba(184,151,98,.3)', background: 'rgba(12,7,24,.5)',
                  }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, fontSize: '.7rem' }}>
                      <span style={{ color: 'var(--text-hi)' }}>
                        {genInstall.state === 'running'
                          ? (genInstall.step || 'Starting…')
                          : (genInstall.message || 'Setup stopped.')}
                      </span>
                      {genInstall.state === 'running' && genInstall.step_total > 0 && (
                        <span className="text-dim" style={{ whiteSpace: 'nowrap' }}>
                          step {genInstall.step_index}/{genInstall.step_total}
                        </span>
                      )}
                    </div>
                    {genInstall.state === 'running' && (
                      <div style={{ marginTop: 8, height: 4, borderRadius: 2, background: 'rgba(184,151,98,.15)', overflow: 'hidden' }}>
                        <div style={{
                          height: '100%', width: `${genInstall.percent ?? 0}%`,
                          background: 'var(--green-hi)', transition: 'width .4s ease',
                        }} />
                      </div>
                    )}
                    {genInstall.state === 'running' && (
                      <div className="text-dim" style={{ fontSize: '.65rem', marginTop: 6, fontStyle: 'italic' }}>
                        Safe to keep playing, and safe to close — it picks up where it left off.
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* profile row — links to the Profile Card, per the mockup */}
              <button onClick={() => { setShowSettings(false); setShowProfileCard(true) }} style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%',
                marginTop: '1.4rem', padding: '11px 14px', cursor: 'pointer',
                border: '1px solid rgba(184,151,98,.3)', background: 'rgba(12,7,24,.5)', color: 'inherit',
              }}>
                <span style={{ fontFamily: "'Cinzel',serif", letterSpacing: '.2em', fontSize: '0.62rem', color: 'var(--muted)' }}>PROFILE</span>
                <span style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <span style={{ fontFamily: "'Cinzel',serif", fontSize: '0.8rem', letterSpacing: '.08em', color: 'var(--text-hi)', textTransform: 'uppercase' }}>{activeProfile}</span>
                  <span style={{ fontFamily: "'Cinzel',serif", fontSize: '0.56rem', letterSpacing: '.16em', color: 'var(--gold-hi)' }}>VIEW CARD ›</span>
                </span>
              </button>

              {/* actions */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem', marginTop: '1.2rem' }}>
                <button className="ilm-btn ilm-btn-violet ilm-btn-block" onClick={() => { setShowSettings(false); setActiveProfile(null) }}>
                  SAVE &amp; RETURN TO TITLE
                </button>
                <button className="ilm-btn ilm-btn-block" style={{
                  color: '#d98a8a', border: '1px solid rgba(192,64,64,.5)', background: 'transparent',
                  clipPath: 'polygon(10px 0,100% 0,calc(100% - 10px) 100%,0 100%)',
                }} onClick={async () => {
                  try { await fetch('/api/quit', { method: 'POST' }) } catch (e) {}
                  window.close()
                }}>
                  SAVE &amp; QUIT TO DESKTOP
                </button>
                <button className="ilm-settings-close-txt" onClick={() => setShowSettings(false)}>CLOSE</button>
              </div>

              <div style={{ textAlign: 'center', fontFamily: "'Cinzel',serif", fontSize: '0.55rem', letterSpacing: '.2em', color: '#4f4766', marginTop: '0.9rem' }}>
                EVERSPIRE · PRE-ALPHA
              </div>
            </div>
          </div>
        </div>
      )}
      {showMail && (
        <Mailbox onClose={() => setShowMail(false)} onChange={refreshResources} />
      )}
      {showGuild && (
        <GuildHall onClose={() => setShowGuild(false)} />
      )}
      {showSocial && (
        <Social onClose={() => setShowSocial(false)} />
      )}
      {showProfileCard && (
        <ProfileCard onClose={() => setShowProfileCard(false)} />
      )}
      {showChat && <HeraldWire onClose={() => setShowChat(false)} onOpenGuild={() => { setShowChat(false); setShowGuild(true) }} />}
      {showHearth && <HearthDrawer onClose={() => setShowHearth(false)} />}
      <ToastContainer />
      {!tutorialComplete && !fairyChosen && (
        <FairyChoice onChosen={(g) => { setFairyGender(g); setFairyChosen(true) }} />
      )}
      {!tutorialComplete && fairyChosen && (
        <TutorialOverlay fairyGender={fairyGender} onComplete={handleTutorialComplete} />
      )}
      {tutorialComplete && tourActive && (
        <TabTourOverlay
          step={TAB_TOUR_STEPS[tourStepIndex]}
          stepIndex={tourStepIndex}
          totalSteps={TAB_TOUR_STEPS.length}
          entered={tourTabEntered}
          fairyGender={fairyGender}
          onNext={handleTourNext}
          onSkip={finishTabTour}
        />
      )}
    </div>
  )
}
