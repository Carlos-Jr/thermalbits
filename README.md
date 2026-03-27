# ThermalBits

A library for inspecting combinational digital circuits from Verilog netlists, focusing on exploring energy limits based on Landauer's principle.

### Installation

With visualization support (matplotlib):

```bash
pip install -r requirements.txt

```

The entropy simulator is a Rust binary bundled under `thermalbits/iron_circuit_sim/`. Build it once before calling `update_entropy()`:

```bash
cd thermalbits/iron_circuit_sim
RUSTFLAGS="-C target-cpu=native" cargo build --release
```

**Packaging**

```bash
python -m build
```

Artifacts will be created in `dist/`.

### Features

* [x] Parse combinational Verilog netlists into an internal circuit representation.
* [x] Access and edit circuit data (`pi`, `po`, and `node`) directly in memory.
* [x] Export the current circuit state to JSON.
* [x] Generate Verilog from the current circuit state.
* [x] Visualize the circuit as a DAG image.
* [x] Create blank circuit objects and deep-copy existing ones.
* [x] Compute total circuit Shannon entropy (Landauer information loss per gate).

## Usage Examples

### Generate Overview

Suppose you have a netlist `netlist.v` with combinational assignments. The circuit is generated automatically at initialization:

```python
from thermalbits import ThermalBits

tb = ThermalBits("netlist.v")
print(tb.pi)
print(tb.po)
print(tb.node[0])

```

You can also create a blank object and fill it manually:

```python
from thermalbits import ThermalBits

tb = ThermalBits()
tb.pi = [0, 1]
tb.po = [2]
tb.node = [{"id": 2, "op": "&", "fanin": [[0, 0], [1, 0]], "level": 1, "suport": [0, 1]}]
```

To create a full copy of an existing object:

```python
from thermalbits import ThermalBits

tb = ThermalBits("netlist.v")
tb2 = tb.copy()
```

The internal properties are editable (`pi`, `po`, `node`). To save the current state to JSON:

```python
from thermalbits import ThermalBits

tb = ThermalBits("netlist.v")
tb.write_json("out.json")
```

The `out.json` file contains:

* `file_name`: Name of the source Verilog file.
* `pis`: Integer IDs of primary inputs.
* `pos`: Integer IDs of primary outputs.
* `nodes`: List of logic nodes in the format:
* `id`: Integer identifier of the node.
* `op`: Gate operator (`&` or `|`).
* `fanin`: Compact list `[[id, inv], [id, inv]]`, where `inv` is `0` or `1`.
* `level`: Logic level of the node.
* `suport`: PI cone of the node (integer IDs).



### Visualize Graph

To visualize the circuit as a DAG (Directed Acyclic Graph):

```python
from thermalbits import ThermalBits

tb = ThermalBits("netlist.v")
tb.visualize_dag(
    output_path="dag_horizontal.png",
    orientation="horizontal",      # or "vertical"
    level_window=[4, 10],          # optional: shows only levels 4..10
)
```

The images below were generated using `test_files/simple.v`:

**Horizontal (all levels):**

<img src="dag_horizontal_test.png" alt="Horizontal test DAG" width="520" />

**Vertical (levels 1..3 only):**

<img src="dag_vertical_window_test.png" alt="Vertical DAG with level range" width="300" />

To get these exact images in your environment:

```python
from thermalbits import ThermalBits

tb = ThermalBits("test_files/simple.v")
tb.visualize_dag(
    output_path="dag_horizontal_test.png",
    orientation="horizontal",
)
tb.visualize_dag(
    output_path="dag_vertical_window_test.png",
    orientation="vertical",
    level_window=[1, 3],
)
```

If necessary, install the visualization dependency:

```bash
pip install matplotlib
```

### Convert to Verilog

To convert an circuit back to Verilog:

```python
from thermalbits import ThermalBits

tb = ThermalBits("netlist.v")
tb.write_verilog("reconstructed.v")
```

Optionally, you can define the module name:

```python
from thermalbits import ThermalBits

tb = ThermalBits("netlist.v")
tb.write_verilog("reconstructed.v", module_name="MyModule")
```

### Compute Shannon Entropy

`update_entropy()` simulates the entire circuit and computes the total Shannon entropy — the sum of information discarded by every logic gate:

```
H_total = Σ_gates [ H(A, B) − H(Y) ]
```

where `H(A, B)` is the joint entropy of the two gate inputs and `H(Y)` is the entropy of its output. This quantity directly maps to the minimum thermodynamic energy dissipation via Landauer's principle (`kT ln 2` per bit erased).

The result is stored in `self.entropy` (in bits) and also returned.

#### Mode selection

The method accepts two parameters:

| Parameter | Description |
|---|---|
| `chunks` | Total number of chunks the circuit is divided into |
| `parallel_chunks` | How many chunks can be executed simultaneously (default: `2`) |

| Call | Mode used |
|---|---|
| `update_entropy()` | **Chunk** — 2 chunks, 2 running simultaneously |
| `update_entropy(chunks=N)` | **Chunk** — `N` chunks total, 2 running simultaneously |
| `update_entropy(chunks=N, parallel_chunks=P)` | **Chunk** — `N` chunks total, `P` running simultaneously |
| `update_entropy(chunks=None)` and max gate support ≤ 25 | **Full** — per-gate truth tables (`2^k` rows each) |

#### Usage

```python
from thermalbits import ThermalBits

tb = ThermalBits("netlist.v")

# Default mode: 2 chunks, 2 running simultaneously
entropy = tb.update_entropy()
print(entropy)       # total entropy in bits
print(tb.entropy)    # same value stored on the object
```

To control the number of chunks and simultaneous execution explicitly:

```python
# Divide into 64 chunks, process 8 at a time
entropy = tb.update_entropy(chunks=64, parallel_chunks=8)
```

To maximise throughput when many CPU cores are available:

```python
# 128 chunks, all dispatched simultaneously
entropy = tb.update_entropy(chunks=128, parallel_chunks=128)
```

To force full mode on circuits with manageable support:

```python
entropy = tb.update_entropy(chunks=None)
```

Chunks are dispatched in successive batches of `parallel_chunks` until all `chunks` have been processed. Chunk results are merged automatically; temporary binary files are created and deleted in a system temp directory.

#### When to use chunk mode

| n_pis | Full table size | Recommendation |
|---|---|---|
| ≤ 20 | ≤ 1 M rows | `chunks=2` by default; `chunks=None` keeps full mode viable |
| 21–25 | 2 M – 33 M rows | `chunks=2` is usually fine; full mode is still feasible with `chunks=None` |
| 26–35 | 64 M – 34 G rows | Chunk mode, `chunks` ≈ 32–1024 |
| > 35 | > 34 G rows | Chunk mode mandatory; use many chunks |

> **Note:** chunk mode requires n_pis ≤ 63 (hardware limit of the 64-bit simulator).

## Observations
* Assignments support `&`, `|`, and `~` (no `^`, `+`, etc.). One-bit constants `1'b0` and `1'b1` are also accepted.
* Each `assign` generates a 2-fanin logic gate. If there is only one literal, a degenerate gate is generated (`x & x` or `~x & ~x`).
* Input/output paths can be absolute or relative to the current directory.
