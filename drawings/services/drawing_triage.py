"""Classifies an incoming drawing as likely-clean-CAD or likely-messy
before automatic room detection is attempted, so the pipeline can fail
fast and gracefully instead of running polygonize() against tens of
thousands of unrelated entities and either hanging or producing garbage.

This is a heuristic, not a guarantee -- false positives/negatives are
expected. Tune MESSY_ENTITY_COUNT_THRESHOLD and MESSY_LAYER_NAME_HINTS
against real samples of what your users actually upload.
"""

# Layer-name substrings commonly left behind by PDF-to-DXF vectorization
# tools and similar auto-trace workflows.
MESSY_LAYER_NAME_HINTS = ["pdf", "underlay", "image", "raster"]

# A native architectural CAD drawing's wall/structural geometry is
# typically a few hundred to a couple thousand entities. Tens of
# thousands of LINE/LWPOLYLINE entities in modelspace is a strong signal
# of auto-traced/vectorized geometry rather than deliberately drawn walls.
MESSY_ENTITY_COUNT_THRESHOLD = 5000


def classify_drawing(doc):
    """Returns 'clean' or 'messy'."""
    layer_names = [layer.dxf.name.lower() for layer in doc.layers]
    if any(hint in name for name in layer_names for hint in MESSY_LAYER_NAME_HINTS):
        return "messy"

    msp = doc.modelspace()
    line_like_count = len(list(msp.query("LWPOLYLINE"))) + len(list(msp.query("LINE")))
    if line_like_count > MESSY_ENTITY_COUNT_THRESHOLD:
        return "messy"

    return "clean"
