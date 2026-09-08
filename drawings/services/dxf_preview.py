"""Renders a DXF to a flat raster preview for the in-browser room-tracing
UI, and reports the world-coordinate extents the render covers so the
frontend can map click coordinates back into drawing space.

No Django imports -- takes/returns plain values, same convention as the
other services modules.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import ezdxf
from ezdxf import bbox
from ezdxf.addons.drawing import Frontend, RenderContext
from ezdxf.addons.drawing.matplotlib import MatplotlibBackend


def render_preview(dxf_path, output_png_path, max_dimension_px=1600):
    """Renders dxf_path to output_png_path and returns the extents dict
    needed to convert pixel coordinates on that image back to the
    drawing's native (unscaled) world coordinates:

        {"xmin", "xmax", "ymin", "ymax", "width_px", "height_px"}
    """
    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()

    box = bbox.extents(msp, fast=True)
    xmin, ymin, _ = box.extmin
    xmax, ymax, _ = box.extmax

    width = xmax - xmin
    height = ymax - ymin
    if width <= 0 or height <= 0:
        raise ValueError("Drawing has no measurable extents to render")

    aspect = width / height
    if aspect >= 1:
        fig_w_px = max_dimension_px
        fig_h_px = max_dimension_px / aspect
    else:
        fig_h_px = max_dimension_px
        fig_w_px = max_dimension_px * aspect

    dpi = 100
    fig = plt.figure(figsize=(fig_w_px / dpi, fig_h_px / dpi), dpi=dpi)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.margins(0)
    ax.set_xlim(xmin, xmax)
    ax.set_ylim(ymin, ymax)
    ax.set_aspect("equal")
    ax.axis("off")

    Frontend(RenderContext(doc), MatplotlibBackend(ax)).draw_layout(msp, finalize=True)

    fig.savefig(output_png_path, dpi=dpi)
    plt.close(fig)

    return {
        "xmin": xmin,
        "xmax": xmax,
        "ymin": ymin,
        "ymax": ymax,
        "width_px": int(round(fig_w_px)),
        "height_px": int(round(fig_h_px)),
    }


def pixel_to_world(px, py, extents):
    """Inverse of the mapping render_preview implicitly defines: image
    pixel (origin top-left, y down) -> drawing world coordinate (origin
    matches the DXF, y up)."""
    x = extents["xmin"] + (px / extents["width_px"]) * (extents["xmax"] - extents["xmin"])
    y = extents["ymax"] - (py / extents["height_px"]) * (extents["ymax"] - extents["ymin"])
    return x, y
