import React, { useState, useEffect } from 'react'
import { getInventory, listEquipment, getFacilities, listHeroes, useItem, useSummonTicket, scrapEquipment } from '../api/client'
import { EquipmentTypeIcon } from '../components/EquipmentTypeIcon'
import ItemIcon from '../components/ItemIcon'
import GameIcon from '../components/GameIcon'
import { confirmDialog, alertDialog } from '../components/DialogHost'
import { Diamond, Meter } from '../components/ilm/Ilm'

const CONSUMABLE_ICONS = { potion: 'potion', scroll: 'scroll', summon_ticket: 'summon_ticket' }
function consumableIconName(item) {
  if (item.item_type === 'summon_ticket') {
    const m = /^(\d)-Star/.exec(item.item_name || '')
    if (m) return `summon_ticket_${m[1]}star`
  }
  return CONSUMABLE_ICONS[item.item_type]
}
const CONSUMABLE_COLORS = { potion: 'var(--green)', scroll: '#a83dff', summon_ticket: 'var(--gold)', food: '#d3a15f' }

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
function rarityColor(rarity) { return RARITY_COLORS[rarity] || '#ffffff' }
const RARITY_SORT = ['F-', 'F', 'F+', 'E-', 'E', 'E+', 'D-', 'D', 'D+', 'C-', 'C', 'C+', 'B-', 'B', 'B+', 'A-', 'A', 'A+', 'S-', 'S', 'S+', 'SS', 'SSS', 'Z']

function formatPct(v) {
  const pct = v * 100
  return `+${pct < 10 ? pct.toFixed(1).replace(/\.0$/, '') : pct.toFixed(0)}%`
}

// Left-console filter ledger. value maps to the existing `filter` states.
const FILTERS = [
  ['All', 'ALL'], ['Weapon', 'WEAPONS'], ['Armor', 'ARMOR'],
  ['Accessory', 'ACCESSORIES'], ['Materials', 'MATERIALS'], ['Consumables', 'CONSUMABLES'],
]

export default function InventoryPage() {
  const [loading, setLoading] = useState(true)
  const [inventory, setInventory] = useState(null)
  const [equipment, setEquipment] = useState({ equipped: [], unequipped: [] })
  const [selectedItem, setSelectedItem] = useState(null)
  const [scrapping, setScrapping] = useState(false)
  const [heroes, setHeroes] = useState([])
  const [useTargetId, setUseTargetId] = useState('')
  const [using, setUsing] = useState(false)
  const [useMessage, setUseMessage] = useState(null)
  const [vaultCapacity, setVaultCapacity] = useState(20)
  const [filter, setFilter] = useState('All')
  const [rarityFilter, setRarityFilter] = useState(new Set())
  const [hideEquipped, setHideEquipped] = useState(false)
  const [bulkScrapping, setBulkScrapping] = useState(false)
  const [multiSelectMode, setMultiSelectMode] = useState(false)
  const [selectedItems, setSelectedItems] = useState(new Set())

  useEffect(() => { refresh() }, [])

  async function refresh() {
    setLoading(true)
    try {
      const [inv, eq, facs, heroList] = await Promise.all([
        getInventory(), listEquipment(), getFacilities().catch(() => null), listHeroes(true).catch(() => []),
      ])
      setInventory(inv || [])
      setEquipment(eq || { equipped: [], unequipped: [] })
      setHeroes(heroList || [])
      let capacity = 20
      if (facs && facs.built) {
        const vault = facs.built.find(f => f.type === 'Vault')
        if (vault) capacity = 20 + (vault.slots_unlocked * 16)
      }
      setVaultCapacity(capacity)
    } catch (e) { console.error(e) } finally { setLoading(false) }
  }

  const toggleRarity = (r) => setRarityFilter(prev => {
    const next = new Set(prev)
    if (next.has(r)) next.delete(r); else next.add(r)
    return next
  })

  // ---- combine raw items -------------------------------------------------
  const rawItems = []
  if (Array.isArray(inventory)) inventory.forEach(item => {
    if (['potion', 'scroll', 'summon_ticket', 'food'].includes(item.item_type)) rawItems.push({ ...item, typeId: item.item_type + '_' + item.item_name, itemType: 'consumable' })
    else rawItems.push({ ...item, typeId: 'mat_' + item.item_name, itemType: 'material' })
  })
  if (equipment.unequipped) equipment.unequipped.forEach(eq => rawItems.push({ ...eq, typeId: 'eq_' + eq.id, itemType: 'equipment', isEquipped: false }))
  if (equipment.equipped) equipment.equipped.forEach(eq => rawItems.push({ ...eq, typeId: 'eq_' + eq.id, itemType: 'equipment', isEquipped: true }))

  const totalItemCount = rawItems.length
  const counts = {
    All: totalItemCount,
    Weapon: rawItems.filter(i => i.itemType === 'equipment' && i.type === 'Weapon').length,
    Armor: rawItems.filter(i => i.itemType === 'equipment' && i.type === 'Armor').length,
    Accessory: rawItems.filter(i => i.itemType === 'equipment' && i.type === 'Accessory').length,
    Materials: rawItems.filter(i => i.itemType === 'material').length,
    Consumables: rawItems.filter(i => i.itemType === 'consumable').length,
  }

  let allItems = rawItems.filter(item => {
    let typeMatch = false
    if (filter === 'All') typeMatch = true
    else if (filter === 'Materials') typeMatch = item.itemType === 'material'
    else if (filter === 'Consumables') typeMatch = item.itemType === 'consumable'
    else if (filter === 'Equipment') typeMatch = item.itemType === 'equipment'
    else if (item.itemType === 'equipment' && filter === item.type) typeMatch = true
    if (!typeMatch) return false
    if (item.itemType === 'equipment' && rarityFilter.size > 0 && !rarityFilter.has(item.rarity)) return false
    if (hideEquipped && item.itemType === 'equipment' && item.isEquipped) return false
    return true
  })

  const kindRank = { equipment: 0, material: 1, consumable: 2 }
  allItems.sort((a, b) => {
    if (kindRank[a.itemType] !== kindRank[b.itemType]) return kindRank[a.itemType] - kindRank[b.itemType]
    if (a.itemType === 'equipment') {
      const typeCmp = (a.type || '').localeCompare(b.type || ''); if (typeCmp) return typeCmp
      const sub = (x) => x.weapon_type || x.armor_type || x.accessory_type || ''
      const subCmp = sub(a).localeCompare(sub(b)); if (subCmp) return subCmp
      const rc = RARITY_SORT.indexOf(b.rarity) - RARITY_SORT.indexOf(a.rarity); if (rc) return rc
      return (a.name || '').localeCompare(b.name || '')
    }
    return (a.item_name || '').localeCompare(b.item_name || '')
  })

  useEffect(() => {
    if (!loading && !selectedItem && allItems.length > 0) setSelectedItem(allItems[0])
  }, [loading, filter, allItems.length, selectedItem])

  const slots = [...allItems]
  while (slots.length < vaultCapacity) slots.push(null)

  const isEquipFilter = ['All', 'Equipment', 'Weapon', 'Armor', 'Accessory'].includes(filter)

  const handleBulkScrap = async () => {
    if (!(await confirmDialog(`Scrap ALL UNEQUIPPED ${filter === 'All' ? 'Equipment' : filter}? This cannot be undone.`))) return
    setBulkScrapping(true)
    try {
      const toScrap = allItems.filter(i => i.itemType === 'equipment' && !i.isEquipped)
      for (const item of toScrap) await scrapEquipment(item.id)
      refresh(); setSelectedItem(null)
    } catch (e) { console.error(e); alertDialog('Error: ' + e.message) } finally { setBulkScrapping(false) }
  }

  if (loading) return <div className="page text-dim">Loading Vault…</div>

  const selColor = selectedItem?.itemType === 'equipment' ? rarityColor(selectedItem.rarity) : 'var(--gold-hi)'

  return (
    <div className="page ilm-vault">
      <div className="ilm-vault-grid">
        {/* ============ LEFT CONSOLE ============ */}
        <div className="ilm-vault-left ent-1">
          <div className="ilm-eyebrow" style={{ marginBottom: 2 }}>ARMORY</div>
          <div className="ilm-title-stack" style={{ height: 96 }}>
            <div className="ghost">ARSENAL</div>
            <div className="solid">VAULT</div>
          </div>

          <div style={{ marginTop: 8 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 7 }}>
              <span style={{ fontFamily: "'Cinzel',serif", letterSpacing: '.24em', fontSize: '0.62rem', color: 'var(--muted)' }}>CAPACITY</span>
              <span style={{ fontFamily: "'Cinzel',serif", fontSize: '0.78rem', color: totalItemCount >= vaultCapacity ? 'var(--red-hi)' : 'var(--gold-hi)' }}>
                {totalItemCount}<span style={{ color: '#6a6a82' }}>/{vaultCapacity}</span>
              </span>
            </div>
            <Meter pct={(totalItemCount / vaultCapacity) * 100} height={6} />
          </div>

          <div style={{ marginTop: 20, display: 'flex', flexDirection: 'column', gap: 2 }}>
            {FILTERS.map(([val, label]) => {
              const active = filter === val
              return (
                <div key={val} className={`ilm-ledger-row ${active ? 'active' : ''}`}
                  onClick={() => { setFilter(val); setSelectedItem(null); setSelectedItems(new Set()) }}>
                  <span>{label}</span>
                  <span style={{ color: active ? '#0a0710' : 'var(--text-dim)' }}>{counts[val] ?? 0}</span>
                </div>
              )
            })}
          </div>
        </div>

        {/* ============ CENTER GRID ============ */}
        <div className="ilm-vault-center ent-2">
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
            <span style={{ fontFamily: "'Cinzel',serif", letterSpacing: '.3em', fontSize: '0.68rem', color: 'var(--gold)' }}>
              {(FILTERS.find(f => f[0] === filter)?.[1]) || 'ITEMS'}
            </span>
            <span style={{ height: 1, flex: 1, background: 'rgba(184,151,98,.2)' }} />
            {isEquipFilter && (
              <>
                <button className="btn" style={{ padding: '5px 12px', fontSize: '0.6rem' }}
                  onClick={() => { setMultiSelectMode(m => !m); setSelectedItems(new Set()); setSelectedItem(null) }}>
                  {multiSelectMode ? 'CANCEL' : 'MULTI-SELECT'}
                </button>
                {multiSelectMode && selectedItems.size > 0 ? (
                  <button className="btn btn-danger" style={{ padding: '5px 12px', fontSize: '0.6rem' }} disabled={bulkScrapping}
                    onClick={async () => {
                      if (!(await confirmDialog(`Scrap ${selectedItems.size} selected items?`))) return
                      setBulkScrapping(true)
                      try {
                        const toScrap = allItems.filter(i => selectedItems.has(i.typeId) && i.itemType === 'equipment' && !i.isEquipped)
                        for (const item of toScrap) await scrapEquipment(item.id)
                        refresh(); setSelectedItems(new Set())
                      } catch (e) { alertDialog('Error: ' + e.message) } finally { setBulkScrapping(false) }
                    }}>
                    SCRAP {selectedItems.size}
                  </button>
                ) : (
                  <button className="btn btn-danger" style={{ padding: '5px 12px', fontSize: '0.6rem' }} onClick={handleBulkScrap} disabled={bulkScrapping}>
                    {bulkScrapping ? 'SCRAPPING…' : 'BULK SCRAP'}
                  </button>
                )}
              </>
            )}
          </div>

          <div className="ilm-vault-gridscroll ilm-page-weave">
            {allItems.length === 0 && (
              <div className="empty-state">
                <div className="empty-state-title">{filter === 'All' && rarityFilter.size === 0 ? 'The Vault Is Empty' : 'Nothing Matches These Filters'}</div>
                <div className="empty-state-hint">
                  {filter === 'All' && rarityFilter.size === 0
                    ? 'Climb the Tower to earn loot, or pull equipment from the Gate. Everything you collect is stored here.'
                    : 'Clear the rarity or type filters to see the rest of your collection.'}
                </div>
              </div>
            )}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(96px, 1fr))', gap: 12, alignContent: 'start' }}>
              {slots.map((item, index) => {
                const isSelected = item && (multiSelectMode ? selectedItems.has(item.typeId) : (selectedItem && item.typeId === selectedItem.typeId))
                let borderColor = 'var(--border)'
                let content = null
                if (item) {
                  if (item.itemType === 'material') { borderColor = 'var(--border-hi)'; content = <ItemIcon name={item.item_name} kind="material" size={48} /> }
                  else if (item.itemType === 'consumable') { borderColor = CONSUMABLE_COLORS[item.item_type] || 'var(--green)'; content = item.item_type === 'summon_ticket' ? <GameIcon name={consumableIconName(item)} size={48} /> : <ItemIcon name={item.item_name} kind={item.item_type} size={48} /> }
                  else if (item.itemType === 'equipment') { borderColor = rarityColor(item.rarity); content = <EquipmentTypeIcon item={item} fontSize="2.4rem" /> }
                }
                return (
                  <div key={item ? item.typeId : `empty-${index}`}
                    className={isSelected ? 'vault-item-selected' : ''}
                    onClick={() => {
                      if (!item) return
                      if (multiSelectMode) setSelectedItems(prev => { const n = new Set(prev); n.has(item.typeId) ? n.delete(item.typeId) : n.add(item.typeId); return n })
                      else setSelectedItem(item)
                    }}
                    style={{ aspectRatio: '1/1', background: item ? 'rgba(255,255,255,0.03)' : 'rgba(12,7,24,.3)', border: `1px solid ${borderColor}`, display: 'flex', alignItems: 'center', justifyContent: 'center', position: 'relative', cursor: item ? 'pointer' : 'default', boxShadow: item && item.itemType === 'equipment' ? `inset 0 0 12px ${borderColor}22` : 'none', opacity: item ? 1 : 0.3, transition: 'transform 0.1s' }}
                    onMouseEnter={e => { if (item) e.currentTarget.style.transform = 'scale(1.05)' }}
                    onMouseLeave={e => { if (item) e.currentTarget.style.transform = 'scale(1)' }}>
                    {content}
                    {item && (item.itemType === 'material' || item.itemType === 'consumable') && (
                      <div style={{ position: 'absolute', bottom: -2, right: -2, background: 'var(--bg)', border: '1px solid var(--border-hi)', fontSize: '0.72rem', padding: '0 5px', fontFamily: 'monospace', fontWeight: 'bold' }}>{item.quantity}</div>
                    )}
                    {item && item.isEquipped && (
                      <div style={{ position: 'absolute', top: 2, left: 3, fontFamily: "'Cinzel',serif", fontSize: '0.6rem', color: 'var(--gold-hi)' }}>E</div>
                    )}
                  </div>
                )
              })}
            </div>
          </div>

          {/* rarity legend / filter */}
          {isEquipFilter && (
            <div style={{ display: 'flex', gap: 8, marginTop: 12, alignItems: 'center', flexWrap: 'wrap' }}>
              <span className="ilm-micro">RARITY</span>
              {['D', 'C', 'B', 'A', 'S', 'SS', 'SSS', 'Z'].map(r => (
                <span key={r} onClick={() => { toggleRarity(r); setSelectedItem(null) }} title={`Filter ${r}`}
                  style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 4, opacity: rarityFilter.size && !rarityFilter.has(r) ? 0.4 : 1 }}>
                  <span style={{ width: 8, height: 8, background: rarityColor(r), boxShadow: r === 'Z' || r === 'SSS' ? `0 0 6px ${rarityColor(r)}` : 'none' }} />
                  <span style={{ fontSize: '0.75rem', color: rarityColor(r) }}>{r}</span>
                </span>
              ))}
              {rarityFilter.size > 0 && <span onClick={() => setRarityFilter(new Set())} className="ilm-micro" style={{ cursor: 'pointer', color: 'var(--lavender)' }}>CLEAR</span>}
            </div>
          )}
        </div>

        {/* ============ RIGHT: DETAIL ============ */}
        <div className="ilm-vault-detail ent-3" style={{ position: 'relative', border: `1px solid ${selectedItem ? selColor + '66' : 'var(--border)'}`, background: 'linear-gradient(160deg,rgba(8,30,34,.35),rgba(12,7,24,.7))', clipPath: 'polygon(0 0,100% 0,100% 100%,14px 100%)', padding: '20px 22px', display: 'flex', flexDirection: 'column' }}>
          <span className="ilm-corner" style={{ borderColor: selColor }} />
          {!selectedItem ? (
            <div className="text-dim" style={{ margin: 'auto', textAlign: 'center', fontStyle: 'italic' }}>Select an item to view details.</div>
          ) : selectedItem.itemType === 'material' ? (
            <>
              <div style={{ textAlign: 'center', marginBottom: '1rem' }}><ItemIcon name={selectedItem.item_name} kind="material" size={64} /></div>
              <div style={{ fontFamily: "'Cinzel',serif", fontWeight: 900, fontSize: '1.5rem', textAlign: 'center', color: 'var(--text-hi)', textTransform: 'capitalize' }}>{selectedItem.item_name.replace(/_/g, ' ')}</div>
              <div className="text-dim" style={{ fontStyle: 'italic', fontSize: '0.95rem', textAlign: 'center', margin: '0.8rem 0 1.4rem', lineHeight: 1.5 }}>A fundamental material of the Tower — spent on crafting and base upgrades.</div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', border: '1px solid var(--border)', padding: '0.9rem 1rem' }}>
                <span className="ilm-micro">AMOUNT OWNED</span>
                <span className="text-gold" style={{ fontSize: '1.6rem', fontFamily: "'Cinzel',serif", fontWeight: 700 }}>{selectedItem.quantity}</span>
              </div>
            </>
          ) : selectedItem.item_type === 'summon_ticket' ? (
            <>
              <div style={{ textAlign: 'center', marginBottom: '1rem' }}><GameIcon name={consumableIconName(selectedItem)} size={80} /></div>
              <div style={{ fontFamily: "'Cinzel',serif", fontWeight: 900, fontSize: '1.4rem', textAlign: 'center', color: 'var(--gold-hi)' }}>{selectedItem.item_name}</div>
              <div className="text-dim" style={{ textAlign: 'center', fontStyle: 'italic', margin: '0.8rem 0 1.4rem', lineHeight: 1.5 }}>{selectedItem.description}</div>
              <div style={{ display: 'flex', justifyContent: 'space-between', border: '1px solid var(--border)', padding: '0.8rem 1rem', marginBottom: '1.4rem' }}>
                <span className="ilm-micro">OWNED</span><span className="text-gold" style={{ fontFamily: "'Cinzel',serif", fontSize: '1.4rem', fontWeight: 700 }}>{selectedItem.quantity}</span>
              </div>
              <button className="btn btn-gold" style={{ width: '100%', padding: '0.8rem', marginTop: 'auto' }} disabled={using}
                onClick={async () => { setUsing(true); setUseMessage(null); try { const res = await useSummonTicket(selectedItem.item_name); const hero = res?.pulled?.[0]; setUseMessage(hero ? `Summoned ${hero.name} (${hero.birth_star}★)!` : 'Used!'); await refresh(); setSelectedItem(null) } catch (e) { setUseMessage(e.message) } finally { setUsing(false) } }}>
                {using ? 'Summoning…' : 'Use Ticket'}
              </button>
              {useMessage && <div className="text-dim text-center" style={{ marginTop: '0.5rem', fontSize: '0.9rem' }}>{useMessage}</div>}
            </>
          ) : selectedItem.itemType === 'consumable' ? (
            <>
              <div style={{ textAlign: 'center', marginBottom: '1rem' }}><ItemIcon name={selectedItem.item_name} kind={selectedItem.item_type} size={80} /></div>
              <div style={{ fontFamily: "'Cinzel',serif", fontWeight: 900, fontSize: '1.4rem', textAlign: 'center', color: 'var(--text-hi)' }}>{selectedItem.item_name}</div>
              <div className="text-dim" style={{ textAlign: 'center', fontStyle: 'italic', margin: '0.8rem 0 1.4rem', lineHeight: 1.5 }}>{selectedItem.description}</div>
              <div style={{ display: 'flex', justifyContent: 'space-between', border: '1px solid var(--border)', padding: '0.8rem 1rem', marginBottom: '1.4rem' }}>
                <span className="ilm-micro">OWNED</span><span className="text-gold" style={{ fontFamily: "'Cinzel',serif", fontSize: '1.4rem', fontWeight: 700 }}>{selectedItem.quantity}</span>
              </div>
              <div style={{ marginTop: 'auto' }}>
                <select className="input" value={useTargetId} onChange={e => setUseTargetId(e.target.value)} style={{ width: '100%', marginBottom: '0.8rem' }}>
                  <option value="">Select a hero…</option>
                  {heroes.map(h => <option key={h.id} value={h.id}>{h.name} (Lv.{h.level})</option>)}
                </select>
                <button className="btn btn-gold" style={{ width: '100%', padding: '0.8rem' }} disabled={!useTargetId || using}
                  onClick={async () => { setUsing(true); setUseMessage(null); try { await useItem(selectedItem.item_name, Number(useTargetId)); setUseMessage('Used!'); await refresh(); setSelectedItem(null) } catch (e) { setUseMessage(e.message) } finally { setUsing(false) } }}>
                  {using ? 'Using…' : 'Use'}
                </button>
                {useMessage && <div className="text-dim text-center" style={{ marginTop: '0.5rem', fontSize: '0.9rem' }}>{useMessage}</div>}
              </div>
            </>
          ) : (
            /* equipment */
            <>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <span style={{ fontFamily: "'Cinzel',serif", letterSpacing: '.2em', fontSize: '0.62rem', color: selColor, border: `1px solid ${selColor}88`, padding: '2px 8px', boxShadow: `0 0 10px ${selColor}44` }}>{selectedItem.rarity}</span>
                <span className="ilm-micro">·</span>
                <span className="ilm-micro">{selectedItem.weapon_type || selectedItem.armor_type || selectedItem.accessory_type || selectedItem.type}</span>
              </div>
              <div style={{ fontFamily: "'Cinzel',serif", fontWeight: 900, fontSize: '1.7rem', color: 'var(--text-hi)', marginTop: 8, textShadow: `0 0 22px ${selColor}66` }}>{selectedItem.name}</div>
              <div style={{ display: 'flex', justifyContent: 'center', margin: '12px 0' }}><EquipmentTypeIcon item={selectedItem} fontSize="3.4rem" /></div>

              <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 4, overflowY: 'auto' }}>
                {[
                  ['STR', selectedItem.base_str, v => `+${v}`], ['INT', selectedItem.base_int, v => `+${v}`],
                  ['END', selectedItem.base_end, v => `+${v}`], ['MAX HP', selectedItem.base_hlt, v => `+${v}`],
                  ['AGI', selectedItem.base_agi, v => `+${v}`], ['WIL', selectedItem.base_wil, v => `+${v}`],
                  ['LCK', selectedItem.base_luck, v => `+${v}`],
                  ['STR %', selectedItem.str_pct, formatPct], ['INT %', selectedItem.int_pct, formatPct],
                  ['HP %', selectedItem.hlt_pct, formatPct], ['AGI %', selectedItem.agi_pct, formatPct],
                  ['CRIT', selectedItem.crit_chance, formatPct], ['DODGE', selectedItem.dodge_chance, formatPct],
                  ['ARMOR PEN', selectedItem.armor_pen, formatPct], ['DMG RED', selectedItem.dmg_reduction_pct, formatPct],
                ].filter(([, v]) => v > 0).map(([label, val, fmt]) => (
                  <div key={label} style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: `1px solid ${selColor}22` }}>
                    <span className="ilm-micro">{label}</span>
                    <span style={{ fontFamily: "'Cinzel',serif", fontWeight: 700, fontSize: '1.1rem', color: 'var(--text-hi)' }}>{fmt(val)}</span>
                  </div>
                ))}
              </div>

              <div style={{ marginTop: 14, paddingTop: 12, borderTop: '1px solid var(--border)' }}>
                {selectedItem.isEquipped ? (
                  <div className="text-center" style={{ color: 'var(--green-hi)', fontSize: '0.9rem', fontStyle: 'italic' }}>Equipped to Hero #{selectedItem.is_equipped_to} · equip from Heroes</div>
                ) : (
                  <>
                    <div className="text-dim text-center" style={{ fontSize: '0.82rem', fontStyle: 'italic', marginBottom: 10 }}>Equip from the Heroes menu.</div>
                    <button className="btn btn-danger" style={{ width: '100%', padding: '0.7rem' }} disabled={scrapping}
                      onClick={async () => { if (!(await confirmDialog(`Scrap ${selectedItem.name}? This destroys it for crafting materials.`))) return; setScrapping(true); try { await scrapEquipment(selectedItem.id); setSelectedItem(null); await refresh() } catch (e) { alertDialog(e.message) } finally { setScrapping(false) } }}>
                      {scrapping ? 'Scrapping…' : 'Salvage for Materials'}
                    </button>
                  </>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
