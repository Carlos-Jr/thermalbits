# Public API

## Imports

```python
from thermalbits import DEPTH_ORIENTED, ENERGY_ORIENTED, ThermalBits
```

## `ThermalBits(verilog_path=None)`

Creates a circuit object. When `verilog_path` is provided, the library parses
the Verilog file immediately.

```python
tb = ThermalBits("test_files/half_adder.v")
blank = ThermalBits()
```

## Attributes

| Attribute | Description |
|---|---|
| `verilog_path` | Verilog path used to generate the circuit. |
| `file_name` | Loaded file name. |
| `pi` | Primary input IDs. |
| `po` | Primary output IDs. |
| `node` | DAG node list. |
| `entropy` | Last computed entropy value, or `None`. |

## `generate_overview()`

Reprocesses `self.verilog_path` and updates `file_name`, `pi`, `po`, and
`node`. Returns an overview dictionary.

```python
tb = ThermalBits()
tb.verilog_path = "test_files/half_adder.v"
overview = tb.generate_overview()
```

## `copy()`

Returns a deep copy of the object.

```python
tb2 = tb.copy()
```

## `apply(method)`

Applies a registered transformation to the current circuit. The method mutates
the object and returns the same instance.

```python
tb.apply(ENERGY_ORIENTED)
```

Accepted methods:

- `ENERGY_ORIENTED`
- `DEPTH_ORIENTED`

## `update_entropy(chunks=2, parallel_chunks=2)`

Computes total circuit entropy in bits, stores it in `self.entropy`, and returns
the value.

```python
energy = tb.update_entropy(chunks=2, parallel_chunks=2)
```

Use `chunks=None` to force full mode when the circuit is small enough.

## `visualize_dag(output_path, orientation="horizontal", level_window=None)`

Generates a PNG image of the DAG.

```python
tb.visualize_dag(
    output_path="circuit.png",
    orientation="horizontal",
    level_window=[1, 3],
)
```

Parameters:

| Parameter | Description |
|---|---|
| `output_path` | Output image path. |
| `orientation` | `"horizontal"` or `"vertical"`. |
| `level_window` | Optional `[start, end]` list to limit displayed levels. |

## `write_json(output_path)`

Exports the current state to JSON.

```python
tb.write_json("circuit.json")
```

## `write_verilog(output_path, module_name=None)`

Generates Verilog from the current state.

```python
tb.write_verilog("rebuilt.v", module_name="rebuilt")
```

When `module_name` is not provided, the library derives the name from
`file_name` or uses a default name.
