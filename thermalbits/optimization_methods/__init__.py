"""Optimization methods available through ThermalBits.apply()."""

from .eo_do import (
    DEPTH_ORIENTED,
    ENERGY_ORIENTED,
    apply_depth_oriented,
    apply_energy_oriented,
)

__all__ = [
    "DEPTH_ORIENTED",
    "ENERGY_ORIENTED",
    "apply_depth_oriented",
    "apply_energy_oriented",
]
