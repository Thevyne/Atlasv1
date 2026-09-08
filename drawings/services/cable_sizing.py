"""Cable selection and sizing following BS7671 (IEE Wiring Regulations)
as used in the reference DB schedules:
  - 1.5mm² for lighting circuits (capacity 15A, VD 29mΩ/m)
  - 2.5mm² for socket circuits (capacity 20A, VD 18mΩ/m)
  - 4.0mm² for ring mains / feeder (capacity 27A, VD 11mΩ/m)
  - 6.0mm² for heavy socket/incoming (capacity 34A, VD 7.3mΩ/m)

Voltage drop limit: 3% of 230V = 6.9V (BS7671 Appendix 4)
"""

VOLTAGE = 230.0          # single-phase supply voltage
VD_LIMIT_PERCENT = 3.0   # maximum voltage drop %
VD_LIMIT_V = VOLTAGE * VD_LIMIT_PERCENT / 100  # 6.9V

# (min cross-section mm², current capacity A, resistance mΩ/m per conductor)
CABLE_TABLE = [
    (1.0,  13.0, 36.0),
    (1.5,  15.5, 24.5),
    (2.5,  20.0, 15.1),
    (4.0,  27.0,  9.4),
    (6.0,  34.0,  6.19),
    (10.0, 46.0,  3.71),
    (16.0, 61.0,  2.36),
]

STANDARD_MCB_RATINGS = [6, 10, 16, 20, 25, 32, 40, 50, 63, 80, 100]


def _cable_for_current(current_a):
    """Return smallest cable that can carry current_a."""
    for csa, capacity, _ in CABLE_TABLE:
        if capacity >= current_a:
            return csa, capacity
    csa, capacity, _ = CABLE_TABLE[-1]
    return csa, capacity


def _voltage_drop(current_a, length_m, resistance_mohm_per_m):
    """Two-conductor (line + neutral) voltage drop in volts."""
    return (2 * current_a * resistance_mohm_per_m * length_m) / 1000.0


def _cable_for_vd(current_a, length_m, min_csa):
    """Upgrade cable until voltage drop is within limit.
    Returns (csa, vd_volts)."""
    for csa, capacity, res in CABLE_TABLE:
        if csa < min_csa:
            continue
        vd = _voltage_drop(current_a, length_m, res)
        if vd <= VD_LIMIT_V:
            return csa, vd
    csa, _, res = CABLE_TABLE[-1]
    return csa, _voltage_drop(current_a, length_m, res)


def select_mcb(current_a, spare_factor=1.25):
    """Next standard MCB rating above current × spare factor."""
    design_current = current_a * spare_factor
    for rating in STANDARD_MCB_RATINGS:
        if rating >= design_current:
            return rating
    return STANDARD_MCB_RATINGS[-1]


def size_circuit_cable(total_load_w, cable_run_length_m, voltage=VOLTAGE, power_factor=0.85):
    """Full cable sizing for a branch circuit.

    Returns a dict matching the DB schedule column layout from the
    reference drawings.
    """
    full_load_a = total_load_w / (voltage * power_factor)
    design_current_a = full_load_a * 1.25   # 25% spare per DB schedule header

    min_csa, _ = _cable_for_current(full_load_a)
    csa, vd = _cable_for_vd(full_load_a, cable_run_length_m, min_csa)

    mcb_rating = select_mcb(full_load_a)

    for _, capacity, res in CABLE_TABLE:
        pass  # just in case

    for c, cap, res in CABLE_TABLE:
        if c == csa:
            vd_final = _voltage_drop(full_load_a, cable_run_length_m, res)
            break
    else:
        vd_final = vd

    return {
        "full_load_a": round(full_load_a, 2),
        "design_current_a": round(design_current_a, 2),
        "mcb_rating_a": mcb_rating,
        "cable_csa_mm2": csa,
        "voltage_drop_v": round(vd_final, 2),
        "voltage_drop_pct": round(vd_final / voltage * 100, 2),
    }


def size_incoming_cable(total_load_w, run_length_m=5.0):
    """Sizes the main incoming feeder cable and selects the DB incomer MCB.

    The 30% spare capacity approach matches your reference DB schedule header.
    """
    full_load_a = total_load_w / VOLTAGE
    spare_a = full_load_a * 0.30
    design_a = full_load_a + spare_a

    csa, vd = _cable_for_vd(design_a, run_length_m, 1.5)
    mcb = select_mcb(design_a, spare_factor=1.0)

    for m in STANDARD_MCB_RATINGS:
        if m >= mcb:
            next_std = m
            break
    else:
        next_std = STANDARD_MCB_RATINGS[-1]

    return {
        "total_load_w": round(total_load_w, 1),
        "full_load_a": round(full_load_a, 2),
        "spare_a": round(spare_a, 2),
        "design_a": round(design_a, 2),
        "incomer_mcb_a": next_std,
        "incoming_cable_csa_mm2": csa,
    }
