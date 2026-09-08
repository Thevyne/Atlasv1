"""Applies user-requested design overrides and regenerates all outputs.
Called by the ATLAS Celery task after a tool_use modifies parameters.
"""
import logging
import os
from datetime import date
from collections import defaultdict

logger = logging.getLogger(__name__)


def get_design_summary(drawing):
    """Structured dict of the current design — injected into ATLAS system prompt."""
    from drawings.models import FixtureType
    rooms_info = []
    for room in drawing.rooms.filter(confirmed=True):
        override = None
        try:
            override = room.override
        except Exception:
            pass
        fixtures = list(room.fixtures.all())
        rooms_info.append({
            "id":               room.pk,
            "label":            room.label or f"Room {room.pk}",
            "room_type":        room.room_type,
            "area_sq_m":        round(room.area_sq_m, 2),
            "required_lux":     room.required_lux,
            "mounting_height_m":room.mounting_height_m,
            "n_fixtures":       len(fixtures),
            "fixture_tags":     [f.tag for f in fixtures],
            "override_fixtures":override.n_fixtures if override else None,
            "override_lux":     override.required_lux if override else None,
            "notes":            override.notes if override else "",
        })
    fixture_types = [
        {"id": ft.pk, "name": ft.name,
         "lumens": ft.luminous_flux_lm, "watts": ft.wattage_w}
        for ft in FixtureType.objects.all()
    ]
    db = drawing.distribution_boards.first()
    return {
        "drawing_id":    drawing.pk,
        "status":        drawing.status,
        "rooms":         rooms_info,
        "fixture_types": fixture_types,
        "db_summary":    {
            "incomer_mcb_a":          db.incomer_mcb_a if db else None,
            "incoming_cable_csa_mm2": db.incoming_cable_csa_mm2 if db else None,
            "total_w": (db.schedule_data or {}).get("total_w") if db else None,
        } if db else None,
    }


def apply_overrides_and_regenerate(drawing_id, progress=None):
    """Full recalc with all active RoomOverrides, then regenerates DXF/SLD/PDF."""
    from django.conf import settings
    from drawings.models import (Circuit, DistributionBoard, Drawing, Fixture,
                         FixtureType, SmallPowerPoint)
    from drawings.services import (circuit_grouping, db_placement, dxf_writer,
                           fixture_placement, lighting_calc, load_schedule,
                           report_generator, sld_generator, small_power,
                           standards, tagging, cable_routing)

    def _p(msg):
        if progress:
            progress(msg)
        logger.info("ATLAS [%s]: %s", drawing_id, msg)

    drawing = Drawing.objects.get(pk=drawing_id)
    drawing.status = "calculating"
    drawing.save(update_fields=["status"])
    scale = getattr(settings, "DRAWING_UNIT_SCALE", 0.001)

    try:
        _p("Clearing previous design")
        Fixture.objects.filter(room__drawing=drawing).delete()
        Circuit.objects.filter(drawing=drawing).delete()
        SmallPowerPoint.objects.filter(drawing=drawing).delete()
        DistributionBoard.objects.filter(drawing=drawing).delete()

        default_fixture = FixtureType.objects.first()
        if not default_fixture:
            raise RuntimeError("No FixtureType in admin.")

        all_fixtures_m, rooms_data = [], []

        for room in drawing.rooms.filter(confirmed=True):
            override = None
            try:
                override = room.override
            except Exception:
                pass

            xs, ys = [p[0] for p in room.polygon], [p[1] for p in room.polygon]
            length_m, width_m = max(xs)-min(xs), max(ys)-min(ys)

            req_lux = (override.required_lux if override and override.required_lux
                       else room.required_lux or standards.get_required_lux(room.room_type))
            ft_id = override.fixture_type_id if override and override.fixture_type_id else None
            ft = FixtureType.objects.filter(pk=ft_id).first() or default_fixture

            if override and override.n_fixtures is not None:
                n_fixtures = override.n_fixtures
                ri  = lighting_calc.room_index(length_m, width_m, room.mounting_height_m)
                uf  = lighting_calc.utilization_factor(ri)
                calc_result = lighting_calc.LightingResult(
                    n_fixtures=n_fixtures, room_index=ri,
                    utilization_factor=uf, required_lux=req_lux)
                achieved = round((n_fixtures * ft.luminous_flux_lm * uf * 0.8)
                                 / max(room.area_sq_m, 0.01), 1)
                _p(f"  {room.label}: override → {n_fixtures} fixtures (achieves {achieved} lux)")
            else:
                calc_result = lighting_calc.calculate_fixture_count(
                    area_sq_m=room.area_sq_m, required_lux=req_lux,
                    fixture_lumens=ft.luminous_flux_lm,
                    length_m=length_m, width_m=width_m,
                    mounting_height_m=room.mounting_height_m)
                n_fixtures = calc_result.n_fixtures
                achieved = None
                _p(f"  {room.label}: calculated → {n_fixtures} fixtures @ {req_lux} lux")

            positions_m = fixture_placement.compute_grid_layout(n_fixtures, room.polygon)
            for x, y in positions_m:
                all_fixtures_m.append({"x": x, "y": y, "room_id": room.pk,
                                       "load_w": ft.wattage_w})
            rooms_data.append({
                "label": room.label, "room_type": room.room_type,
                "area_sq_m": room.area_sq_m, "required_lux": req_lux,
                "fixture_lumens": ft.luminous_flux_lm, "fixture_watts": ft.wattage_w,
                "calc": {"n_fixtures": calc_result.n_fixtures,
                         "room_index": calc_result.room_index,
                         "utilization_factor": calc_result.utilization_factor},
                "positions_m": positions_m, "room": room,
                "fixture_type": ft, "achieved_lux": achieved,
            })

        _p("Placing sockets and switches")
        all_sockets_m, all_switches_m, room_to_switches = [], [], {}
        for room in drawing.rooms.filter(confirmed=True):
            sp = small_power.place_sockets_and_switches(
                {"room_type": room.room_type, "polygon": room.polygon})
            all_sockets_m.extend(sp["sockets"])
            for sw in sp["switches"]:
                sw["_room_pk"] = room.pk
            all_switches_m.extend(sp["switches"])
            room_to_switches[room.pk] = sp["switches"]

        _p("Grouping circuits and tagging")
        grouped_lp, grouped_sp_sk, circuit_summary = circuit_grouping.assign_circuits(
            all_fixtures_m, all_sockets_m)
        tagging.assign_tags(grouped_lp, grouped_sp_sk, all_switches_m, floor=0)

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

        _p("Load schedule and cable sizing")
        confirmed_rooms = list(drawing.rooms.filter(confirmed=True).values(
            "polygon", "room_type", "label"))
        db_x_m, db_y_m = db_placement.find_db_location(
            confirmed_rooms, grouped_lp, grouped_sp_sk)
        db_x_native, db_y_native = db_x_m / scale, db_y_m / scale
        cable_routing.route_from_db(grouped_lp,    db_x_m, db_y_m)
        cable_routing.route_from_db(grouped_sp_sk, db_x_m, db_y_m)
        schedule = load_schedule.build_schedule(circuit_summary, db_x_m, db_y_m)

        _p("Saving to database")
        tag_lookup = {(round(f["x"],6), round(f["y"],6)): f.get("tag","")
                      for f in grouped_lp}
        for rd in rooms_data:
            room, ft = rd["room"], rd["fixture_type"]
            for x, y in rd["positions_m"]:
                Fixture.objects.create(
                    room=room, fixture_type=ft, x=x, y=y,
                    tag=tag_lookup.get((round(x,6), round(y,6)), ""))

        for row in schedule["circuits"]:
            Circuit.objects.create(
                drawing=drawing, cct_label=row["cct_label"],
                cct_type=row["type"], phase=row["phase"],
                n_points=row["n_points"],
                total_load_w=(row.get("connected_load_r") or
                              row.get("connected_load_y") or
                              row.get("connected_load_b") or 0),
                cable_csa_mm2=row["cable_csa_mm2"],
                mcb_rating_a=row["mcb_rating_a"],
                voltage_drop_v=row.get("voltage_drop_v", 0))

        for s in grouped_sp_sk:
            SmallPowerPoint.objects.create(
                drawing=drawing, tag=s.get("tag",""), kind=s.get("kind","SP"),
                x=s["x"], y=s["y"], circuit_no=s.get("circuit_no",0),
                phase=s.get("phase",""), load_w=s.get("load_w",150))
        for sw in all_switches_m:
            SmallPowerPoint.objects.create(
                drawing=drawing, tag=sw.get("tag",""), kind="SW",
                x=sw["x"], y=sw["y"], circuit_no=sw.get("circuit_no",0),
                phase=sw.get("phase",""), load_w=0)

        _p("Writing output files")
        output_dir = os.path.join(settings.MEDIA_ROOT, "outputs")
        sld_dir    = os.path.join(settings.MEDIA_ROOT, "outputs", "sld")
        rep_dir    = os.path.join(settings.MEDIA_ROOT, "outputs", "reports")
        for d in (output_dir, sld_dir, rep_dir):
            os.makedirs(d, exist_ok=True)

        lp_by_cct = defaultdict(list)
        sp_by_cct = defaultdict(list)
        for f in grouped_lp:  lp_by_cct[f["circuit_no"]].append(f)
        for s in grouped_sp_sk: sp_by_cct[s["circuit_no"]].append(s)

        gf = [{"circuit_no": c, "phase": items[0]["phase"], "items": items}
              for c, items in lp_by_cct.items()]
        gs = [{"circuit_no": c, "phase": items[0]["phase"], "items": items}
              for c, items in sp_by_cct.items()]
        rw = [{"fixtures": rd["positions_m"],
               "switch": (room_to_switches[rd["room"].pk][0]["x"],
                          room_to_switches[rd["room"].pk][0]["y"])
               if room_to_switches.get(rd["room"].pk) else None}
              for rd in rooms_data]

        dxf_path = os.path.join(output_dir, f"drawing_{drawing.pk}_full_design.dxf")
        dxf_writer.write_full_design(
            input_path=drawing.original_file.path, output_path=dxf_path,
            grouped_fixtures=gf, grouped_sockets=gs,
            switches=all_switches_m, rooms_wiring=rw,
            db_x_native=db_x_native, db_y_native=db_y_native, scale=scale,
            project_info={
                "project_name":"DUPLEX","floor_label":"Ground Floor",
                "title":"LIGHTING AND POWER DESIGN",
                "prepared_by":"OJUGBELI DIVINE","approved_by":"MR. GOODNEWS EBUBE",
                "contract_no":"8607000061","item":"10100-30100",
                "sheet_no":"006","total_sheets":"007"})
        drawing.output_file.name = os.path.relpath(dxf_path, settings.MEDIA_ROOT)

        sld_path = os.path.join(sld_dir, f"drawing_{drawing.pk}_sld.dxf")
        sld_generator.generate_sld(sld_path, schedule, project_name="DUPLEX")

        report_path = os.path.join(rep_dir, f"drawing_{drawing.pk}_report.pdf")
        report_generator.generate_report(
            output_path=report_path,
            project_info={"project_name":"Duplex","client":"—",
                          "prepared_by":"AutoDesign","date":date.today().isoformat()},
            rooms_data=rooms_data, schedule=schedule,
            fixture_type_name=default_fixture.name,
            db_x=db_x_m, db_y=db_y_m)

        db_obj = DistributionBoard.objects.create(
            drawing=drawing, label="DB", x=db_x_m, y=db_y_m,
            incomer_mcb_a=schedule["incomer_mcb_a"],
            incoming_cable_csa_mm2=schedule["incoming_cable_csa_mm2"],
            schedule_data=schedule)
        db_obj.sld_file.name    = os.path.relpath(sld_path,    settings.MEDIA_ROOT)
        db_obj.report_file.name = os.path.relpath(report_path, settings.MEDIA_ROOT)
        db_obj.save()

        drawing.status = "done"
        drawing.save(update_fields=["output_file", "status"])
        _p("Done")
        return get_design_summary(drawing)

    except Exception as exc:
        logger.exception("ATLAS regeneration failed for drawing %s", drawing_id)
        drawing.status = "failed"
        drawing.error_message = str(exc)
        drawing.save(update_fields=["status", "error_message"])
        raise
