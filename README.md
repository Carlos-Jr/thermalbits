# ThermalBits

<p align="center">
  <img src="logo.svg" alt="ThermalBits logo" width="100%">
</p>

ThermalBits is a Python library for inspecting combinational digital circuits from Verilog netlists, transforming them as editable DAGs, and estimating their information loss through Shannon entropy.

It helps compare original and optimized circuit structures by parsing Verilog, exporting JSON or reconstructed Verilog, rendering DAG images, applying transformations, and computing Landauer-related entropy with a bundled Rust simulator.

The main advantages are a compact Python API, direct access to the internal `pi`, `po`, and `node` representation, reproducible optimization flows, visual inspection support, and batch CSV reporting for experiments across many netlists.

## Quick start

The repository ships a setup script that installs the Python dependencies and
builds both Rust binaries (`iron_circuit_sim` for `update_entropy()` and
`eo_do_rs` for `apply()`) with native CPU optimizations enabled:

```bash
./fast_start.sh
```

Flags (combinable):

| Flag | Effect |
|---|---|
| `--dev` | Install `requirements-dev.txt` (adds `pytest`, `ruff`, `build`, `twine`). |
| `--docs` | Install `documentation/requirements-docs.txt` (MkDocs Material). |
| `--no-native` | Drop `RUSTFLAGS="-C target-cpu=native"` for portable binaries. |
| `--help` | Print usage. |

Example for a full development machine:

```bash
./fast_start.sh --dev --docs
```

The script aborts early if `python3` or `cargo` is missing. If you prefer to do
each step by hand, follow the section below.

## Installation

Install the Python dependencies from the repository root:

```bash
python -m pip install -r requirements.txt
```

For development dependencies:

```bash
python -m pip install -r requirements-dev.txt
```

The entropy simulator is a Rust binary bundled under `thermalbits/iron_circuit_sim/`. Build it once before calling `update_entropy()`:

```bash
cd thermalbits/iron_circuit_sim
RUSTFLAGS="-C target-cpu=native" cargo build --release
```

The EO/DO optimizations used by `apply()` are implemented in a second Rust binary bundled under `thermalbits/eo_do_rs/` and parallelized with [`rayon`](https://crates.io/crates/rayon). Build it once before calling `apply(ENERGY_ORIENTED)` or `apply(DEPTH_ORIENTED)`:

```bash
cd thermalbits/eo_do_rs
RUSTFLAGS="-C target-cpu=native" cargo build --release
```

The `RUSTFLAGS="-C target-cpu=native"` flag enables CPU-specific optimizations (AVX2, AVX-512, BMI2, etc.) and produces a noticeably faster binary on the machine that compiled it. Omit it if you need a binary portable across different CPUs.

If the binary is missing, `apply()` falls back to the Python reference implementation and emits a `RuntimeWarning`. Set `THERMALBITS_EODO_BACKEND=rust` to turn the missing binary into an error, or `THERMALBITS_EODO_BACKEND=python` to force the Python path. Use `THERMALBITS_EODO_BIN=/path/to/eo_do_rs` to override the binary location.

To build package artifacts:

```bash
python -m build
```

Artifacts will be created in `dist/`.

## Full Documentation

The complete documentation is in [`documentation/docs`](documentation/docs).
Start with:

- [Getting Started](documentation/docs/getting-started.md)
- [Documentation index](documentation/docs/index.md)

To serve the documentation locally:

```bash
python -m pip install -r documentation/requirements-docs.txt
mkdocs serve -f documentation/mkdocs.yml
```
