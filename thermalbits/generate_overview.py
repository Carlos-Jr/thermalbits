import json
from pathlib import Path

from .verilog_utils import (
    build_drivers,
    build_gates,
    compute_cone_for_gate,
    compute_levels,
    load_verilog,
)


def _build_signal_ids(inputs, gates):
    signal_to_id = {}
    next_id = 0
    for pi in inputs:
        if pi in signal_to_id:
            raise ValueError(f"Duplicated primary input: {pi}")
        signal_to_id[pi] = next_id
        next_id += 1
    for gate in gates:
        output_name = gate["output"]  # type: ignore[index]
        if output_name in signal_to_id:
            raise ValueError(
                f"Signal '{output_name}' is both a primary input and a gate output"
            )
        signal_to_id[output_name] = next_id
        next_id += 1
    return signal_to_id


def _compute_overview(verilog_path: str):
    inputs, outputs, wires, assigns = load_verilog(verilog_path)
    assign_dests = [dest for dest, _ in assigns]
    all_signals = list(dict.fromkeys(inputs + outputs + wires + assign_dests))

    gates = build_gates(assigns, all_signals)
    drivers = build_drivers(gates)
    levels = compute_levels(inputs, assigns, all_signals)
    signal_to_id = _build_signal_ids(inputs, gates)

    nodes = []
    for gate in gates:
        output_name = gate["output"]  # type: ignore[index]
        output_id = signal_to_id[output_name]
        fanin_terms = gate["fanin"]  # type: ignore[index]
        cone_inputs = compute_cone_for_gate(output_name, inputs, drivers)
        fanin = []
        for fanin_name, inv in fanin_terms:
            if fanin_name not in signal_to_id:
                raise ValueError(
                    f"Signal '{fanin_name}' used by '{output_name}' has no assigned integer ID"
                )
            fanin.append([signal_to_id[fanin_name], int(inv)])

        nodes.append(
            {
                "id": output_id,
                "op": gate["op"],  # type: ignore[index]
                "fanin": fanin,
                "level": int(levels.get(output_name, 0)),
                "suport": [signal_to_id[name] for name in cone_inputs],
            }
        )

    nodes = sorted(nodes, key=lambda node: node["id"])

    pos = []
    for output_name in outputs:
        if output_name not in signal_to_id:
            raise ValueError(f"Output '{output_name}' has no driver in the parsed netlist")
        pos.append(signal_to_id[output_name])

    return {
        "file_name": Path(verilog_path).name,
        "pis": [signal_to_id[name] for name in inputs],
        "pos": pos,
        "nodes": nodes,
    }


def generate_overview(self):
    if not self.verilog_path:
        raise ValueError(
            "This ThermalBits object has no verilog_path. "
            "Initialize with ThermalBits('netlist.v') or assign verilog_path before generate_overview()."
        )
    overview = _compute_overview(self.verilog_path)
    self.file_name = overview["file_name"]
    self.pi = overview["pis"]
    self.po = overview["pos"]
    self.node = overview["nodes"]
    return overview


def _state_overview(self):
    return {
        "file_name": self.file_name,
        "pis": self.pi,
        "pos": self.po,
        "nodes": self.node,
    }


def write_json(self, output_path: str) -> None:
    overview = _state_overview(self)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(overview, f, ensure_ascii=False, indent=2)
