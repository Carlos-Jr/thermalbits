# Iron Circuit Sim

Exact combinational circuit simulator in Rust. The program processes all nodes in the circuit, collects input and output state counts for each output (fanout) of every node, and computes the informational entropy per output and for the entire circuit.

## What the program computes

Each node can have multiple outputs (fanout). For each output with N inputs:

- Joint count of the N inputs: `n00...0`, `n00...1`, ..., `n11...1` (2^N counters)
- `pop_y`: how many times `Y=1` occurred

The metric reported per output is:

```text
H(X) - H(Y)
```

where `H(X)` is the Shannon entropy of the joint input distribution and `H(Y)` is the entropy of the output.

The total circuit entropy is the sum over all outputs of all nodes.

## Input JSON format

The circuit is read from a JSON file with the following structure:

```json
{
  "file_name": "original_name",
  "pis": [1, 2, 3],
  "pos": [4],
  "nodes": [
    {
      "id": 4,
      "fanin": [
        [1, 0],
        [2, 0],
        [3, 0]
      ],
      "fanout": [
        {"input": [0, 1, 2], "invert": [0, 0, 0], "op": "M"},
        {"input": [0, 1], "invert": [0, 0], "op": "&"},
        {"input": [0], "invert": [0], "op": "-"},
        {"input": [1], "invert": [1], "op": "-"}
      ],
      "level": 1,
      "suport": [1, 2, 3]
    }
  ]
}
```

### JSON fields

- `pis`: Primary Input IDs
- `pos`: Primary Output IDs
- `nodes`: list of circuit nodes

### Node fields

- `id`: unique node identifier
- `fanin`: list of input signal references, each in the format `[node_id, output_index]`
  - `node_id`: ID of the source node (can be a PI or another node)
  - `output_index`: which output of the source node is being used (position in that node's `fanout` vector). For PIs, this is always `0`
- `fanout`: list of node outputs (see below)
- `level`: topological level of the node (1 = first level after PIs)
- `suport`: set of PIs the node depends on (transitively)

### Output fields (`fanout`)

Each element in `fanout` describes an independent output of the node:

- `input`: vector of indices (0-indexed) referencing positions in the same node's `fanin` vector. Defines which inputs participate in this output
- `invert`: vector of the same size as `input`, with `0` or `1`, indicating whether each corresponding input is negated before applying the operator
- `op`: logical operator applied to the selected inputs:
  - `"&"` — AND of all inputs
  - `"|"` — OR of all inputs
  - `"^"` — XOR of all inputs
  - `"M"` — MAJORITY: returns `1` if the majority of inputs are `1`. Requires an odd number of inputs
  - `"-"` — Wire: passes the single input value through directly. Requires exactly 1 input

### Detailed example

In the example above, node 4 receives 3 inputs (`fanin` references PIs 1, 2, 3) and produces 4 outputs:

| Output | Op | Inputs | Description |
|--------|-----|--------|-------------|
| 0 | `M` | fanin[0], fanin[1], fanin[2] | MAJ(PI1, PI2, PI3) |
| 1 | `&` | fanin[0], fanin[1] | PI1 AND PI2 |
| 2 | `-` | fanin[0] | Passes PI1 through |
| 3 | `-` | fanin[1] | Passes NOT PI2 (invert=1) |

When another node references this node, it uses `[4, output_index]` in its `fanin` to indicate which of the 4 outputs it is consuming.

### Parser validations

- Indices in `fanout[*].input` must be valid positions within the same node's `fanin`
- `fanout[*].invert` must have the same size as `fanout[*].input`
- When `op` is `"-"`, `input` must have exactly 1 element
- When `op` is `"M"`, `input` must have an odd number of elements

## Simulation modes

### `--mode auto`

Default mode. The program decides as follows:

- if the largest local support in the circuit is less than or equal to `25`, runs `full`
- if it is greater than `25`, refuses automatic execution and asks for an explicit choice

When `auto` receives `--start` or `--count`, it switches to `chunk`.

### `--mode full`

Forces full simulation using local truth tables, even for large circuits. This mode is useful when you want to compare performance, debug results, or know that the circuit fits in memory despite exceeding the automatic mode threshold.

Restrictions:

- `--start` and `--count` cannot be used with `--mode full`
- `--binary` cannot be used with `--mode full`
- the largest local support must still fit in the program's internal representation

### `--mode chunk`

Simulates a slice of the global truth table, represented by the range:

```text
[start, start + count)
```

This mode exists for large circuits and for distributed execution across multiple independent jobs. Each job can generate a binary partial file, later combined with `merge`.

Rules:

- `--start` is optional, defaults to `0`
- `--count` is optional only when the number of PIs is `<= 63`
- `--binary` writes the partial result in binary format

## Command-line interface

### Simulation

```bash
circuit_sim <input.json> [-o states.txt] [--mode auto|full|chunk] \
  [--start <u64>] [--count <u64>] [--binary <partial.bin>]
```

Examples:

```bash
# automatic mode
cargo run --release -- circuit.json

# force full simulation
cargo run --release -- circuit.json --mode full -o full_states.txt

# manual chunk
cargo run --release -- circuit.json --mode chunk --start 0 --count 1048576 \
  --binary part_0.bin -o part_0.txt

# auto switches to chunk when start/count are provided
cargo run --release -- circuit.json --count 64 -o quick_chunk.txt
```

### Merging partials

```bash
circuit_sim merge <p1.bin> [p2.bin ...] [-o merged.txt]
```

Example:

```bash
cargo run --release -- merge part_0.bin part_1.bin -o merged.txt
```

## Generated outputs

### Text report

The text output file contains one line per output of each node:

```text
# circuit_sim state counts | pis=3 outputs=4
# gate out op k total joint_counts... y0 y1
gate=4 out=0 op=M k=3 total=8 n000=1 n001=1 n010=1 n011=1 n100=1 n101=1 n110=1 n111=1 y0=4 y1=4
gate=4 out=1 op=& k=3 total=8 n00=2 n01=2 n10=2 n11=2 y0=6 y1=2
gate=4 out=2 op=- k=3 total=8 n0=4 n1=4 y0=4 y1=4
gate=4 out=3 op=- k=3 total=8 n0=4 n1=4 y0=4 y1=4
```

Where:

- `gate`: node ID
- `out`: output index within the node's `fanout`
- `op`: output operator
- `k`: local support size of the node
- `total`: total number of evaluated vectors
- `nXXX=V`: joint input pattern count (labels generated dynamically based on number of inputs)
- `y0`, `y1`: counts of `Y=0` and `Y=1`

### Binary partial file

Binary format (version 3, little-endian):

```text
Header (38 bytes):
  magic[4]       = "CSIM"
  version u8     = 3
  flags   u8     = 1
  n_pis   u32
  start   u64
  count   u64
  circuit_hash u64
  n_records u32

Record (variable size):
  gate_id       u32
  output_index  u32
  op            u8
  n_jc          u16    (number of joint counts: 2^n_inputs)
  pop_y         u64
  joint_counts  u64 x n_jc
```

The merge validates:

- `circuit_hash`
- `n_pis`
- record count
- overlap between `[start, start + count)` ranges

## How the program works

### 1. Circuit representation

The circuit is loaded into:

- `Circuit`: PIs, POs, gates, topological levels, and metadata
- `Gate`: fanins, fanouts (each with op, input indices, and inversions), local support
- `GateResult`: final counts per output of each node

### 2. `full` mode

Each node is simulated over its local support:

- Local PIs are generated as bitsets
- Intermediate signals can be expanded from a smaller support to a larger one
- Each `fanout` output is evaluated independently, producing its truth table and counts

This mode works well when the circuit's largest support is moderate.

### 3. `chunk` mode

Instead of materializing local tables per node, `chunk` mode simulates a range of the global truth table:

- Each signal occupies `ceil(count / 64)` 64-bit words
- PIs are generated analytically, without disk-stored tables
- Nodes are evaluated level by level, with each output producing its signal vector
- Results can be saved as partials for later merging

### 4. Bit-parallel kernel

The evaluation kernel (`eval_output_words`) is generalized for N inputs:

- Applies per-input inversion as indicated in the `fanout`
- Computes the operation (`AND`, `OR`, `XOR`, `Majority`, `Wire`)
- Counts the 2^N joint input combinations via popcount
- Computes `pop_y` (count of `Y=1`)

For `Majority` with arbitrary odd N inputs, it uses a word-level adder tree to efficiently compute the threshold.

### 5. Memory management

The program uses reference counting to release intermediate signals as soon as they are no longer needed. This reduces peak memory usage in both `full` and `chunk` modes.

## Code organization

`src/` structure:

- `main.rs`: binary bootstrap
- `lib.rs`: module registration
- `cli.rs`: command-line parsing
- `app.rs`: orchestration of simulation and merge flows
- `circuit.rs`: circuit domain and JSON parser
- `stats.rs`: entropy from counts
- `sim/shared.rs`: generalized bit-parallel kernel and shared utilities
- `sim/full.rs`: full simulation
- `sim/chunk.rs`: chunk simulation
- `io/report.rs`: text output with dynamic labels
- `io/partial_bin.rs`: binary partial read, write, and merge

## Building

```bash
cargo build --release
```

Recommended optimization for the local CPU:

```bash
RUSTFLAGS="-C target-cpu=native" cargo build --release
```

## Limits and notes

- `chunk` supports up to `64` PIs
- `chunk` without `--count` only works when `n_pis <= 63`
- `full` depends on the size of the largest local support, not just the total number of PIs
- Forced `full` may be correct but still infeasible in memory/time for some circuits
- Automatic mode is conservative by design

## Recommended workflow

- Use `auto` for small or medium circuits.
- Use `--mode full` when you want to force full simulation by local support.
- Use `--mode chunk --count ... --binary ...` for large circuits or distributed execution.
- Use `merge` to combine partials from the entire circuit into a final report.
