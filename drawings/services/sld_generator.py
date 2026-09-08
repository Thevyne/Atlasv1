"""Single Line Diagram (SLD) generator for a distribution board.

Matches the reference blueprint structure:

  FEED (arrow + cable size)
       |
  ┌ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┐   ← busbar: DASHED rectangle
  |     |    |    |    |    |    |    |  |     (grounds hang off the two
  ╲     |    |    |    |    |    |    |  ╱      top corners as a diagonal
   (E) [M]  [M]  [M]  [M]  [M]  [M]  [M] (E)     lead ending in one tick)
  └ ─ ─ |─ ─ |─ ─ |─ ─ |─ ─ |─ ─ |─ ─ |─ ┘
        |    |    |    |    |    |    |     ← circuit lines pass straight
      CCT1  CCT2 CCT3  ...                     through the busbar box
       LP1  LP17  SP1
       LP2  LP18  SP2
       ...

Sheet size is chosen automatically (A2 -> A1 -> A0) based on circuit
count and load-list length, so nothing overlaps or gets truncated.
"""

import ezdxf
from ezdxf.enums import TextEntityAlignment

# ── Standard ISO sheet sizes, landscape (mm) ─────────────────────────────
SHEET_SIZES = [
    ("A2", 594, 420),
    ("A1", 841, 594),
    ("A0", 1189, 841),
]

MX, MY = 15, 15

MCB_W, MCB_H = 10, 10       # breaker symbol size
BUS_H        = 12            # busbar rectangle height
STUB         = 10            # stub length: busbar top edge -> breaker
STEP         = 6             # vertical spacing between load tags
MIN_COL_W    = 30            # minimum width per circuit column (mm)
COL_START    = MX + 20

TH_TITLE = 8
TH_HEAD  = 5
TH_BODY  = 3.8
TH_SMALL = 2.8

PHASE_COLOR = {"R": 1, "Y": 2, "B": 5}   # optional colour-coding by phase

L_BD, L_BUS, L_R, L_Y, L_B, L_TXT, L_INF = (
    "SLD_BORDER", "SLD_BUS", "SLD_R", "SLD_Y", "SLD_B", "SLD_TEXT", "SLD_INFO"
)


def _pl(phase):
    return {"R": L_R, "Y": L_Y, "B": L_B}.get(phase, L_BUS)


def _ensure_resources(doc):
    for name, color in [
        (L_BD, 7), (L_BUS, 7), (L_R, 1), (L_Y, 2), (L_B, 5), (L_TXT, 7), (L_INF, 4)
    ]:
        if name not in doc.layers:
            doc.layers.add(name=name, color=color)
    # DASHED linetype for the busbar rectangle (setup=True in ezdxf.new()
    # already loads standard linetypes, this is just a safety net)
    if "DASHED" not in doc.linetypes:
        doc.linetypes.add("DASHED", pattern="A,.6,-.3", description="Dashed")


def _t(msp, x, y, text, layer=L_TXT, h=TH_BODY, align="LEFT"):
    a = {
        "LEFT": TextEntityAlignment.LEFT,
        "CENTER": TextEntityAlignment.CENTER,
        "RIGHT": TextEntityAlignment.RIGHT,
    }.get(align, TextEntityAlignment.LEFT)
    msp.add_text(text, dxfattribs={"layer": layer, "height": h}).set_placement((x, y), align=a)


def _breaker(msp, cx, cy, layer=L_BUS):
    """Small square with a diagonal slash - matches the reference symbol."""
    hw, hh = MCB_W / 2, MCB_H / 2
    msp.add_lwpolyline(
        [(cx - hw, cy - hh), (cx + hw, cy - hh), (cx + hw, cy + hh), (cx - hw, cy + hh)],
        close=True, dxfattribs={"layer": layer})
    msp.add_line((cx - hw, cy - hh), (cx + hw, cy + hh), dxfattribs={"layer": layer})


def _ground(msp, corner_x, corner_y, direction, layer=L_BUS):
    """Ground lead hanging off a busbar corner: a diagonal line ending in
    one short perpendicular tick, matching the reference (not the
    triple-bar IEC symbol - this drawing uses the simplified version)."""
    dx = 8 * direction   # direction: -1 for left end, +1 for right end
    dy = -10
    ex, ey = corner_x + dx, corner_y + dy
    msp.add_line((corner_x, corner_y), (ex, ey), dxfattribs={"layer": layer})
    # perpendicular tick at the end of the lead
    tick = 4
    perp_dx, perp_dy = -dy, dx  # perpendicular to the (dx, dy) direction
    norm = (perp_dx ** 2 + perp_dy ** 2) ** 0.5
    ux, uy = perp_dx / norm * tick, perp_dy / norm * tick
    msp.add_line((ex - ux, ey - uy), (ex + ux, ey + uy), dxfattribs={"layer": layer})


# ── Dynamic sheet sizing ──────────────────────────────────────────────────

def _compute_layout(schedule):
    circuits = schedule.get("circuits", [])
    n = max(len(circuits), 1)
    max_items = max((len(c.get("items", [])) for c in circuits), default=0)

    col_w = MIN_COL_W
    needed_width = COL_START + n * col_w + MX + 20

    top_chrome = 20 + 30 + 34 + STUB + MCB_H + 6 + BUS_H  # header+title+feed+breaker+bus
    drop_chrome = 8 + TH_SMALL + 3 + TH_BODY + 2          # gap + cable text + cct label
    bottom_chrome = MY + 15

    needed_drop_height = drop_chrome + max_items * STEP + 15
    needed_height = MY + top_chrome + needed_drop_height + bottom_chrome

    for name, w, h in SHEET_SIZES:
        if w >= needed_width and h >= needed_height:
            return name, w, h, col_w

    name, w, h = SHEET_SIZES[-1]
    scale = min(
        1.0,
        (w - COL_START - MX - 20) / max(1, n * MIN_COL_W),
        (h - MY - top_chrome - bottom_chrome - drop_chrome - 15) / max(1, max_items * STEP),
    )
    scale = max(scale, 0.5)
    return name, w, h, MIN_COL_W * scale


# ── Header / title ─────────────────────────────────────────────────────────

def _draw_header(msp, W, H, header_lines, title_y):
    y = H - MY - 6
    for line in header_lines:
        _t(msp, W / 2, y, line, layer=L_TXT, h=TH_HEAD, align="CENTER")
        y -= 7
    _t(msp, W / 2, title_y, "SINGLE LINE DIAGRAM OF DISTRIBUTION BOARD",
       layer=L_TXT, h=TH_TITLE, align="CENTER")
    _t(msp, W / 2, title_y - 7, "NOT TO SCALE", layer=L_INF, h=TH_SMALL, align="CENTER")


# ── FEED ──────────────────────────────────────────────────────────────────

def _draw_feed(msp, schedule, feed_x, feed_top_y, busbar_top_y):
    csa = schedule.get("incoming_cable_csa_mm2", 4)
    _t(msp, feed_x - 12, feed_top_y + 4, "FEED", layer=L_TXT, h=TH_HEAD)
    msp.add_line((feed_x, feed_top_y), (feed_x, busbar_top_y), dxfattribs={"layer": L_BUS})
    arrow_y = feed_top_y - 10
    msp.add_lwpolyline([(feed_x - 3, arrow_y + 6), (feed_x, arrow_y), (feed_x + 3, arrow_y + 6)],
                        dxfattribs={"layer": L_BUS})
    _t(msp, feed_x + 6, arrow_y - 2, f"3C x {csa}mm2", layer=L_INF, h=TH_SMALL)


# ── Busbar (dashed rectangle + ground leads) ───────────────────────────────

def _draw_busbar(msp, x_left, x_right, top_y, bot_y):
    msp.add_lwpolyline(
        [(x_left, bot_y), (x_right, bot_y), (x_right, top_y), (x_left, top_y)],
        close=True, dxfattribs={"layer": L_BUS, "linetype": "DASHED", "lineweight": 35})
    _ground(msp, x_left, top_y, direction=-1)
    _ground(msp, x_right, top_y, direction=1)


# ── Single circuit column ────────────────────────────────────────────────

def _draw_circuit(msp, cct, col_x, busbar_top_y, busbar_bot_y, bottom_y, col_w):
    phase = cct.get("phase", "")
    pl = _pl(phase)

    # breaker sits on a stub above the busbar top edge
    breaker_cy = busbar_top_y + STUB + MCB_H / 2
    msp.add_line((col_x, busbar_top_y), (col_x, breaker_cy - MCB_H / 2), dxfattribs={"layer": pl})
    _breaker(msp, col_x, breaker_cy, layer=pl)
    _t(msp, col_x + MCB_W / 2 + 2, breaker_cy + 2, f"{cct['mcb_rating_a']}A", layer=pl, h=TH_SMALL)

    # circuit line passes straight through the busbar rectangle
    msp.add_line((col_x, breaker_cy - MCB_H / 2), (col_x, busbar_bot_y - 8), dxfattribs={"layer": pl})

    y = busbar_bot_y - 8
    _t(msp, col_x, y, f"{cct['cct_label']}-3C x {cct['cable_csa_mm2']}mm2",
       layer=L_TXT, h=TH_SMALL, align="CENTER")
    y -= TH_SMALL + 4

    spine_top = y

    for item in cct.get("items", []):
        tag = item.get("tag", "")
        if not tag:
            continue
        if y < bottom_y:
            _t(msp, col_x, y, "+more", layer=L_INF, h=TH_SMALL, align="CENTER")
            break
        _t(msp, col_x, y, tag, layer=L_TXT, h=TH_SMALL, align="CENTER")
        y -= STEP

    msp.add_line((col_x, spine_top), (col_x, max(y + STEP, bottom_y)), dxfattribs={"layer": pl})
    return y


# ── Border ────────────────────────────────────────────────────────────────

def _draw_border(msp, W, H):
    msp.add_lwpolyline([(0, 0), (W, 0), (W, H), (0, H)], close=True,
                        dxfattribs={"layer": L_BD, "lineweight": 50})
    msp.add_lwpolyline([(4, 4), (W - 4, 4), (W - 4, H - 4), (4, H - 4)], close=True,
                        dxfattribs={"layer": L_BD})


# ── Entry point ───────────────────────────────────────────────────────────

def generate_sld(output_path, schedule, project_name="PROJECT", header_lines=None):
    """header_lines: optional list of strings shown above the title
    (e.g. client name, project name, building type) - matches the
    stacked header text seen in the reference blueprint."""
    doc = ezdxf.new(setup=True)
    try:
        doc.header["$INSUNITS"] = 4
    except Exception:
        pass
    _ensure_resources(doc)
    msp = doc.modelspace()

    circuits = schedule.get("circuits", [])
    type_order = {"lighting": 0, "socket": 1, "socket_key": 2}
    circuits = sorted(circuits, key=lambda c: (type_order.get(c.get("type"), 9), c.get("cct_label", "")))

    if header_lines is None:
        header_lines = [project_name] if project_name else []

    sheet_name, W, H, col_w = _compute_layout(schedule)

    n = max(len(circuits), 1)
    col_xs = [COL_START + col_w * i + col_w / 2 for i in range(n)]
    bus_x_left = col_xs[0] - col_w / 2 - 6
    bus_x_right = col_xs[-1] + col_w / 2 + 6

    title_y = H - MY - 6 - len(header_lines) * 7 - 6
    feed_top_y = title_y - 20
    busbar_top_y = feed_top_y - 24
    busbar_bot_y = busbar_top_y - BUS_H
    bottom_y = MY + 10

    _draw_border(msp, W, H)
    _draw_header(msp, W, H, header_lines, title_y)
    _draw_feed(msp, schedule, bus_x_left + 10, feed_top_y, busbar_top_y)
    _draw_busbar(msp, bus_x_left, bus_x_right, busbar_top_y, busbar_bot_y)

    for cct, cx in zip(circuits, col_xs):
        _draw_circuit(msp, cct, cx, busbar_top_y, busbar_bot_y, bottom_y, col_w)

    doc.saveas(output_path)
    print(f"Saved: {output_path}  (sheet {sheet_name}, {W}x{H}mm, {n} circuits)")
    return {"sheet_size": sheet_name, "width_mm": W, "height_mm": H}