"""Pure-Python DXF reading helpers. No Django imports here -- this module
should be testable with nothing but a DXF file on disk.

`scale` converts raw DXF coordinates into metres. Architectural DXFs are
very often drawn in millimetres, so the caller (drawings/tasks.py) passes
settings.DRAWING_UNIT_SCALE through here rather than this module reaching
into Django settings itself.
"""
import ezdxf


def load_dxf(filepath):
    return ezdxf.readfile(filepath)


def extract_wall_lines(doc, layer_names=None, scale=1.0):
    """Return wall segments as a list of ((x1, y1), (x2, y2)) tuples,
    pulled from LINE entities and the segments of LWPOLYLINE entities,
    optionally filtered to specific layer names (case-insensitive)."""
    msp = doc.modelspace()
    layer_filter = {name.lower() for name in layer_names} if layer_names else None
    segments = []

    for entity in msp.query("LINE"):
        if layer_filter and entity.dxf.layer.lower() not in layer_filter:
            continue
        start = (entity.dxf.start.x * scale, entity.dxf.start.y * scale)
        end = (entity.dxf.end.x * scale, entity.dxf.end.y * scale)
        segments.append((start, end))

    for entity in msp.query("LWPOLYLINE"):
        if layer_filter and entity.dxf.layer.lower() not in layer_filter:
            continue
        points = [(p[0] * scale, p[1] * scale) for p in entity.get_points()]
        if entity.closed and len(points) > 1:
            points.append(points[0])
        for a, b in zip(points, points[1:]):
            segments.append((a, b))

    return segments


def extract_closed_polylines(doc, layer_names=None, scale=1.0):
    """Return polygons from LWPOLYLINE entities that are already
    explicitly closed -- the easy case, where the architect drew room
    boundaries directly rather than relying on wall geometry."""
    msp = doc.modelspace()
    layer_filter = {name.lower() for name in layer_names} if layer_names else None
    polygons = []

    for entity in msp.query("LWPOLYLINE"):
        if not entity.closed:
            continue
        if layer_filter and entity.dxf.layer.lower() not in layer_filter:
            continue
        points = [(p[0] * scale, p[1] * scale) for p in entity.get_points()]
        if len(points) >= 3:
            polygons.append(points)

    return polygons


def extract_text_labels(doc, scale=1.0):
    """Return [(text, x, y), ...] from TEXT and MTEXT entities."""
    msp = doc.modelspace()
    labels = []

    for entity in msp.query("TEXT"):
        pos = entity.dxf.insert
        labels.append((entity.dxf.text, pos.x * scale, pos.y * scale))

    for entity in msp.query("MTEXT"):
        pos = entity.dxf.insert
        labels.append((entity.plain_text(), pos.x * scale, pos.y * scale))

    return labels
