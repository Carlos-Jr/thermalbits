"""Bridge that runs the Rust binary eo_do_rs and returns the transformed overview.

The binary reads a JSON overview from a file, applies the EO/DO transformation in
parallel (rayon), and writes a JSON overview to disk. This module handles building
the subprocess call and parsing the result so that the Python ThermalBits object
can update its internal circuit representation (file_name, pi, po, node).
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

Overview = dict[str, object]

DEPTH_ORIENTED = "depth_oriented"
ENERGY_ORIENTED = "energy_oriented"

_ENV_BIN = "THERMALBITS_EODO_BIN"

_BIN_CANDIDATES = (
    Path(__file__).resolve().parents[1] / "eo_do_rs" / "target" / "release" / "eo_do_rs",
    Path(__file__).resolve().parents[1] / "eo_do_rs" / "target" / "debug" / "eo_do_rs",
)


class RustBinaryUnavailable(RuntimeError):
    """Raised when the compiled eo_do_rs binary cannot be located."""


def locate_binary() -> Path:
    override = os.environ.get(_ENV_BIN)
    if override:
        candidate = Path(override).expanduser()
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
        raise RustBinaryUnavailable(
            f"{_ENV_BIN}={override!r} does not point to an executable file"
        )

    for candidate in _BIN_CANDIDATES:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate

    raise RustBinaryUnavailable(
        "eo_do_rs binary not found. Build it with:\n"
        "  (cd thermalbits/eo_do_rs && cargo build --release)\n"
        f"or set {_ENV_BIN}=/path/to/eo_do_rs."
    )


def run_transform(overview: Overview, method: str) -> Overview:
    """Call the Rust binary and return the transformed overview as a Python dict."""

    binary = locate_binary()

    with tempfile.TemporaryDirectory(prefix="thermalbits_eodo_") as work_dir:
        input_path = Path(work_dir) / "overview.json"
        output_path = Path(work_dir) / "result.json"

        with input_path.open("w", encoding="utf-8") as handle:
            json.dump(overview, handle, ensure_ascii=False)

        completed = subprocess.run(
            [
                str(binary),
                str(input_path),
                "--method",
                method,
                "-o",
                str(output_path),
            ],
            capture_output=True,
            check=False,
            text=True,
        )

        if completed.returncode != 0:
            stderr = completed.stderr.strip() or completed.stdout.strip()
            raise RuntimeError(f"eo_do_rs failed (exit {completed.returncode}): {stderr}")

        with output_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)


__all__ = [
    "DEPTH_ORIENTED",
    "ENERGY_ORIENTED",
    "RustBinaryUnavailable",
    "locate_binary",
    "run_transform",
]
