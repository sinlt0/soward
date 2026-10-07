import importlib
import logging
from pathlib import Path
from typing import Optional

log = logging.getLogger("soward.emoji")

_table: dict[str, str] = {}

def load_all(emoji_dir: Path) -> None:
    _table.clear()
    for path in sorted(emoji_dir.glob("*.py")):
        if path.stem.startswith("_"):
            continue
        module_name = f"emoji.{path.stem}"
        try:
            mod = importlib.import_module(module_name)
            mapping: dict = getattr(mod, "emojis", {})
            for k, v in mapping.items():
                if k in _table:
                    log.warning("Emoji key collision: '%s' redefined in %s", k, path.stem)
                _table[k] = v
            log.info("Loaded %d emoji(s) from emoji/%s.py", len(mapping), path.stem)
        except Exception as exc:
            log.error("FAILED to load emoji/%s.py: %s", path.stem, exc)
            raise

    log.info("EmojiManager ready with %d total emoji(s).", len(_table))

def get(key: str, fallback: str = "") -> str:
    return _table.get(key, fallback)

def all_emojis() -> dict[str, str]:
    return dict(_table)
