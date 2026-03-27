import re

from .generate_overview import _state_overview


def _require_int_list(field_name: str, values: object) -> list[int]:
    if not isinstance(values, list):
        raise ValueError(f"Overview field '{field_name}' must be a list")
    out: list[int] = []
    for value in values:
        if not isinstance(value, int):
            raise ValueError(f"Overview field '{field_name}' must contain only integers")
        out.append(value)
    return out


def _sanitize_module_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]", "_", name.strip())
    if not cleaned:
        return "GeneratedModule"
    if cleaned[0].isdigit():
        return f"m_{cleaned}"
    return cleaned


def _literal_expr(signal_name: str, inv: int) -> str:
    return f"~{signal_name}" if inv else signal_name


def _parse_nodes(nodes_raw: object) -> dict[int, dict[str, object]]:
    if not isinstance(nodes_raw, list):
        raise ValueError("Overview field 'nodes' must be a list")

    parsed: dict[int, dict[str, object]] = {}
    for node in nodes_raw:
        if not isinstance(node, dict):
            raise ValueError("Each node must be an object")

        node_id = node.get("id")
        if not isinstance(node_id, int):
            raise ValueError("Each node must contain integer field 'id'")
        if node_id in parsed:
            raise ValueError(f"Duplicated node id in overview: {node_id}")

        if "op" not in node:
            raise ValueError(f"Node {node_id} must contain field 'op'")
        op = node.get("op")
        if op not in ("&", "|"):
            raise ValueError(f"Unsupported node operator for id {node_id}: {op}")

        fanin_raw = node.get("fanin")
        if not isinstance(fanin_raw, list) or len(fanin_raw) != 2:
            raise ValueError(f"Node {node_id} must contain exactly 2 fanins")

        fanin: list[tuple[int, int]] = []
        for item in fanin_raw:
            if not isinstance(item, list) or len(item) != 2:
                raise ValueError(f"Node {node_id} has invalid fanin entry: {item}")
            fanin_id, inv = item
            if not isinstance(fanin_id, int):
                raise ValueError(f"Node {node_id} has non-integer fanin id: {fanin_id}")
            if inv not in (0, 1):
                raise ValueError(f"Node {node_id} has invalid inversion flag: {inv}")
            fanin.append((fanin_id, inv))

        parsed[node_id] = {"op": op, "fanin": fanin}

    return parsed


def write_verilog(
    self,
    output_path: str,
    module_name: str | None = None,
) -> None:
    overview = _state_overview(self)
    pis = _require_int_list("pis", overview["pis"])
    pos = _require_int_list("pos", overview["pos"])
    node_by_id = _parse_nodes(overview["nodes"])

    if len(set(pis)) != len(pis):
        raise ValueError("Overview field 'pis' contains duplicated ids")

    node_ids = set(node_by_id)
    pi_ids = set(pis)
    if node_ids & pi_ids:
        overlap = sorted(node_ids & pi_ids)
        raise ValueError(f"Primary inputs and nodes share IDs: {overlap}")

    known_ids = pi_ids | node_ids
    for node_id, node in node_by_id.items():
        fanin = node["fanin"]  # type: ignore[index]
        for fanin_id, _ in fanin:
            if fanin_id not in known_ids:
                raise ValueError(f"Node {node_id} references unknown fanin id: {fanin_id}")

    for po_id in pos:
        if po_id not in known_ids:
            raise ValueError(f"Overview output id has no source signal: {po_id}")

    if module_name is None:
        file_name = overview["file_name"]
        if isinstance(file_name, str) and file_name.strip():
            module_name = file_name.rsplit(".", 1)[0]
        else:
            module_name = "generated_module"
    module_name = _sanitize_module_name(module_name)

    signal_name_by_id: dict[int, str] = {}
    for pi_id in pis:
        signal_name_by_id[pi_id] = f"pi{pi_id}"
    for node_id in sorted(node_ids):
        signal_name_by_id[node_id] = f"n{node_id}"

    input_ports = [signal_name_by_id[pi_id] for pi_id in pis]
    output_ports = [f"po{idx}" for idx in range(len(pos))]
    wire_names = [signal_name_by_id[node_id] for node_id in sorted(node_ids)]
    module_ports = input_ports + output_ports

    lines: list[str] = []
    if module_ports:
        lines.append(f"module {module_name} (")
        for idx, port_name in enumerate(module_ports):
            suffix = "," if idx < len(module_ports) - 1 else ""
            lines.append(f"    {port_name}{suffix}")
        lines.append(");")
    else:
        lines.append(f"module {module_name} ();")

    if input_ports:
        lines.append(f"    input  {', '.join(input_ports)};")
    if output_ports:
        lines.append(f"    output {', '.join(output_ports)};")
    if wire_names:
        lines.append(f"    wire   {', '.join(wire_names)};")

    if node_by_id or output_ports:
        lines.append("")

    for node_id in sorted(node_by_id):
        node = node_by_id[node_id]
        op = node["op"]  # type: ignore[index]
        fanin = node["fanin"]  # type: ignore[index]
        left_id, left_inv = fanin[0]
        right_id, right_inv = fanin[1]
        left_expr = _literal_expr(signal_name_by_id[left_id], left_inv)
        right_expr = _literal_expr(signal_name_by_id[right_id], right_inv)
        lines.append(
            f"    assign {signal_name_by_id[node_id]} = {left_expr} {op} {right_expr};"
        )

    for idx, po_id in enumerate(pos):
        lines.append(f"    assign {output_ports[idx]} = {signal_name_by_id[po_id]};")

    lines.append("endmodule")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
