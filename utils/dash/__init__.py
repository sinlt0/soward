import importlib

from utils.dash.base import ACTIONS, SECTIONS, ActionContext, collect_sections

MODULE_FILES = ("tickets", "leveling", "moderation", "security", "community", "embeds", "music")

for _name in MODULE_FILES:
    importlib.import_module(f"utils.dash.{_name}")

__all__ = ["ACTIONS", "SECTIONS", "ActionContext", "collect_sections", "MODULE_FILES"]
