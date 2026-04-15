# Internal Representation

A `ThermalBits` object stores the circuit in memory through the `file_name`,
`pi`, `po`, `node`, and `entropy` fields.

```python
from thermalbits import ThermalBits

tb = ThermalBits("test_files/half_adder.v")

print(tb.pi)
print(tb.po)
print(tb.node)
```

## Main fields

| Field | Type | Description |
|---|---|---|
| `file_name` | `str` | Source Verilog file name. |
| `pi` | `list[int]` | Primary input IDs. |
| `po` | `list[int]` | Primary output IDs. |
| `node` | `list[dict]` | Internal logic nodes. |
| `entropy` | `float \| None` | Last value computed by `update_entropy()`. |

## Node format

Each entry in `tb.node` represents a logic gate:

```python
{
    "id": 2,
    "fanin": [[0, 0], [1, 0]],
    "fanout": [
        {
            "input": [0, 1],
            "invert": [0, 0],
            "op": "&",
        }
    ],
    "level": 1,
    "suport": [0, 1],
}
```

| Field | Description |
|---|---|
| `id` | Integer node ID. |
| `fanin` | Input references in `[source_id, output_index]` format. |
| `fanout` | Outputs produced by the node. |
| `fanout[].input` | Local fanin indexes consumed by that output. |
| `fanout[].invert` | Inversion flags aligned with `input`, using `0` or `1`. |
| `fanout[].op` | Output operator: `&`, `|`, `^`, `M`, or `-`. |
| `level` | Logic level of the node in the DAG. |
| `suport` | PI cone that influences the node. |

!!! note
    The field is named `suport` to preserve compatibility with the current
    library format.

## Operators

| Operator | Meaning |
|---|---|
| `&` | AND |
| `|` | OR |
| `^` | XOR |
| `M` | Majority |
| `-` | WIRE/unary |

## Create an object manually

```python
from thermalbits import ThermalBits

tb = ThermalBits()
tb.file_name = "manual.v"
tb.pi = [0, 1]
tb.po = [2]
tb.node = [
    {
        "id": 2,
        "fanin": [[0, 0], [1, 0]],
        "fanout": [{"input": [0, 1], "invert": [0, 0], "op": "&"}],
        "level": 1,
        "suport": [0, 1],
    }
]
```

## Export the state

```python
tb.write_json("manual.json")
tb.write_verilog("manual.v", module_name="manual")
```
