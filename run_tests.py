#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

from thermalbits import DEPTH_ORIENTED, ENERGY_ORIENTED, ThermalBits


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Calcula tamanho, profundidade e energia de arquivos Verilog em CSV."
    )
    parser.add_argument(
        "input_dir",
        help="Pasta contendo os arquivos Verilog (.v e .sv). A busca eh recursiva.",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="entropy_results.csv",
        help="Arquivo CSV para registrar os resultados.",
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
    parser.add_argument(
        "--energy-oriented",
        action="store_true",
        help=(
            "Inclui o metodo Energy-Oriented (EO). Se nenhum metodo for "
            "selecionado, EO e DO sao executados por padrao."
        ),
    )
    parser.add_argument(
        "--depth-oriented",
        action="store_true",
        help=(
            "Inclui o metodo Depth-Oriented (DO). Se nenhum metodo for "
            "selecionado, EO e DO sao executados por padrao."
        ),
    )
    parser.add_argument(
        "--images-dir",
        default=None,
        help=(
            "Pasta opcional para salvar imagens PNG dos circuitos de cada "
            "arquivo/metodo."
        ),
    )
    parser.add_argument(
        "--image-orientation",
        choices=("horizontal", "vertical"),
        default="horizontal",
        help="Orientacao das imagens geradas com --images-dir (padrao: horizontal).",
    )
    return parser.parse_args()


def find_verilog_files(root: Path) -> list[Path]:
    files = [path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in {".v", ".sv"}]
    return sorted(files)


def circuit_size_and_depth(tb: ThermalBits) -> tuple[int, int]:
    size = len(tb.node)
    depth = max((int(node.get("level", 0)) for node in tb.node), default=0)
    return size, depth


def image_output_path(images_dir: Path, relative_path: Path, method: str) -> Path:
    image_name = f"{relative_path.stem}_{method}.png"
    return images_dir / relative_path.parent / image_name


def selected_methods(args: argparse.Namespace) -> list[tuple[str, str | None]]:
    methods: list[tuple[str, str | None]] = [("original", None)]
    run_all_transforms = not args.energy_oriented and not args.depth_oriented

    if args.energy_oriented or run_all_transforms:
        methods.append(("eo", ENERGY_ORIENTED))
    if args.depth_oriented or run_all_transforms:
        methods.append(("do", DEPTH_ORIENTED))

    return methods


def main() -> int:
    args = parse_args()
    input_dir = Path(args.input_dir).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    images_dir = (
        Path(args.images_dir).expanduser().resolve()
        if args.images_dir is not None
        else None
    )

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
    if images_dir is not None:
        images_dir.mkdir(parents=True, exist_ok=True)
    verilog_files = find_verilog_files(input_dir)

    methods = selected_methods(args)
    with output_path.open("w", encoding="utf-8", newline="") as out:
        writer = csv.DictWriter(
            out,
            fieldnames=[
                "file",
                "method",
                "size",
                "depth",
                "energy",
                "entropy_time_s",
                "image_path",
            ],
        )
        writer.writeheader()
        out.flush()

        print(f"input_dir={input_dir}")
        print(f"output={output_path}")
        print(f"chunks={args.chunks}")
        print(f"parallel_chunks={args.parallel_chunks}")
        print(f"methods={','.join(label for label, _method in methods)}")
        if images_dir is not None:
            print(f"images_dir={images_dir}")
            print(f"image_orientation={args.image_orientation}")
        print(f"total_files={len(verilog_files)}")

        if not verilog_files:
            print("Nenhum arquivo Verilog encontrado.")
            return 0

        total_started = time.perf_counter()
        ok_count = 0
        error_count = 0

        for verilog_path in verilog_files:
            relative = verilog_path.relative_to(input_dir)
            relative_path = str(relative)
            print(f"Arquivo: {relative_path}")

            try:
                tb = ThermalBits(str(verilog_path))
            except Exception as exc:
                print(
                    f"ERROR\t{relative_path}\tload\t{type(exc).__name__}: {exc}",
                    file=sys.stderr,
                )
                error_count += 1
                continue

            for label, method in methods:
                started = time.perf_counter()
                try:
                    variant = tb.copy().apply(method) if method is not None else tb
                    size, depth = circuit_size_and_depth(variant)
                    entropy_started = time.perf_counter()
                    energy = variant.update_entropy(
                        chunks=args.chunks,
                        parallel_chunks=args.parallel_chunks,
                    )
                    entropy_time_s = time.perf_counter() - entropy_started
                    image_path = ""
                    if images_dir is not None:
                        png_path = image_output_path(images_dir, relative, label)
                        png_path.parent.mkdir(parents=True, exist_ok=True)
                        variant.visualize_dag(
                            str(png_path),
                            orientation=args.image_orientation,
                        )
                        image_path = str(png_path)
                    elapsed_s = time.perf_counter() - started
                    writer.writerow(
                        {
                            "file": relative_path,
                            "method": label,
                            "size": size,
                            "depth": depth,
                            "energy": f"{energy:.6f}",
                            "entropy_time_s": f"{entropy_time_s:.3f}",
                            "image_path": image_path,
                        }
                    )
                    out.flush()
                    print(
                        f"OK\t{relative_path}\t{label}"
                        f"\tsize={size}\tdepth={depth}\tenergy={energy:.6f}"
                        f"\tentropy_time_s={entropy_time_s:.3f}"
                        f"\timage={image_path or '-'}"
                        f"\telapsed_s={elapsed_s:.3f}"
                    )
                    ok_count += 1
                except Exception as exc:
                    elapsed_s = time.perf_counter() - started
                    print(
                        f"ERROR\t{relative_path}\t{label}"
                        f"\t{type(exc).__name__}: {exc}"
                        f"\telapsed_s={elapsed_s:.3f}",
                        file=sys.stderr,
                    )
                    error_count += 1

        total_elapsed = time.perf_counter() - total_started
        print(
            f"fim\tok={ok_count}\terros={error_count}"
            f"\ttotal_elapsed_s={total_elapsed:.3f}"
        )

    return 0 if error_count == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
