OFFLINE_HOURS: int = 12
MEDITATE_COOLDOWN: int = 14400
MEDITATE_HOURS: int = 3
MINOR_CHANCE: int = 85
MAJOR_CHANCE: int = 55
CHANCE_CAP: int = 98
MINOR_LOSS: float = 0.10
MAJOR_LOSS: float = 0.30
DEVIATION_SECONDS: int = 3600
INJURY_SECONDS: int = 43200
PILL_DAILY_LIMIT: int = 3
REROLLS: int = 1
ROOTS: dict = {
    "common": {"weight": 85, "mult": 1.0, "names": ("Fire", "Water", "Wood", "Metal", "Earth")},
    "rare": {"weight": 12, "mult": 1.15, "names": ("Lightning", "Ice", "Wind")},
    "legendary": {"weight": 3, "mult": 1.4, "names": ("Heavenly", "Chaos")},
}
QUALITIES: tuple = (
    {"name": "Mortal", "weight": 40, "mult": 0.85},
    {"name": "Spirit", "weight": 35, "mult": 1.0},
    {"name": "Earth", "weight": 18, "mult": 1.2},
    {"name": "Heaven", "weight": 7, "mult": 1.5},
)
PATHS: dict = {
    "sword": {"origin": "Wanjian Pavilion", "name": "Sword", "perk": "+10% qi from meditation", "meditate": 1.10},
    "body": {"origin": "Xuanwu Hall", "name": "Body", "perk": "+10% idle qi", "idle": 1.10},
    "alchemy": {"origin": "Danding Valley", "name": "Alchemy", "perk": "pills are 15% stronger and 10% cheaper", "pill_power": 1.15, "pill_price": 0.90},
    "formation": {"origin": "Tianji Pavilion", "name": "Formation", "perk": "+5% breakthrough chance and +2 hours of offline cap", "chance": 5, "offline": 2},
}
REALMS: tuple = (
    {"name": "Qi Condensation", "stages": tuple(f"Layer {i}" for i in range(1, 10)), "gain": 20, "base": 167, "growth": 1.18, "fee": 2000},
    {"name": "Foundation Establishment", "stages": ("Early", "Middle", "Late", "Peak"), "gain": 60, "base": 3040, "growth": 1.35, "fee": 10000},
    {"name": "Core Formation", "stages": ("Early", "Middle", "Late", "Peak"), "gain": 180, "base": 17035, "growth": 1.40, "fee": 40000},
    {"name": "Nascent Soul", "stages": ("Early", "Middle", "Late", "Peak"), "gain": 540, "base": 79579, "growth": 1.45, "fee": 0},
)
FUTURE_REALMS: tuple = ("Soul Transformation", "Void Refinement", "Body Integration", "Mahayana", "Tribulation Transcendence")
ITEMS: dict = {
    "qi_pill": {"name": "Qi Gathering Pill", "price": 200, "scale": True, "hours": 8, "info": "Instantly gives qi worth 8 hours of idle gain. Limited per day."},
    "tribulation_pill": {"name": "Heaven-Defying Pill", "price": 4000, "scale": True, "chance": 15, "info": "Adds 15% to your next tribulation, up to 30%."},
    "healing_pill": {"name": "Healing Pill", "price": 800, "scale": False, "info": "Removes an injury or qi deviation."},
}
EVENT_DAILY: int = 3
TALK_DAILY: int = 1
FIGHT_DAILY: int = 8
FIGHT_COINS: tuple = ((15, 35), (60, 140), (250, 560), (1000, 2200))
FIGHT_QI_HOURS: float = 0.5
FIGHT_MATERIAL_CHANCE: int = 35
FIGHT_GEAR_CHANCE: int = 4
FIGHT_DEFEAT_QI: float = 0.03
PVP_DAILY: int = 5
PVP_TARGET_COOLDOWN: int = 21600
PVP_REALM_GAP: int = 2
PVP_ROBBED_DAILY: int = 3
PVP_STEAL_PCT: float = 0.08
PVP_STEAL_MAX: int = 3000
PVP_MIN_POUCH: int = 200
PVP_LOSS_PCT: float = 0.05
PVP_LOSS_MAX: int = 1500
PVP_ITEM_DROP: int = 5
SHIELD_DAYS: int = 7
SAFE_BASE: int = 2000
SAFE_GROWTH: int = 3
DUAL_COOLDOWN: int = 28800
DUAL_HOURS: float = 2.0
DUAL_BONUS: float = 1.25
BLOOD_ROOT_CHANCE: int = 35
BLOOD_RACE_CHANCE: int = 25
TREASURY_BASE: int = 10000
TREASURY_PER_MEMBER: int = 5000
TREASURY_MAX: int = 100000
INHERIT_DAYS: int = 60
DUNGEON_DAILY: int = 2
DUNGEON_MAX_PARTY: int = 4
DUNGEON_COIN_MULT: int = 2
DUNGEON_MATERIAL_CHANCE: int = 60
DUNGEON_GEAR_CHANCE: int = 8
BUILDINGS: dict = {
    "array": {"name": "Spirit Gathering Array", "zh": "聚灵阵", "info": "+2% idle qi per level for every member."},
    "pavilion": {"name": "Alchemy Pavilion", "zh": "丹阁", "info": "Pills cost 3% less per level for every member."},
    "hall": {"name": "Martial Hall", "zh": "演武堂", "info": "+3% attack and +2% health in combat per level."},
    "scripture": {"name": "Scripture Pavilion", "zh": "藏经阁", "info": "Unlocks a sect technique for every member at each level."},
    "guard": {"name": "Mountain Guardian Formation", "zh": "护山大阵", "info": "Raiders steal 10% less from members per level."},
}
BUILDING_COSTS: tuple = (20000, 50000, 120000, 250000, 500000)
BUILDING_MAX: int = 5
BOSS_COINS_MULT: int = 6
BOSS_HP_PER_MEMBER: int = 3000
BOSS_DAYS: int = 7
BOSS_RESPAWN_HOURS: int = 48
BOSS_DAILY: int = 3
BOSS_TURNS: int = 10
BOSS_PERSONAL_HP: float = 3.0
BOSS_BANK_PER_LEVEL: int = 5000
BOSS_GEAR_CHANCE: int = 25
WAR_MIN_TIER: int = 2
WAR_HOURS: int = 48
WAR_PENDING_HOURS: int = 24
WAR_MIN_SCORE: int = 5
WAR_STAKE_PCT: float = 0.05
WAR_STAKE_MAX: int = 100000
WAR_COOLDOWN_HOURS: int = 72
EXPLORE_DAILY: int = 12
EXPLORE_COOLDOWN: int = 300
EXPLORE_WEIGHTS: dict = {"beast": 38, "traveler": 18, "treasure": 14, "event": 14, "rift": 6, "boss": 3, "nothing": 7}
WILD_COIN_MULT: float = 0.5
WILD_BOSS_COIN_MULT: int = 3
WILD_BOSS_GEAR_CHANCE: int = 20
WILD_BOSS_SHARD_CHANCE: int = 40
NPC_LIMIT: int = 12
TALK_AFFINITY: tuple = (5, 12)
SPAR_DAILY: int = 3
BOND_MAX: int = 5
BOND_QI: float = 0.01
WILD_DAILY: int = 10
WILD_STRIKE_DAILY: int = 4
SPAWN_COOLDOWN: int = 1200
SPAWN_MESSAGES: int = 25
SPAWN_CHANCE: int = 10
SPAWN_BOSS_CHANCE: int = 12
SPAWN_BEAST_SECONDS: int = 300
SPAWN_BOSS_SECONDS: int = 1800
SPAWN_BOSS_HP: int = 12000
MATERIAL_VALUES: dict = {"beast_core": 25, "spirit_iron": 100, "thunder_crystal": 400, "chaos_shard": 1600, "rift_shard": 150}


BOUNTY_COUNT = 3
BOUNTY_COINS = 300
BOUNTY_QI = 0.03
BOUNTY_BONUS_COINS = 600
BOUNTY_BONUS_MATERIALS = 2


BREW_MATERIALS = 3
BREW_COINS = 150
BREWS: dict = {
    "vigor_pill": {"name": "Vigor Pill", "zh": "神力丹", "info": "+20% attack until midnight UTC", "atk": 1.20},
    "ironskin_pill": {"name": "Iron Skin Pill", "zh": "铁肤丹", "info": "+20% health and defense until midnight UTC", "hp": 1.20, "def": 1.20},
    "windstep_pill": {"name": "Windstep Pill", "zh": "风行丹", "info": "+8% dodge until midnight UTC", "dodge": 8},
    "fortune_pill": {"name": "Fortune Pill", "zh": "福运丹", "info": "+50% spirit stones from fights until midnight UTC", "coins": 1.5},
}

MARKET_FEE_PCT: int = 5
MARKET_MAX_LISTINGS: int = 10
MARKET_DAYS: int = 7
MARKET_MAX_PRICE: int = 1_000_000_000
MARKET_MAX_QTY: int = 9999
AUCTION_FEE_PCT: int = 8
AUCTION_MAX: int = 5
AUCTION_MIN_HOURS: int = 1
AUCTION_MAX_HOURS: int = 72
AUCTION_DEFAULT_HOURS: int = 24
AUCTION_RAISE_PCT: int = 5
AUCTION_SNIPE_SECONDS: int = 300
TRADE_PAGE: int = 8
GATHER_DAILY: int = 8
GATHER_HERB_KINDS: int = 2
GATHER_HERB_QTY: tuple = (1, 3)
GATHER_UP_CHANCE: int = 10
GATHER_FIBER_CHANCE: int = 30
GATHER_HIDE_CHANCE: int = 40
HUNT_QTY: tuple = (1, 3)
HERB_FIGHT_CHANCE: int = 20
HERB_EXPLORE_CHANCE: int = 30
STONE_COINS_PER_LOW: int = 1
STONE_MID: int = 100
STONE_HIGH: int = 100
TRANSCEND_MAX: int = 9
TRANSCEND_FEE: int = 250000
TRANSCEND_WAVES: int = 3
TRANSCEND_WAVES_MAX: int = 7
TRANSCEND_POWER: float = 0.06
TRANSCEND_QI: float = 0.05
TRANSCEND_OMEN: int = 64
TRANSCEND_OMEN_STEP: int = 3
TRANSCEND_OMEN_MIN: int = 45
TRANSCEND_HEALS: int = 2
TRANSCEND_HEAL: float = 0.30
TRANSCEND_FAIL_QI: float = 0.5
TRANSCEND_INJURY: float = 2.0
TRANSCEND_BASE: float = 0.15
TRANSCEND_WAVE_STEP: float = 0.012
TRANSCEND_TIER_STEP: float = 0.014
TRANSCEND_RIGHT: float = 0.45
TRANSCEND_WRONG: float = 1.2
TRANSCEND_TIMEOUT: int = 240
