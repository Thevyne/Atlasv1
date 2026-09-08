"""Writes the full electrical design into the original DXF.

Grey-out : color 8 (true medium grey) on all existing layers.
New layers:
  LIGHTING    4  cyan    -- fixture circles + LP tags  (matches Image A)
  SOCKETS     1  red     -- socket triangles
  SWITCHES    4  cyan    -- switch arcs (same cyan family as lighting, Image A)
  WIRING      4  cyan    -- fixture-to-switch arc connections
  DB_LOCATION 1  red     -- distribution board symbol
  TAGS        7  white   -- all tag text
Then adds a professional drawing border (grid refs + title block + legend).
"""

import ezdxf
from . import dxf_symbols, drawing_border

DESIGN_LAYERS = {
    "LIGHTING":    4,   # cyan  (matches Image A)
    "SOCKETS":     1,   # red
    "SWITCHES":    4,   # cyan  (matches Image A)
    "WIRING":      4,   # cyan
    "DB_LOCATION": 1,   # red
    "TAGS":        7,
    # border layers added by drawing_border module
    "BORDER":      7,
    "GRID_REF":    7,
    "TITLE_BLOCK": 7,
    "LEGEND_BOX":  7,
}
ARCH_GREY = 8   # ACI 8 = true medium grey #808080


def _grey_existing(doc):
    for layer in doc.layers:
        if layer.dxf.name not in DESIGN_LAYERS and layer.dxf.name != "Defpoints":
            layer.dxf.color = ARCH_GREY
    for entity in doc.modelspace():
        try:
            if entity.dxf.hasattr("color"):
                entity.dxf.color = ARCH_GREY
        except Exception:
            pass


def _ensure_layers(doc):
    for name, color in DESIGN_LAYERS.items():
        if name not in doc.layers:
            doc.layers.add(name=name, color=color)


def _sort_chain(pts):
    if not pts:
        return []
    rem = list(pts)
    out = [rem.pop(0)]
    while rem:
        last = out[-1]
        n = min(rem, key=lambda p:(p[0]-last[0])**2+(p[1]-last[1])**2)
        out.append(n); rem.remove(n)
    return out


def _arc(msp, x1, y1, x2, y2, bulge=0.35):
    msp.add_lwpolyline(
        [(x1,y1,0,0,bulge),(x2,y2,0,0,0)],
        dxfattribs={"layer":"WIRING"})


def draw_room_wiring(msp, rooms_wiring, scale):
    for room in rooms_wiring:
        fpts = [(x/scale, y/scale) for x,y in room.get("fixtures",[])]
        sw   = room.get("switch")
        if not fpts:
            continue
        fpts = _sort_chain(fpts)
        for i in range(len(fpts)-1):
            _arc(msp, fpts[i][0],fpts[i][1], fpts[i+1][0],fpts[i+1][1])
        if sw:
            sx,sy = sw[0]/scale, sw[1]/scale
            near = min(fpts, key=lambda p:(p[0]-sx)**2+(p[1]-sy)**2)
            _arc(msp, sx,sy, near[0],near[1], bulge=0.18)


def write_full_design(
    input_path, output_path,
    grouped_fixtures, grouped_sockets, switches,
    rooms_wiring, db_x_native, db_y_native, scale,
    project_info=None,
):
    doc = ezdxf.readfile(input_path)
    msp = doc.modelspace()

    _grey_existing(doc)
    _ensure_layers(doc)

    # ── Lighting fixtures ──────────────────────────────────────────
    for cct in grouped_fixtures:
        for item in cct.get("items",[]):
            x_n,y_n = item["x"]/scale, item["y"]/scale
            kind,tag = item.get("kind","LP"), item.get("tag","")
            if kind == "chandelier":
                dxf_symbols.draw_chandelier(msp,x_n,y_n,tag=tag)
            elif kind == "wall_light":
                dxf_symbols.draw_wall_light(msp,x_n,y_n,tag=tag)
            else:
                dxf_symbols.draw_lighting_fixture(msp,x_n,y_n,tag=tag)

    # ── Sockets ────────────────────────────────────────────────────
    for cct in grouped_sockets:
        for item in cct.get("items",[]):
            x_n,y_n = item["x"]/scale, item["y"]/scale
            kind,tag = item.get("kind","SP"), item.get("tag","")
            if kind == "SK":
                dxf_symbols.draw_socket_double_13a(msp,x_n,y_n,tag=tag)
            elif kind == "SP15":
                dxf_symbols.draw_socket_15a(msp,x_n,y_n,tag=tag)
            elif kind == "SK15":
                dxf_symbols.draw_socket_double_15a(msp,x_n,y_n,tag=tag)
            else:
                dxf_symbols.draw_socket_13a(msp,x_n,y_n,tag=tag)

    # ── Switches ───────────────────────────────────────────────────
    for sw in switches:
        x_n,y_n = sw["x"]/scale, sw["y"]/scale
        kind,tag = sw.get("switch_type","single"), sw.get("tag","")
        if kind == "double":
            dxf_symbols.draw_switch_double(msp,x_n,y_n,tag=tag,
                                           layer_sym="SWITCHES")
        elif kind == "triple":
            dxf_symbols.draw_switch_triple(msp,x_n,y_n,tag=tag,
                                           layer_sym="SWITCHES")
        elif kind == "2way":
            dxf_symbols.draw_switch_2way(msp,x_n,y_n,tag=tag,
                                         layer_sym="SWITCHES")
        else:
            dxf_symbols.draw_switch_single(msp,x_n,y_n,tag=tag,
                                           layer_sym="SWITCHES")

    # ── Wiring arcs ────────────────────────────────────────────────
    draw_room_wiring(msp, rooms_wiring, scale)

    # ── DB symbol ──────────────────────────────────────────────────
    dxf_symbols.draw_distribution_board(msp, db_x_native, db_y_native)

    # ── Professional drawing border + title block + legend ─────────
    if project_info:
        drawing_border.add_professional_border(doc, msp, project_info)

    doc.saveas(output_path)


def write_lighting_layer(input_path, output_path, rooms_with_fixtures):
    doc = ezdxf.readfile(input_path)
    _grey_existing(doc)
    if "LIGHTING" not in doc.layers:
        doc.layers.add(name="LIGHTING", color=4)
    msp = doc.modelspace()
    for room in rooms_with_fixtures:
        for x,y in room["fixtures"]:
            dxf_symbols.draw_lighting_fixture(msp, x, y)
    doc.saveas(output_path)
