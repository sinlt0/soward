import math
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

FONT_FILE = Path(__file__).resolve().parent.parent / "assets" / "fonts" / "Poppins-Medium.ttf"
SS = 2
TEXT_SIZE = 17 * SS
PAD_X = 16 * SS
BOX_H = 38 * SS
PARTNER_GAP = 26 * SS
SIBLING_GAP = 26 * SS
ROW_GAP = 86 * SS
MARGIN = 28 * SS
MAX_WIDTH = 9000
CAPTION_H = 46 * SS
BACKGROUND = (255, 255, 255)
BOX = (0, 0, 0)
HIGHLIGHT = (30, 64, 255)
LINE = (0, 0, 0)
TEXT = (255, 255, 255)


def load_font(size: int):
    try:
        return ImageFont.truetype(str(FONT_FILE), size)
    except OSError:
        try:
            return ImageFont.truetype("DejaVuSans.ttf", size)
        except OSError:
            return ImageFont.load_default()


def glyph(font, char: str) -> bytes:
    canvas = Image.new("L", (TEXT_SIZE * 2, TEXT_SIZE * 2), 0)
    ImageDraw.Draw(canvas).text((4, 4), char, font=font, fill=255)
    return canvas.tobytes()


def clean_name(name: str, font, fallback: str) -> str:
    blank = glyph(font, "\ue000")
    cache: dict[str, bool] = {}
    kept = []
    for ch in name:
        if ch.isspace():
            kept.append(" ")
            continue
        if ch not in cache:
            cache[ch] = glyph(font, ch) != blank
        if cache[ch]:
            kept.append(ch)
    text = " ".join("".join(kept).split())
    if sum(ch.isalnum() for ch in text) < 2:
        text = fallback
    return text if len(text) <= 20 else text[:19].rstrip() + "…"


def order_members(members: list[int], links: dict[int, set[int]]) -> list[int]:
    remaining = set(members)
    ordered = []
    while remaining:
        start = min(remaining, key=lambda m: (len(links[m] & remaining), m))
        stack = [start]
        while stack:
            current = stack.pop()
            if current not in remaining:
                continue
            remaining.discard(current)
            ordered.append(current)
            stack.extend(sorted(links[current] & remaining, reverse=True))
    return ordered


def build_units(comp: dict) -> tuple[list[list[int]], dict[int, int]]:
    nodes = sorted(comp["nodes"])
    links: dict[int, set[int]] = {n: set() for n in nodes}
    for a, b in comp["couples"]:
        links[a].add(b)
        links[b].add(a)
    seen: set[int] = set()
    units = []
    for node in nodes:
        if node in seen:
            continue
        group, stack = [], [node]
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            group.append(current)
            stack.extend(links[current] - seen)
        units.append(order_members(group, links))
    return units, {m: i for i, unit in enumerate(units) for m in unit}


def arrange(comp: dict) -> dict:
    units, unit_of = build_units(comp)
    parents = comp["parents"]
    kids_of: dict[int, list[tuple[int, float, int]]] = {i: [] for i in range(len(units))}
    for child, (parent, stamp) in parents.items():
        owner = unit_of[parent]
        kids_of[owner].append((units[owner].index(parent), stamp, child))
    has_parent = {unit_of[c] for c in parents}
    roots = [i for i in range(len(units)) if i not in has_parent]
    placed: set[int] = set()
    tree_nodes = []

    def build(index: int, depth: int) -> dict:
        placed.add(index)
        node = {"unit": index, "depth": depth, "children": []}
        for _, _, child in sorted(kids_of[index]):
            child_unit = unit_of[child]
            if child_unit in placed:
                continue
            placed.add(child_unit)
            node["children"].append(child_unit)
        node["children"] = [build(c, depth + 1) for c in node["children"]]
        return node

    for root in roots:
        if root not in placed:
            tree_nodes.append(build(root, 0))
    for index in range(len(units)):
        if index not in placed:
            tree_nodes.append(build(index, 0))
    return {"units": units, "unit_of": unit_of, "forest": tree_nodes}


def generations(layout: dict) -> int:
    def depth(node):
        return 1 + max((depth(c) for c in node["children"]), default=0)
    return max((depth(n) for n in layout["forest"]), default=0)


def render(comp: dict, names: dict[int, str], highlight=None, usernames: Optional[dict[int, str]] = None, groups: Optional[dict[int, str]] = None) -> Image.Image:
    font = load_font(TEXT_SIZE)
    caption_font = load_font(int(TEXT_SIZE * 1.15))
    marked = set(highlight) if isinstance(highlight, (set, list, tuple, frozenset)) else {highlight} if highlight is not None else set()
    top = MARGIN + (CAPTION_H if groups else 0)
    layout = arrange(comp)
    units = layout["units"]
    usernames = usernames or {}
    labels = {m: clean_name(names.get(m, ""), font, usernames.get(m) or f"User {str(m)[-4:]}") for m in comp["nodes"]}
    widths = {m: int(font.getlength(labels[m])) + PAD_X * 2 for m in comp["nodes"]}

    def unit_width(index: int) -> int:
        members = units[index]
        return sum(widths[m] for m in members) + PARTNER_GAP * (len(members) - 1)

    def subtree_width(node: dict) -> int:
        node["unit_w"] = unit_width(node["unit"])
        child_total = sum(subtree_width(c) for c in node["children"]) + SIBLING_GAP * max(0, len(node["children"]) - 1)
        node["child_w"] = child_total
        node["width"] = max(node["unit_w"], child_total)
        return node["width"]

    boxes: dict[int, tuple[int, int, int, int]] = {}
    links: list[tuple[int, int]] = []
    captioned: set[str] = set()
    captions: list[tuple[int, str]] = []

    def place(node: dict, x0: int):
        width = node["width"]
        y = top + node["depth"] * (BOX_H + ROW_GAP)
        x = x0 + (width - node["unit_w"]) // 2
        members = units[node["unit"]]
        if groups and node["depth"] == 0:
            caption = groups.get(members[0])
            if caption and caption not in captioned:
                captioned.add(caption)
                captions.append((x0, caption))
        for i, member in enumerate(members):
            boxes[member] = (x, y, x + widths[member], y + BOX_H)
            if i + 1 < len(members):
                links.append((member, members[i + 1]))
            x += widths[member] + PARTNER_GAP
        cx = x0 + (width - node["child_w"]) // 2
        for child in node["children"]:
            place(child, cx)
            cx += child["width"] + SIBLING_GAP

    cursor = MARGIN
    for node in layout["forest"]:
        subtree_width(node)
        place(node, cursor)
        cursor += node["width"] + SIBLING_GAP * 2
    total_w = max(cursor - SIBLING_GAP * 2 + MARGIN, MARGIN * 2 + 200)
    total_h = top + MARGIN + generations(layout) * BOX_H + max(0, generations(layout) - 1) * ROW_GAP
    image = Image.new("RGB", (total_w, total_h), BACKGROUND)
    draw = ImageDraw.Draw(image)
    line_w = 3 * SS

    for a, b in links:
        ax1, ay1, ax2, ay2 = boxes[a]
        bx1, by1, bx2, by2 = boxes[b]
        mid = (ay1 + ay2) // 2
        draw.line([(ax2, mid), (bx1, mid)], fill=LINE, width=line_w)

    for child, (parent, _) in comp["parents"].items():
        px1, py1, px2, py2 = boxes[parent]
        cx1, cy1, cx2, cy2 = boxes[child]
        start = ((px1 + px2) / 2, py2)
        end = ((cx1 + cx2) / 2, cy1)
        mid_y = (start[1] + end[1]) / 2
        points = []
        for step in range(41):
            t = step / 40
            u = 1 - t
            x = u ** 3 * start[0] + 3 * u * u * t * start[0] + 3 * u * t * t * end[0] + t ** 3 * end[0]
            y = u ** 3 * start[1] + 3 * u * u * t * mid_y + 3 * u * t * t * mid_y + t ** 3 * end[1]
            points.append((x, y))
        draw.line(points, fill=LINE, width=line_w, joint="curve")

    for member, (x1, y1, x2, y2) in boxes.items():
        draw.rectangle((x1, y1, x2, y2), fill=HIGHLIGHT if member in marked else BOX)
        draw.text(((x1 + x2) / 2, (y1 + y2) / 2), labels[member], font=font, fill=TEXT, anchor="mm")

    for x, caption in captions:
        draw.text((x, MARGIN // 2 + 6 * SS), caption, font=caption_font, fill=LINE, anchor="lm")
        draw.line([(x, MARGIN // 2 + 6 * SS + 18 * SS), (x + int(caption_font.getlength(caption)), MARGIN // 2 + 6 * SS + 18 * SS)], fill=HIGHLIGHT, width=3 * SS)

    scale = 1.0
    if image.width / SS > MAX_WIDTH:
        scale = MAX_WIDTH / (image.width / SS)
    target = (max(1, int(image.width / SS * scale)), max(1, int(image.height / SS * scale)))
    return image.resize(target, Image.LANCZOS)


def stats(comp: dict) -> dict:
    layout = arrange(comp)
    return {
        "members": len(comp["nodes"]),
        "couples": len(comp["couples"]),
        "adoptions": len(comp["parents"]),
        "generations": generations(layout),
        "truncated": comp["truncated"],
    }


def report(comp: dict) -> list[list[dict]]:
    layout = arrange(comp)
    units = layout["units"]
    partners: dict[int, list[int]] = {n: [] for n in comp["nodes"]}
    for a, b in comp["couples"]:
        partners[a].append(b)
        partners[b].append(a)
    levels: dict[int, list[dict]] = {}

    def walk(node: dict):
        for member in units[node["unit"]]:
            parent = comp["parents"].get(member)
            levels.setdefault(node["depth"], []).append({"id": member, "partners": partners[member], "parent": parent[0] if parent else None})
        for child in node["children"]:
            walk(child)

    for root in layout["forest"]:
        walk(root)
    return [levels[d] for d in sorted(levels)]
