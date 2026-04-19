# Getting Started

## Requirements

- Python 3.10 or newer.
- Rust/Cargo to build the entropy simulator.
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
