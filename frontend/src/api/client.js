import { emitToast } from '../toastBus'

const BASE = ''

// Every reward-granting endpoint in this codebase uses a slightly different
// response shape (flat gold_gained/gems_gained on tower floors, {type,
// reward} on daily dungeons, {effects:{...}} on event/explore resolution,
// {equipment:{...}} on forge crafting). Rather than wire a toast call into
// every individual call site (and inevitably miss one — see the gems display
// bug), every response funnels through here once, so nothing can silently
// fail to surface again.
function extractRewards(data) {
  if (!data || typeof data !== 'object') return null
  const gold = (data.gold_gained || 0) + (data.effects?.gold || 0) + (data.type === 'gold' ? (data.reward || 0) : 0)
  const gems = (data.gems_gained || 0) + (data.effects?.gems || 0)
  const ingredients = (data.ingredients_gained || 0) + (data.type === 'ingredients' ? (data.reward || 0) : 0)
  const materials = { ...(data.materials_gained || {}) }
  if (data.type === 'materials' && data.reward && typeof data.reward === 'object') {
    for (const [k, v] of Object.entries(data.reward)) materials[k] = (materials[k] || 0) + v
  }
  const equipment = data.equipment_drop || data.equipment || null
  const relic = data.relic_drop || null

  const lines = []
  if (gold > 0) lines.push({ label: 'Gold', value: `+${gold.toLocaleString()}`, color: 'var(--gold)' })
  if (gems > 0) lines.push({ label: 'Gems', value: `+${gems.toLocaleString()}`, color: '#00ffff' })
  if (ingredients > 0) lines.push({ label: 'Ingredients', value: `+${ingredients.toLocaleString()}`, color: '#9fd68a' })
  for (const [name, qty] of Object.entries(materials)) {
    if (qty > 0) lines.push({ label: name, value: `+${qty}`, color: 'var(--text-hi)' })
  }
  if (equipment?.name) lines.push({ label: 'Equipment', value: equipment.name, color: 'var(--green)' })
  if (relic?.name) lines.push({ label: relic.relic_type === 'rune' ? 'Rune' : 'Seal', value: relic.name, color: '#c060ff' })

  return lines.length ? lines : null
}

// These already reveal their own rewards through dedicated, properly-paced
// UI (the post-combat screen, event/explore resolution panels) — the
// generic toast below would otherwise fire the instant the response lands,
// which for floor/enter means "before the player has even watched the
// fight play out."
const SKIP_AUTO_TOAST_PATHS = ['/tower/floor/enter', '/tower/floor/event/resolve', '/tower/floor/explore/resolve']

async function request(path, options = {}) {
  const isGet = !options.method || options.method === 'GET'
  const url = isGet ? BASE + path + (path.includes('?') ? '&' : '?') + 't=' + Date.now() : BASE + path
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    cache: 'no-store',
    ...options,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    let msg = err.detail || err.error || 'Request failed'
    if (typeof msg === 'object') msg = JSON.stringify(msg)
    throw new Error(msg)
  }
  const data = await res.json()
  const skipToast = SKIP_AUTO_TOAST_PATHS.some(p => path.startsWith(p))
  const lines = skipToast ? null : extractRewards(data)
  if (lines) emitToast({ title: 'Rewards', lines, borderColor: 'var(--gold)' })
  if (Array.isArray(data?.ego_rebellions) && data.ego_rebellions.length) {
    for (const reb of data.ego_rebellions) {
      emitToast({
        title: 'Ego Rebellion',
        lines: [{ label: reb.hero_name, value: reb.message, color: '#ff8888' }],
        borderColor: '#ff4444',
      })
    }
  }
  return data
}

export const getChatLogs = (limit = 10) => request(`/chat/?limit=${limit}`)
export const getHearth = () => request('/chat/hearth')
export const sendHearthWord = (tone) => request('/chat/word', { method: 'POST', body: JSON.stringify({ tone }) })
export const getAthenaeumState = () => request('/base/facilities/athenaeum/state')
export const studyAthenaeumNode = (nodeId) => request('/base/facilities/athenaeum/study', { method: 'POST', body: JSON.stringify({ node_id: nodeId }) })
export const egoAutoTeam = (teamId, egoHeroId) => request('/heroes/team/ego_auto', { method: 'POST', body: JSON.stringify({ team_id: teamId, ego_hero_id: egoHeroId }) })
export const getEgoRecommendation = (heroId) => request(`/heroes/${heroId}/ego_recommendation`)

// Base
export const getBase = () => request('/base/')
export const getSupportBoons = () => request('/base/support')
export const setMasterName = (name) => request('/base/master-name', { method: 'POST', body: JSON.stringify({ name }) })
export const completeTutorial = () => request('/base/tutorial/complete', { method: 'POST' })
export const chooseFairy = (fairy_gender) => request('/base/fairy', { method: 'POST', body: JSON.stringify({ fairy_gender }) })
export const getApiKeyStatus = () => request('/settings/apikey')
export const setApiKey = (api_key) => request('/settings/apikey', { method: 'POST', body: JSON.stringify({ api_key }) })
export const getGenerationEnabled = () => request('/settings/generation')
export const setGenerationEnabled = (enabled) => request('/settings/generation', { method: 'POST', body: JSON.stringify({ enabled }) })
// One-click generation setup — everything INSTALL_GENERATION.bat does, run
// from Settings so the player never leaves the game for a separate script.
export const getGenerationInstallStatus = () => request('/settings/generation/install-status')
export const startGenerationInstall = () => request('/settings/generation/install', { method: 'POST' })
export const upgradeBase = () => request('/base/upgrade', { method: 'POST' })
export const restHeroes = () => request('/base/rest', { method: 'POST' })
export const runDailyDungeon = (type, tier = 1) => request(`/base/daily_dungeon/${type}?tier=${tier}`, { method: 'POST' })
export const getDailyDungeonStatus = () => request('/base/daily_dungeon/status')
export const getHeraldFeed = () => request('/herald/')
export const getExpeditions = () => request('/base/expeditions')
export const dispatchExpedition = (lane, heroIds, qualityMult = 1.0) => request('/base/expeditions/dispatch', { method: 'POST', body: JSON.stringify({ lane, hero_ids: heroIds, quality_mult: qualityMult }) })
export const collectExpedition = (lane) => request('/base/expeditions/collect', { method: 'POST', body: JSON.stringify({ lane }) })
export const recallExpedition = (lane) => request('/base/expeditions/recall', { method: 'POST', body: JSON.stringify({ lane }) })
export const getTavern = () => request('/base/tavern')
export const buyTavernRound = (heroId = null) => request('/base/tavern/round', { method: 'POST', body: JSON.stringify({ hero_id: heroId }) })
export const tavernDice = (wager, mult, heroId = null) => request('/base/tavern/dice', { method: 'POST', body: JSON.stringify({ wager, mult, hero_id: heroId }) })
export const huntBeast = (mult) => request('/base/bestiary/hunt', { method: 'POST', body: JSON.stringify({ mult }) })
export const shrineRite = (mult) => request('/base/shrine/rite', { method: 'POST', body: JSON.stringify({ mult }) })
export const getSparkWishlist = () => request('/gacha/wishlist')
export const setSparkWishlist = (classes) => request('/gacha/wishlist', { method: 'POST', body: JSON.stringify({ classes }) })
export const payLocalFee = (amount, reason = '') => request('/base/pay_fee', { method: 'POST', body: JSON.stringify({ amount, reason }) })
export const getBaseFloors = () => request('/base/floors')
export const assignBaseFloor = (heroId, floor) => request('/base/floors/assign', { method: 'POST', body: JSON.stringify({ hero_id: heroId, floor }) })

export const getFacilities = () => request('/base/facilities')
export const buildFacility = (type) => request('/base/facilities/build', { method: 'POST', body: JSON.stringify({ facility_type: type }) })
export const assignFacility = (facId, heroId) => request('/base/facilities/assign', { method: 'POST', body: JSON.stringify({ facility_id: facId, hero_id: heroId }) })
export const removeFacility = (heroId) => request('/base/facilities/remove', { method: 'POST', body: JSON.stringify({ hero_id: heroId }) })
export const upgradeFacility = (facilityId) => request('/base/facilities/upgrade', { method: 'POST', body: JSON.stringify({ facility_id: facilityId }) })
export const configTraining = (facilityId, heroId, role, targetSkillId, targetHeroId) => request('/base/facilities/training-config', { method: 'POST', body: JSON.stringify({ facility_id: facilityId, hero_id: heroId, role, target_skill_id: targetSkillId, target_hero_id: targetHeroId }) })
export const getMageTowerUpgrades = () => request('/base/facilities/mage-tower/upgrades')
export const buyResearchUpgrade = (upgradeId) => request('/base/facilities/mage-tower/buy', { method: 'POST', body: JSON.stringify({ upgrade_id: upgradeId }) })

export const getBaseUpgrades = () => request('/base/upgrades')
export const buyBaseUpgrade = (upgradeId) => request('/base/upgrades/purchase', { method: 'POST', body: JSON.stringify({ upgrade_id: upgradeId }) })
export const revealHeroTalent = (heroId, qualityMult = 1.0) => request('/base/talent-observatory/reveal', { method: 'POST', body: JSON.stringify({ hero_id: heroId, quality_mult: qualityMult }) })

export const grantResources = (gold = 0, gems = 0, ingredients = 0, aether = 0) => request('/base/dev/grant', { method: 'POST', body: JSON.stringify({ gold, gems, ingredients, aether }) })

// Training Grounds sparring (peer + mentorship, auto-detected by level gap)
export const sparHeroes = (heroAId, heroBId) => request('/base/facilities/spar', { method: 'POST', body: JSON.stringify({ hero_a_id: heroAId, hero_b_id: heroBId }) })

// Hero relationships (mentors, students, rivals/comrades) for the card
export const getHeroRelationships = (heroId) => request(`/heroes/${heroId}/relationships`)
// Deeds — permanent accomplishment records (persist after death)
export const getHeroDeeds = (heroId) => request(`/heroes/${heroId}/deeds`)
// The Commander's Table — strategy-duel minigame reward (once/day/hero)
export const managerSpar = (heroId, mult) => request(`/heroes/${heroId}/manager-spar`, { method: 'POST', body: JSON.stringify({ mult }) })

// Training Grounds solo drills (regimens)
export const getTrainingStatus = () => request('/base/facilities/training')
export const setTrainingRegimen = (heroId, regimen, focus, intensity) => request('/base/facilities/training/regimen', { method: 'POST', body: JSON.stringify({ hero_id: heroId, regimen, focus, intensity }) })
export const runTrainingTournament = () => request('/base/facilities/training/tournament', { method: 'POST' })

// Forge Recipe Book (blueprint recipes discovered in the Tower)
export const getForgeRecipes = () => request('/forge/recipes')
export const craftPremadeRecipe = (crafterId, recipeId, qualityMult = 1.0) => request('/forge/craft/premade', { method: 'POST', body: JSON.stringify({ crafter_id: crafterId, recipe_id: recipeId, quality_mult: qualityMult }) })

// Team banner
export const getBanner = () => request('/base/banner')
export const saveBanner = (templateTier, emblem, paint, extra = {}) => request('/base/banner', { method: 'POST', body: JSON.stringify({ template_tier: templateTier, emblem, paint, ...extra }) })

// Dining Hall cooking + Alchemist aether refining
export const getDiningCatalog = () => request('/base/dining/catalog')
export const cookFood = (recipeId, quantity = 1, qualityMult = 1.0) => request('/base/dining/cook', { method: 'POST', body: JSON.stringify({ recipe_id: recipeId, quantity, quality_mult: qualityMult }) })
export const refineAether = (batches = 1, qualityMult = 1.0) => request('/base/alchemist/refine-aether', { method: 'POST', body: JSON.stringify({ batches, quality_mult: qualityMult }) })

// Endgame facilities
export const getBestiary = () => request('/base/bestiary')
export const releaseBeast = (id) => request(`/base/bestiary/release/${id}`, { method: 'POST' })
export const getReliquary = () => request('/base/reliquary')
export const mountTrophy = (trophyId, mounted) => request('/base/reliquary/mount', { method: 'POST', body: JSON.stringify({ trophy_id: trophyId, mounted }) })
export const getChronosphere = () => request('/base/chronosphere')
export const activateChronosphere = () => request('/base/chronosphere/activate', { method: 'POST' })
export const getTranscendence = () => request('/base/transcendence')
export const infuseTranscendence = () => request('/base/transcendence/infuse', { method: 'POST' })
export const clearDevInventory = () => request('/base/dev/clear-inventory', { method: 'POST' })
export const setDevLevel = (heroId, level) => request('/base/dev/set-level', { method: 'POST', body: JSON.stringify({ hero_id: heroId, level }) })
export const grantInventoryItem = (itemName, itemType, quantity = 1) => request(`/base/inventory/add?item_name=${encodeURIComponent(itemName)}&item_type=${encodeURIComponent(itemType)}&quantity=${quantity}`, { method: 'POST' })

export const listUpgrades = () => request('/base/upgrades')
export const purchaseUpgrade = (facilityId) => request('/base/upgrades/purchase', { method: 'POST', body: JSON.stringify({ upgrade_id: facilityId }) })
export const getInventory = () => request('/base/inventory')
export const useItem = (itemName, heroId, targetSkillId = null) => request('/base/inventory/use', { method: 'POST', body: JSON.stringify({ item_name: itemName, hero_id: heroId, target_skill_id: targetSkillId }) })
export const useSummonTicket = (itemName) => request('/gacha/use-ticket', { method: 'POST', body: JSON.stringify({ item_name: itemName }) })

// Achievements
export const getAchievements = () => request('/achievements/')
export const claimAchievement = (achievementId) => request('/achievements/claim', { method: 'POST', body: JSON.stringify({ achievement_id: achievementId }) })
export const getRites = () => request('/achievements/rites')
export const claimRite = (questId) => request('/achievements/rites/claim', { method: 'POST', body: JSON.stringify({ quest_id: questId }) })

// Heroes
export const listHeroes = (aliveOnly = false) => request(`/heroes/?alive_only=${aliveOnly}`)
export const getHero = (id) => request(`/heroes/${id}`)
export const setTeam = (teamId, heroIds) => request('/heroes/team/set', { method: 'POST', body: JSON.stringify({ team_id: teamId, hero_ids: heroIds }) })
export const removeHeroFromTeam = (heroId) => request(`/heroes/${heroId}/remove-from-team`, { method: 'POST' })
export const reorderTeam = (teamId, heroIds) => request('/heroes/team/reorder', { method: 'POST', body: JSON.stringify({ team_id: teamId, hero_ids: heroIds }) })
export const getTeam = (teamId = 1) => request(`/heroes/team/${teamId}`)
export const getAllTeams = () => request('/heroes/teams/all')
export const assignTeamLeader = (heroId) => request('/heroes/team/assign-leader', { method: 'POST', body: JSON.stringify({ hero_id: heroId }) })
export const getLeaderRecommendation = (teamId) => request(`/heroes/team/${teamId}/leader-recommendation`)
export const dismissHero = (id) => request(`/heroes/${id}`, { method: 'DELETE' })
export const dismissHeroesBulk = (heroIds) => request('/heroes/dismiss-bulk', { method: 'POST', body: JSON.stringify({ hero_ids: heroIds }) })
export const synthesizeHero = (targetId, sacrificeIds) => request('/heroes/synthesize', { method: 'POST', body: JSON.stringify({ target_id: targetId, sacrifice_ids: Array.isArray(sacrificeIds) ? sacrificeIds : [sacrificeIds] }) })
export const ascendHero = (heroId) => request(`/heroes/${heroId}/ascend`, { method: 'POST' })
export const getAscensionInfo = (heroId) => request(`/heroes/${heroId}/ascension-info`)
export const promoteHero = (heroId) => request(`/heroes/${heroId}/promote`, { method: 'POST' })
export const getEvolutionInfo = (heroId) => request(`/heroes/${heroId}/evolution-info`)
export const regeneratePortraits = () => request('/heroes/regenerate-portraits', { method: 'POST' })
export const toggleFavorite = (heroId) => request(`/heroes/${heroId}/favorite`, { method: 'POST' })
export const getGiftCatalog = () => request('/heroes/gifts/catalog')
export const giveGift = (heroId, giftId) => request(`/heroes/${heroId}/gift`, { method: 'POST', body: JSON.stringify({ gift_id: giftId }) })
export const getShip = () => request('/base/ship')
export const buildShip = () => request('/base/ship/build', { method: 'POST' })
export const refitShip = (stat, delta) => request('/base/ship/refit', { method: 'POST', body: JSON.stringify({ stat, delta }) })
export const buyRefitPoint = () => request('/base/ship/refit/buy_point', { method: 'POST' })
export const getFreePullStatus = () => request('/gacha/free-status')
export const freePull = () => request('/gacha/free-pull', { method: 'POST' })
export const renameShip = (name) => request('/base/ship/rename', { method: 'POST', body: JSON.stringify({ name }) })
export const craftMaterialEquipment = (material, targetClass) => request('/base/craft-equipment', { method: 'POST', body: JSON.stringify({ material, target_class: targetClass }) })
export const craftBandages = (crafterId, quantity = 1) => request('/base/infirmary/craft-bandages', { method: 'POST', body: JSON.stringify({ crafter_id: crafterId, quantity }) })
export const getMarketCatalog = () => request('/base/market/catalog')
export const purchaseMarketItem = (itemId) => request('/base/market/purchase', { method: 'POST', body: JSON.stringify({ item_id: itemId }) })
export const evolveHero = (heroId, targetClass) => request(`/heroes/${heroId}/evolve`, { method: 'POST', body: JSON.stringify({ target_class: targetClass }) })
export const getClassEvolutions = () => request('/heroes/classes/evolutions')
export const getLegacies = () => request('/heroes/legacies')
export const regenerateProfile = (heroId) => request(`/heroes/${heroId}/regenerate-profile`, { method: 'POST' })
export const getHeroAptitudes = (heroId) => request(`/heroes/${heroId}/aptitudes`)
export const getBonds = () => request('/heroes/bonds')

// Equipment
export const listEquipment = () => request('/equipment/')
export const craftEquipment = (crafterId) => request('/equipment/craft', { method: 'POST', body: JSON.stringify({ crafter_id: crafterId }) })
export const equipItem = (equipmentId, heroId) => request('/equipment/equip', { method: 'POST', body: JSON.stringify({ equipment_id: equipmentId, hero_id: heroId }) })
export const unequipItem = (equipmentId) => request('/equipment/unequip', { method: 'POST', body: JSON.stringify({ equipment_id: equipmentId }) })
export const scrapEquipment = (equipmentId) => request('/equipment/scrap', { method: 'POST', body: JSON.stringify({ equipment_id: equipmentId }) })
export const autoEquipHero = (heroId) => request('/equipment/auto-equip', { method: 'POST', body: JSON.stringify({ hero_id: heroId }) })
export const unequipAllHero = (heroId) => request('/equipment/unequip-all', { method: 'POST', body: JSON.stringify({ hero_id: heroId }) })

export const equipConsumable = (heroId, itemName) => request('/base/heroes/equip-consumable', { method: 'POST', body: JSON.stringify({ hero_id: heroId, item_name: itemName }) })

// Gacha
export const pullHeroes = (count = 1, usePortrait = false, currency = 'gem', banner = 'standard') => request('/gacha/pull', { method: 'POST', body: JSON.stringify({ count, use_portrait: usePortrait, currency, banner }) })
export const pullEquipment = (count = 1, currency = 'gold', banner = 'standard') => request('/gacha/equipment-pull', { method: 'POST', body: JSON.stringify({ count, currency, banner }) })
export const getSeason = () => request('/gacha/season')
export const getOdds = (currency = 'gem') => request(`/gacha/odds?currency=${currency}`)
export const getEquipmentOdds = (currency = 'gold') => request(`/gacha/equipment-odds?currency=${currency}`)
export const getPityInfo = () => request('/gacha/pity-info')
export const redeemSpark = () => request('/gacha/spark-redeem', { method: 'POST' })
export const redeemEquipSpark = () => request('/gacha/equip-spark-redeem', { method: 'POST' })

// Tower / Runs
export const enterFloor = (floorNumber, teamIds, stance = 'balanced') => request('/tower/floor/enter', { method: 'POST', body: JSON.stringify({ floor_number: floorNumber, team_ids: Array.isArray(teamIds) ? teamIds : [teamIds], stance }) })
// Called the instant a fight's animation finishes — reveals the fallen NOW
// (deaths are deferred server-side so they don't spoil on other tabs mid-fight).
export const finalizeCombat = (pendingCombatId = null) => request('/tower/floor/finalize', { method: 'POST', body: JSON.stringify({ pending_combat_id: pendingCombatId }) })
export const getNarrative = (narrativeId) => request(`/tower/narrative/${narrativeId}`)
export const previewFloor = (floorNumber) => request(`/tower/floor/preview/${floorNumber}`)
export const resolveEvent = (floorNumber, teamId, templateId, choiceId, theme) => request('/tower/floor/event/resolve', { method: 'POST', body: JSON.stringify({ floor_number: floorNumber, team_id: teamId, template_id: templateId, choice_id: choiceId, theme: theme }) })
export const resolveExplore = (floorNumber, teamId, choiceId) => request('/tower/floor/explore/resolve', { method: 'POST', body: JSON.stringify({ floor_number: floorNumber, team_id: teamId, choice_id: choiceId }) })
export const getLore = () => request('/tower/lore')
export const listRuns = () => request('/runs/')
export const getEventLog = (runId = null, limit = 50) => request(`/runs/log?${runId ? `run_id=${runId}&` : ''}limit=${limit}`)

// Arena (local backend side only — resolves a team's full combat stats
// exactly like a Tower floor would, for shipping to the separate Arena
// server. See api/arenaServerClient.js for the remote-host calls.)
export const getArenaSnapshot = (teamId) => request(`/arena/team/${teamId}/snapshot`)
export const applyTraining = (studentId, gemCost, teacherStats, teacherSkills) => request('/arena/apply_training', { method: 'POST', body: JSON.stringify({ student_id: studentId, gem_cost: gemCost, teacher_stats: teacherStats, teacher_skills: teacherSkills }) })
export const recordArenaResult = (win, newElo) => request('/arena/result', { method: 'POST', body: JSON.stringify({ win, new_elo: newElo }) })

// Profiles
export const listProfiles = () => request('/profiles/')
export const switchProfile = (name, difficulty) => request('/profiles/switch', { method: 'POST', body: JSON.stringify(difficulty ? { name, difficulty } : { name }) })
export const renameProfile = (oldName, newName) => request('/profiles/rename', { method: 'POST', body: JSON.stringify({ old_name: oldName, new_name: newName }) })
export const deleteProfile = (name) => request('/profiles/delete', { method: 'POST', body: JSON.stringify({ name }) })

// Mail
export const getMailList = () => request('/base/mail/list')
export const claimMail = (mailId) => request('/base/mail/claim', { method: 'POST', body: JSON.stringify({ mail_id: mailId }) })
export const receiveMail = (sender, subject, body, rewardsJson) => request('/base/mail/receive', { method: 'POST', body: JSON.stringify({ sender, subject, body, rewards_json: rewardsJson }) })

/* ============================================================
   Base Raids (local side) — the raid defense snapshot, scouting
   spend, and applying results/prisoners against your own save.
   The World/Arena server calls live in api/arenaServerClient.js.
   ============================================================ */
export const raidDefenseSnapshot = () => request('/raid/defense_snapshot')
export const raidScoutPower = () => request('/raid/scout_power')
export const raidPayScout = (currency = 'gold') => request('/raid/pay_scout', { method: 'POST', body: JSON.stringify({ currency }) })
export const raidApplyAttackResult = (won, goldStolen = 0, ingredientsStolen = 0) => request('/raid/apply_attack_result', { method: 'POST', body: JSON.stringify({ won, gold_stolen: goldStolen, ingredients_stolen: ingredientsStolen }) })
export const raidApplyEvent = (eventType, payload = {}) => request('/raid/apply_raid_event', { method: 'POST', body: JSON.stringify({ event_type: eventType, payload }) })
export const raidIntegratePrisoner = (prisoner, originalMaster) => request('/raid/integrate_prisoner', { method: 'POST', body: JSON.stringify({ prisoner, original_master: originalMaster }) })
export const raidListPrisoners = () => request('/raid/prisoners')
export const raidWinOverPrisoner = (heroId) => request(`/raid/prisoner/${heroId}/win_over`, { method: 'POST' })
export const setGuildBoons = (heroExpPct, refitDiscountPct) =>
  request('/base/guild_boons', { method: 'POST', body: JSON.stringify({ hero_exp_pct: heroExpPct, refit_discount_pct: refitDiscountPct }) })
