"""Produces the DB schedule data structure matching the reference drawings.

The reference shows these columns (per circuit row):
  Sub-circuit no | Description | No. points | Load/point (W) | Load factor |
  Connected phase load R/Y/B (W) | Voltage (V) | Current (A) |
  Current+25% (A) | MCB rating (A) | Cable size (mm²)

And a summary row: Normal running load per phase, Total power (W),
Current (A), +30% spare, ideal DB rating, next standard rating.
"""
from . import cable_sizing, cable_routing


VOLTAGE = 230.0
SPARE_FACTOR = 0.30   # 30% spare capacity for DB incomer sizing


def build_schedule(circuit_summary, db_x, db_y, floor_label="Ground Floor"):
    """Builds and returns a serialisable schedule dict from circuit_summary
    (output of circuit_grouping.assign_circuits).

    Returns:
        {
          'floor': str,
          'circuits': [circuit_row, ...],
          'totals': {phase load R/Y/B, total_w, full_load_a,
                     spare_a, design_a, db_rating_a},
        }
    """
    rows = []
    phase_load = {"R": 0.0, "Y": 0.0, "B": 0.0}

    for cct in circuit_summary:
        items = cct.get("items", [])
        worst_run = cable_routing.worst_case_run(
            [{"x": i["x"], "y": i["y"]} for i in items], db_x, db_y
        ) if items else 10.0

        sizing = cable_sizing.size_circuit_cable(
            total_load_w=cct["total_load_w"],
            cable_run_length_m=max(worst_run, 5.0),   # minimum 5m assumed
        )

        phase = cct["phase"]
        phase_load[phase] = phase_load.get(phase, 0.0) + cct["total_load_w"]

        rows.append({
            "cct_label": cct["cct_label"],
            "description": _description(cct),
            "n_points": cct["n_points"],
            "load_per_point_w": cct["load_per_point_w"],
            "load_factor": cct["load_factor"],
            "connected_load_r": cct["total_load_w"] if phase == "R" else 0.0,
            "connected_load_y": cct["total_load_w"] if phase == "Y" else 0.0,
            "connected_load_b": cct["total_load_w"] if phase == "B" else 0.0,
            "voltage_v": VOLTAGE,
            "full_load_a": sizing["full_load_a"],
            "design_current_a": sizing["design_current_a"],
            "mcb_rating_a": sizing["mcb_rating_a"],
            "cable_csa_mm2": sizing["cable_csa_mm2"],
            "voltage_drop_v": sizing["voltage_drop_v"],
            "phase": phase,
            "type": cct["type"],
            "items": [{"tag": i.get("tag", "")} for i in cct.get("items", [])],
        })

    total_w = sum(v for v in phase_load.values())
    full_load_a = total_w / VOLTAGE
    spare_a = full_load_a * SPARE_FACTOR
    design_a = full_load_a + spare_a

    incomer = cable_sizing.size_incoming_cable(total_w)

    return {
        "floor": floor_label,
        "circuits": rows,
        "phase_load": phase_load,
        "total_w": round(total_w, 1),
        "full_load_a": round(full_load_a, 2),
        "spare_a": round(spare_a, 2),
        "design_a": round(design_a, 2),
        "incomer_mcb_a": incomer["incomer_mcb_a"],
        "incoming_cable_csa_mm2": incomer["incoming_cable_csa_mm2"],
    }


def _description(cct):
    items = cct.get("items", [])
    tags = [i.get("tag", "") for i in items if i.get("tag")]
    if not tags:
        return cct["cct_label"]
    if len(tags) <= 4:
        return ", ".join(tags)
    return f"{tags[0]}, {tags[1]}, ..., {tags[-1]}"
