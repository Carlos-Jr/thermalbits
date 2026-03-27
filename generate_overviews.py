import argparse
import json
import sys
from pathlib import Path

from thermalbits.generate_overview import _compute_overview


def generate_overviews(folder: Path) -> None:
    verilog_files = list(folder.glob("*.v"))

    if not verilog_files:
        print(f"Nenhum arquivo .v encontrado em: {folder}")
        return

    success = 0
    errors = 0

    for verilog_path in sorted(verilog_files):
        json_path = verilog_path.with_suffix(".json")
        try:
            overview = _compute_overview(str(verilog_path))
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(overview, f, ensure_ascii=False, indent=2)
            n_inputs = len(overview["pis"])
            n_outputs = len(overview["pos"])
            size = len(overview["nodes"])
            depth = max((n["level"] for n in overview["nodes"]), default=0)
            print(
                f"[OK] {verilog_path.name} -> {json_path.name} "
                f"| inputs={n_inputs}  outputs={n_outputs}  size={size}  depth={depth}"
            )
            success += 1
        except Exception as e:
            print(f"[ERRO] {verilog_path.name}: {e}", file=sys.stderr)
            errors += 1

    print(f"\n{success} arquivo(s) gerado(s), {errors} erro(s).")


def main():
    parser = argparse.ArgumentParser(
        description="Gera overviews JSON de arquivos Verilog em uma pasta."
    )
    parser.add_argument("folder", help="Pasta contendo os arquivos .v")
    args = parser.parse_args()

    folder = Path(args.folder)
    if not folder.is_dir():
        print(f"Erro: '{folder}' não é uma pasta válida.", file=sys.stderr)
        sys.exit(1)

    generate_overviews(folder)


if __name__ == "__main__":
    main()
