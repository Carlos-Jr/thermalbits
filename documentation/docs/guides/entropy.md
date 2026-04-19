# Shannon Entropy

`update_entropy()` simulates the circuit and computes total entropy in bits. The
value represents the sum of information discarded by the logic gates:

```text
H_total = sum_gates [H(inputs) - H(output)]
```

For a two-input gate, this is `H(A, B) - H(Y)`, where `H(A, B)` is the joint
entropy of the gate inputs and `H(Y)` is the entropy of the output. The value
maps to the minimum thermodynamic energy dissipation through Landauer's
principle, `kT ln 2` per bit erased.

The result is also stored in `tb.entropy`.

```python
from thermalbits import ThermalBits

tb = ThermalBits("test_files/half_adder.v")
energy = tb.update_entropy(chunks=2, parallel_chunks=2)

print(energy)
print(tb.entropy)
```

## Rust simulator dependency

Before calling `update_entropy()`, build the simulator:

```bash
cd thermalbits/iron_circuit_sim
RUSTFLAGS="-C target-cpu=native" cargo build --release
```

If the binary does not exist, the library raises `FileNotFoundError` with the
expected path.

## Execution modes

The method accepts these parameters:

| Parameter | Description |
|---|---|
| `chunks` | Total number of chunks the circuit is divided into. |
| `parallel_chunks` | Number of chunks executed simultaneously. Defaults to `2`. |

| Call | Mode |
|---|---|
| `update_entropy()` | Chunk mode with `chunks=2` and `parallel_chunks=2`. |
| `update_entropy(chunks=N)` | Chunk mode with `N` chunks and `parallel_chunks=2`. |
| `update_entropy(chunks=N, parallel_chunks=P)` | Chunk mode with `N` chunks and `P` simultaneous chunks. |
| `update_entropy(chunks=None)` | Full mode when the largest gate support has up to 25 PIs. |

Chunks are dispatched in successive batches of `parallel_chunks` until all
chunks have been processed. Chunk results are merged automatically. Temporary
binary files are created and deleted in a system temp directory.

To control chunking explicitly:

```python
entropy = tb.update_entropy(chunks=64, parallel_chunks=8)
```

To maximize throughput when enough CPU cores are available:

```python
entropy = tb.update_entropy(chunks=128, parallel_chunks=128)
```

To force full mode on circuits with manageable support:

```python
entropy = tb.update_entropy(chunks=None)
```

## When to use chunks

| Number of PIs | Full table size | Recommendation |
|---|---:|---|
| Up to 20 | Up to 1 M rows | `chunks=2` by default; `chunks=None` keeps full mode viable. |
| 21 to 25 | 2 M to 33 M rows | `chunks=2` is usually fine; full mode can still be used explicitly. |
| 26 to 35 | 64 M to 34 G rows | Use chunk mode with roughly 32 to 1024 chunks. |
| More than 35 | More than 34 G rows | Chunk mode is mandatory; use many chunks. |

!!! warning
    Chunk mode accepts at most 63 primary inputs due to the 64-bit simulator
    limit.

## Measure entropy time

For batch measurements, use `run_tests.py`. It stores `entropy_time_s`, which
measures only the time spent inside `update_entropy()` for each circuit/method
pair.
