# run_tests.py

`run_tests.py` runs batch analysis for all `.v` and `.sv` files in a directory.
The main output is a CSV containing circuit size, depth, energy, and entropy
calculation time.

## Basic usage

```bash
python run_tests.py test_files -o entropy_results.csv --chunks 2 --parallel_chunks 2
```

By default, the script runs:

- `original`: circuit without transformation.
- `eo`: circuit with `ENERGY_ORIENTED`.
- `do`: circuit with `DEPTH_ORIENTED`.

## Select methods

Run only original + EO:

```bash
python run_tests.py test_files -o eo_results.csv --energy-oriented
```

Run only original + DO:

```bash
python run_tests.py test_files -o do_results.csv --depth-oriented
```

When `--energy-oriented` and `--depth-oriented` are used together, both methods
are included. The original circuit is always used as the baseline.

## CSV columns

```text
file,method,size,depth,energy,entropy_time_s,image_path
```

| Column | Description |
|---|---|
| `file` | Relative Verilog path inside the input directory. |
| `method` | `original`, `eo`, or `do`. |
| `size` | Number of circuit nodes. |
| `depth` | Largest logic level found. |
| `energy` | Total entropy computed for the circuit/method pair. |
| `entropy_time_s` | Time, in seconds, spent by `update_entropy()`. |
| `image_path` | Generated image path, or empty when images are not requested. |

## Generate images with the CSV

```bash
python run_tests.py test_files \
  -o entropy_results.csv \
  --images-dir dag_outputs \
  --image-orientation horizontal
```

Use `--image-orientation vertical` to generate vertical images.

Images are saved while preserving relative subdirectories. For example:

```text
dag_outputs/EPFL/sin_original.png
dag_outputs/EPFL/sin_eo.png
dag_outputs/EPFL/sin_do.png
```

## Error handling

Files that fail during loading, transformation, entropy calculation, or image
generation are reported to `stderr`. Successful rows are still written to the
CSV.

Exit codes:

| Code | Meaning |
|---|---|
| `0` | All files/methods were processed successfully. |
| `1` | Argument error or missing input directory. |
| `2` | At least one file/method failed during processing. |
