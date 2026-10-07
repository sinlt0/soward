import importlib
import logging
import pkgutil
import traceback
from pathlib import Path

from discord.ext import commands

log = logging.getLogger("soward.loader")

def discover_extensions(package_dir: Path, package_name: str) -> list[str]:
    extensions = []
    for module_info in pkgutil.iter_modules([str(package_dir)]):
        if module_info.name.startswith("_"):
            continue
        extensions.append(f"{package_name}.{module_info.name}")
    return extensions

async def load_cogs(bot: commands.Bot, cogs_dir: Path) -> tuple[list[str], list[tuple[str, str]]]:
    extensions = discover_extensions(cogs_dir, "cogs")
    loaded: list[str] = []
    failed: list[tuple[str, str]] = []

    for ext in extensions:
        try:
            await bot.load_extension(ext)
            loaded.append(ext)
            log.info("Loaded cog: %s", ext)
        except Exception as exc:
            reason = f"{type(exc).__name__}: {exc}"
            failed.append((ext, reason))
            log.error(
                "FAILED to load cog '%s' — %s\n%s",
                ext,
                reason,
                traceback.format_exc(),
            )

    log.info("Cogs: %d loaded, %d failed (of %d discovered).", len(loaded), len(failed), len(extensions))
    if failed:
        log.warning(
            "The following cogs FAILED to load and are NOT active: %s",
            ", ".join(name for name, _ in failed),
        )
    return loaded, failed

def load_events(bot: commands.Bot, events_dir: Path) -> tuple[list[str], list[tuple[str, str]]]:
    extensions = discover_extensions(events_dir, "events")
    loaded: list[str] = []
    failed: list[tuple[str, str]] = []

    for ext in extensions:
        try:
            mod = importlib.import_module(ext)
            if hasattr(mod, "setup"):
                mod.setup(bot)
            loaded.append(ext)
            log.info("Loaded event module: %s", ext)
        except Exception as exc:
            reason = f"{type(exc).__name__}: {exc}"
            failed.append((ext, reason))
            log.error(
                "FAILED to load event module '%s' — %s\n%s",
                ext,
                reason,
                traceback.format_exc(),
            )

    log.info("Events: %d loaded, %d failed (of %d discovered).", len(loaded), len(failed), len(extensions))
    if failed:
        log.warning(
            "The following event modules FAILED to load and are NOT active: %s",
            ", ".join(name for name, _ in failed),
        )
    return loaded, failed

def preload_utils(utils_dir: Path) -> None:
    extensions = discover_extensions(utils_dir, "utils")
    loaded = 0
    for ext in extensions:
        try:
            importlib.import_module(ext)
            loaded += 1
        except Exception as exc:
            log.error("FAILED to import util module '%s': %s", ext, exc, exc_info=True)
            raise
    log.info("Preloaded %d/%d util module(s).", loaded, len(extensions))
