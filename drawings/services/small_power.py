"""Places socket outlets and light switches in rooms using standard
practice rules (loosely based on BS7671 and common Nigerian/UK residential
design practice, matching the reference drawings).

Socket counts by room type (approximate, tune per project):
  bedroom:      4 SP + 2 SK (double socket above desk/bedside)
  living_room:  6 SP + 4 SK
  kitchen:      6 SP + 2 SK (worktop sockets)
  dining:       2 SP + 2 SK
  bathroom:     1 SP (shaver socket only, min 3m from shower)
  corridor:     1 SP
  office:       4 SP + 2 SK
  other:        2 SP

Switch placement: one switch per room near the door opening (offset
inward 0.3m from the nearest corner of the polygon bounding box as a
simple heuristic -- the user can move them on the review screen).
"""
import math
from shapely.geometry import Point, Polygon


SOCKET_SPEC = {
    "bedroom":    {"SP": 4, "SK": 2, "load_w": 150,  "sk_load_w": 150},
    "living_room":{"SP": 4, "SK": 2, "load_w": 150,  "sk_load_w": 1060},
    "kitchen":    {"SP": 2, "SK": 2, "load_w": 150,  "sk_load_w": 1060},
    "dining":     {"SP": 2, "SK": 1, "load_w": 150,  "sk_load_w": 150},
    "bathroom":   {"SP": 0, "SK": 0, "load_w": 150,  "sk_load_w": 0},
    "corridor":   {"SP": 1, "SK": 0, "load_w": 150,  "sk_load_w": 0},
    "office":     {"SP": 4, "SK": 2, "load_w": 150,  "sk_load_w": 1060},
    "storage":    {"SP": 1, "SK": 0, "load_w": 150,  "sk_load_w": 0},
    "other":      {"SP": 1, "SK": 1, "load_w": 150,  "sk_load_w": 150},
}

WALL_OFFSET = 0.15   # sockets placed 150mm from wall (centre of outlet box)
SWITCH_OFFSET = 0.3  # switches placed 300mm from room corner (near door)


def _distribute_along_walls(polygon_coords, n_points, offset):
    """Places n_points evenly spaced around the room perimeter, each
    offset inward by `offset` metres, returning [(x, y), ...]."""
    poly = Polygon(polygon_coords)
    boundary = poly.boundary
    total_len = boundary.length

    if n_points == 0 or total_len == 0:
        return []

    step = total_len / n_points
    points = []
    for i in range(n_points):
        pt_on_wall = boundary.interpolate(step * (i + 0.5))
        centroid = poly.centroid
        dx = centroid.x - pt_on_wall.x
        dy = centroid.y - pt_on_wall.y
        dist = math.hypot(dx, dy)
        if dist < 1e-6:
            points.append((pt_on_wall.x, pt_on_wall.y))
            continue
        nudge_x = pt_on_wall.x + (dx / dist) * offset
        nudge_y = pt_on_wall.y + (dy / dist) * offset
        nudged = Point(nudge_x, nudge_y)
        if poly.contains(nudged):
            points.append((nudge_x, nudge_y))
        else:
            points.append((pt_on_wall.x, pt_on_wall.y))
    return points


def place_sockets_and_switches(room):
    """Given a room dict with 'room_type' and 'polygon' (metres), returns:
      {
        'sockets': [{'x', 'y', 'kind': 'SP'|'SK', 'load_w'}, ...],
        'switches': [{'x', 'y'}, ...],
      }
    """
    spec = SOCKET_SPEC.get(room["room_type"], SOCKET_SPEC["other"])
    polygon_coords = room["polygon"]

    n_sp = spec["SP"]
    n_sk = spec["SK"]
    total_sockets = n_sp + n_sk

    positions = _distribute_along_walls(polygon_coords, total_sockets, WALL_OFFSET)
    sp_positions = positions[:n_sp]
    sk_positions = positions[n_sp:]

    sockets = []
    for x, y in sp_positions:
        sockets.append({"x": x, "y": y, "kind": "SP", "load_w": spec["load_w"]})
    for x, y in sk_positions:
        sockets.append({"x": x, "y": y, "kind": "SK", "load_w": spec["sk_load_w"]})

    # Single switch near the "top-left" corner of the bounding box as a
    # simple door-adjacent heuristic. Real door positions would need to
    # come from the drawing, which isn't reliably available for all inputs.
    poly = Polygon(polygon_coords)
    min_x, min_y, max_x, max_y = poly.bounds
    sw_x = min_x + SWITCH_OFFSET
    sw_y = max_y - SWITCH_OFFSET
    sw_pt = Point(sw_x, sw_y)
    if not poly.contains(sw_pt):
        sw_pt = poly.centroid
    switches = [{"x": sw_pt.x, "y": sw_pt.y}]

    return {"sockets": sockets, "switches": switches}
