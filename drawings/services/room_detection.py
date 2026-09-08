"""Reconstructs room polygons either from explicit closed polylines (the
easy case) or, more often, from a tangle of wall LINE/LWPOLYLINE segments
that don't form closed shapes on their own.

This is the part of the pipeline most likely to need tuning against your
actual drawings -- real CAD files have small gaps, overshoots, and
duplicate lines that break clean polygonization. snap_tolerance is your
main knob for that.
"""
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import polygonize, snap, unary_union


def _snap_segments(segments, tolerance):
    """Snap nearby endpoints together so small gaps don't break polygonization."""
    lines = [
        LineString(seg) for seg in segments
        if Point(seg[0]).distance(Point(seg[1])) > 1e-6
    ]
    if not lines:
        return []

    merged = unary_union(lines)
    snapped = snap(merged, merged, tolerance)
    return list(snapped.geoms) if hasattr(snapped, "geoms") else [snapped]


def _nearest_label(face, text_labels):
    for text, x, y in text_labels:
        if face.contains(Point(x, y)):
            return text.strip()
    return ""


def detect_rooms_from_walls(wall_segments, text_labels, snap_tolerance=0.05, min_area=1.0):
    """Polygonize a wall-line network into room polygons and attach the
    nearest enclosed text label as the room name.

    snap_tolerance and min_area are in metres (assuming the caller already
    scaled coordinates via DRAWING_UNIT_SCALE) -- defaults assume a 5cm
    snap tolerance and a 1 sq m minimum room size to filter out sliver
    polygons from imperfect geometry.
    """
    lines = _snap_segments(wall_segments, snap_tolerance)
    if not lines:
        return []

    faces = list(polygonize(lines))
    rooms = []

    for face in faces:
        if not face.is_valid or face.area < min_area:
            continue
        rooms.append({
            "polygon": list(face.exterior.coords),
            "area_sq_m": face.area,
            "label": _nearest_label(face, text_labels),
        })

    return rooms


def rooms_from_closed_polylines(polygons, text_labels):
    """Use explicit closed polylines as rooms directly."""
    rooms = []
    for points in polygons:
        face = Polygon(points)
        if not face.is_valid or face.area <= 0:
            continue
        rooms.append({
            "polygon": list(face.exterior.coords),
            "area_sq_m": face.area,
            "label": _nearest_label(face, text_labels),
        })
    return rooms


def detect_rooms(wall_segments, closed_polylines, text_labels, snap_tolerance=0.05):
    """Entry point: prefer explicit closed polylines (e.g. on a ROOMS
    layer), fall back to wall-graph polygonization if none are found."""
    if closed_polylines:
        return rooms_from_closed_polylines(closed_polylines, text_labels)
    return detect_rooms_from_walls(wall_segments, text_labels, snap_tolerance=snap_tolerance)
