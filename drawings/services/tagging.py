"""Generates fixture/socket tags following the convention shown in the
reference drawings:

  LP-{phase}{circuit}-{seq:02d}   Ground floor lighting point
  LP1-{phase}{circuit}-{seq:02d}  First floor lighting point
  SP-{phase}{circuit}-{seq:02d}   Socket point (13A)
  SK-{phase}{circuit}-{seq:02d}   Socket key (double socket)
  SW-{phase}{circuit}-{seq:02d}   Light switch

Phases are R, Y, B (balanced across circuits).
"""

PHASES = ["R", "Y", "B"]


def _phase(index):
    return PHASES[index % 3]


def tag_lighting_point(floor, phase, circuit_no, seq):
    prefix = "LP1" if floor == 1 else "LP"
    return f"{prefix}-{phase}{circuit_no}-{seq:02d}"


def tag_socket_point(phase, circuit_no, seq):
    return f"SP-{phase}{circuit_no}-{seq:02d}"


def tag_socket_key(phase, circuit_no, seq):
    return f"SK-{phase}{circuit_no}-{seq:02d}"


def tag_switch(phase, circuit_no, seq):
    return f"SW-{phase}{circuit_no}-{seq:02d}"


def assign_tags(fixtures, sockets, switches, floor=0):
    """Assigns tags to all electrical elements in-place (adds a 'tag' key).

    fixtures / sockets / switches: lists of dicts, each already having
    'circuit_no' and 'phase' assigned by circuit_grouping.assign_circuits.
    """
    lp_seq = {}
    for f in fixtures:
        key = (f["circuit_no"], f["phase"])
        lp_seq[key] = lp_seq.get(key, 0) + 1
        f["tag"] = tag_lighting_point(floor, f["phase"], f["circuit_no"], lp_seq[key])

    sp_seq = {}
    for s in sockets:
        key = (s["circuit_no"], s["phase"])
        sp_seq[key] = sp_seq.get(key, 0) + 1
        kind = s.get("kind", "SP")
        if kind == "SK":
            s["tag"] = tag_socket_key(s["phase"], s["circuit_no"], sp_seq[key])
        else:
            s["tag"] = tag_socket_point(s["phase"], s["circuit_no"], sp_seq[key])

    sw_seq = {}
    for w in switches:
        key = (w.get("circuit_no", 0), w.get("phase", "R"))
        sw_seq[key] = sw_seq.get(key, 0) + 1
        w["tag"] = tag_switch(key[1], key[0] or 1, sw_seq[key])
