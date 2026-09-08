"""Estimates cable run lengths from each fixture/socket to the DB.

Real conduit routing follows walls and structural elements, which we
can't fully reconstruct from the available geometry. This module uses a
Manhattan-distance approximation (horizontal + vertical only, like
surface conduit on walls) with a 1.2× routing factor to account for
bends, set-downs, and drops -- a conservative assumption that gives
defensible cable quantities for the design report and schedule.

If you later add door/wall positions to the model, replace
_manhattan_distance with an A* grid search for exact results.
"""

ROUTING_FACTOR = 1.2   # 20% extra for bends, drops, and set-downs
CONDUIT_DROP = 0.5     # assumed vertical drop to socket/switch height (m)


def _manhattan(x1, y1, x2, y2):
    return abs(x2 - x1) + abs(y2 - y1)


def route_from_db(items, db_x, db_y, routing_factor=ROUTING_FACTOR):
    """Adds 'cable_run_m' to each item dict (in-place) and returns the
    list with that field populated."""
    for item in items:
        raw = _manhattan(item["x"], item["y"], db_x, db_y)
        item["cable_run_m"] = round((raw + CONDUIT_DROP) * routing_factor, 2)
    return items


def circuit_run_length(circuit_items, db_x, db_y):
    """Total cable length for one circuit: DB → first fixture → subsequent
    fixtures daisy-chained, × routing factor. Assumes a radial spur layout
    (each point individually from DB), which is conservative."""
    total = 0.0
    for item in circuit_items:
        raw = _manhattan(item["x"], item["y"], db_x, db_y)
        total += (raw + CONDUIT_DROP) * ROUTING_FACTOR
    return round(total, 2)


def worst_case_run(circuit_items, db_x, db_y):
    """Returns the single longest run in the circuit, used for voltage
    drop calculation (worst case, not average)."""
    if not circuit_items:
        return 0.0
    runs = [
        (_manhattan(i["x"], i["y"], db_x, db_y) + CONDUIT_DROP) * ROUTING_FACTOR
        for i in circuit_items
    ]
    return round(max(runs), 2)
