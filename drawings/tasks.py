"""Celery task chain.

Split into two tasks around the human review step:

  parse_and_detect_rooms  -- runs right after upload. Parses the DXF,
                              detects room polygons, classifies room
                              types, and stops at "pending_review".

  calculate_and_place     -- runs after the user confirms/corrects rooms
                              on the review screen. Does the lighting
                              calc, places fixtures, writes the output
                              DXF.
"""
import logging
import os

from celery import shared_task
from django.conf import settings

from shapely.geometry import Point, Polygon as ShapelyPolygon

from .models import Circuit, DistributionBoard, Drawing, Fixture, FixtureType, Room, SmallPowerPoint


def _point_in_polygon(x, y, polygon_coords):
    """Returns True if (x,y) is inside the polygon (in metres)."""
    try:
        return ShapelyPolygon(polygon_coords).contains(Point(x, y))
    except Exception:
        return False
from .services import (
    circuit_grouping,
    db_placement,
    drawing_triage,
    dxf_parser,
    dxf_preview,
    dxf_writer,
    fixture_placement,
    lighting_calc,
    load_schedule,
    report_generator,
    room_classifier,
    room_detection,
    sld_generator,
    small_power,
    standards,
    tagging,
    cable_routing,
)

logger = logging.getLogger(__name__)

# Layer names to look for in the *input* drawing. Adjust to match the
# naming convention your source drawings actually use.
WALL_LAYER_NAMES = ["WALLS", "A-WALL"]
ROOM_BOUNDARY_LAYER_NAMES = ["ROOMS", "A-AREA"]


@shared_task(bind=True)
def parse_and_detect_rooms(self, drawing_id):
    drawing = Drawing.objects.get(pk=drawing_id)
    drawing.status = "detecting_rooms"
    drawing.save(update_fields=["status"])

    scale = getattr(settings, "DRAWING_UNIT_SCALE", 1.0)

    try:
        doc = dxf_parser.load_dxf(drawing.original_file.path)
        closed_polylines = dxf_parser.extract_closed_polylines(
            doc, layer_names=ROOM_BOUNDARY_LAYER_NAMES, scale=scale
        )
        text_labels = dxf_parser.extract_text_labels(doc, scale=scale)

        detected = []

        if closed_polylines:
            # Explicit room boundaries exist (drawn by the user, by a CAD
            # template, or traced manually after a previous "messy" verdict)
            # -- always prefer these regardless of how messy the rest of
            # the drawing is.
            detected = room_detection.rooms_from_closed_polylines(closed_polylines, text_labels)

        elif drawing_triage.classify_drawing(doc) == "clean":
            # Only attempt wall-graph polygonization on drawings that look
            # like genuine CAD line work -- running it against tens of
            # thousands of auto-traced entities is slow and produces
            # garbage, not just "wrong" rooms.
            wall_segments = dxf_parser.extract_wall_lines(doc, layer_names=WALL_LAYER_NAMES, scale=scale)
            detected = room_detection.detect_rooms_from_walls(wall_segments, text_labels)

        if not detected:
            # Not a crash -- this is an expected outcome for inputs we
            # can't auto-process. Stop here and ask for manually traced
            # room boundaries instead of failing with a stack trace.
            drawing.status = "needs_manual_rooms"
            drawing.error_message = (
                "Automatic room detection didn't find usable geometry. "
                "Trace room boundaries directly on the drawing."
            )
            drawing.save(update_fields=["status", "error_message"])
            render_drawing_preview.delay(drawing.pk)
            return

        for room_data in detected:
            room_type = room_classifier.classify_room_type(room_data["label"])
            Room.objects.create(
                drawing=drawing,
                label=room_data["label"],
                room_type=room_type,
                polygon=room_data["polygon"],
                area_sq_m=room_data["area_sq_m"],
                required_lux=standards.get_required_lux(room_type),
            )

        drawing.status = "pending_review"
        drawing.save(update_fields=["status"])

    except Exception as exc:
        logger.exception("Room detection failed for drawing %s", drawing_id)
        drawing.status = "failed"
        drawing.error_message = str(exc)
        drawing.save(update_fields=["status", "error_message"])
        raise


@shared_task(bind=True)
def render_drawing_preview(self, drawing_id):
    """Renders a flat raster preview of the drawing for the in-browser
    tracing UI. Runs as its own task (rather than inline in a view)
    because rendering a large/messy drawing can take a while -- the
    trace_rooms view polls drawing.preview_image until this finishes."""
    drawing = Drawing.objects.get(pk=drawing_id)

    output_dir = os.path.join(settings.MEDIA_ROOT, "previews")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"drawing_{drawing.pk}_preview.png")

    try:
        extents = dxf_preview.render_preview(drawing.original_file.path, output_path)
        drawing.preview_image.name = os.path.relpath(output_path, settings.MEDIA_ROOT)
        drawing.preview_extents = extents
        drawing.save(update_fields=["preview_image", "preview_extents"])
    except Exception:
        logger.exception("Preview rendering failed for drawing %s", drawing_id)
        raise


@shared_task(bind=True)
def calculate_and_place(self, drawing_id):
    from datetime import date
    drawing = Drawing.objects.get(pk=drawing_id)
    drawing.status = "calculating"
    drawing.save(update_fields=["status"])

    scale = getattr(settings, "DRAWING_UNIT_SCALE", 1.0)

    try:
        default_fixture = FixtureType.objects.first()
        if default_fixture is None:
            raise RuntimeError(
                "No FixtureType configured -- add one via /admin/drawings/fixturetype/ first."
            )

        # ── Step 1: lighting calc + placement ─────────────────────────
        rooms_data = []
        all_fixtures_m = []     # all fixture positions in metres, with tags reserved

        for room in drawing.rooms.filter(confirmed=True):
            xs = [p[0] for p in room.polygon]
            ys = [p[1] for p in room.polygon]
            length_m = max(xs) - min(xs)
            width_m  = max(ys) - min(ys)

            result = lighting_calc.calculate_fixture_count(
                area_sq_m=room.area_sq_m,
                required_lux=room.required_lux or standards.get_required_lux(room.room_type),
                fixture_lumens=default_fixture.luminous_flux_lm,
                length_m=length_m,
                width_m=width_m,
                mounting_height_m=room.mounting_height_m,
            )

            positions_m = fixture_placement.compute_grid_layout(result.n_fixtures, room.polygon)
            for x, y in positions_m:
                all_fixtures_m.append({"x": x, "y": y, "room_id": room.pk, "load_w": 120})

            fixture_watts = getattr(default_fixture, "wattage_w", 120)
            rooms_data.append({
                "label": room.label,
                "room_type": room.room_type,
                "area_sq_m": room.area_sq_m,
                "required_lux": room.required_lux,
                "fixture_lumens": default_fixture.luminous_flux_lm,
                "fixture_watts": fixture_watts,
                "calc": {
                    "n_fixtures": result.n_fixtures,
                    "room_index": result.room_index,
                    "utilization_factor": result.utilization_factor,
                },
                "polygon": room.polygon,
                "positions_m": positions_m,
                "room": room,
            })

        # ── Step 2: small power placement ─────────────────────────────
        # One switch per room, placed near the top-left corner (door-adjacent
        # heuristic). Switches are tracked with their room reference so they
        # can be assigned the same circuit/phase as that room's lights.
        all_sockets_m  = []
        all_switches_m = []
        room_to_switches = {}   # room.pk → [switch_dict, ...]

        for room in drawing.rooms.filter(confirmed=True):
            room_dict = {"room_type": room.room_type, "polygon": room.polygon}
            sp_result = small_power.place_sockets_and_switches(room_dict)
            all_sockets_m.extend(sp_result["sockets"])
            for sw in sp_result["switches"]:
                sw["_room_pk"] = room.pk   # track which room this switch belongs to
            all_switches_m.extend(sp_result["switches"])
            room_to_switches[room.pk] = sp_result["switches"]

        # ── Step 3: circuit grouping + phase balancing ─────────────────
        grouped_lp, grouped_sp_sk, circuit_summary = circuit_grouping.assign_circuits(
            all_fixtures_m, all_sockets_m
        )

        # ── Step 4: tagging ───────────────────────────────────────────
        tagging.assign_tags(grouped_lp, grouped_sp_sk, all_switches_m, floor=0)

        # After tagging, give each switch the same circuit/phase as its
        # room's lighting fixtures so the switch tag matches the light circuit.
        # e.g. if Bedroom 1 lights are LP-R1-01..03, the switch becomes SW-R1-01
        room_pk_to_circuit = {}
        for f in grouped_lp:
            rpk = f.get("room_id")
            if rpk and rpk not in room_pk_to_circuit:
                room_pk_to_circuit[rpk] = (f.get("circuit_no", 1), f.get("phase", "R"))

        sw_room_seq = {}
        for sw in all_switches_m:
            rpk = sw.get("_room_pk")
            if rpk and rpk in room_pk_to_circuit:
                cno, phase = room_pk_to_circuit[rpk]
                key = (cno, phase)
                sw_room_seq[key] = sw_room_seq.get(key, 0) + 1
                sw["tag"] = tagging.tag_switch(phase, cno, sw_room_seq[key])
                sw["circuit_no"] = cno
                sw["phase"] = phase

        # ── Step 5: DB placement ──────────────────────────────────────
        confirmed_rooms = list(drawing.rooms.filter(confirmed=True).values(
            "polygon", "room_type", "label"
        ))
        db_x_m, db_y_m = db_placement.find_db_location(
            confirmed_rooms, grouped_lp, grouped_sp_sk
        )
        db_x_native = db_x_m / scale
        db_y_native = db_y_m / scale

        # ── Step 6: cable routing (worst-case run per circuit) ─────────
        cable_routing.route_from_db(grouped_lp, db_x_m, db_y_m)
        cable_routing.route_from_db(grouped_sp_sk, db_x_m, db_y_m)

        # ── Step 7: load schedule + cable sizing ───────────────────────
        schedule = load_schedule.build_schedule(circuit_summary, db_x_m, db_y_m)

        # ── Step 8: persist to DB ──────────────────────────────────────
        # Build a quick (x,y) → tag lookup from the tagged grouped_lp list
        fixture_tag_lookup = {
            (round(f["x"], 6), round(f["y"], 6)): f.get("tag", "")
            for f in grouped_lp
        }

        # Fixtures
        for room_data in rooms_data:
            room = room_data["room"]
            for x, y in room_data["positions_m"]:
                tag = fixture_tag_lookup.get((round(x, 6), round(y, 6)), "")
                Fixture.objects.create(
                    room=room, fixture_type=default_fixture,
                    x=x, y=y, tag=tag,
                )

        # Circuits
        for cct_row in schedule["circuits"]:
            Circuit.objects.create(
                drawing=drawing,
                cct_label=cct_row["cct_label"],
                cct_type=cct_row["type"],
                phase=cct_row["phase"],
                n_points=cct_row["n_points"],
                total_load_w=cct_row.get("connected_load_r", 0) or
                             cct_row.get("connected_load_y", 0) or
                             cct_row.get("connected_load_b", 0) or 0,
                cable_csa_mm2=cct_row["cable_csa_mm2"],
                mcb_rating_a=cct_row["mcb_rating_a"],
                voltage_drop_v=cct_row.get("voltage_drop_v", 0),
            )

        # Small power
        for s in grouped_sp_sk:
            SmallPowerPoint.objects.create(
                drawing=drawing,
                tag=s.get("tag", ""),
                kind=s.get("kind", "SP"),
                x=s["x"],
                y=s["y"],
                circuit_no=s.get("circuit_no", 0),
                phase=s.get("phase", ""),
                load_w=s.get("load_w", 150),
            )
        for sw in all_switches_m:
            SmallPowerPoint.objects.create(
                drawing=drawing,
                tag=sw.get("tag", ""),
                kind="SW",
                x=sw["x"],
                y=sw["y"],
                circuit_no=sw.get("circuit_no", 0),
                phase=sw.get("phase", ""),
                load_w=0,
            )

        # ── Step 9: output files ───────────────────────────────────────
        output_dir  = os.path.join(settings.MEDIA_ROOT, "outputs")
        sld_dir     = os.path.join(settings.MEDIA_ROOT, "outputs", "sld")
        report_dir  = os.path.join(settings.MEDIA_ROOT, "outputs", "reports")
        for d in (output_dir, sld_dir, report_dir):
            os.makedirs(d, exist_ok=True)

        # Build rooms_wiring: per room → fixture positions + that room's switch
        # This drives the arc wiring in the DXF (switch → fixtures → each other)
        rooms_wiring = []
        for room_data in rooms_data:
            room     = room_data["room"]
            sw_list  = room_to_switches.get(room.pk, [])
            sw_pos   = (sw_list[0]["x"], sw_list[0]["y"]) if sw_list else None
            rooms_wiring.append({
                "fixtures": room_data["positions_m"],
                "switch":   sw_pos,
            })

        # Main DXF with all design layers
        dxf_path = os.path.join(output_dir, f"drawing_{drawing.pk}_full_design.dxf")

        # Build circuit-grouped fixture list for the new writer
        from collections import defaultdict
        lp_by_circuit = defaultdict(list)
        for f in grouped_lp:
            lp_by_circuit[f["circuit_no"]].append(f)

        sp_by_circuit = defaultdict(list)
        for s in grouped_sp_sk:
            sp_by_circuit[s["circuit_no"]].append(s)

        grouped_fixtures_for_writer = [
            {"circuit_no": cno, "phase": items[0]["phase"], "items": items}
            for cno, items in lp_by_circuit.items()
        ]
        grouped_sockets_for_writer = [
            {"circuit_no": cno, "phase": items[0]["phase"], "items": items}
            for cno, items in sp_by_circuit.items()
        ]

        dxf_writer.write_full_design(
            input_path=drawing.original_file.path,
            output_path=dxf_path,
            grouped_fixtures=grouped_fixtures_for_writer,
            grouped_sockets=grouped_sockets_for_writer,
            switches=all_switches_m,
            rooms_wiring=rooms_wiring,
            db_x_native=db_x_native,
            db_y_native=db_y_native,
            scale=scale,
            project_info={
                "project_name":  "DUPLEX",
                "floor_label":   "Ground Floor",
                "title":         "LIGHTING AND POWER DESIGN",
                "prepared_by":   "OJUGBELI DIVINE",
                "approved_by":   "MR. GOODNEWS EBUBE",
                "contract_no":   "8607000061",
                "item":          "10100-30100",
                "sheet_no":      "006",
                "total_sheets":  "007",
            },
        )
        drawing.output_file.name = os.path.relpath(dxf_path, settings.MEDIA_ROOT)

        # SLD
        sld_path = os.path.join(sld_dir, f"drawing_{drawing.pk}_sld.dxf")
        sld_generator.generate_sld(sld_path, schedule, project_name="DUPLEX")

        # Report PDF
        report_path = os.path.join(report_dir, f"drawing_{drawing.pk}_report.pdf")
        report_generator.generate_report(
            output_path=report_path,
            project_info={
                "project_name": "Duplex",
                "client": "—",
                "prepared_by": "AutoDesign",
                "date": date.today().isoformat(),
            },
            rooms_data=rooms_data,
            schedule=schedule,
            fixture_type_name=default_fixture.name,
            db_x=db_x_m,
            db_y=db_y_m,
        )

        # Persist DB object
        db_obj = DistributionBoard.objects.create(
            drawing=drawing,
            label="DB",
            x=db_x_m,
            y=db_y_m,
            incomer_mcb_a=schedule["incomer_mcb_a"],
            incoming_cable_csa_mm2=schedule["incoming_cable_csa_mm2"],
            schedule_data=schedule,
        )
        db_obj.sld_file.name = os.path.relpath(sld_path, settings.MEDIA_ROOT)
        db_obj.report_file.name = os.path.relpath(report_path, settings.MEDIA_ROOT)
        db_obj.save()

        drawing.status = "done"
        drawing.save(update_fields=["output_file", "status"])

    except Exception as exc:
        logger.exception("Lighting calculation failed for drawing %s", drawing_id)
        drawing.status = "failed"
        drawing.error_message = str(exc)
        drawing.save(update_fields=["status", "error_message"])
        raise


@shared_task(bind=True)
def atlas_regenerate(self, drawing_id):
    """Triggered by ATLAS after a tool_use modifies design parameters."""
    from .services.design_modifier import apply_overrides_and_regenerate
    messages = []
    def _p(msg):
        messages.append(msg)
        self.update_state(state="PROGRESS", meta={"status": msg, "log": messages})
    result = apply_overrides_and_regenerate(drawing_id, progress=_p)
    return {"status": "done", "summary": result, "log": messages}
