#!/usr/bin/env python3
"""
Uso:
    scripts/run_parallel_chunks.py <circuit.json> <num_chunks>

Comportamento:
    1. Garante que exista um build release de circuit_sim, a menos que SIM_BIN esteja definido.
    2. Divide a tabela-verdade completa em chunks contíguos balanceados.
    3. Executa um processo do simulador por chunk em paralelo.
    4. Mescla todos os parciais em um relatório final.
    5. Imprime pis, pos, gates, levels, entropy e tempo total de simulação.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("json_path", help="Path to the circuit JSON file")
    parser.add_argument("num_chunks", type=int, help="Number of parallel chunks")
    parser.add_argument(
        "--keep-temp",
        action="store_true",
        help="Keep chunk partials and logs after a successful run",
    )
    return parser.parse_args()


def load_metadata(json_path: Path) -> dict[str, int]:
    with json_path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)

    levels = [node["level"] for node in data["nodes"]]
    return {
        "pis": len(data["pis"]),
        "pos": len(data["pos"]),
        "gates": len(data["nodes"]),
        "levels": len(set(levels)),
        "max_level": max(levels) if levels else 0,
    }


def build_or_find_binary(repo_root: Path) -> Path:
    sim_bin_env = os.environ.get("SIM_BIN")
    if sim_bin_env:
        sim_bin = Path(sim_bin_env).expanduser().resolve()
        if not sim_bin.is_file() or not os.access(sim_bin, os.X_OK):
            raise SystemExit(f"Simulator binary not found or not executable: {sim_bin}")
        return sim_bin

    subprocess.run(
        ["cargo", "build", "--release", "--quiet", "--manifest-path", str(repo_root / "Cargo.toml")],
        check=True,
        cwd=repo_root,
    )
    sim_bin = repo_root / "target" / "release" / "circuit_sim"
    if not sim_bin.is_file() or not os.access(sim_bin, os.X_OK):
        raise SystemExit(f"Simulator binary not found or not executable: {sim_bin}")
    return sim_bin


def build_chunk_plan(n_pis: int, num_chunks: int) -> list[tuple[int, int, int]]:
    if num_chunks <= 0:
        raise SystemExit("num_chunks must be a positive integer")
    if n_pis > 63:
        raise SystemExit(
            f"Full chunk sweep requires <= 63 PIs so 2^n fits in u64; found {n_pis}"
        )

    total_vectors = 1 << n_pis
    if num_chunks > total_vectors:
        raise SystemExit(
            f"num_chunks={num_chunks} is larger than total vectors={total_vectors}"
        )

    base = total_vectors // num_chunks
    rem = total_vectors % num_chunks
    start = 0
    plan: list[tuple[int, int, int]] = []

    for idx in range(num_chunks):
        count = base + (1 if idx < rem else 0)
        plan.append((idx, start, count))
        start += count

    return plan


def parse_entropy(merge_stdout: str) -> str:
    match = re.search(r"total_circuit_entropy\s*=\s*([0-9.+-eE]+)", merge_stdout)
    if not match:
        raise SystemExit("Failed to parse merged entropy")
    return match.group(1)


def run_parallel_chunks(
    sim_bin: Path,
    repo_root: Path,
    json_path: Path,
    num_chunks: int,
    keep_temp: bool,
) -> int:
    metadata = load_metadata(json_path)
    plan = build_chunk_plan(metadata["pis"], num_chunks)

    json_stem = json_path.stem
    merged_output = repo_root / f"{json_stem}.chunks-{num_chunks}.merged.txt"

    temp_dir = Path(tempfile.mkdtemp(prefix="circuit_sim_chunks.", dir=os.environ.get("TMPDIR", "/tmp")))
    success = False
    simulation_started = time.perf_counter()

    try:
        processes: list[tuple[subprocess.Popen[str], Path, object]] = []
        part_files: list[Path] = []

        for chunk_idx, chunk_start, chunk_count in plan:
            part_file = temp_dir / f"chunk_{chunk_idx}.bin"
            log_file = temp_dir / f"chunk_{chunk_idx}.log"
            part_files.append(part_file)

            log_handle = log_file.open("w", encoding="utf-8")
            proc = subprocess.Popen(
                [
                    str(sim_bin),
                    str(json_path),
                    "--mode",
                    "chunk",
                    "--start",
                    str(chunk_start),
                    "--count",
                    str(chunk_count),
                    "--binary",
                    str(part_file),
                    "-o",
                    os.devnull,
                ],
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=repo_root,
            )
            processes.append((proc, log_file, log_handle))

        failed_logs: list[Path] = []
        for proc, log_file, log_handle in processes:
            return_code = proc.wait()
            log_handle.close()
            if return_code != 0:
                failed_logs.append(log_file)

        if failed_logs:
            print(f"Pelo menos um chunk falhou. Os logs estão em: {temp_dir}", file=sys.stderr)
            for log_file in failed_logs:
                print(f"log_falho={log_file}", file=sys.stderr)
            return 1

        merge_result = subprocess.run(
            [str(sim_bin), "merge", *map(str, part_files), "-o", str(merged_output)],
            check=True,
            capture_output=True,
            text=True,
            cwd=repo_root,
        )
        if merge_result.stderr:
            sys.stderr.write(merge_result.stderr)

        total_time_s = time.perf_counter() - simulation_started
        entropy = parse_entropy(merge_result.stdout)

        print(
            "{pis},{pos},{gates},{levels},{max_level}"
            ",{entropy},{total_time:.6f}".format(
                pis=metadata["pis"],
                pos=metadata["pos"],
                gates=metadata["gates"],
                levels=metadata["levels"],
                max_level=metadata["max_level"],
                entropy=entropy,
                total_time=total_time_s,
            )
        )
        print(f"saida_mesclada={merged_output}")
        success = True
        return 0
    finally:
        if success and not keep_temp:
            shutil.rmtree(temp_dir, ignore_errors=True)
        elif not success or keep_temp:
            print(f"dir_temporario={temp_dir}", file=sys.stderr)


def main() -> int:
    args = parse_args()
    json_path = Path(args.json_path).expanduser().resolve()
    if not json_path.is_file():
        raise SystemExit(f"JSON file not found: {json_path}")

    repo_root = Path(__file__).resolve().parent.parent
    sim_bin = build_or_find_binary(repo_root)
    return run_parallel_chunks(sim_bin, repo_root, json_path, args.num_chunks, args.keep_temp)


if __name__ == "__main__":
    sys.exit(main())
