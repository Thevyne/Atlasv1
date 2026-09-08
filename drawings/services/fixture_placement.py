"""Grid-based fixture placement within a room polygon."""
import math

from shapely.geometry import Point, Polygon


def _best_grid(n_fixtures, length, width):
    """Pick rows x cols closest to n_fixtures that roughly matches the
    room's aspect ratio, so spacing stays even in both directions."""
    best = (1, n_fixtures)
    best_score = float("inf")

    for rows in range(1, n_fixtures + 1):
        cols = math.ceil(n_fixtures / rows)
        if rows * cols < n_fixtures:
            continue

        row_spacing = width / rows
        col_spacing = length / cols
        score = abs(row_spacing - col_spacing) + 0.01 * (rows * cols - n_fixtures)

        if score < best_score:
            best_score = score
            best = (rows, cols)

    return best


def compute_grid_layout(n_fixtures, polygon_coords):
    """Returns a list of (x, y) fixture positions inside the polygon, in
    the same units/frame as polygon_coords (metres, if you're following
    the rest of this pipeline).

    Builds an even grid over the room's bounding box, then keeps only the
    points that actually fall inside the polygon -- important for
    L-shaped or otherwise non-rectangular rooms, where a plain bounding-
    box grid would place fixtures outside the actual floor area.
    """
    polygon = Polygon(polygon_coords)
    min_x, min_y, max_x, max_y = polygon.bounds
    length = max_x - min_x
    width = max_y - min_y

    if length <= 0 or width <= 0 or n_fixtures <= 0:
        return []

    rows, cols = _best_grid(n_fixtures, length, width)
    cell_w = length / cols
    cell_h = width / rows

    candidates = []
    for row in range(rows):
        for col in range(cols):
            x = min_x + cell_w * (col + 0.5)
            y = min_y + cell_h * (row + 0.5)
            candidates.append((x, y))

    inside = [pt for pt in candidates if polygon.contains(Point(pt))]

    # Non-rectangular rooms can clip away more grid points than we can
    # afford to lose. Nudge a few of the clipped candidates toward the
    # centroid as a simple fallback, rather than quietly under-lighting
    # the room.
    shortfall = n_fixtures - len(inside)
    if shortfall > 0:
        centroid = polygon.centroid
        for pt in candidates:
            if shortfall <= 0:
                break
            if pt in inside:
                continue
            nudged = (
                pt[0] + (centroid.x - pt[0]) * 0.3,
                pt[1] + (centroid.y - pt[1]) * 0.3,
            )
            if polygon.contains(Point(nudged)):
                inside.append(nudged)
                shortfall -= 1

    return inside[:n_fixtures] if len(inside) > n_fixtures else inside
