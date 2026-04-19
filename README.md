# ThermalBits

<p align="center">
  <img src="logo.svg" alt="ThermalBits logo" width="100%">
</p>

ThermalBits is a Python library for inspecting combinational digital circuits from Verilog netlists, transforming them as editable DAGs, and estimating their information loss through Shannon entropy.

It helps compare original and optimized circuit structures by parsing Verilog, exporting JSON or reconstructed Verilog, rendering DAG images, applying transformations, and computing Landauer-related entropy with a bundled Rust simulator.

The main advantages are a compact Python API, direct access to the internal `pi`, `po`, and `node` representation, reproducible optimization flows, visual inspection support, and batch CSV reporting for experiments across many netlists.

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
