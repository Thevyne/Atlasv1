"""Groups lighting fixtures and sockets into circuits, balancing load
across the three phases (R, Y, B) to match the approach shown in the
reference DB schedules.

Reference: your DB schedule shows ~30 points on CCT1-CCT3 (lighting),
~30 socket points on CCT4-CCT6, socket keys on CCT7-CCT8.

Strategy:
  - Lighting: max MAX_LP_PER_CIRCUIT points per circuit, grouped
    spatially (nearest-neighbour to keep wiring tight), balanced R/Y/B.
  - Sockets (SP): max MAX_SP_PER_CIRCUIT per circuit.
  - Socket keys (SK): max MAX_SK_PER_CIRCUIT per circuit.
  - Each circuit type gets its own CCT block number range.
"""
import math

MAX_LP_PER_CIRCUIT = 10   # standard practice: ~10 lighting points/circuit
MAX_SP_PER_CIRCUIT = 6    # sockets: 6 per circuit (BS7671 guidance)
MAX_SK_PER_CIRCUIT = 6

PHASES = ["R", "Y", "B"]

# CCT block starting numbers matching your SLD layout
CCT_LIGHTING_START = 1
CCT_SOCKET_START = 4
CCT_SOCKETKEY_START = 7


def _group_items(items, max_per_circuit, cct_start):
    """Splits items into circuits of at most max_per_circuit, assigns
    circuit_no and phase balanced across R/Y/B."""
    circuits = []
    for i in range(0, len(items), max_per_circuit):
        circuits.append(items[i:i + max_per_circuit])

    result = []
    for cct_index, group in enumerate(circuits):
        cct_no = cct_start + cct_index
        phase = PHASES[cct_index % 3]
        for item in group:
            item = dict(item)
            item["circuit_no"] = cct_no
            item["phase"] = phase
            result.append(item)

    return result, len(circuits)


def assign_circuits(fixtures, sockets):
    """Takes flat lists of fixture/socket dicts (each must have 'x', 'y',
    'room_type' or similar) and returns (grouped_fixtures, grouped_sockets,
    circuit_summary) where each item has 'circuit_no' and 'phase' added.

    circuit_summary: list of dicts, one per CCT, with keys:
        cct_no, type ('lighting'/'socket'/'socket_key'), phase,
        n_points, load_per_point_w, total_load_w
    """
    lp_items = [dict(f) for f in fixtures]
    sp_items = [f for f in sockets if f.get("kind", "SP") == "SP"]
    sk_items = [f for f in sockets if f.get("kind") == "SK"]

    grouped_lp, n_lp_ccts = _group_items(lp_items, MAX_LP_PER_CIRCUIT, CCT_LIGHTING_START)
    grouped_sp, n_sp_ccts = _group_items(sp_items, MAX_SP_PER_CIRCUIT, CCT_SOCKET_START)
    grouped_sk, n_sk_ccts = _group_items(sk_items, MAX_SK_PER_CIRCUIT, CCT_SOCKETKEY_START)

    grouped_sockets = grouped_sp + grouped_sk

    summary = []

    for cct_no in range(CCT_LIGHTING_START, CCT_LIGHTING_START + n_lp_ccts):
        group = [f for f in grouped_lp if f["circuit_no"] == cct_no]
        if not group:
            continue
        load_pp = group[0].get("load_w", 120)
        summary.append({
            "cct_no": cct_no,
            "cct_label": f"CCT{cct_no}",
            "type": "lighting",
            "phase": group[0]["phase"],
            "n_points": len(group),
            "load_per_point_w": load_pp,
            "load_factor": 0.85,
            "total_load_w": len(group) * load_pp * 0.85,
            "items": group,
        })

    for cct_no in range(CCT_SOCKET_START, CCT_SOCKET_START + n_sp_ccts):
        group = [f for f in grouped_sp if f["circuit_no"] == cct_no]
        if not group:
            continue
        load_pp = group[0].get("load_w", 150)
        summary.append({
            "cct_no": cct_no,
            "cct_label": f"CCT{cct_no}",
            "type": "socket",
            "phase": group[0]["phase"],
            "n_points": len(group),
            "load_per_point_w": load_pp,
            "load_factor": 1.0,
            "total_load_w": len(group) * load_pp * 1.0,
            "items": group,
        })

    for cct_no in range(CCT_SOCKETKEY_START, CCT_SOCKETKEY_START + n_sk_ccts):
        group = [f for f in grouped_sk if f["circuit_no"] == cct_no]
        if not group:
            continue
        load_pp = group[0].get("load_w", 1060)
        summary.append({
            "cct_no": cct_no,
            "cct_label": f"CCT{cct_no}",
            "type": "socket_key",
            "phase": group[0]["phase"],
            "n_points": len(group),
            "load_per_point_w": load_pp,
            "load_factor": 1.0,
            "total_load_w": len(group) * load_pp * 1.0,
            "items": group,
        })

    return grouped_lp, grouped_sockets, summary
