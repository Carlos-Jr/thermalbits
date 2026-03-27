import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from thermalbits import ThermalBits
from thermalbits.generate_overview import _compute_overview


def test_compute_overview_uses_fanout_schema(tmp_path: Path) -> None:
    verilog_path = tmp_path / "simple.v"
    verilog_path.write_text(
        "\n".join(
            [
                "module simple(a, b, y);",
                "    input a, b;",
                "    output y;",
                "    assign y = a & ~b;",
                "endmodule",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    overview = _compute_overview(str(verilog_path))

    assert overview == {
        "file_name": "simple.v",
        "pis": [0, 1],
        "pos": [2],
        "nodes": [
            {
                "id": 2,
                "fanin": [[0, 0], [1, 0]],
                "fanout": [{"input": [0, 1], "invert": [0, 1], "op": "&"}],
                "level": 1,
                "suport": [0, 1],
            }
        ],
    }


def test_compute_overview_uses_wire_fanout_for_unary_assign(tmp_path: Path) -> None:
    verilog_path = tmp_path / "wire.v"
    verilog_path.write_text(
        "\n".join(
            [
                "module wire_only(a, y);",
                "    input a;",
                "    output y;",
                "    assign y = ~a;",
                "endmodule",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    overview = _compute_overview(str(verilog_path))

    assert overview["nodes"] == [
        {
            "id": 1,
            "fanin": [[0, 0]],
            "fanout": [{"input": [0], "invert": [1], "op": "-"}],
            "level": 1,
            "suport": [0],
        }
    ]


def test_write_verilog_supports_multi_output_nodes(tmp_path: Path) -> None:
    tb = ThermalBits()
    tb.file_name = "special.json"
    tb.pi = [0, 1, 2]
    tb.po = [4]
    tb.node = [
        {
            "id": 3,
            "fanin": [[0, 0], [1, 0], [2, 0]],
            "fanout": [
                {"input": [0, 1, 2], "invert": [0, 0, 0], "op": "M"},
                {"input": [0, 1], "invert": [0, 0], "op": "&"},
                {"input": [0], "invert": [0], "op": "-"},
                {"input": [1], "invert": [1], "op": "-"},
            ],
            "level": 1,
            "suport": [0, 1, 2],
        },
        {
            "id": 4,
            "fanin": [[3, 1], [3, 2]],
            "fanout": [{"input": [0, 1], "invert": [0, 0], "op": "|"}],
            "level": 2,
            "suport": [0, 1, 2],
        },
    ]

    output_path = tmp_path / "special.v"
    tb.write_verilog(str(output_path), module_name="special")

    rendered = output_path.read_text(encoding="utf-8")

    assert "assign n3 = (pi0 & pi1) | (pi0 & pi2) | (pi1 & pi2);" in rendered
    assert "assign n3_o1 = pi0 & pi1;" in rendered
    assert "assign n3_o2 = pi0;" in rendered
    assert "assign n3_o3 = ~pi1;" in rendered
    assert "assign n4 = n3_o1 | n3_o2;" in rendered
    assert "assign po0 = n4;" in rendered


def test_sin_epfl_entropy_matches_expected_value() -> None:
    tb = ThermalBits("test_files/EPFL/sin.v")

    assert tb.file_name == "sin.v"
    assert tb.pi
    assert tb.po
    assert tb.node

    entropy = tb.update_entropy(chunks=None)

    assert entropy == pytest.approx(3409.470823, abs=1e-6)
    assert tb.entropy == pytest.approx(3409.470823, abs=1e-6)
