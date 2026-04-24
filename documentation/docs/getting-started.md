# Getting Started

## Requirements

- Python 3.10 or newer.
- Rust/Cargo to build the entropy simulator and the EO/DO transformer.
- `matplotlib` and `networkx` for DAG visualization.

## Install library dependencies

From the repository root:

```bash
python -m pip install -r requirements.txt
```

For development:

```bash
python -m pip install -r requirements-dev.txt
```

## Build package artifacts

To build the package distribution files:

```bash
python -m build
```

The generated artifacts are written to `dist/`.

## Build the Rust simulator

`update_entropy()` calls the `circuit_sim` binary located at
`thermalbits/iron_circuit_sim/target/release/circuit_sim`. Build it once before
computing entropy:

```bash
cd thermalbits/iron_circuit_sim
RUSTFLAGS="-C target-cpu=native" cargo build --release
```

Then return to the repository root before running the examples:

```bash
cd ../..
```

## Build the Rust EO/DO transformer

`apply(ENERGY_ORIENTED)` and `apply(DEPTH_ORIENTED)` call the `eo_do_rs`
binary located at `thermalbits/eo_do_rs/target/release/eo_do_rs`. It is
parallelized with `rayon` and reads/writes the overview JSON from disk, so the
Python `ThermalBits` object always ends up with `file_name`, `pi`, `po`, and
`node` refreshed from the transformed result. Build it once before running
`apply()`:

```bash
cd thermalbits/eo_do_rs
RUSTFLAGS="-C target-cpu=native" cargo build --release
cd ../..
```

`RUSTFLAGS="-C target-cpu=native"` enables CPU-specific instructions
(AVX2, AVX-512, BMI2, …) and yields a noticeably faster binary on the same
machine that compiled it. Drop the flag if you need a portable build.

If the binary is missing, `apply()` falls back to the Python reference
implementation and emits a `RuntimeWarning`. Three environment variables control
the dispatch:

| Variable | Effect |
|---|---|
| `THERMALBITS_EODO_BACKEND=auto` | Default. Prefer Rust; fall back to Python with a warning when the binary is missing. |
| `THERMALBITS_EODO_BACKEND=rust` | Require the Rust binary; raise `RuntimeError` when it is unavailable. |
| `THERMALBITS_EODO_BACKEND=python` | Force the Python reference implementation. |
| `THERMALBITS_EODO_BIN=/path/to/eo_do_rs` | Override the binary location. |

## Load a circuit

Input paths can be absolute or relative to the current working directory.

```python
from thermalbits import ThermalBits

tb = ThermalBits("test_files/half_adder.v")

print(tb.file_name)
print(tb.pi)
print(tb.po)
print(tb.node[0])
```

## Copy a circuit

Use `copy()` before applying transformations when the original circuit must be
preserved:

```python
from thermalbits import ENERGY_ORIENTED, ThermalBits

tb = ThermalBits("test_files/half_adder.v")
optimized = tb.copy().apply(ENERGY_ORIENTED)
```

## Export JSON and Verilog

```python
tb.write_json("half_adder.json")
tb.write_verilog("half_adder_rebuilt.v", module_name="half_adder_rebuilt")
```

## Render an image

```python
tb.visualize_dag("half_adder.png", orientation="horizontal")
```

Use `orientation="vertical"` for the vertical layout.

## Verilog parser notes

- The parser supports combinational `assign` expressions using `&`, `|`, and
  `~`.
- One-bit constants `1'b0` and `1'b1` are accepted.
- Operators such as `^` and `+` are not parsed from Verilog input.
- Each `assign` generates one node with a single `fanout` entry.
- Unary assignments are represented with `op: "-"`.
