"""Generates a professional PDF design and building report containing:
  - Project information
  - Room-by-room lighting calculations (lumen method workings)
  - Fixture schedule (type, quantity per room, lux achieved)
  - DB schedule (reproduced from load_schedule output)
  - Cable selection summary
  - Design basis and standards referenced
"""
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
)

PAGE_W, PAGE_H = A4
MARGIN = 20 * mm

STYLES = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=STYLES["Heading1"], fontSize=14, spaceAfter=6)
H2 = ParagraphStyle("H2", parent=STYLES["Heading2"], fontSize=11, spaceAfter=4)
BODY = ParagraphStyle("BODY", parent=STYLES["Normal"], fontSize=9, spaceAfter=3)
SMALL = ParagraphStyle("SMALL", parent=STYLES["Normal"], fontSize=8, spaceAfter=2)

TBL_HEADER = colors.HexColor("#1a3a5c")
TBL_ALT = colors.HexColor("#eef2f7")
TBL_GRID = colors.HexColor("#bbbbbb")


def _table_style(has_header=True):
    cmds = [
        ("GRID", (0, 0), (-1, -1), 0.4, TBL_GRID),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, TBL_ALT]),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    if has_header:
        cmds += [
            ("BACKGROUND", (0, 0), (-1, 0), TBL_HEADER),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ]
    return TableStyle(cmds)


def generate_report(output_path, project_info, rooms_data, schedule,
                    fixture_type_name, db_x, db_y):
    """
    project_info:  dict with 'project_name', 'client', 'prepared_by', 'date'
    rooms_data:    list of room dicts with lighting calc results
    schedule:      output of load_schedule.build_schedule
    fixture_type_name: str name of the fixture type used
    db_x, db_y:   DB position in metres
    """
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=MARGIN,
    )
    story = []

    # ---- Cover header ----
    story.append(Paragraph("LIGHTING & SMALL POWER DESIGN REPORT", H1))
    story.append(HRFlowable(width="100%", thickness=1.5, color=TBL_HEADER))
    story.append(Spacer(1, 4 * mm))

    info_rows = [
        ["Project", project_info.get("project_name", "—")],
        ["Client", project_info.get("client", "—")],
        ["Prepared by", project_info.get("prepared_by", "—")],
        ["Date", project_info.get("date", "—")],
        ["Standard", "BS7671 / EN 12464-1"],
        ["Supply", "230V, 50Hz, 3-phase"],
    ]
    info_tbl = Table(info_rows, colWidths=[45 * mm, 110 * mm])
    info_tbl.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, TBL_ALT]),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(info_tbl)
    story.append(Spacer(1, 8 * mm))

    # ---- 1. Lighting calculations ----
    story.append(Paragraph("1. Lighting Design Calculations", H1))
    story.append(Paragraph(
        "Fixture layout and counts determined by the Lumen (Zonal Cavity) method: "
        "<b>N = (E × A) / (F × UF × MF)</b>  where E = required illuminance (lux), "
        "A = room area (m²), F = fixture flux (lm), UF = utilisation factor, MF = 0.80.",
        BODY,
    ))
    story.append(Spacer(1, 4 * mm))

    calc_header = [
        "Room", "Type", "Area\n(m²)", "Req'd\nLux",
        "Room\nIndex", "UF", "Fixture\nFlux (lm)",
        "N\nFixtures", "Achieved\nLux",
    ]
    calc_rows = [calc_header]
    for r in rooms_data:
        calc = r.get("calc", {})
        achieved = "—"
        if calc.get("n_fixtures") and r.get("fixture_lumens"):
            achieved = round(
                (calc["n_fixtures"] * r["fixture_lumens"] * calc.get("utilization_factor", 0.6) * 0.8)
                / max(r["area_sq_m"], 0.01), 1
            )
        calc_rows.append([
            r.get("label") or "Room",
            r.get("room_type", "—"),
            f"{r['area_sq_m']:.1f}",
            f"{r.get('required_lux', '—')}",
            f"{calc.get('room_index', 0):.2f}",
            f"{calc.get('utilization_factor', 0):.2f}",
            f"{r.get('fixture_lumens', '—')}",
            str(calc.get("n_fixtures", "—")),
            str(achieved),
        ])
    col_w = [30, 22, 14, 14, 14, 10, 22, 14, 18]
    tbl = Table(calc_rows, colWidths=[w * mm for w in col_w])
    tbl.setStyle(_table_style())
    story.append(tbl)
    story.append(Spacer(1, 8 * mm))

    # ---- 2. Fixture schedule ----
    story.append(Paragraph("2. Fixture Schedule", H1))
    fix_header = ["Room", "Fixture Type", "Qty", "Wattage (W)", "Total Load (W)"]
    fix_rows = [fix_header]
    total_lp = 0
    for r in rooms_data:
        n = r.get("calc", {}).get("n_fixtures", 0)
        watts = r.get("fixture_watts", 120)
        fix_rows.append([
            r.get("label") or "Room",
            fixture_type_name,
            str(n),
            str(watts),
            str(n * watts),
        ])
        total_lp += n
    fix_rows.append(["TOTAL", "", str(total_lp), "", ""])
    tbl2 = Table(fix_rows, colWidths=[50 * mm, 55 * mm, 15 * mm, 25 * mm, 25 * mm])
    tbl2.setStyle(_table_style())
    story.append(tbl2)
    story.append(Spacer(1, 8 * mm))

    # ---- 3. DB schedule ----
    story.append(Paragraph(f"3. Distribution Board Schedule — {schedule['floor']}", H1))
    story.append(Paragraph(
        f"DB location: ({db_x:.2f} m, {db_y:.2f} m) from drawing origin.  "
        f"Incomer: {schedule.get('incomer_mcb_a', '—')} A MCB, "
        f"{schedule.get('incoming_cable_csa_mm2', '—')} mm² cable.",
        BODY,
    ))
    story.append(Spacer(1, 3 * mm))

    db_header = [
        "Circuit", "Description", "Pts", "Load/pt\n(W)", "Load\nFactor",
        "Phase\nLoad (W)", "V", "I (A)", "I+25%\n(A)", "MCB\n(A)", "Cable\n(mm²)"
    ]
    db_rows = [db_header]
    for cct in schedule["circuits"]:
        phase_load = cct.get(
            f"connected_load_{cct['phase'].lower()}", cct.get("total_load_w", 0)
        )
        db_rows.append([
            cct["cct_label"],
            cct["description"][:20],
            str(cct["n_points"]),
            str(cct["load_per_point_w"]),
            str(cct["load_factor"]),
            f"{phase_load:.0f}",
            "230",
            f"{cct['full_load_a']:.2f}",
            f"{cct['design_current_a']:.2f}",
            str(cct["mcb_rating_a"]),
            str(cct["cable_csa_mm2"]),
        ])
    col_w_db = [16, 38, 10, 16, 16, 18, 10, 12, 14, 12, 14]
    tbl3 = Table(db_rows, colWidths=[w * mm for w in col_w_db])
    tbl3.setStyle(_table_style())
    story.append(tbl3)
    story.append(Spacer(1, 4 * mm))

    # Summary totals
    story.append(Paragraph(
        f"<b>Normal running load:</b>  "
        f"R = {schedule['phase_load'].get('R', 0):.0f} W &nbsp;&nbsp; "
        f"Y = {schedule['phase_load'].get('Y', 0):.0f} W &nbsp;&nbsp; "
        f"B = {schedule['phase_load'].get('B', 0):.0f} W",
        BODY,
    ))
    story.append(Paragraph(
        f"<b>Total power:</b> {schedule['total_w']:.0f} W at 230 V &nbsp;&nbsp; "
        f"<b>Full load current:</b> {schedule['full_load_a']:.2f} A &nbsp;&nbsp; "
        f"+30% spare: {schedule['design_a']:.2f} A &nbsp;&nbsp; "
        f"<b>Selected incomer MCB:</b> {schedule['incomer_mcb_a']} A",
        BODY,
    ))
    story.append(Spacer(1, 8 * mm))

    # ---- 4. Cable summary ----
    story.append(Paragraph("4. Cable Selection Summary", H1))
    story.append(Paragraph(
        "Cable sizes selected per BS7671 Appendix 4, maximum 3% voltage drop (6.9 V at 230 V). "
        "Run lengths estimated using Manhattan-distance routing with 1.2× routing factor. "
        "All cables: 3-core (L+N+E) PVC/SWA or PVC/PVC twin-and-earth as appropriate.",
        BODY,
    ))
    story.append(Spacer(1, 3 * mm))
    cable_header = ["Circuit", "Type", "Phase", "Cable (mm²)", "MCB (A)", "VD (V)", "VD (%)"]
    cable_rows = [cable_header]
    for cct in schedule["circuits"]:
        cable_rows.append([
            cct["cct_label"],
            cct["type"].replace("_", " ").title(),
            cct["phase"],
            str(cct["cable_csa_mm2"]),
            str(cct["mcb_rating_a"]),
            f"{cct.get('voltage_drop_v', '—')}",
            f"{cct.get('voltage_drop_v', 0) / 230 * 100:.2f}%" if isinstance(cct.get('voltage_drop_v'), float) else "—",
        ])
    tbl4 = Table(cable_rows, colWidths=[20, 35, 15, 22, 18, 16, 16])
    tbl4.setStyle(_table_style())
    story.append(tbl4)
    story.append(Spacer(1, 8 * mm))

    # ---- 5. Design basis ----
    story.append(Paragraph("5. Design Basis & Assumptions", H1))
    for line in [
        "Illuminance targets: EN 12464-1 (offices 500 lux, bedrooms 150 lux, kitchens 300 lux, corridors 100 lux).",
        "Lumen method: maintenance factor MF = 0.80, utilisation factor from simplified zonal cavity table.",
        "Supply voltage: 230 V, 50 Hz single-phase, 3-phase incomer.",
        "Cable volt-drop limit: 3% of 230 V = 6.9 V (BS7671 Appendix 12).",
        "Protective device: MCB to BS EN 60898, next standard rating above 125% of design current.",
        "Socket-outlet quantities: BS7671 guidance; minimum one per 8 m² for living/kitchen areas.",
        "DB spare capacity: 30% above calculated full-load current for future load growth.",
        "Cable routing factor: 1.20 applied to straight-line distances for bends and set-downs.",
        "This report is produced by automated calculation and must be verified by a qualified engineer.",
    ]:
        story.append(Paragraph(f"• {line}", SMALL))

    doc.build(story)
