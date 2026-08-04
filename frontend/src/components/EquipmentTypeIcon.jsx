import React from 'react'
import Sigil from './Sigil'

// House-style line SVGs under /icons/equip/ — NO emoji anywhere (user rule).
export const EQUIPMENT_ICONS = { Weapon: 'SWORD', Armor: 'HEAVY_ARMOR', Accessory: 'RING' }
export const WEAPON_TYPE_ICONS = { Sword: 'SWORD', Spear: 'SPEAR', Tome: 'TOME', Staff: 'TOME', Bow: 'BOW', Dagger: 'DAGGER' }
export const ARMOR_TYPE_ICONS = { 'Heavy Armor': 'HEAVY_ARMOR', 'Brigandine': 'BRIGANDINE', 'Light Armor': 'LIGHT_ARMOR', 'Robe': 'ROBE' }
export const ACCESSORY_TYPE_ICONS = { Ring: 'RING', Amulet: 'AMULET', Charm: 'CHARM' }

// Returns the equip-set SIGIL NAME for an item (was an emoji glyph).
export function equipmentIcon(item) {
  if (item.type === 'Weapon' && item.weapon_type) return WEAPON_TYPE_ICONS[item.weapon_type] || EQUIPMENT_ICONS.Weapon
  if (item.type === 'Armor' && item.armor_type) return ARMOR_TYPE_ICONS[item.armor_type] || EQUIPMENT_ICONS.Armor
  if (item.type === 'Accessory' && item.accessory_type) return ACCESSORY_TYPE_ICONS[item.accessory_type] || EQUIPMENT_ICONS.Accessory
  return EQUIPMENT_ICONS[item.type] || 'SWORD'
}

// Equipment renders as the house line sigil ONLY. The generated PNG batches
// (acc_*.png, /static/icons/weapons|armor/*) are retired from the UI — the
// painterly AI look clashed with the sigil language (Liam, 08-03).
export function EquipmentTypeIcon({ item, fontSize = '1.5rem', glow, color = 'var(--gold-hi)' }) {
  const px = fontSize === '1.5rem' ? 28 : fontSize === '3rem' ? 88 : 64
  return (
    <span style={{ display: 'inline-flex', color, filter: glow ? `drop-shadow(0 0 4px ${glow})` : undefined }}>
      <Sigil set="equip" name={equipmentIcon(item)} size={px} fallback={<span style={{ color: 'var(--gold-dim)' }}>◆</span>} />
    </span>
  )
}
