"""Finds a strategic Distribution Board location: the load-weighted
centroid of all fixtures and sockets, snapped to the nearest room wall.

'Strategic' in practice means: close to the geometric centre of
electrical load, near a corridor or landing (so the DB is accessible),
against a wall (for a surface or semi-flush mount). This heuristic
matches the approach used in the reference drawings, where the DB is
placed in the corridor/entrance area central to both floors.
"""
from shapely.geometry import LineString, MultiLineString, Point, Polygon


def _load_centroid(items):
    total_w = sum(i.get("load_w", 1) for i in items)
    if total_w == 0:
        xs = [i["x"] for i in items]
        ys = [i["y"] for i in items]
        return sum(xs) / len(xs), sum(ys) / len(ys)
    cx = sum(i["x"] * i.get("load_w", 1) for i in items) / total_w
    cy = sum(i["y"] * i.get("load_w", 1) for i in items) / total_w
    return cx, cy


def _all_edges(rooms):
    edges = []
    for room in rooms:
        coords = room["polygon"]
        for a, b in zip(coords, coords[1:]):
            edges.append(LineString([a, b]))
    return edges


def find_db_location(rooms, fixtures, sockets):
    """Returns (db_x, db_y) in metres (same coordinate frame as the rooms).

    Algorithm:
    1. Compute load-weighted centroid of all fixtures + sockets.
    2. Find the nearest point on any room wall to that centroid.
    3. Nudge 0.1m inward so the DB sits just inside the room.
    """
    all_items = list(fixtures) + list(sockets)
    if not all_items:
        polys = [Polygon(r["polygon"]) for r in rooms if len(r.get("polygon", [])) >= 3]
        if not polys:
            return 0.0, 0.0
        union = polys[0]
        for p in polys[1:]:
            union = union.union(p)
        c = union.centroid
        return c.x, c.y

    cx, cy = _load_centroid(all_items)
    centroid_pt = Point(cx, cy)

    edges = _all_edges(rooms)
    if not edges:
        return cx, cy

    best_pt = centroid_pt
    best_dist = float("inf")
    for edge in edges:
        nearest = edge.interpolate(edge.project(centroid_pt))
        d = centroid_pt.distance(nearest)
        if d < best_dist:
            best_dist = d
            best_pt = nearest

    # Nudge inward toward centroid so it sits inside the building
    dx = cx - best_pt.x
    dy = cy - best_pt.y
    length = (dx**2 + dy**2) ** 0.5
    if length > 1e-6:
        db_x = best_pt.x + (dx / length) * 0.1
        db_y = best_pt.y + (dy / length) * 0.1
    else:
        db_x, db_y = best_pt.x, best_pt.y

    return round(db_x, 3), round(db_y, 3)
