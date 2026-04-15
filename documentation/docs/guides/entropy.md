# Shannon Entropy

`update_entropy()` simulates the circuit and computes total entropy in bits. The
value represents the sum of information discarded by the logic gates:

```text
H_total = sum_gates H(inputs) - H(output)
```

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

| Call | Mode |
|---|---|
| `update_entropy()` | Chunk mode with `chunks=2` and `parallel_chunks=2`. |
| `update_entropy(chunks=N)` | Chunk mode with `N` chunks and `parallel_chunks=2`. |
| `update_entropy(chunks=N, parallel_chunks=P)` | Chunk mode with `N` chunks and `P` simultaneous chunks. |
| `update_entropy(chunks=None)` | Full mode when the largest gate support has up to 25 PIs. |

## When to use chunks

| Number of PIs | Recommendation |
|---|---|
| Up to 20 | `chunks=2` or `chunks=None`. |
| 21 to 25 | `chunks=2`; full mode can still be used explicitly. |
| 26 to 35 | Use chunk mode with tens or hundreds of chunks. |
| More than 35 | Chunk mode is mandatory. |

!!! warning
    Chunk mode accepts at most 63 primary inputs due to the 64-bit simulator
    limit.

## Measure entropy time

For batch measurements, use `run_tests.py`. It stores `entropy_time_s`, which
measures only the time spent inside `update_entropy()` for each circuit/method
pair.
