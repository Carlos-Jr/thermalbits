#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

from thermalbits import ThermalBits


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Calcula a entropia de todos os arquivos Verilog em uma pasta."
    )
    parser.add_argument(
        "input_dir",
        help="Pasta contendo os arquivos Verilog (.v e .sv). A busca eh recursiva.",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="entropy_results.txt",
        help="Arquivo TXT para registrar os resultados em tempo real.",
    )
    parser.add_argument(
        "--chunks",
        type=int,
        default=2,
        help="Numero total de chunks em que o circuito sera dividido (padrao: 2).",
    )
    parser.add_argument(
        "--parallel_chunks",
        type=int,
        default=2,
        help="Numero de chunks calculados simultaneamente (padrao: 2).",
    )
    return parser.parse_args()


def find_verilog_files(root: Path) -> list[Path]:
    files = [path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in {".v", ".sv"}]
    return sorted(files)


def format_result(status: str, relative_path: str, message: str, elapsed_s: float) -> str:
    timestamp = datetime.now().isoformat(timespec="seconds")
    return f"{timestamp}\t{status}\t{relative_path}\t{message}\telapsed_s={elapsed_s:.3f}"


def write_line(handle, line: str) -> None:
    print(line)
    print(line, file=handle)
    handle.flush()


def main() -> int:
    args = parse_args()
    input_dir = Path(args.input_dir).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()

    if not input_dir.is_dir():
        print(f"Pasta nao encontrada: {input_dir}", file=sys.stderr)
        return 1

    if args.chunks <= 0:
        print("--chunks deve ser um inteiro positivo.", file=sys.stderr)
        return 1

    if args.parallel_chunks <= 0:
        print("--parallel_chunks deve ser um inteiro positivo.", file=sys.stderr)
        return 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    verilog_files = find_verilog_files(input_dir)

    with output_path.open("w", encoding="utf-8") as out:
        write_line(
            out,
            (
                f"# inicio={datetime.now().isoformat(timespec='seconds')}"
                f"\tinput_dir={input_dir}"
                f"\toutput={output_path}"
                f"\tchunks={args.chunks}"
                f"\tparallel_chunks={args.parallel_chunks}"
                f"\ttotal_files={len(verilog_files)}"
            ),
        )

        if not verilog_files:
            write_line(out, "Nenhum arquivo Verilog encontrado.")
            return 0

        total_started = time.perf_counter()
        ok_count = 0
        error_count = 0

        for verilog_path in verilog_files:
            print(f"Tentando arquivo {verilog_path}")
            started = time.perf_counter()
            relative_path = str(verilog_path.relative_to(input_dir))

            try:
                tb = ThermalBits(str(verilog_path))
                entropy = tb.update_entropy(chunks=args.chunks, parallel_chunks=args.parallel_chunks)
                elapsed_s = time.perf_counter() - started
                write_line(
                    out,
                    format_result(
                        "OK",
                        relative_path,
                        f"entropy={entropy:.6f}",
                        elapsed_s,
                    ),
                )
                ok_count += 1
            except Exception as exc:
                elapsed_s = time.perf_counter() - started
                write_line(
                    out,
                    format_result(
                        "ERROR",
                        relative_path,
                        f"{type(exc).__name__}: {exc}",
                        elapsed_s,
                    ),
                )
                error_count += 1

        total_elapsed = time.perf_counter() - total_started
        write_line(
            out,
            (
                f"# fim={datetime.now().isoformat(timespec='seconds')}"
                f"\tok={ok_count}"
                f"\terros={error_count}"
                f"\ttotal_elapsed_s={total_elapsed:.3f}"
            ),
        )

    return 0 if error_count == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
