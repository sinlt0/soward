from utils import db


def _fmt(row, kind: str) -> tuple[float, str]:
    return float(row["ts"]), f"{kind} {row['detail']}".strip()


async def collect(guild_id: int, user_id: int, limit: int = 30) -> list[tuple[float, str]]:
    events: list[tuple[float, str]] = []
    queries = (
        ("**Case**", "SELECT created_at AS ts, '`' || action || '` by <@' || moderator_id || '>: ' || COALESCE(reason, 'no reason') AS detail FROM mod_cases WHERE guild_id=? AND user_id=?"),
        ("**Warn**", "SELECT created_at AS ts, 'by <@' || moderator_id || '>: ' || COALESCE(reason, 'no reason') AS detail FROM warn_cases WHERE guild_id=? AND user_id=?"),
        ("**Reported**", "SELECT created_at AS ts, '(' || status || COALESCE(', ' || outcome, '') || ') ' || reason AS detail FROM message_reports WHERE guild_id=? AND target_id=?"),
        ("**Filed a report**", "SELECT created_at AS ts, '(' || status || ')' AS detail FROM message_reports WHERE guild_id=? AND reporter_id=?"),
        ("**Appeal**", "SELECT created_at AS ts, '(' || status || ')' AS detail FROM ban_appeals WHERE guild_id=? AND user_id=?"),
        ("**Trust**", "SELECT created_at AS ts, printf('%+d', delta) || ' by <@' || moderator_id || '>: ' || reason AS detail FROM trust_adjustments WHERE guild_id=? AND user_id=?"),
        ("**Ticket**", "SELECT created_at AS ts, COALESCE(subject, 'opened') || ' (' || status || ')' AS detail FROM tickets WHERE guild_id=? AND owner_id=?"),
        ("**Application**", "SELECT created_at AS ts, form || ' (' || status || ')' AS detail FROM app_submissions WHERE guild_id=? AND user_id=?"),
        ("**Ban link**", "SELECT created_at AS ts, 'possible evasion of <@' || banned_id || '> (' || score || '/100, ' || status || ')' AS detail FROM evasion_links WHERE guild_id=? AND user_id=?"),
        ("**Timed role**", "SELECT created_at AS ts, '<@&' || role_id || '> until <t:' || CAST(expires_at AS INTEGER) || ':f>' AS detail FROM timed_roles WHERE guild_id=? AND user_id=?"),
    )
    for kind, sql in queries:
        for row in await db.raw_fetch(sql, (guild_id, user_id)):
            events.append(_fmt(row, kind))
    events.sort(key=lambda e: -e[0])
    return events[:limit]
