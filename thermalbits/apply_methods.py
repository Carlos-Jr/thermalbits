"""Dispatch optimization methods for ThermalBits overview circuits."""

from __future__ import annotations

from copy import deepcopy
from typing import Callable

from .generate_overview import _state_overview
from .optimization_methods import (
    DEPTH_ORIENTED,
    ENERGY_ORIENTED,
    apply_depth_oriented,
    apply_energy_oriented,
)

Overview = dict[str, object]
Transformation = Callable[[Overview], Overview]


def _normalize_method(method: object) -> str:
    """Return a registry key from a public constant or string-like enum value."""

    if isinstance(method, str):
        normalized = method
    else:
        value = getattr(method, "value", None)
        if not isinstance(value, str):
            raise ValueError(
                "method must be a registered string constant, such as DEPTH_ORIENTED"
            )
        normalized = value
    return normalized.strip().lower()


def _state_overview_like(self) -> Overview:
    """Return a deep copy of the current ThermalBits state as an overview-like dict."""

    return deepcopy(_state_overview(self))


METHOD_REGISTRY: dict[str, Transformation] = {
    DEPTH_ORIENTED: apply_depth_oriented,
    ENERGY_ORIENTED: apply_energy_oriented,
}


def apply(self, method: object):
    """Apply a registered optimization method to the current circuit."""

    if not self.node:
        raise ValueError(
            "Circuit has no nodes. Run generate_overview() before apply()."
        )

    method_key = _normalize_method(method)
    transform = METHOD_REGISTRY.get(method_key)
    if transform is None:
        available = ", ".join(sorted(METHOD_REGISTRY))
        raise ValueError(
            f"Unknown apply method {method!r}. Available methods: {available}"
        )

    overview = _state_overview_like(self)
    transformed = transform(overview)

    self.file_name = str(transformed["file_name"])
    self.pi = list(transformed["pis"])
    self.po = list(transformed["pos"])
    self.node = list(transformed["nodes"])
    self.entropy = None
    return self


__all__ = [
    "DEPTH_ORIENTED",
    "ENERGY_ORIENTED",
    "METHOD_REGISTRY",
    "apply",
]
