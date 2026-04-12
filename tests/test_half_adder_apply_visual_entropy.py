import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from thermalbits import DEPTH_ORIENTED, ENERGY_ORIENTED, ThermalBits
from thermalbits.update_entropy import _BINARY


def test_half_adder_depth_and_energy_visual_entropy(
    output_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("matplotlib")
    if not _BINARY.exists():
        pytest.skip(f"circuit_sim binary not found at {_BINARY}")

    mplconfigdir = output_dir / "mplconfig"
    mplconfigdir.mkdir(exist_ok=True)
    monkeypatch.setenv("MPLCONFIGDIR", str(mplconfigdir))

    original_tb = ThermalBits("test_files/half_adder.v")
    depth_tb = original_tb.copy().apply(DEPTH_ORIENTED)
    energy_tb = original_tb.copy().apply(ENERGY_ORIENTED)

    original_img = output_dir / "half_adder_original_horizontal.png"
    depth_img = output_dir / "half_adder_depth_horizontal.png"
    energy_img = output_dir / "half_adder_energy_horizontal.png"

    original_tb.visualize_dag(str(original_img), orientation="horizontal")
    depth_tb.visualize_dag(str(depth_img), orientation="horizontal")
    energy_tb.visualize_dag(str(energy_img), orientation="horizontal")

    original_json = output_dir / "half_adder_original.json"
    depth_json = output_dir / "half_adder_depth.json"
    energy_json = output_dir / "half_adder_energy.json"

    original_tb.write_json(str(original_json))
    depth_tb.write_json(str(depth_json))
    energy_tb.write_json(str(energy_json))

    original_entropy = original_tb.update_entropy(chunks=None)
    depth_entropy = depth_tb.update_entropy(chunks=None)
    energy_entropy = energy_tb.update_entropy(chunks=None)

    def _circuit_stats(tb: ThermalBits) -> tuple[int, int]:
        """Retorna (tamanho, profundidade) do circuito."""
        nodes = tb.node
        size = len(nodes)
        depth = max((n["level"] for n in nodes), default=0)
        return size, depth

    orig_size, orig_depth = _circuit_stats(original_tb)
    dep_size, dep_depth = _circuit_stats(depth_tb)
    ene_size, ene_depth = _circuit_stats(energy_tb)

    print(f"\n{'Circuito':<20} {'Entropia':>10} {'Nos':>6} {'Profundidade':>13}")
    print("-" * 52)
    print(f"{'Original':<20} {original_entropy:>10.6f} {orig_size:>6} {orig_depth:>13}")
    print(f"{'Depth-oriented':<20} {depth_entropy:>10.6f} {dep_size:>6} {dep_depth:>13}")
    print(f"{'Energy-oriented':<20} {energy_entropy:>10.6f} {ene_size:>6} {ene_depth:>13}")

    print(f"\nOriginal image:      {original_img}")
    print(f"Depth-oriented image: {depth_img}")
    print(f"Energy-oriented image: {energy_img}")
    print(f"Original JSON:       {original_json}")
    print(f"Depth-oriented JSON:  {depth_json}")
    print(f"Energy-oriented JSON: {energy_json}")

    assert original_img.exists() and original_img.stat().st_size > 0
    assert depth_img.exists() and depth_img.stat().st_size > 0
    assert energy_img.exists() and energy_img.stat().st_size > 0

    assert original_json.exists() and original_json.stat().st_size > 0
    assert depth_json.exists() and depth_json.stat().st_size > 0
    assert energy_json.exists() and energy_json.stat().st_size > 0

    assert original_entropy == pytest.approx(original_tb.entropy, abs=1e-6)
    assert depth_entropy == pytest.approx(depth_tb.entropy, abs=1e-6)
    assert energy_entropy == pytest.approx(energy_tb.entropy, abs=1e-6)

    assert depth_tb.node != original_tb.node
    assert energy_tb.node != original_tb.node
    assert dep_depth == orig_depth
    assert ene_depth > orig_depth

    assert original_entropy == pytest.approx(3.76, abs=1e-2)
    assert depth_entropy == pytest.approx(1.88, abs=1e-2)
    assert energy_entropy == pytest.approx(0.69, abs=1e-2)
    assert energy_entropy < depth_entropy < original_entropy
