"""Lumen (zonal cavity) method for estimating fixture count per room.

    N = (E x A) / (F x UF x MF)

This is the standard, auditable hand-calculation method used for
preliminary lighting design. _UF_TABLE below is a simplified stand-in for
manufacturer photometric data -- for a production-grade design you'd
replace utilization_factor() with a lookup against the actual fixture's
published UF table (or do a full point-by-point calculation from its IES
file instead of this method entirely).
"""
from dataclasses import dataclass

# (room_index, utilization_factor) pairs for a typical recessed/surface
# luminaire with moderate surface reflectances. Linearly interpolated.
_UF_TABLE = [
    (0.6, 0.40),
    (0.8, 0.48),
    (1.0, 0.55),
    (1.25, 0.60),
    (1.5, 0.64),
    (2.0, 0.68),
    (2.5, 0.71),
    (3.0, 0.73),
    (4.0, 0.76),
    (5.0, 0.78),
]


@dataclass
class LightingResult:
    n_fixtures: int
    room_index: float
    utilization_factor: float
    required_lux: float


def room_index(length_m, width_m, mounting_height_m):
    denom = mounting_height_m * (length_m + width_m)
    if denom <= 0:
        return 0.0
    return (length_m * width_m) / denom


def utilization_factor(ri):
    """Linear interpolation over the simplified UF table."""
    if ri <= _UF_TABLE[0][0]:
        return _UF_TABLE[0][1]
    if ri >= _UF_TABLE[-1][0]:
        return _UF_TABLE[-1][1]

    for (ri_a, uf_a), (ri_b, uf_b) in zip(_UF_TABLE, _UF_TABLE[1:]):
        if ri_a <= ri <= ri_b:
            fraction = (ri - ri_a) / (ri_b - ri_a)
            return uf_a + fraction * (uf_b - uf_a)

    return _UF_TABLE[-1][1]


def calculate_fixture_count(
    area_sq_m,
    required_lux,
    fixture_lumens,
    length_m,
    width_m,
    mounting_height_m=2.7,
    maintenance_factor=0.8,
):
    if fixture_lumens <= 0:
        raise ValueError("fixture_lumens must be greater than zero")

    ri = room_index(length_m, width_m, mounting_height_m)
    uf = utilization_factor(ri)

    n = (required_lux * area_sq_m) / (fixture_lumens * uf * maintenance_factor)
    n_fixtures = max(1, round(n))

    return LightingResult(
        n_fixtures=n_fixtures,
        room_index=ri,
        utilization_factor=uf,
        required_lux=required_lux,
    )
