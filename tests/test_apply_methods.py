import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from thermalbits import DEPTH_ORIENTED, ENERGY_ORIENTED, ThermalBits
from thermalbits.apply_methods import METHOD_REGISTRY


def _build_branching_tb() -> ThermalBits:
    tb = ThermalBits()
    tb.file_name = "branching.v"
    tb.pi = [0, 1]
    tb.po = [7, 8, 9]
    tb.node = [
        {
            "id": 2,
            "fanin": [[0, 0], [1, 0]],
            "fanout": [{"input": [0, 1], "invert": [0, 0], "op": "&"}],
            "level": 1,
            "suport": [0, 1],
        },
        {
            "id": 3,
            "fanin": [[2, 0], [0, 0]],
            "fanout": [{"input": [0, 1], "invert": [0, 0], "op": "|"}],
            "level": 2,
            "suport": [0, 1],
        },
        {
            "id": 4,
            "fanin": [[2, 0], [1, 0]],
            "fanout": [{"input": [0, 1], "invert": [1, 0], "op": "&"}],
            "level": 2,
            "suport": [0, 1],
        },
        {
            "id": 10,
            "fanin": [[0, 0], [1, 0]],
            "fanout": [{"input": [0, 1], "invert": [1, 0], "op": "|"}],
            "level": 1,
            "suport": [0, 1],
        },
        {
            "id": 11,
            "fanin": [[3, 0], [1, 0]],
            "fanout": [{"input": [0, 1], "invert": [0, 0], "op": "^"}],
            "level": 3,
            "suport": [0, 1],
        },
        {
            "id": 12,
            "fanin": [[4, 0], [0, 0]],
            "fanout": [{"input": [0, 1], "invert": [0, 1], "op": "&"}],
            "level": 3,
            "suport": [0, 1],
        },
        {
            "id": 5,
            "fanin": [[2, 0], [11, 0]],
            "fanout": [{"input": [0, 1], "invert": [0, 0], "op": "^"}],
            "level": 4,
            "suport": [0, 1],
        },
        {
            "id": 6,
            "fanin": [[2, 0], [12, 0]],
            "fanout": [{"input": [0, 1], "invert": [0, 0], "op": "&"}],
            "level": 4,
            "suport": [0, 1],
        },
        {
            "id": 7,
            "fanin": [[5, 0], [1, 0]],
            "fanout": [{"input": [0, 1], "invert": [0, 0], "op": "|"}],
            "level": 5,
            "suport": [0, 1],
        },
        {
            "id": 8,
            "fanin": [[6, 0], [0, 0]],
            "fanout": [{"input": [0, 1], "invert": [0, 0], "op": "&"}],
            "level": 5,
            "suport": [0, 1],
        },
        {
            "id": 9,
            "fanin": [[2, 0], [10, 0]],
            "fanout": [{"input": [0, 1], "invert": [0, 0], "op": "|"}],
            "level": 2,
            "suport": [0, 1],
        },
    ]
    return tb


def _node_map(tb: ThermalBits) -> dict[int, dict[str, object]]:
    return {node["id"]: node for node in tb.node}


def _max_depth(tb: ThermalBits) -> int:
    return max((node["level"] for node in tb.node), default=0)


def _fanout_count(tb: ThermalBits) -> int:
    return sum(len(node["fanout"]) for node in tb.node)


def _assert_no_duplicate_wire_fanouts(tb: ThermalBits) -> None:
    for node in tb.node:
        wire_keys = [
            (tuple(fanout["input"]), tuple(fanout["invert"]))
            for fanout in node["fanout"]
            if fanout["op"] == "-"
        ]
        assert len(wire_keys) == len(set(wire_keys))


def _evaluate(tb: ThermalBits, pi_values: dict[int, int]) -> tuple[int, ...]:
    values = {(pi_id, 0): value for pi_id, value in pi_values.items()}

    for node in sorted(tb.node, key=lambda item: (item["level"], item["id"])):
        fanin_values = [
            values[(source_id, output_index)]
            for source_id, output_index in node["fanin"]
        ]
        for output_index, fanout in enumerate(node["fanout"]):
            terms = [
                fanin_values[input_index] ^ invert
                for input_index, invert in zip(fanout["input"], fanout["invert"])
            ]
            op = fanout["op"]
            if op == "&":
                value = int(all(terms))
            elif op == "|":
                value = int(any(terms))
            elif op == "^":
                value = 0
                for term in terms:
                    value ^= term
            elif op == "M":
                value = int(sum(terms) > len(terms) // 2)
            elif op == "-":
                value = terms[0]
            else:
                raise AssertionError(f"Unexpected op: {op}")
            values[(node["id"], output_index)] = value

    return tuple(values[(po_id, 0)] for po_id in tb.po)


def test_apply_requires_loaded_circuit() -> None:
    tb = ThermalBits()

    with pytest.raises(ValueError, match="Circuit has no nodes"):
        tb.apply(DEPTH_ORIENTED)


def test_apply_rejects_unknown_method() -> None:
    tb = _build_branching_tb()

    with pytest.raises(ValueError, match="Unknown apply method"):
        tb.apply("area_oriented")


def test_apply_depth_and_energy_use_different_selection_policies(tmp_path: Path) -> None:
    assert METHOD_REGISTRY[DEPTH_ORIENTED]
    assert METHOD_REGISTRY[ENERGY_ORIENTED]

    original_tb = _build_branching_tb()
    original_depth = _max_depth(original_tb)
    original_fanouts = _fanout_count(original_tb)

    depth_tb = _build_branching_tb()
    depth_tb.entropy = 123.0
    returned_tb = depth_tb.apply(DEPTH_ORIENTED)

    energy_tb = _build_branching_tb().apply(ENERGY_ORIENTED)

    assert returned_tb is depth_tb
    assert depth_tb.entropy is None

    depth_nodes = _node_map(depth_tb)
    energy_nodes = _node_map(energy_tb)

    assert _max_depth(depth_tb) == original_depth
    assert _max_depth(energy_tb) > original_depth
    assert _fanout_count(depth_tb) > original_fanouts
    assert _fanout_count(energy_tb) > _fanout_count(depth_tb)
    _assert_no_duplicate_wire_fanouts(depth_tb)
    _assert_no_duplicate_wire_fanouts(energy_tb)
    for pi0 in (0, 1):
        for pi1 in (0, 1):
            pi_values = {0: pi0, 1: pi1}
            assert _evaluate(depth_tb, pi_values) == _evaluate(original_tb, pi_values)
            assert _evaluate(energy_tb, pi_values) == _evaluate(original_tb, pi_values)

    assert any(ref[0] == 2 for ref in depth_nodes[4]["fanin"])
    assert not any(ref[0] == 2 for ref in energy_nodes[4]["fanin"])
    assert any(ref[0] == 3 for ref in energy_nodes[4]["fanin"])

    assert any(ref == [2, 0] for ref in depth_nodes[9]["fanin"])
    assert any(ref[0] == 4 for ref in energy_nodes[9]["fanin"])

    assert depth_nodes[9]["level"] == 2
    assert energy_nodes[9]["level"] > depth_nodes[9]["level"]
    assert depth_nodes[9]["suport"] == [0, 1]
    assert energy_nodes[9]["suport"] == [0, 1]

    json_path = tmp_path / "transformed.json"
    verilog_path = tmp_path / "transformed.v"

    energy_tb.write_json(str(json_path))
    energy_tb.write_verilog(str(verilog_path), module_name="branching_transformed")

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["nodes"]
    assert "suport" in payload["nodes"][0]

    rendered = verilog_path.read_text(encoding="utf-8")
    assert "module branching_transformed" in rendered
    assert "assign po0" in rendered
