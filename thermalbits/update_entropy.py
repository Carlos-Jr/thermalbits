import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

from .generate_overview import _state_overview

_BINARY = Path(__file__).parent / "iron_circuit_sim" / "target" / "release" / "circuit_sim"

# Gates with support > this threshold are expensive in full mode (2^k truth tables)
# and should be simulated with chunk mode instead.
_FULL_MODE_MAX_SUPPORT = 25


def _check_binary():
    if not _BINARY.exists():
        raise FileNotFoundError(
            f"circuit_sim binary not found at {_BINARY}. "
            "Run: cd iron_circuit_sim && cargo build --release"
        )


def _parse_entropy(stdout: str) -> float:
    match = re.search(r"total_circuit_entropy\s*=\s*([0-9.+-eE]+)", stdout)
    if not match:
        raise RuntimeError(f"Unexpected output from circuit_sim:\n{stdout}")
    return float(match.group(1))


def _run_full(json_path: str) -> float:
    result = subprocess.run(
        [str(_BINARY), json_path, "--mode", "full", "-o", os.devnull],
        capture_output=True,
        text=True,
        check=True,
    )
    return _parse_entropy(result.stdout)


def _build_chunk_plan(n_pis: int, n_chunks: int) -> list[tuple[int, int, int]]:
    if n_chunks <= 0:
        raise ValueError("chunks must be a positive integer")

    if n_pis > 63:
        raise ValueError(
            f"n_pis={n_pis} exceeds the 63-PI limit of chunk mode. "
            "Split the circuit or reduce the number of primary inputs."
        )

    total = 1 << n_pis
    if n_chunks > total:
        raise ValueError(f"chunks={n_chunks} is larger than total vectors={total}")

    base_count, remainder = divmod(total, n_chunks)
    plan: list[tuple[int, int, int]] = []
    start = 0
    for chunk_idx in range(n_chunks):
        count = base_count + (1 if chunk_idx < remainder else 0)
        plan.append((chunk_idx, start, count))
        start += count
    return plan


def _run_chunks_parallel(json_path: str, n_pis: int, n_chunks: int, parallel_chunks: int) -> float:
    plan = _build_chunk_plan(n_pis, n_chunks)

    with tempfile.TemporaryDirectory(prefix="circuit_sim_") as tmpdir:
        bin_files: list[str] = [
            str(Path(tmpdir) / f"chunk_{chunk_idx}.bin")
            for chunk_idx, _, _ in plan
        ]
        failures: list[str] = []

        for batch_start in range(0, len(plan), parallel_chunks):
            batch = plan[batch_start : batch_start + parallel_chunks]
            processes: list[tuple[int, subprocess.Popen[str]]] = []

            for chunk_idx, start, count in batch:
                bin_path = bin_files[chunk_idx]
                proc = subprocess.Popen(
                    [
                        str(_BINARY),
                        json_path,
                        "--mode",
                        "chunk",
                        "--start",
                        str(start),
                        "--count",
                        str(count),
                        "--binary",
                        bin_path,
                        "-o",
                        os.devnull,
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
                processes.append((chunk_idx, proc))

            for chunk_idx, proc in processes:
                stdout, _ = proc.communicate()
                if proc.returncode != 0:
                    failures.append(
                        f"chunk {chunk_idx} failed with exit code {proc.returncode}:\n{stdout}"
                    )

        if failures:
            raise RuntimeError("\n\n".join(failures))

        merge_txt = str(Path(tmpdir) / "merged.txt")
        result = subprocess.run(
            [str(_BINARY), "merge"] + bin_files + ["-o", merge_txt],
            capture_output=True,
            text=True,
            check=True,
        )

    return _parse_entropy(result.stdout)


def update_entropy(self, chunks: int | None = 2, parallel_chunks: int = 2) -> float:
    """Simulate the circuit and store the total Shannon entropy in self.entropy.

    Parameters
    ----------
    chunks : int | None
        Total number of chunks the circuit is divided into for simulation.
        - 2 (default) → divide the simulation into 2 chunks.
        - None        → full mode if max gate support ≤ 25, otherwise require
                        the caller to choose a chunk count explicitly.
        - int         → always use chunk mode with that many chunks.
    parallel_chunks : int
        Number of chunks that can be executed simultaneously (default: 2).
        Must be a positive integer. Chunks are dispatched in successive
        batches of this size until all ``chunks`` have been processed.

    Returns
    -------
    float
        Total circuit entropy in bits (also stored in self.entropy).
    """
    if not isinstance(parallel_chunks, int) or parallel_chunks <= 0:
        raise ValueError("parallel_chunks must be a positive integer")
    if not self.node:
        raise ValueError(
            "Circuit has no nodes. Run generate_overview() before update_entropy()."
        )

    _check_binary()

    circuit_json = _state_overview(self)
    n_pis = len(self.pi)
    max_support = max((len(n["suport"]) for n in self.node), default=0)

    use_chunk = chunks is not None or max_support > _FULL_MODE_MAX_SUPPORT
    if chunks is None and max_support > _FULL_MODE_MAX_SUPPORT:
        raise ValueError(
            "This circuit requires chunk mode because max gate support exceeds 25. "
            "Pass chunks=<N> to choose how many parallel chunks to run."
        )

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as tmp:
        json.dump(circuit_json, tmp, ensure_ascii=False)
        json_path = tmp.name

    try:
        if use_chunk:
            assert chunks is not None
            entropy = _run_chunks_parallel(json_path, n_pis, chunks, parallel_chunks)
        else:
            entropy = _run_full(json_path)
    finally:
        Path(json_path).unlink(missing_ok=True)

    self.entropy = entropy
    return entropy
