# ThermalBits

ThermalBits is a Python library for inspecting combinational digital circuits
from Verilog netlists. It represents circuits as editable DAGs, applies
energy/depth-oriented transformations, renders circuit images, and computes
total Shannon entropy related to information loss at logic gates.

## What the library provides

- Load combinational Verilog netlists.
- Convert circuits into an editable internal representation.
- Export the current circuit state to JSON.
- Rebuild Verilog from the current state.
- Render DAG images with Matplotlib and NetworkX.
- Apply the `ENERGY_ORIENTED` and `DEPTH_ORIENTED` methods.
- Compute Shannon entropy with the bundled Rust simulator.
- Run batch experiments with `run_tests.py` and save CSV reports.

## Quick example

```python
from thermalbits import ENERGY_ORIENTED, ThermalBits

tb = ThermalBits("test_files/half_adder.v")

original_energy = tb.update_entropy(chunks=None)
optimized = tb.copy().apply(ENERGY_ORIENTED)
optimized_energy = optimized.update_entropy(chunks=None)

optimized.visualize_dag("half_adder_eo.png", orientation="horizontal")

print(original_energy)
print(optimized_energy)
```

## Documentation map

- [Getting Started](getting-started.md): installation and first use.
- [Internal Representation](guides/overview.md): `pi`, `po`, and `node` fields.
- [DAG Visualization](guides/visualization.md): image generation and visual
  conventions.
- [Apply Optimizations](guides/optimization.md): applying optimization methods.
- [Shannon Entropy](guides/entropy.md): computation modes and the Rust simulator.
- [run_tests.py](cli/run-tests.md): batch execution and CSV reports.
- [Public API](api/thermalbits.md): summary of the main methods.
