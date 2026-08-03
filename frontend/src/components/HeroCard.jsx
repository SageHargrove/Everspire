import React, { useState, useEffect } from 'react'
import { regenerateProfile, getHeroAptitudes, getHeroRelationships } from '../api/client'
import { EquipmentTypeIcon } from './EquipmentTypeIcon'
import { classSigil } from '../classSigils'
import GameIcon from './GameIcon'
import ParallaxCard from './ParallaxCard'
import Sigil from './Sigil'
// Keep in sync with InventoryPage's ladder: common gray -> uncommon green ->
// rare blue -> epic purple -> legendary orange -> red/cyan/magenta top end.
const RARITY_COLORS = {
  'F-': '#6e6e6e', 'F': '#787878', 'F+': '#828282',
  'E-': '#969696', 'E': '#a2a2a2', 'E+': '#aeaeae',
  'D-': '#c8c8c8', 'D': '#d8d8d8', 'D+': '#e8e8e8',
  'C-': '#3fae5a', 'C': '#4dc06a', 'C+': '#63d97f',
  'B-': '#3f7fd0', 'B': '#4f92e8', 'B+': '#6ba6f2',
  'A-': '#8e44dd', 'A': '#a05aee', 'A+': '#b476f7',
  'S-': '#e0912b', 'S': '#f2a63c', 'S+': '#ffc25e',
  'SS': '#ff4444', 'SSS': '#00e5ff', 'Z': '#ff30dd',
}
function rarityColor(rarity) { return RARITY_COLORS[rarity] || '#888' }

const MORALE_STATE_LABEL = {
  steady: 'Steady', shaken: 'Shaken', fearful: 'Fearful', broken: 'Broken',
}

// Every base class evolves into a whole tree of named tiers (Warrior →
// Knight/Berserker/Paladin → Aegis/Templar/Bloodrager/... etc — see
// backend services/class_service.py). Hand-mapping ~90 individual evolution
// names to icons/colors is unmaintainable and silently breaks (showing '?')
// every time a new evolution tier gets added. Instead, every evolution name
// is grouped under its base-class family here, and the whole family shares
// one icon + color — new evolutions just need a one-line addition to a list,
// not a whole new icon/color decision.
export const CLASS_FAMILIES = {
  'Warrior': { icon: 'class_warrior', color: '#c87830', members: ['Warrior', 'Knight', 'Berserker', 'Paladin', 'Aegis', 'Templar', 'Bloodrager', 'Juggernaut', 'Crusader', 'Divine Sentinel'] },
  'Spearman': { icon: 'class_dragoon', color: '#c8a030', members: ['Spearman', 'Lancer', 'Halberdier', 'Dragoon', 'Pikemaster', 'Vanguard', 'Glaive Lord', 'Warlord', 'Wyvern Rider', 'Dragon Knight'] },
  'Thief': { icon: 'class_rogue', color: '#7030c8', members: ['Thief', 'Assassin', 'Rogue', 'Ninja', 'Shadowblade', 'Nightstalker', 'Trickster', 'Shinobi', 'Shadowmaster', 'Infiltrator'] },
  'Archer': { icon: 'class_ranger', color: '#30a030', members: ['Archer', 'Sniper', 'Ranger', 'Crossbowman', 'Marksman', 'Deadeye', 'Beastmaster', 'Warden', 'Arbalist', 'Siege Master'] },
  'Mage': { icon: 'element_arcane', color: '#4060c8', members: ['Mage', 'Sorcerer', 'Warlock', 'Necromancer', 'Summoner', 'Archmage', 'Elementalist', 'Demonologist', 'Voidwalker', 'Lich', 'Deathcaller', 'Grand Summoner', 'Conjurer'] },
  'Spellsword': { icon: 'element_lightning', color: '#5040d0', members: ['Spellsword', 'Eldritch Knight', 'Rune Blade', 'Arcane Lord', 'Mystic Vanguard', 'Rune Master', 'Spellweaver'] },
  'Acolyte': { icon: 'element_sun', color: '#c0c0e0', members: ['Acolyte', 'Cleric', 'Bard', 'Druid', 'Monk', 'High Priest', 'Bishop', 'Maestro', 'Troubadour', 'Archdruid', 'Hierophant', 'Grandmaster', 'Zenith'] },
  'Priest': { icon: 'element_holy', color: '#d8d8f0', members: ['Priest', 'Chaplain', 'Confessor', 'High Confessor', 'Oracle', 'Prophet', 'Saint'] },
  'Tactician': { icon: 'class_leader', color: '#8030c8', members: ['Tactician', 'Strategist', 'Grand Strategist', 'War Master'] },
  'Scout': { icon: 'creature_eagle', color: '#a8c830', members: ['Scout', 'Pathfinder', 'Trailblazer', 'Void Walker'] },
  'Blacksmith': { icon: 'class_smith', color: '#888888', members: ['Blacksmith', 'Master Smith', 'Runesmith', 'Weaponsmith', 'Armorer', 'Artificer', 'Forge Lord'] },
  'Chef': { icon: 'class_cook', color: '#c85030', members: ['Chef', 'Head Chef', 'Culinary Master', 'Brewmaster', 'Iron Chef', 'Sous Chef', 'Gourmet', 'Master Chef', 'Butcher'] },
  'Medic': { icon: 'class_healer', color: '#30c870', members: ['Medic', 'Field Medic', 'Surgeon', 'Miracle Worker', 'Chief Medical Officer'] },
  'Quartermaster': { icon: 'class_paladin', color: '#c8c030', members: ['Quartermaster', 'Logistics Officer', 'Guild Treasurer', 'Trade Baron', 'Advisor', 'General', 'Commander'] },
  'Farmer': { icon: 'element_nature', color: '#9aaa30', members: ['Farmer', 'Master Farmer', 'Harvest Lord', 'Beast Tamer', 'Apex Predator', 'Wild Master', 'Forager', 'Scavenger', 'Hoarder', 'Tracker'] },
  'Merchant': { icon: 'coin_pouch', color: '#d4af37', members: ['Merchant', 'Trader', 'Guild Master', 'Trade Prince', 'Smuggler', 'Black Market Baron', 'Spy', 'Spymaster', 'Tycoon', 'Guildmaster'] },
  'Alchemist': { icon: 'alchemy_flask', color: '#30c8a0', members: ['Alchemist', 'Master Alchemist', 'Transmuter', 'Philosopher', 'Apothecary', 'Grand Alchemist', 'Herbalist', 'Poisoner', 'Plague Doctor'] },
  'Magic Engineer': { icon: 'class_engineer', color: '#30b8c8', members: ['Magic Engineer'] },
  'Classless': { icon: 'classless_runestone', color: '#888899', members: ['Classless', 'Adventurer', 'Veteran', 'Mercenary', 'Bounty Hunter', 'Hero', 'Champion'] },
}

const CLASS_ICONS = {}
const CLASS_COLORS = {}
for (const family of Object.values(CLASS_FAMILIES)) {
  for (const name of family.members) {
    CLASS_ICONS[name] = family.icon
    CLASS_COLORS[name] = family.color
  }
}

const SKILL_RARITY_COLORS = {
  common: '#888',
  uncommon: '#4a9a6a',
  rare: '#4a7aaa',
  epic: '#8030c8',
  legendary: '#c9a84c',
}

const APTITUDE_ORDER = ['Combat', 'Survival', 'Tactical', 'Mental', 'Leadership']

function getAptitudeColor(value) {
  if (value >= 90) return '#c9a84c' // gold - exceptional
  if (value >= 75) return '#6fba6f' // green - high
  if (value >= 50) return 'var(--text-hi)' // normal
  if (value >= 25) return '#c87030' // orange - low
  return 'var(--red)' // very low
}

export function Stars({ count, max = 7 }) {
  return (
    <div className={`stars birth-star-${count}`}>
      {Array.from({ length: max }).map((_, i) => (
        <span key={i} className={count === 7 && i < count ? 'rainbow-text' : 'star'}>
          {i < count ? '★' : '☆'}
        </span>
      ))}
    </div>
  )
}

// Keyed by CLASS_FAMILIES name (not individual evolution name) — an
// evolution like Rogue, Paladin, or Adventurer inherits its family's
// tooltip via the same family lookup ClassBadge already does for
// icon/color/archetype below. Per-evolution-name entries previously left
// most of the ~90 evolutions (and, embarrassingly, two base classes that
// had silently-overwritten duplicate keys) falling through to the generic
// "A powerful hero." fallback.
const CLASS_TOOLTIPS = {
  'Warrior': 'A durable frontline fighter that absorbs damage and protects allies.',
  'Spearman': 'A frontline combatant wielding a long-reaching weapon with high pierce damage.',
  'Thief': 'A nimble combatant that strikes from the shadows with high crit chance.',
  'Archer': 'A ranged attacker that rains arrows on the enemy backline.',
  'Mage': 'A spellcaster dealing devastating magical area damage.',
  'Spellsword': 'A hybrid combatant mixing martial prowess with devastating magical strikes.',
  'Acolyte': 'A devout follower providing essential support and minor healing to allies.',
  'Priest': 'Offers divine protection and massive morale recovery.',
  'Tactician': 'A strategic mastermind that provides combat buffs and re-rolls.',
  'Scout': 'Reveals hidden paths and traps, reducing ambush chances.',
  'Blacksmith': 'Upgrades team equipment and provides a baseline stat aura.',
  'Chef': 'Provides powerful morale and Health recovery buffs after combat.',
  'Medic': 'Heals wounds and significantly reduces trauma and stress.',
  'Quartermaster': 'Manages the party inventory, increasing gold and supply gains.',
  "Farmer": "A hardy worker who increases the Farm's ingredient yields for the base.",
  'Merchant': 'A savvy trader who boosts gold income and finds better deals.',
  'Alchemist': 'Brews potent potions and increases rare material drop rates.',
  'Magic Engineer': 'A master of magical contraptions, building turrets and traps.',
  'Classless': 'A blank slate. Though weak now, it harbors the potential for unique, secret evolutions at higher levels.',
};

const EGO_TOOLTIPS = {
  'Aggressive': 'Desires a team full of damage dealers (Mage, Warrior, etc).',
  'Cautious': 'Desires a team with strong intelligence and healing support.',
  'Tactical': 'Desires a perfectly balanced formation (2 Frontline, 3 Backline).',
  'Leader': 'Desires to be the undisputed leader (highest star rarity on the team).',
  'Lone Wolf': 'Desires a smaller team (3 or fewer heroes) for maximum glory.',
  'Resonant': 'Desires a team composed entirely of the exact same class.'
};

const BATTLE_TENDENCY_TOOLTIPS = {
  'Reckless': 'Fights without caution — as squad Leader, pushes the team to finish off the weakest enemy first. If 1-2★, prone to panicking and fleeing a losing fight.',
  'Calculating': 'Fights with cold precision — as squad Leader, pushes the team to remove the biggest threat first. If 1-2★, may calculate that retreat is the smart play.',
  'Protective': 'Fights to shield others above all else — never breaks and runs, regardless of star.',
  'Glory-Seeking': 'Fights for the kill, not the plan — as squad Leader, pushes the team to finish off the weakest enemy first. Too proud to flee.',
  'Stoic': 'Fights without flair or hesitation, unreadable under pressure — never breaks and runs.',
  'Vengeful': 'Fights like every battle is personal — anger keeps them in the fight, never fleeing.',
};

export const FRONTLINE_FAMILIES = ['Warrior', 'Spearman', 'Thief', 'Spellsword', 'Scout', 'Blacksmith', 'Farmer']

export function tierForStar(birthStar) {
  if (birthStar >= 7) return 'prismatic'
  if (birthStar >= 5) return 'gold'
  if (birthStar >= 3) return 'silver'
  return 'bronze'
}

// Status overlay (injured/kia) drawn over the templated card-image background
// (see card_template_service.py — the border/frame itself is now baked into
// that backend-composited image, not drawn here, to avoid a doubled border).
// Reused by both the full HeroCard portrait and the lightweight post-combat
// Team Status summary cards.
//
// The art tilts under the pointer (ParallaxCard). Only the framed art moves —
// the name/stats below stay put, so the card reads as a still page with a
// window cut into it rather than as a whole slab being skewed. That also keeps
// clear of .hero-card:hover, which already owns a transform on the outer card.
//
// A dead hero doesn't tilt: the roster dims them to 40% and they aren't
// clickable, and giving a corpse a jaunty shine is the wrong note.
export function CardFrame({ birthStar, status, children, style, parallax = true }) {
  const tier = tierForStar(birthStar)
  return (
    <ParallaxCard
      className={`card-frame card-frame-${tier}`}
      style={style}
      disabled={!parallax || status === 'kia'}
      maxTilt={6}
    >
      {/* Depth 6 on the art, 3 on the status wash: an overlay travelling
          slightly less than what it tints keeps reading as glass over the
          portrait rather than as part of it. */}
      <div className="parallax-layer" style={{ '--depth': 6 }}>
        {children}
      </div>
      {status === 'injured' && (
        <div className="card-frame-overlay card-frame-overlay-injured parallax-layer"
             style={{ '--depth': 3 }} />
      )}
      {status === 'kia' && (
        <>
          <div className="card-frame-overlay card-frame-overlay-kia" />
          <div className="card-frame-banner">KILLED IN ACTION</div>
        </>
      )}
    </ParallaxCard>
  )
}

export function ClassBadge({ heroClass }) {
  if (!heroClass) return null
  const color = CLASS_COLORS[heroClass] || '#555'
  const icon = CLASS_ICONS[heroClass] || '?'
  
  let familyName = 'Classless'
  for (const [fam, data] of Object.entries(CLASS_FAMILIES)) {
    if (data.members.includes(heroClass)) {
      familyName = fam; break;
    }
  }
  let archetype = 'Backline'
  if (heroClass === 'Classless') archetype = 'Wildcard'
  else if (FRONTLINE_FAMILIES.includes(familyName)) archetype = 'Frontline'

  // Prefer the custom class sigil (class-base/<FAMILY>.svg, recolorable),
  // falling back to the legacy flat PNG GameIcon when no SVG exists. Family
  // name → UPPER_SNAKE, except the set ships M_ENGINEER.svg (not
  // MAGIC_ENGINEER) and has no CLASSLESS.svg (fallback covers it).
  const sigilName = familyName === 'Magic Engineer'
    ? 'M_ENGINEER'
    : familyName.toUpperCase().replace(/ /g, '_')
  const glyph = (
    <Sigil
      set="class-base" name={sigilName} size={14} color={color}
      fallback={icon !== '?' ? <GameIcon name={icon} size={14} /> : '?'}
    />
  )

  return (
    <span 
      title={`[${archetype}] ${CLASS_TOOLTIPS[familyName] || 'A powerful hero.'}`}
      style={{
      display: 'inline-flex', alignItems: 'center', gap: '3px',
      background: `${color}22`, border: `1px solid ${color}66`,
      color: color, borderRadius: 3,
      padding: '1px 6px', fontSize: '0.7em',
      fontFamily: 'Cinzel, serif', letterSpacing: '0.05em',
      marginTop: '0.3em',
      cursor: 'help',
    }}>
      {glyph} {heroClass}
    </span>
  )
}

export function LevelBadge({ level, ascensionStar, large = false }) {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center',
      background: 'rgba(201,168,76,0.1)', border: '1px solid rgba(201,168,76,0.3)',
      color: 'var(--gold)', borderRadius: 3,
      padding: large ? '2px 9px' : '1px 6px', fontSize: large ? '1.15em' : '0.7em',
      fontFamily: 'Cinzel, serif', marginLeft: '0.3em',
    }}>
      Lv.{level}
    </span>
  )
}

// Mirrors the real combat formula in calc_damage() (combat_service.py):
// below 40 morale, a hero's own damage output is multiplied by
// 0.5 + morale/80 — a sliding penalty, not a stepped one. At 40+ morale
// there is currently no penalty at all (the "shaken" tier is cosmetic only).
function moraleEffectDesc(morale) {
  if (morale >= 40) return 'No combat penalty at this morale.'
  const factor = 0.5 + morale / 80
  const pct = Math.round((1 - factor) * 100)
  return `Damage output reduced by ${pct}% while attacking, until morale recovers to 40+.`
}

export function MoraleBar({ morale, state }) {
  return (
    <div className="morale-bar-wrap" title={moraleEffectDesc(morale)} style={{ cursor: 'help' }}>
      <div className="morale-label">
        <span>Morale</span>
        <span className={`text-${state === 'steady' ? 'green' : state === 'broken' ? 'red' : 'gold'}`}>
          {MORALE_STATE_LABEL[state] || state} ({morale})
        </span>
      </div>
      <div className="morale-bar-bg">
        <div className={`morale-bar-fill ${state}`} style={{ width: `${morale}%` }} />
      </div>
    </div>
  )
}

export function HpBar({ health, maxHp }) {
  const pct = Math.max(0, Math.min(100, (health / maxHp) * 100))
  return (
    <div className="health-bar-wrap">
      <div className="morale-label">
        <span>Health</span>
        <span>{health} / {maxHp}</span>
      </div>
      <div className="health-bar-bg">
        <div className="health-bar-fill" style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

export function ManaBar({ maxMana }) {
  // Mana is combat-session-only state (resets to 50% of max at the start of
  // every fight, see services/combat_service.py) — there's no persisted
  // "current" value to show outside combat, so this always reads as full,
  // same as how a weapon's damage stat is shown at its base value on the
  // roster screen rather than mid-fight state.
  return (
    <div className="mana-bar-wrap" title="Mana resets each fight — this is the pool size, not a current value.">
      <div className="morale-label">
        <span>Mana</span>
        <span>{maxMana}</span>
      </div>
      <div className="mana-bar-bg">
        <div className="mana-bar-fill" style={{ width: '100%' }} />
      </div>
    </div>
  )
}

function AscensionStars({ count }) {
  if (!count || count <= 0) return null
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: '2px',
      marginTop: '0.3em',
    }}>
      <span className="text-dim" style={{ fontSize: '0.65em', marginRight: '0.3em' }}>Ascension</span>
      {Array.from({ length: 7 }).map((_, i) => (
        <span key={i} style={{
          fontSize: '0.7em',
          color: i < count ? 'var(--gold)' : 'var(--border)',
          textShadow: i < count ? '0 0 4px rgba(201,168,76,0.5)' : 'none',
        }}>◆</span>
      ))}
    </div>
  )
}

const KIND_STYLE = {
  rival: { label: 'Rival', color: '#e0913c' },
  comrade: { label: 'Comrade', color: '#4f92e8' },
}

// Mentors / students / sparring bonds, shown on the full hero card. A
// student who's trained a lot under one mentor grows real attachment
// ("looks up to", "reveres"), which is why we lead with mentors.
function RelationshipsDisplay({ hero }) {
  const [data, setData] = useState(null)

  useEffect(() => {
    let cancelled = false
    getHeroRelationships(hero.id).then(d => { if (!cancelled) setData(d) }).catch(() => {})
    return () => { cancelled = true }
  }, [hero.id])

  if (!data) return null
  const { mentors = [], students = [], bonds = [] } = data
  // Bonds that aren't already represented as a mentor/student pairing.
  const otherBonds = bonds.filter(b => !b.is_mentor_pair)
  if (mentors.length === 0 && students.length === 0 && otherBonds.length === 0) return null

  return (
    <div className="story-block" style={{ marginTop: '1em', paddingTop: '0.75em', borderTop: '1px solid var(--border)' }}>
      <div style={{ fontFamily: 'Cinzel, serif', color: 'var(--gold)', fontSize: '0.95em', marginBottom: '0.4em' }}>Bonds & Mentorship</div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.3em', fontSize: '0.9em' }}>
        {mentors.map(m => (
          <div key={`m${m.id}`} className="text-dim">
            <span style={{ color: '#c9a84c' }}>★ Mentor:</span> {hero.name} {m.attachment} <span className="text-hi">{m.name}</span>
            <span style={{ opacity: 0.6 }}> ({m.sessions} session{m.sessions === 1 ? '' : 's'})</span>
          </div>
        ))}
        {students.map(s => (
          <div key={`s${s.id}`} className="text-dim">
            <span style={{ color: '#6fba6f' }}>✎ Student:</span> raised <span className="text-hi">{s.name}</span>
            <span style={{ opacity: 0.6 }}> ({s.sessions} session{s.sessions === 1 ? '' : 's'})</span>
          </div>
        ))}
        {otherBonds.map(b => {
          const st = KIND_STYLE[b.kind] || KIND_STYLE.comrade
          return (
            <div key={`b${b.id}`} className="text-dim">
              <span style={{ color: st.color }}>◆ {st.label}:</span> <span className="text-hi">{b.name}</span>
              <span style={{ opacity: 0.6 }}> (Bond Lv.{b.bond_level})</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function AptitudeDisplay({ hero }) {
  const [data, setData] = useState(null)

  useEffect(() => {
    let cancelled = false
    getHeroAptitudes(hero.id).then(d => { if (!cancelled) setData(d) }).catch(() => {})
    return () => { cancelled = true }
  }, [hero.id, hero.level])

  const aptitudes = data?.aptitudes || {}
  const reveals = Object.values(aptitudes).filter(v => v != null).length
  const talentTitle = data?.talent_title

  return (
    <div style={{ marginTop: '0.5em' }}>
      <div className="text-dim" style={{ fontSize: '0.7em', marginBottom: '0.3em', fontFamily: 'Cinzel, serif' }}>
        Aptitudes
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.2em' }}>
        {APTITUDE_ORDER.map((apt) => {
          const key = `apt_${apt.toLowerCase()}`
          const value = aptitudes[key]
          const isRevealed = value != null
          return (
            <div key={apt} style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              fontSize: '0.72em',
              padding: '0.15rem 0.4em',
              background: isRevealed ? 'rgba(255,255,255,0.03)' : 'transparent',
              borderRadius: 2,
            }}>
              <span className="text-dim">{apt}</span>
              {isRevealed ? (
                <span style={{
                  color: getAptitudeColor(value),
                  fontFamily: 'Cinzel, serif',
                  fontWeight: value >= 75 ? 'bold' : 'normal',
                }}>
                  {value}
                </span>
              ) : (
                <span style={{ color: 'var(--border)', fontStyle: 'italic', fontSize: '0.68em' }}>???</span>
              )}
            </div>
          )
        })}
      </div>
      {talentTitle && (
        <div style={{
          marginTop: '0.4em', textAlign: 'center', fontSize: '0.78em',
          fontFamily: 'Cinzel, serif', fontWeight: 'bold', color: '#c9a84c',
          textShadow: '0 0 6px rgba(201,168,76,0.5)',
        }}>
          ✦ {talentTitle} ✦
          <div className="text-dim" style={{ fontSize: '0.65em', fontWeight: 'normal', fontStyle: 'italic' }}>
            est. 1 in {data.talent_rarity_one_in?.toLocaleString()}
          </div>
        </div>
      )}
      {reveals < 5 && (
        <div className="text-dim" style={{ fontSize: '0.6em', marginTop: '0.2em', fontStyle: 'italic' }}>
          Next reveal at Lv.{(reveals + 1) * 5}
        </div>
      )}
    </div>
  )
}

export default function HeroCard({ hero, onAssign, onManageEquipment, onManageConsumable, onAutoEquip, selected, onClick, onToggleSelect, showFull = false, scale = 1, onRegenerateProfile, actions }) {
  if (!hero) return null
  const dead = !hero.is_alive
  const [refreshing, setRefreshing] = useState(false)
  const [cardImgError, setCardImgError] = useState(false)
  const [imgError, setImgError] = useState(false)
  const [retryKey, setRetryKey] = useState(0)
  const retryCountRef = React.useRef(0)
  const [showSynergyTip, setShowSynergyTip] = useState(false)

  const handleRegenerateProfile = async (e) => {
    e.stopPropagation()
    setRefreshing(true)
    try {
      await regenerateProfile(hero.id)
      if (onRegenerateProfile) onRegenerateProfile()
    } catch (err) {
      console.error(err)
    } finally {
      setRefreshing(false)
    }
  }

  // Backstory unlocks SENTENCE by sentence with promotions (never slicing
  // mid-word like the old percentage cut), scaling all the way to 6★.
  const activeStar = hero.current_star || hero.birth_star
  const storySentences = hero.backstory
    ? (hero.backstory.match(/[^.!?]+[.!?]+["']?\s*/g) || [hero.backstory])
    : []
  // Spread the sentences across stars 1→6: a 1★ knows only the opening
  // line of their own legend; the full story belongs to a 6★.
  const unlockedCount = storySentences.length
    ? Math.max(1, Math.ceil(storySentences.length * Math.min(1, activeStar / 6)))
    : 0
  const unlockedStory = storySentences.slice(0, unlockedCount).join('')
  const lockedSentences = storySentences.length - unlockedCount
  const storyFullyUnlocked = lockedSentences <= 0

  return (
    <div
      className={`hero-card ${selected ? 'selected' : ''} ${dead ? 'dead' : ''} ${showFull ? 'full' : ''}`} style={{ fontSize: showFull ? "1.6em" : `${scale}em` }}
      onClick={!dead && onClick ? onClick : undefined}
    >
      {onToggleSelect && (
        <div 
          onClick={(e) => { e.stopPropagation(); onToggleSelect(); }}
          style={{
            position: 'absolute', top: 5, left: 5, zIndex: 10,
            width: 20, height: 20, borderRadius: '50%',
            border: '2px solid var(--border-light)',
            background: selected ? 'var(--gold)' : 'rgba(0,0,0,0.5)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            cursor: 'pointer',
            color: '#000', fontSize: '0.8em', fontWeight: 'bold'
          }}
        >
          {selected && '✓'}
        </div>
      )}
      <CardFrame birthStar={hero.birth_star} style={{ position: 'relative', flexShrink: 0 }}>
        {hero.is_on_team > 0 && !showFull && (
          <div style={{
            position: 'absolute', top: 5, right: 5, zIndex: 10,
            background: 'rgba(64, 96, 200, 0.9)', color: '#fff', fontSize: '0.65em',
            padding: '2px 6px', borderRadius: '4px', fontWeight: 'bold',
            border: '1px solid rgba(255,255,255,0.3)'
          }}>
            T{hero.is_on_team}
          </div>
        )}
        {hero.portrait_path && !imgError && !hero.portrait_path.includes('default_') ? (
          <img
            key={retryKey}
            src={(showFull || cardImgError)
              // Full view shows the raw transparent cutout on the CSS CardFrame
              // (the old baked-in ornate card composite is retired — Liam). Mini
              // grid thumbs still use the server face-crop.
              ? `/${hero.portrait_path}?t=${new Date().getTime()}`
              : `/heroes/${hero.id}/card-image?mini=1&t=${new Date().getTime()}`}
            alt={hero.name}
            className="hero-portrait"
            draggable={false}
            style={showFull ? { height: 'auto', maxHeight: '700px', objectFit: 'contain' } : {}}
            onError={() => {
              // A transient failure (composite still being prewarmed, brief
              // backend hiccup) shouldn't permanently stick on the
              // placeholder — retry the current URL a couple times before
              // falling through to the next fallback stage.
              if (retryCountRef.current < 2) {
                retryCountRef.current += 1
                setTimeout(() => setRetryKey(k => k + 1), 1500)
                return
              }
              retryCountRef.current = 0
              if (cardImgError) setImgError(true)
              else setCardImgError(true)
            }}
          />
        ) : (
          <div className="hero-portrait-placeholder" style={{ 
            display: 'flex', 
            flexDirection: 'column', 
            alignItems: 'center', 
            justifyContent: 'center',
            background: `radial-gradient(circle at top, ${CLASS_COLORS[hero.hero_class] || '#444'}, #1a1a24)`,
            ...(showFull ? { height: '400px' } : {}),
            width: '100%',
            position: 'relative',
            overflow: 'hidden'
          }}>
          <div style={{ opacity: 0.5, marginBottom: '20px' }}>
            <Sigil set={classSigil(hero.hero_class).set} name={classSigil(hero.hero_class).name} size={showFull ? 64 : 40} color="var(--lavender)"
              fallback={<Sigil set="class-base" name="CLASSLESS" size={showFull ? 64 : 40} color="var(--lavender)" />} />
          </div>
            <div style={{
              position: 'absolute', bottom: '15px', left: 0, right: 0,
              textAlign: 'center', background: 'rgba(200, 50, 50, 0.8)',
              color: 'white', fontSize: '0.65em', padding: '2px',
              fontWeight: 'bold', textTransform: 'uppercase'
            }}>
              Placeholder (Regenerate Profile)
            </div>
          </div>
        )}
        
        {showFull && !dead && (
          <button
            className="btn btn-gold"
            style={{ position: 'absolute', bottom: '5px', right: '5px', padding: '2px 6px', fontSize: '0.6em' }}
            onClick={handleRegenerateProfile}
            disabled={refreshing}
            title="Reroll this hero's portrait — keeps their name, lore, and stats."
          >
            {refreshing ? '...' : 'Regenerate Portrait'}
          </button>
        )}
      </CardFrame>

      <div className="hero-name">{hero.name}</div>
      <div className="hero-title">{hero.title}</div>
      {showFull && hero.synergy_group && (
        <div style={{ marginTop: '0.4em', marginBottom: '0.2em', position: 'relative', display: 'inline-block' }}>
          <span
            onMouseEnter={(e) => { e.stopPropagation(); setShowSynergyTip(true) }}
            onMouseLeave={() => setShowSynergyTip(false)}
            style={{
              fontSize: '0.65em',
              background: 'rgba(200, 160, 48, 0.2)',
              color: '#e8c050',
              padding: '0.2rem 0.5em',
              borderRadius: '4px',
              fontFamily: 'Cinzel, serif',
              fontWeight: 'bold',
              border: '1px solid rgba(200, 160, 48, 0.4)',
              cursor: 'help',
            }}
          >
            <span style={{ marginRight: '4px' }}><GameIcon name="crest" size={13} /></span>
            {hero.synergy_group}
          </span>
          {showSynergyTip && (
            <div style={{
              position: 'absolute',
              bottom: '100%',
              left: '50%',
              transform: 'translateX(-50%)',
              marginBottom: '6px',
              width: '220px',
              background: '#1a1a1a',
              border: '1px solid rgba(200, 160, 48, 0.5)',
              borderRadius: '4px',
              padding: '0.6em 0.7em',
              fontSize: '0.7em',
              fontFamily: 'inherit',
              fontWeight: 'normal',
              color: '#ddd',
              lineHeight: 1.4,
              zIndex: 20,
              boxShadow: '0 4px 12px rgba(0,0,0,0.5)',
              pointerEvents: 'none',
            }}>
              <strong style={{ color: '#e8c050' }}>{hero.synergy_group} Synergy</strong><br/>
              Deploying multiple "{hero.synergy_group}" heroes on the same team grants +5% STR/INT/AGI/Health per group member in combat (stacks with team size).
            </div>
          )}
        </div>
      )}

      <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: '0.3em', marginTop: '0.3em' }}>
        <Stars count={hero.birth_star} />
        <LevelBadge level={hero.level || 1} ascensionStar={hero.ascension_star || 0} large={showFull} />
      </div>

      <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: '0.3em', marginTop: '0.3em' }}>
        <ClassBadge heroClass={hero.hero_class} />
        {hero.condition && hero.condition !== 'Normal' && (
          <span
            title={hero.condition === 'Depressed' ? `Depressed (-75% Stats) until ${new Date(hero.condition_until).toLocaleString()}` : "Mind broken from Survivor's Guilt. Permanently retired from combat."}
            style={{
            display: 'inline-flex', alignItems: 'center', gap: '3px',
            background: hero.condition === 'Depressed' ? 'rgba(100,150,255,0.15)' : 'rgba(100,100,100,0.15)', border: `1px solid ${hero.condition === 'Depressed' ? 'rgba(100,150,255,0.4)' : 'rgba(100,100,100,0.4)'}`,
            color: hero.condition === 'Depressed' ? '#88bbff' : '#888', borderRadius: 3,
            padding: '1px 6px', fontSize: '0.7em',
            fontFamily: 'Cinzel, serif', marginTop: '0.3em', cursor: 'help'
          }}>
            {hero.condition === 'Depressed' ? '◆️ Depressed' : '✦ Retired'}
          </span>
        )}
        {!showFull && (hero.is_team_leader || (hero.ego_type && hero.ego_type.toLowerCase() !== 'null')) && (
          <span title="Click for Ego/leadership details" style={{
            display: 'inline-flex', alignItems: 'center', gap: '3px',
            background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.18)',
            color: 'var(--text-dim)', borderRadius: 3,
            padding: '1px 6px', fontSize: '0.7em',
            fontFamily: 'Cinzel, serif', marginTop: '0.3em', cursor: 'help'
          }}>
            {hero.is_team_leader ? '♛' : '✦'} more...
          </span>
        )}
      </div>

      {showFull && (
      <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: '0.3em', marginTop: '0.3em' }}>
        {hero.ego_type && hero.ego_type.toLowerCase() !== 'null' && (
          <span
            title={`Ego Preference: ${EGO_TOOLTIPS[hero.ego_type] || 'Unknown desires.'}\nPatience: ${hero.ego_patience ?? 100}/100\n\n${
              hero.is_ego_satisfied === undefined ? '"I await deployment."' :
              hero.is_ego_satisfied ? '"This formation is acceptable."' :
              (hero.ego_patience ?? 100) > 50 ? '"This team composition displeases me. Fix it."' :
              '"My patience wears thin... I will take matters into my own hands soon."'
            }`}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: '4px',
              background: 'rgba(255,100,100,0.1)', border: '1px solid rgba(255,100,100,0.3)',
              color: '#ff8888', borderRadius: 3,
              padding: '1px 6px', fontSize: '0.7em',
              fontFamily: 'Cinzel, serif',
              marginTop: '0.3em',
              cursor: 'help'
            }}>
            ✦ Ego: {hero.ego_type}
            <span style={{ display: 'inline-block', width: '28px', height: '4px', background: 'rgba(255,255,255,0.15)', borderRadius: 2, overflow: 'hidden' }}>
              <span style={{
                display: 'block', height: '100%',
                width: `${hero.ego_patience ?? 100}%`,
                background: (hero.ego_patience ?? 100) <= 30 ? '#ff4444' : (hero.ego_patience ?? 100) <= 60 ? '#ffaa44' : '#88ff88',
              }} />
            </span>
          </span>
        )}
        {/* !! matters: is_team_leader is a SQLite integer, and {0 && ...}
            renders a literal "0" next to the badges. */}
        {!!hero.is_team_leader && (
          <span title="Team Leader — sets the squad's tactical doctrine in combat (if they have an Ego, their preferences also shape the recommended lineup)." style={{
            display: 'inline-flex', alignItems: 'center', gap: '3px',
            background: 'rgba(201,168,76,0.15)', border: '1px solid rgba(201,168,76,0.4)',
            color: 'var(--gold)', borderRadius: 3,
            padding: '1px 6px', fontSize: '0.7em',
            fontFamily: 'Cinzel, serif', marginTop: '0.3em', cursor: 'help'
          }}>
            ♛ Leader
          </span>
        )}
        {hero.battle_tendency && (
          <span title={BATTLE_TENDENCY_TOOLTIPS[hero.battle_tendency] || 'Their instinct in a fight.'} style={{
            display: 'inline-flex', alignItems: 'center', gap: '3px',
            background: 'rgba(140,140,160,0.12)', border: '1px solid rgba(140,140,160,0.35)',
            color: '#b0b0c8', borderRadius: 3,
            padding: '1px 6px', fontSize: '0.7em',
            fontFamily: 'Cinzel, serif', marginTop: '0.3em', cursor: 'help'
          }}>
            {hero.battle_tendency}
          </span>
        )}
        {hero.bonds && hero.bonds.length > 0 && (() => {
          // 1% stat boost per total bond level shared with current teammates
          // in combat (see bonds_service.get_team_bonds_multiplier) — only
          // actually applies when teammates with these bonds are deployed
          // together, but the total here is the cap that boost can reach.
          const totalBondLevel = hero.bonds.reduce((sum, b) => sum + b.bond_level, 0)
          const tooltip = [
            ...hero.bonds.map(b => `${b.hero_a_name} & ${b.hero_b_name} (Lv ${b.bond_level})`),
            `Up to +${totalBondLevel}% stats when bonded teammates fight together`,
          ].join('\n')
          return (
            <span
              title={tooltip}
              style={{
                display: 'inline-flex', alignItems: 'center', gap: '3px',
                background: 'rgba(255,105,180,0.15)', border: '1px solid rgba(255,105,180,0.4)',
                color: '#ff69b4', borderRadius: 3,
                padding: '1px 6px', fontSize: '0.7em',
                fontFamily: 'Cinzel, serif', marginTop: '0.3em', cursor: 'help'
              }}>
              ♥ {hero.bonds.length} (+{totalBondLevel}%)
            </span>
          )
        })()}
        {hero.legacies && hero.legacies.length > 0 && (
          <span 
            title={hero.legacies.join('\n')}
            style={{
            display: 'inline-flex', alignItems: 'center', gap: '3px',
            background: 'rgba(180,180,255,0.15)', border: '1px solid rgba(180,180,255,0.4)',
            color: '#a0a0ff', borderRadius: 3,
            padding: '1px 6px', fontSize: '0.7em',
            fontFamily: 'Cinzel, serif', marginTop: '0.3em', cursor: 'help'
          }}>
            ✦️ {hero.legacies.length}
          </span>
        )}
      </div>
      )}

      <div style={{ flex: 1 }} />

      {/* Ascension stars */}
      <AscensionStars count={hero.ascension_star || 0} />

      {dead && <div className="text-red text-sm" style={{ marginTop: '0.3em' }}>✦ Fallen</div>}

      {!dead && (
        <>
          <HpBar health={hero.health} maxHp={hero.max_health} />
          <MoraleBar morale={hero.morale} state={hero.morale_state || 'steady'} />
          {hero.max_mana != null && <ManaBar maxMana={hero.max_mana} />}

          <div className="stats-grid" style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <div className="stats-row">
              <div className="stat" title={`Base: ${hero.base_strength ?? hero.strength}`}>STR <span>{hero.strength}</span></div>
              <div className="stat" title={`Base: ${hero.base_intelligence ?? hero.intelligence}`}>INT <span>{hero.intelligence}</span></div>
              <div className="stat" title={`Base: ${hero.base_endurance ?? hero.endurance ?? 5}`}>END <span>{hero.endurance ?? 5}</span></div>
            </div>
            <div className="stats-row">
              <div className="stat" title={`Base: ${hero.base_agility ?? hero.agility}`}>AGI <span>{hero.agility}</span></div>
              <div className="stat" title={`Base: ${hero.base_willpower ?? hero.willpower ?? 6}`}>WIL <span>{hero.willpower ?? 6}</span></div>
              <div className="stat" title={`Base: ${hero.base_luck ?? hero.luck ?? 5}`}>LUC <span>{hero.luck ?? 5}</span></div>
            </div>
          </div>

          {showFull && (
            <div style={{ marginTop: '0.75em', borderTop: '1px solid var(--border)', paddingTop: '0.75em' }}>
              <div className="stats-row" style={{ marginTop: '0.5em' }}>
                <div className="stat">Kills <span>{hero.kills}</span></div>
                <div className="stat">Floors <span>{hero.floors_survived}</span></div>
                <div className="stat">Stress <span>{hero.stress}</span></div>
                <div className="stat">Trauma <span>{hero.trauma}</span></div>
                <div className="stat" title="Loyalty (affinity) — raised by gifts they love. Feeds the upcoming raid/loyalty mechanics: a low-loyalty hero captured in a raid may turn on you.">
                  Loyalty <span style={{ color: (hero.affinity ?? 0) >= 50 ? '#e06080' : undefined }}>{hero.affinity ?? 0}</span>
                </div>
              </div>
              {hero.can_pilot === 1 && (
                <div style={{ marginTop: '0.4em', color: 'var(--blue)', fontSize: '0.75em' }}>
                  ⚙ Can pilot vessels
                </div>
              )}

              {/* Aptitude display */}
              <AptitudeDisplay hero={hero} />

              {/* Equipment Display */}
              <div style={{ marginTop: '0.75em' }}>
                <div style={{ display: 'flex', alignItems: 'center', marginBottom: '0.3em' }}>
                  <div className="text-dim" style={{ fontSize: '0.7em', fontFamily: 'Cinzel, serif', flex: 1 }}>
                    Equipment
                  </div>
                  {onAutoEquip && (
                    <div style={{ display: 'flex', gap: '0.25em' }}>
                      <button onClick={(e) => { e.stopPropagation(); onAutoEquip(hero, 'auto'); }} style={{ fontSize: '0.6em', padding: '0.15em 0.4em', background: 'rgba(201,168,76,0.15)', border: '1px solid var(--gold)', color: 'var(--gold)', borderRadius: 3, cursor: 'pointer' }}>Auto Equip</button>
                      <button onClick={(e) => { e.stopPropagation(); onAutoEquip(hero, 'unequip_all'); }} style={{ fontSize: '0.6em', padding: '0.15em 0.4em', background: 'transparent', border: '1px solid var(--border)', color: 'var(--text-dim)', borderRadius: 3, cursor: 'pointer' }}>Unequip All</button>
                    </div>
                  )}
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.3em' }}>
                  {/* Heroes wear two accessories now — each accessory row
                      shows the nth equipped accessory independently. */}
                  {[['weapon', 0], ['armor', 0], ['accessory', 0], ['accessory', 1]].map(([slot, slotIdx]) => {
                    const matches = hero.equipment ? hero.equipment.filter(e => e.type?.toLowerCase() === slot) : [];
                    const eq = matches[slotIdx] || null;
                    const slotLabel = slot === 'accessory' ? `accessory ${slotIdx + 1}` : slot;
                    return (
                      <div key={`${slot}-${slotIdx}`} style={{
                        padding: '0.3rem 0.5em',
                        background: 'rgba(255,255,255,0.02)',
                        borderLeft: `2px solid ${eq ? rarityColor(eq.rarity) : '#444'}`,
                        borderRadius: '0 3px 3px 0',
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center'
                      }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.4em', flex: 1, marginRight: '0.5em', minWidth: 0 }}>
                          {eq && <EquipmentTypeIcon item={eq} fontSize="1rem" glow={rarityColor(eq.rarity)} />}
                          <div style={{ minWidth: 0 }}>
                          <div style={{ fontSize: '0.65em', color: 'var(--text-dim)', textTransform: 'capitalize', marginBottom: '0.1em' }}>{slotLabel}</div>
                          {eq ? (
                            <>
                              <div style={{ fontSize: '0.75em', color: 'var(--text-hi)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{eq.name}</div>
                              {eq.stats_json && (
                                <div style={{ display: 'flex', gap: '0.4em', flexWrap: 'wrap', marginTop: '0.1em' }}>
                                  {Object.entries(JSON.parse(eq.stats_json)).map(([k, v]) => (
                                    <span key={k} className="text-green" style={{ fontSize: '0.6em' }}>
                                      +{v} {k.toUpperCase()}
                                    </span>
                                  ))}
                                </div>
                              )}
                            </>
                          ) : (
                            <div style={{ fontSize: '0.75em', color: 'var(--text-dim)', fontStyle: 'italic' }}>Empty</div>
                          )}
                          </div>
                        </div>
                        {onManageEquipment && (
                          <button 
                            onClick={() => onManageEquipment(hero, slot, eq)}
                            style={{ 
                              background: eq ? 'transparent' : 'rgba(201,168,76,0.1)', 
                              border: eq ? '1px solid var(--border)' : '1px solid var(--gold)', 
                              color: eq ? 'var(--text-dim)' : 'var(--gold)', 
                              padding: '0.2rem 0.4em', 
                              borderRadius: '3px', 
                              cursor: 'pointer',
                              fontSize: '0.7em'
                            }}
                          >
                            {eq ? 'Unequip' : 'Equip'}
                          </button>
                        )}
                      </div>
                    )
                  })}
                  <div style={{
                    padding: '0.3rem 0.5em',
                    background: 'rgba(255,255,255,0.02)',
                    borderLeft: `2px solid ${hero.equipped_consumable ? '#4a9a6a' : '#444'}`,
                    borderRadius: '0 3px 3px 0',
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center'
                  }}>
                    <div style={{ flex: 1, marginRight: '0.5em' }}>
                      <div style={{ fontSize: '0.65em', color: 'var(--text-dim)', textTransform: 'capitalize', marginBottom: '0.1em' }}>consumable</div>
                      {hero.equipped_consumable ? (
                        <div style={{ fontSize: '0.75em', color: 'var(--text-hi)' }}>{hero.equipped_consumable}</div>
                      ) : (
                        <div style={{ fontSize: '0.75em', color: 'var(--text-dim)', fontStyle: 'italic' }}>Empty</div>
                      )}
                    </div>
                    {onManageConsumable && (
                      <button
                        onClick={() => onManageConsumable(hero)}
                        style={{
                          background: hero.equipped_consumable ? 'transparent' : 'rgba(201,168,76,0.1)',
                          border: hero.equipped_consumable ? '1px solid var(--border)' : '1px solid var(--gold)',
                          color: hero.equipped_consumable ? 'var(--text-dim)' : 'var(--gold)',
                          padding: '0.2rem 0.4em',
                          borderRadius: '3px',
                          cursor: 'pointer',
                          fontSize: '0.7em'
                        }}
                      >
                        {hero.equipped_consumable ? 'Change' : 'Equip'}
                      </button>
                    )}
                  </div>
                </div>
              </div>

              {/* Traits Display */}
              {hero.traits && (
                <div style={{ marginTop: '0.75em' }}>
                  <div className="text-dim" style={{ fontSize: '0.7em', marginBottom: '0.3em', fontFamily: 'Cinzel, serif' }}>
                    Traits
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.3em' }}>
                    {(() => {
                      try {
                        const traits = JSON.parse(hero.traits)
                        if (traits.length === 0) return <div className="text-dim text-sm" style={{ fontStyle: 'italic' }}>No unique traits.</div>
                        return traits.map((t, idx) => (
                          <div key={idx} style={{ 
                            padding: '0.3rem 0.5em', 
                            background: 'rgba(255,255,255,0.02)', 
                            borderLeft: `2px solid var(--gold)`,
                            borderRadius: '0 3px 3px 0'
                          }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.1em' }}>
                              <span style={{ fontSize: '0.75em', color: 'var(--text-hi)' }}>{t.name}</span>
                            </div>
                            <div className="text-dim" style={{ fontSize: '0.65em' }}>{t.desc}</div>
                          </div>
                        ))
                      } catch {
                        return <div className="text-dim text-sm" style={{ fontStyle: 'italic' }}>Trait data corrupted.</div>
                      }
                    })()}
                  </div>
                </div>
              )}

              {/* Skills Display */}
              {hero.skills && (
                <div style={{ marginTop: '0.75em' }}>
                  <div className="text-dim" style={{ fontSize: '0.7em', marginBottom: '0.3em', fontFamily: 'Cinzel, serif' }}>
                    Skills
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.3em' }}>
                    {(() => {
                      try {
                        const skills = JSON.parse(hero.skills)
                        if (skills.length === 0) return <div className="text-dim text-sm" style={{ fontStyle: 'italic' }}>No skills learned.</div>
                        return skills.map((s, idx) => (
                          <div key={idx} style={{ 
                            padding: '0.3rem 0.5em', 
                            background: 'rgba(255,255,255,0.02)', 
                            borderLeft: `2px solid ${SKILL_RARITY_COLORS[s.rarity] || '#888'}`,
                            borderRadius: '0 3px 3px 0'
                          }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.1em' }}>
                              <span style={{ fontSize: '0.75em', color: SKILL_RARITY_COLORS[s.rarity] || 'var(--text-hi)' }}>{s.name}</span>
                              <span className="text-dim" style={{ fontSize: '0.65em', textTransform: 'uppercase' }}>
                                {s.type} {s.cooldown ? `(${s.cooldown} CD)` : ''}
                                {/* 25 mirrors backend's DEFAULT_SKILL_MANA_COST fallback for
                                    active skills with no explicit effect.mana_cost set yet. */}
                                {s.type === 'active' && ` · ${s.effect?.mana_cost ?? 25} MP`}
                              </span>
                            </div>
                            {s.tier && (
                              <div style={{ fontSize: '0.65em', color: 'var(--gold)', marginBottom: '0.2em' }}>
                                {s.tier} Lv.{s.level} ({s.xp}/{s.max_xp} XP)
                              </div>
                            )}
                            <div className="text-dim" style={{ fontSize: '0.65em' }}>{s.desc}</div>
                          </div>
                        ))
                      } catch {
                        return <div className="text-dim text-sm" style={{ fontStyle: 'italic' }}>Skill data corrupted.</div>
                      }
                    })()}
                  </div>
                </div>
              )}
              
              <div className="story-block" style={{ marginTop: '1em', paddingTop: '0.75em', borderTop: '1px solid var(--border)' }}>
                <div className="text-dim" style={{ fontStyle: 'italic', lineHeight: 1.6 }}>
                  <span>{unlockedStory}</span>
                  {!storyFullyUnlocked && (
                    <span style={{
                      display: 'inline-block',
                      marginLeft: '0.35em',
                      opacity: 0.45,
                      fontStyle: 'normal',
                      background: 'linear-gradient(90deg, var(--text-dim), transparent)',
                      WebkitBackgroundClip: 'text',
                      backgroundClip: 'text',
                      color: 'transparent',
                    }}>
                      and the rest is still theirs to prove…
                    </span>
                  )}
                </div>
                {!storyFullyUnlocked && (
                  <div style={{
                    display: 'flex', alignItems: 'center', gap: '0.5em',
                    marginTop: '0.5em', fontSize: '0.8em', color: 'var(--text-dim)',
                  }}>
                    <span style={{ opacity: 0.7 }}>?</span>
                    <span>
                      {lockedSentences} more {lockedSentences === 1 ? 'passage' : 'passages'} of their legend
                      unlock{lockedSentences === 1 ? 's' : ''} with promotion (fully told at 6★)
                    </span>
                  </div>
                )}
                <div className="text-dim" style={{ marginTop: '0.4em', lineHeight: 1.5 }}>
                  {hero.personality}
                </div>
              </div>

              <RelationshipsDisplay hero={hero} />

              {actions && (
                <div style={{ marginTop: '1.2em', paddingTop: '0.8em', borderTop: '1px solid rgba(255,255,255,0.05)' }}>
                  {actions}
                </div>
              )}
            </div>
          )}
        </>
      )}

      {selected && (
        <div style={{
          position: 'absolute', top: -6, right: -6,
          color: '#111', fontSize: '0.85em', background: 'var(--gold)',
          borderRadius: '50%', width: 22, height: 22,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          boxShadow: '0 0 5px rgba(0,0,0,0.8)', zIndex: 20
        }}>✓</div>
      )}
    </div>
  )
}