"""Electrical symbols matching the reference drawing legend.

Symbols use the user's own conventions:
  Lighting    → plain circle (YELLOW layer)
  13A socket  → upward triangle + base line (RED layer)
  15A socket  → upward triangle + apex dot (RED layer)
  Double 13A  → two offset triangles (RED layer)
  Switch      → arc symbol (MAGENTA layer)
  DB          → rectangle with diagonal cross

Symbol sizes are large enough to be clearly visible on a typical
architectural floor plan at 1:50 or 1:100 scale.
"""

import math
from ezdxf.enums import TextEntityAlignment

# ── Sizes (native DXF units = mm) ─────────────────────────────────────────
R_LP      = 150    # lighting circle radius
R_CHAN    = 150
DOT_R     = 28
WL_W, WL_H = 120, 60
TRI_HW    = 100    # socket triangle half-base
TRI_H     = 150    # socket triangle height
DOT_SOCK  = 22     # 15A apex dot
SW_LEN    = 90     # switch stem
SW_R      = 80     # switch arc radius
DB_HALF   = 280
TAG_H     = 80

# ── Layer assignments ─────────────────────────────────────────────────────
L_LIGHT   = "LIGHTING"  # cyan (4)     # yellow (2)
L_SOCKET  = "SOCKETS"      # red (1)
L_SWITCH  = "SWITCHES"  # cyan (4)     # magenta (6)
L_DB      = "DB_LOCATION"  # red (1)
L_WIRING  = "WIRING"       # cyan (4)
L_TAG     = "TAGS"         # white (7)


def _text(msp, x, y, s, layer=L_TAG, h=TAG_H):
    msp.add_text(
        s, dxfattribs={"layer": layer, "height": h}
    ).set_placement((x, y), align=TextEntityAlignment.LEFT)


# ── Lighting ──────────────────────────────────────────────────────────────

def draw_lighting_fixture(msp, x, y, tag="",
                           layer_sym=L_LIGHT, layer_tag=L_TAG):
    msp.add_circle((x, y), radius=R_LP, dxfattribs={"layer": layer_sym})
    if tag:
        _text(msp, x + R_LP + 12, y + 12, tag, layer=layer_tag,
              h=int(TAG_H * 0.7))


def draw_chandelier(msp, x, y, tag="",
                    layer_sym=L_LIGHT, layer_tag=L_TAG):
    msp.add_circle((x, y), radius=R_CHAN, dxfattribs={"layer": layer_sym})
    msp.add_circle((x, y), radius=DOT_R,  dxfattribs={"layer": layer_sym})
    if tag:
        _text(msp, x + R_CHAN + 12, y + 12, tag, layer=layer_tag,
              h=int(TAG_H * 0.7))


def draw_wall_light(msp, x, y, tag="",
                    layer_sym=L_LIGHT, layer_tag=L_TAG):
    hw, hh = WL_W // 2, WL_H // 2
    msp.add_lwpolyline(
        [(x-hw,y-hh),(x+hw,y-hh),(x+hw,y+hh),(x-hw,y+hh)],
        close=True, dxfattribs={"layer": layer_sym},
    )
    msp.add_line((x-hw,y-hh),(x+hw,y+hh), dxfattribs={"layer": layer_sym})
    if tag:
        _text(msp, x+hw+12, y, tag, layer=layer_tag, h=int(TAG_H*0.7))


# ── Sockets — user triangle convention, on red SOCKETS layer ─────────────

def _tri(msp, x, y, layer):
    hw = TRI_HW
    msp.add_line((x-hw, y),(x+hw, y), dxfattribs={"layer": layer})
    msp.add_lwpolyline(
        [(x-hw,y),(x+hw,y),(x,y+TRI_H)],
        close=True, dxfattribs={"layer": layer},
    )


def draw_socket_13a(msp, x, y, tag="",
                    layer_sym=L_SOCKET, layer_tag=L_TAG):
    """13A socket — triangle + base line."""
    _tri(msp, x, y, layer_sym)
    if tag:
        _text(msp, x+TRI_HW+15, y+TRI_H//2, tag, layer=layer_tag,
              h=int(TAG_H*0.7))


def draw_socket_double_13a(msp, x, y, tag="",
                            layer_sym=L_SOCKET, layer_tag=L_TAG):
    """Double 13A — two offset triangles."""
    off = int(TRI_HW * 0.5)
    for ox in (-off//2, off//2):
        hw = TRI_HW
        msp.add_line((x-hw+ox,y),(x+hw+ox,y), dxfattribs={"layer": layer_sym})
        msp.add_lwpolyline(
            [(x-hw+ox,y),(x+hw+ox,y),(x+ox,y+TRI_H)],
            close=True, dxfattribs={"layer": layer_sym},
        )
    if tag:
        _text(msp, x+TRI_HW+off+15, y+TRI_H//2, tag, layer=layer_tag,
              h=int(TAG_H*0.7))


def draw_socket_15a(msp, x, y, tag="",
                    layer_sym=L_SOCKET, layer_tag=L_TAG):
    """15A socket — triangle + dot at apex."""
    _tri(msp, x, y, layer_sym)
    msp.add_circle((x, y+TRI_H), radius=DOT_SOCK,
                   dxfattribs={"layer": layer_sym})
    if tag:
        _text(msp, x+TRI_HW+15, y+TRI_H//2, tag, layer=layer_tag,
              h=int(TAG_H*0.7))


def draw_socket_double_15a(msp, x, y, tag="",
                            layer_sym=L_SOCKET, layer_tag=L_TAG):
    off = int(TRI_HW * 0.5)
    for ox in (-off//2, off//2):
        hw = TRI_HW
        msp.add_line((x-hw+ox,y),(x+hw+ox,y), dxfattribs={"layer": layer_sym})
        msp.add_lwpolyline(
            [(x-hw+ox,y),(x+hw+ox,y),(x+ox,y+TRI_H)],
            close=True, dxfattribs={"layer": layer_sym},
        )
        msp.add_circle((x+ox,y+TRI_H), radius=DOT_SOCK,
                       dxfattribs={"layer": layer_sym})
    if tag:
        _text(msp, x+TRI_HW+off+15, y+TRI_H//2, tag, layer=layer_tag,
              h=int(TAG_H*0.7))


# ── Switches — on magenta SWITCHES layer ──────────────────────────────────

def _arc_unit(msp, cx, cy, layer):
    msp.add_line((cx, cy),(cx, cy+SW_LEN), dxfattribs={"layer": layer})
    msp.add_arc((cx, cy+SW_LEN), radius=SW_R,
                start_angle=0, end_angle=180,
                dxfattribs={"layer": layer})


def draw_switch_single(msp, x, y, tag="",
                       layer_sym=L_SWITCH, layer_tag=L_TAG):
    _arc_unit(msp, x, y, layer_sym)
    if tag:
        _text(msp, x+SW_R+15, y+SW_LEN//2, tag, layer=layer_tag,
              h=int(TAG_H*0.7))


def draw_switch_double(msp, x, y, tag="",
                       layer_sym=L_SWITCH, layer_tag=L_TAG):
    gap = SW_R*2+25
    _arc_unit(msp, x-gap//2, y, layer_sym)
    _arc_unit(msp, x+gap//2, y, layer_sym)
    if tag:
        _text(msp, x+gap+SW_R+15, y+SW_LEN//2, tag, layer=layer_tag,
              h=int(TAG_H*0.7))


def draw_switch_triple(msp, x, y, tag="",
                       layer_sym=L_SWITCH, layer_tag=L_TAG):
    gap = SW_R*2+25
    for dx in (-gap, 0, gap):
        _arc_unit(msp, x+dx, y, layer_sym)
    if tag:
        _text(msp, x+gap*1.5+SW_R+15, y+SW_LEN//2, tag, layer=layer_tag,
              h=int(TAG_H*0.7))


def draw_switch_2way(msp, x, y, tag="",
                     layer_sym=L_SWITCH, layer_tag=L_TAG):
    msp.add_line((x,y),(x,y+SW_LEN), dxfattribs={"layer": layer_sym})
    msp.add_arc((x,y+SW_LEN), radius=SW_R, start_angle=0, end_angle=180,
                dxfattribs={"layer": layer_sym})
    msp.add_arc((x,y), radius=SW_R, start_angle=180, end_angle=360,
                dxfattribs={"layer": layer_sym})
    if tag:
        _text(msp, x+SW_R+15, y+SW_LEN//2, tag, layer=layer_tag,
              h=int(TAG_H*0.7))


# ── DB symbol ─────────────────────────────────────────────────────────────

def draw_distribution_board(msp, x, y, label="DB",
                             layer_sym=L_DB, layer_tag=L_TAG):
    h = DB_HALF
    msp.add_lwpolyline(
        [(x-h,y-h),(x+h,y-h),(x+h,y+h),(x-h,y+h)],
        close=True, dxfattribs={"layer": layer_sym},
    )
    msp.add_line((x-h,y-h),(x+h,y+h), dxfattribs={"layer": layer_sym})
    msp.add_line((x+h,y-h),(x-h,y+h), dxfattribs={"layer": layer_sym})
    _text(msp, x, y+h+50, label, layer=layer_tag, h=int(TAG_H*1.5))


def draw_earthing(msp, x, y, layer_sym=L_SOCKET):
    s = 65
    msp.add_lwpolyline(
        [(x-s,y),(x+s,y),(x,y-s)],
        close=True, dxfattribs={"layer": layer_sym},
    )
    for i, f in enumerate([0.65,0.4,0.2]):
        yy = y-s-16-i*16
        hw = int(s*f)
        msp.add_line((x-hw,yy),(x+hw,yy), dxfattribs={"layer": layer_sym})
