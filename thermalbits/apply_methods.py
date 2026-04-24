"""Dispatch optimization methods for ThermalBits overview circuits."""

from __future__ import annotations

import os
import warnings
from copy import deepcopy
from typing import Callable

from .generate_overview import _state_overview
from .optimization_methods import (
    DEPTH_ORIENTED,
    ENERGY_ORIENTED,
    apply_depth_oriented,
    apply_energy_oriented,
)
from .optimization_methods.eo_do_rs_bridge import (
    RustBinaryUnavailable,
    run_transform as _run_rust_transform,
)

Overview = dict[str, object]
Transformation = Callable[[Overview], Overview]

_ENV_BACKEND = "THERMALBITS_EODO_BACKEND"


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


def _resolve_backend() -> str:
    raw = os.environ.get(_ENV_BACKEND, "auto").strip().lower()
    if raw not in {"auto", "rust", "python"}:
        raise ValueError(
            f"{_ENV_BACKEND} must be one of 'auto', 'rust', 'python' (got {raw!r})"
        )
    return raw


def _transform_overview(method_key: str, overview: Overview) -> Overview:
    """Run the requested EO/DO transformation via Rust when possible."""

    backend = _resolve_backend()

    if backend in {"auto", "rust"}:
        try:
            return _run_rust_transform(overview, method_key)
        except RustBinaryUnavailable as exc:
            if backend == "rust":
                raise RuntimeError(
                    f"{_ENV_BACKEND}=rust but Rust binary is unavailable: {exc}"
                ) from exc
            warnings.warn(
                f"eo_do_rs binary not available, falling back to Python implementation: {exc}",
                RuntimeWarning,
                stacklevel=2,
            )

    transform = METHOD_REGISTRY[method_key]
    return transform(overview)


def apply(self, method: object):
    """Apply a registered optimization method to the current circuit."""

    if not self.node:
        raise ValueError(
            "Circuit has no nodes. Run generate_overview() before apply()."
        )

    method_key = _normalize_method(method)
    if method_key not in METHOD_REGISTRY:
        available = ", ".join(sorted(METHOD_REGISTRY))
        raise ValueError(
            f"Unknown apply method {method!r}. Available methods: {available}"
        )

    overview = _state_overview_like(self)
    transformed = _transform_overview(method_key, overview)

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
