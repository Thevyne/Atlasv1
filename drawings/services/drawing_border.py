"""Adds a professional ISO-style drawing border, grid references, title
block, and legend to the design DXF — matching the reference Image A.

All geometry is sized relative to the drawing extents so it scales
correctly regardless of the architectural drawing's unit scale.

Border structure (matching reference Image A):
  ┌───1──2──3──4──5──6──7──8───┐ ← grid numbers top
  A                             A
  B       drawing content       B  ← grid letters sides
  ...                          ...
  F                             F
  └───1──2──3──4──5──6──7──8───┘
  ┌────────────────────────────────────── title block ──┐
  │ Based on │ Approved │ Title │ Contract │ Sheet      │
  └──────────┴──────────┴───────┴──────────┴────────────┘

Legend box: bottom-right inside drawing area.
"""

import math
from ezdxf import bbox
from ezdxf.enums import TextEntityAlignment

L_BORDER = "BORDER"
L_GRID   = "GRID_REF"
L_TITLE  = "TITLE_BLOCK"
L_LEGEND = "LEGEND_BOX"

GRID_COLS = 8   # columns: 1-8
GRID_ROWS = 6   # rows: A-F
ROW_LABELS = "ABCDEF"


def _ensure(doc):
    for name, color in [
        (L_BORDER, 7), (L_GRID, 7), (L_TITLE, 7), (L_LEGEND, 7)
    ]:
        if name not in doc.layers:
            doc.layers.add(name=name, color=color)


def _t(msp, x, y, text, layer, h, align="LEFT"):
    a = {
        "LEFT":   TextEntityAlignment.LEFT,
        "CENTER": TextEntityAlignment.CENTER,
        "RIGHT":  TextEntityAlignment.RIGHT,
    }.get(align, TextEntityAlignment.LEFT)
    msp.add_text(text, dxfattribs={"layer": layer, "height": h}).set_placement(
        (x, y), align=a
    )


def _hline(msp, x1, y, x2, layer):
    msp.add_line((x1, y), (x2, y), dxfattribs={"layer": layer})


def _vline(msp, x, y1, y2, layer):
    msp.add_line((x, y1), (x, y2), dxfattribs={"layer": layer})


def _rect(msp, x1, y1, x2, y2, layer):
    msp.add_lwpolyline(
        [(x1, y1), (x2, y1), (x2, y2), (x1, y2)],
        close=True, dxfattribs={"layer": layer},
    )


def add_professional_border(doc, msp, project_info):
    """
    project_info keys: project_name, floor_label, prepared_by, approved_by,
                        title, contract_no, sheet_no, total_sheets
    """
    _ensure(doc)

    # ── Compute drawing extents from existing entities ─────────────────
    box = bbox.extents(msp, fast=True)
    if box is None:
        return

    xmin, ymin, _ = box.extmin
    xmax, ymax, _ = box.extmax
    W = xmax - xmin
    H = ymax - ymin

    # ── Layout constants (relative to drawing size) ────────────────────
    MARGIN      = W * 0.025          # space between content and inner border
    BAND        = W * 0.025          # grid reference band width
    TB_H        = H * 0.10           # title block height
    TH          = BAND * 0.35        # text height in border/title
    TH_SMALL    = TH * 0.75

    # Inner border (wraps content + small margin)
    ib_x1 = xmin - MARGIN
    ib_x2 = xmax + MARGIN
    ib_y1 = ymin - MARGIN
    ib_y2 = ymax + MARGIN

    # Grid band positions (outside the inner border)
    ob_x1 = ib_x1 - BAND
    ob_x2 = ib_x2 + BAND
    ob_y1 = ib_y1 - BAND - TB_H
    ob_y2 = ib_y2 + BAND

    # ── Outer border ───────────────────────────────────────────────────
    _rect(msp, ob_x1, ob_y1, ob_x2, ob_y2, L_BORDER)

    # ── Inner border ───────────────────────────────────────────────────
    _rect(msp, ib_x1, ib_y1, ib_x2, ib_y2, L_BORDER)

    # ── Top / bottom grid bands ────────────────────────────────────────
    for band_y1, band_y2 in [
        (ib_y2, ob_y2),
        (ib_y1 - BAND, ib_y1),
    ]:
        _rect(msp, ob_x1, band_y1, ob_x2, band_y2, L_GRID)
        col_w = (ob_x2 - ob_x1) / GRID_COLS
        for i in range(GRID_COLS):
            cx = ob_x1 + col_w * i
            _vline(msp, cx, band_y1, band_y2, L_GRID)
            _t(msp, cx + col_w/2, band_y1 + (band_y2-band_y1)*0.3,
               str(i + 1), L_GRID, TH, align="CENTER")

    # ── Left / right grid bands ────────────────────────────────────────
    for band_x1, band_x2 in [
        (ob_x1, ib_x1),
        (ib_x2, ob_x2),
    ]:
        _rect(msp, band_x1, ib_y1, band_x2, ib_y2, L_GRID)
        row_h = (ib_y2 - ib_y1) / GRID_ROWS
        for i in range(GRID_ROWS):
            cy = ib_y2 - row_h * i
            _hline(msp, band_x1, cy, band_x2, L_GRID)
            mid_y = cy - row_h/2
            _t(msp, band_x1 + (band_x2-band_x1)*0.5, mid_y - TH*0.4,
               ROW_LABELS[i], L_GRID, TH, align="CENTER")

    # ── Title block ────────────────────────────────────────────────────
    tb_y1 = ib_y1 - BAND - TB_H
    tb_y2 = ib_y1 - BAND

    _rect(msp, ob_x1, tb_y1, ob_x2, tb_y2, L_TITLE)

    # Divide into columns
    c1 = ob_x1 + (ob_x2 - ob_x1) * 0.20
    c2 = ob_x1 + (ob_x2 - ob_x1) * 0.40
    c3 = ob_x1 + (ob_x2 - ob_x1) * 0.62
    c4 = ob_x1 + (ob_x2 - ob_x1) * 0.78
    for cx in [c1, c2, c3, c4]:
        _vline(msp, cx, tb_y1, tb_y2, L_TITLE)

    # Horizontal divider mid-title block
    mid_tb = (tb_y1 + tb_y2) / 2
    for x1, x2 in [(ob_x1,c1),(c1,c2),(c3,ob_x2)]:
        _hline(msp, x1, mid_tb, x2, L_TITLE)

    # Labels
    pad = BAND * 0.15
    data = project_info
    _t(msp, ob_x1+pad, tb_y2-TH_SMALL*1.5, "Based on",    L_TITLE, TH_SMALL)
    _t(msp, ob_x1+pad, mid_tb-TH_SMALL*1.5,"Scale",        L_TITLE, TH_SMALL)

    _t(msp, c1+pad, tb_y2-TH_SMALL*1.5, "Approved",        L_TITLE, TH_SMALL)
    _t(msp, c1+pad, tb_y2-TH_SMALL*3,   data.get("approved_by","—"), L_TITLE, TH)
    _t(msp, c1+pad, mid_tb-TH_SMALL*1.5,"Prepared",        L_TITLE, TH_SMALL)
    _t(msp, c1+pad, mid_tb-TH_SMALL*3,  data.get("prepared_by","—"), L_TITLE, TH)

    _t(msp, c2+pad, (tb_y1+tb_y2)/2,
       f"Title  {data.get('title','LIGHTING AND POWER DESIGN')}",
       L_TITLE, TH, align="LEFT")

    _t(msp, c3+pad, tb_y2-TH_SMALL*1.5, "Contract No.", L_TITLE, TH_SMALL)
    _t(msp, c3+pad, tb_y2-TH_SMALL*3,   data.get("contract_no","—"), L_TITLE, TH_SMALL)
    _t(msp, c3+pad, mid_tb-TH_SMALL*1.5,"Item",         L_TITLE, TH_SMALL)
    _t(msp, c3+pad, mid_tb-TH_SMALL*3,  data.get("item","—"),        L_TITLE, TH_SMALL)

    _t(msp, c4+pad, tb_y2-TH_SMALL*1.5, "Sheet",  L_TITLE, TH_SMALL)
    _t(msp, c4+pad, tb_y2-TH_SMALL*3,
       f"{data.get('sheet_no','006')} / {data.get('total_sheets','007')}",
       L_TITLE, TH)

    # Project name strip at the bottom of title block
    proj_h = TB_H * 0.2
    _hline(msp, ob_x1, tb_y1 + proj_h, ob_x2, L_TITLE)
    _t(msp, (ob_x1+ob_x2)/2, tb_y1 + proj_h*0.3,
       f"Project name  {data.get('project_name','DUPLEX')}",
       L_TITLE, TH, align="CENTER")

    # ── Legend box (bottom-right of drawing area) ──────────────────────
    leg_w = W * 0.18
    leg_h = H * 0.28
    leg_x2 = ib_x2 - MARGIN * 0.5
    leg_x1 = leg_x2 - leg_w
    leg_y1 = ib_y1 + MARGIN * 0.5
    leg_y2 = leg_y1 + leg_h

    _rect(msp, leg_x1, leg_y1, leg_x2, leg_y2, L_LEGEND)

    # Legend title bar
    ltb_h = leg_h * 0.1
    _hline(msp, leg_x1, leg_y2 - ltb_h, leg_x2, L_LEGEND)
    _t(msp, (leg_x1+leg_x2)/2, leg_y2 - ltb_h*0.5 - TH*0.4,
       "LEGEND", L_LEGEND, TH * 1.1, align="CENTER")

    items = [
        ("□✕", "Distribution Board"),
        ("○",  "Lighting fixture"),
        ("△",  "13 Amp wall socket"),
        ("△·", "15 Amps wall socket"),
        ("▲▲", "Double 13Amp wall socket"),
        ("⌒",  "Single gang switch"),
        ("⌒⌒","Double gang switch"),
        ("⌒⌒⌒","Triple gang switch"),
        ("⇅",  "Two way switch"),
        ("⏚",  "Earthing"),
    ]
    item_h = (leg_y2 - ltb_h - leg_y1) / (len(items) + 0.5)
    for i, (sym, desc) in enumerate(items):
        y = leg_y2 - ltb_h - item_h * (i + 1)
        _t(msp, leg_x1 + leg_w*0.05, y, sym,  L_LEGEND, TH_SMALL)
        _t(msp, leg_x1 + leg_w*0.25, y, desc, L_LEGEND, TH_SMALL)
