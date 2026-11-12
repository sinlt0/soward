TABLES = (
        """CREATE TABLE IF NOT EXISTS cult_raid_log (
            attacker_id INTEGER NOT NULL,
            target_id INTEGER NOT NULL,
            result TEXT NOT NULL DEFAULT '',
            coins INTEGER NOT NULL DEFAULT 0,
            item TEXT NOT NULL DEFAULT '',
            at REAL NOT NULL DEFAULT 0
        )""",
        """CREATE TABLE IF NOT EXISTS cult_titles (
            user_id INTEGER NOT NULL,
            title_key TEXT NOT NULL,
            earned_at REAL NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, title_key)
        )""",
        """CREATE TABLE IF NOT EXISTS cult_story (
            user_id INTEGER PRIMARY KEY,
            chapter INTEGER NOT NULL DEFAULT 0,
            progress TEXT NOT NULL DEFAULT '{}',
            flags TEXT NOT NULL DEFAULT '{}',
            updated_at REAL NOT NULL DEFAULT 0
        )""",
        """CREATE TABLE IF NOT EXISTS cult_calamity (
            user_id INTEGER NOT NULL,
            day TEXT NOT NULL,
            slot INTEGER NOT NULL,
            won INTEGER NOT NULL DEFAULT 0,
            started_at REAL NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, day, slot)
        )""",
        """CREATE TABLE IF NOT EXISTS cult_commissions (
            user_id INTEGER NOT NULL,
            period TEXT NOT NULL,
            slot INTEGER NOT NULL,
            kind TEXT NOT NULL,
            goal INTEGER NOT NULL DEFAULT 1,
            progress INTEGER NOT NULL DEFAULT 0,
            claimed INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, period, slot)
        )""",
        """CREATE TABLE IF NOT EXISTS cult_feats (
            user_id INTEGER NOT NULL,
            feat TEXT NOT NULL,
            count INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, feat)
        )""",
        """CREATE TABLE IF NOT EXISTS clan_branches (
            clan_id TEXT NOT NULL,
            branch_key TEXT NOT NULL,
            name TEXT NOT NULL,
            founder_id INTEGER NOT NULL,
            created_at REAL NOT NULL DEFAULT 0,
            PRIMARY KEY (clan_id, branch_key)
        )""",
    """CREATE TABLE IF NOT EXISTS cult_weapons (
        weapon_id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_id INTEGER NOT NULL,
        grade INTEGER NOT NULL DEFAULT 0,
        quality INTEGER NOT NULL DEFAULT 1,
        durability INTEGER NOT NULL DEFAULT 1,
        max_durability INTEGER NOT NULL DEFAULT 1,
        equipped INTEGER NOT NULL DEFAULT 0,
        listed INTEGER NOT NULL DEFAULT 0,
        created_at REAL NOT NULL DEFAULT 0
    )""",
    """CREATE INDEX IF NOT EXISTS idx_cult_weapons_owner ON cult_weapons (owner_id)""",
    """CREATE TABLE IF NOT EXISTS cult_pouches (
        user_id INTEGER NOT NULL,
        kind TEXT NOT NULL,
        tier INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (user_id, kind)
    )""",
    """CREATE TABLE IF NOT EXISTS market_listings (
        listing_id INTEGER PRIMARY KEY AUTOINCREMENT,
        seller_id INTEGER NOT NULL,
        item TEXT NOT NULL,
        qty INTEGER NOT NULL DEFAULT 1,
        price INTEGER NOT NULL DEFAULT 0,
        created_at REAL NOT NULL DEFAULT 0,
        expires_at REAL NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'open'
    )""",
    """CREATE TABLE IF NOT EXISTS auctions (
        auction_id INTEGER PRIMARY KEY AUTOINCREMENT,
        seller_id INTEGER NOT NULL,
        item TEXT NOT NULL,
        qty INTEGER NOT NULL DEFAULT 1,
        start_price INTEGER NOT NULL DEFAULT 0,
        buyout INTEGER NOT NULL DEFAULT 0,
        bid INTEGER NOT NULL DEFAULT 0,
        bidder_id INTEGER NOT NULL DEFAULT 0,
        bids INTEGER NOT NULL DEFAULT 0,
        created_at REAL NOT NULL DEFAULT 0,
        ends_at REAL NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'open'
    )""",
)

COLUMNS = (
    ("cult_characters", "weapon_r INTEGER NOT NULL DEFAULT 0"),
    ("cult_characters", "armor_r INTEGER NOT NULL DEFAULT 0"),
    ("cult_characters", "charm_r INTEGER NOT NULL DEFAULT 0"),
    ("cult_characters", "weapon_e TEXT NOT NULL DEFAULT ''"),
    ("cult_characters", "armor_e TEXT NOT NULL DEFAULT ''"),
    ("cult_characters", "charm_e TEXT NOT NULL DEFAULT ''"),
    ("cult_characters", "title TEXT NOT NULL DEFAULT ''"),
    ("cult_characters", "transcend INTEGER NOT NULL DEFAULT 0"),
    ("cult_characters", "trans_realm INTEGER NOT NULL DEFAULT 0"),
    ("cult_characters", "attune TEXT NOT NULL DEFAULT ''"),
    ("cult_characters", "attune_until REAL NOT NULL DEFAULT 0"),
    ("clan_members", "branch TEXT NOT NULL DEFAULT ''"),
)

state = {"done": False}


async def ensure(force: bool = False) -> None:
    if state["done"] and not force:
        return
    from utils import db
    for statement in TABLES:
        await db.raw_execute(statement)
    for table, column in COLUMNS:
        try:
            await db.raw_execute(f"ALTER TABLE {table} ADD COLUMN {column}")
        except Exception:
            pass
    state["done"] = True
