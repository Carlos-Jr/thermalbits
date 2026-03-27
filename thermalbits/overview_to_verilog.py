import re
from itertools import combinations

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


def _join_terms(terms: list[str], op: str) -> str:
    if not terms:
        raise ValueError("A fanout expression requires at least one input term")
    if len(terms) == 1:
        return terms[0]
    return f" {op} ".join(terms)


def _majority_expr(terms: list[str]) -> str:
    if not terms:
        raise ValueError("Majority requires at least one input")
    if len(terms) % 2 == 0:
        raise ValueError("Majority requires an odd number of inputs")

    threshold = len(terms) // 2 + 1
    product_terms = []
    for combo in combinations(terms, threshold):
        product = _join_terms(list(combo), "&")
        if len(combo) > 1:
            product = f"({product})"
        product_terms.append(product)
    return _join_terms(product_terms, "|")


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

        fanin_raw = node.get("fanin")
        if not isinstance(fanin_raw, list):
            raise ValueError(f"Node {node_id} field 'fanin' must be a list")

        fanin: list[tuple[int, int]] = []
        for item in fanin_raw:
            if not isinstance(item, list) or len(item) != 2:
                raise ValueError(f"Node {node_id} has invalid fanin entry: {item}")
            fanin_id, output_index = item
            if not isinstance(fanin_id, int):
                raise ValueError(f"Node {node_id} has non-integer fanin id: {fanin_id}")
            if not isinstance(output_index, int) or output_index < 0:
                raise ValueError(
                    f"Node {node_id} has invalid fanin output index: {output_index}"
                )
            fanin.append((fanin_id, output_index))

        fanout_raw = node.get("fanout")
        if not isinstance(fanout_raw, list) or not fanout_raw:
            raise ValueError(f"Node {node_id} field 'fanout' must be a non-empty list")

        fanout: list[dict[str, object]] = []
        for fanout_idx, fanout_entry in enumerate(fanout_raw):
            if not isinstance(fanout_entry, dict):
                raise ValueError(
                    f"Node {node_id} has invalid fanout entry at index {fanout_idx}"
                )

            input_raw = fanout_entry.get("input")
            invert_raw = fanout_entry.get("invert")
            op = fanout_entry.get("op")

            if not isinstance(input_raw, list):
                raise ValueError(
                    f"Node {node_id} fanout[{fanout_idx}] field 'input' must be a list"
                )
            if not isinstance(invert_raw, list):
                raise ValueError(
                    f"Node {node_id} fanout[{fanout_idx}] field 'invert' must be a list"
                )
            if len(input_raw) != len(invert_raw):
                raise ValueError(
                    f"Node {node_id} fanout[{fanout_idx}] fields 'input' and 'invert' must have the same length"
                )
            if op not in ("&", "|", "^", "M", "-"):
                raise ValueError(
                    f"Unsupported node operator for id {node_id} fanout[{fanout_idx}]: {op}"
                )

            input_indices: list[int] = []
            invert_flags: list[int] = []
            for input_idx in input_raw:
                if not isinstance(input_idx, int) or input_idx < 0:
                    raise ValueError(
                        f"Node {node_id} fanout[{fanout_idx}] has invalid input index: {input_idx}"
                    )
                if input_idx >= len(fanin):
                    raise ValueError(
                        f"Node {node_id} fanout[{fanout_idx}] references fanin index {input_idx}, but fanin has size {len(fanin)}"
                    )
                input_indices.append(input_idx)
            for invert_flag in invert_raw:
                if invert_flag not in (0, 1):
                    raise ValueError(
                        f"Node {node_id} fanout[{fanout_idx}] has invalid invert flag: {invert_flag}"
                    )
                invert_flags.append(invert_flag)

            if not input_indices:
                raise ValueError(f"Node {node_id} fanout[{fanout_idx}] must have inputs")
            if op == "-" and len(input_indices) != 1:
                raise ValueError(
                    f"Node {node_id} fanout[{fanout_idx}] wire output must have exactly 1 input"
                )
            if op == "M" and len(input_indices) % 2 == 0:
                raise ValueError(
                    f"Node {node_id} fanout[{fanout_idx}] majority output must have an odd number of inputs"
                )

            fanout.append(
                {
                    "input": input_indices,
                    "invert": invert_flags,
                    "op": op,
                }
            )

        level = node.get("level", 0)
        if not isinstance(level, int):
            raise ValueError(f"Node {node_id} field 'level' must be an integer")

        parsed[node_id] = {"fanin": fanin, "fanout": fanout, "level": level}

    return parsed


def _fanout_expr(
    node_id: int,
    fanout_idx: int,
    node: dict[str, object],
    signal_name_by_ref: dict[tuple[int, int], str],
) -> str:
    fanin = node["fanin"]  # type: ignore[index]
    fanout = node["fanout"][fanout_idx]  # type: ignore[index]
    input_indices = fanout["input"]  # type: ignore[index]
    invert_flags = fanout["invert"]  # type: ignore[index]
    op = fanout["op"]  # type: ignore[index]

    terms = []
    for input_idx, invert_flag in zip(input_indices, invert_flags):
        source_ref = fanin[input_idx]
        signal_name = signal_name_by_ref[source_ref]
        terms.append(_literal_expr(signal_name, invert_flag))

    if op == "-":
        return terms[0]
    if op in ("&", "|", "^"):
        return _join_terms(terms, op)
    if op == "M":
        return _majority_expr(terms)
    raise ValueError(f"Unsupported node operator for id {node_id} fanout[{fanout_idx}]: {op}")


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
        for fanin_id, output_index in fanin:
            if fanin_id not in known_ids:
                raise ValueError(f"Node {node_id} references unknown fanin id: {fanin_id}")
            if fanin_id in pi_ids and output_index != 0:
                raise ValueError(
                    f"Node {node_id} references primary input {fanin_id} with invalid output index {output_index}"
                )
            if fanin_id in node_by_id:
                source_fanout = node_by_id[fanin_id]["fanout"]  # type: ignore[index]
                if output_index >= len(source_fanout):
                    raise ValueError(
                        f"Node {node_id} references node {fanin_id} output index {output_index}, but that node has only {len(source_fanout)} outputs"
                    )

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

    signal_name_by_ref: dict[tuple[int, int], str] = {}
    for pi_id in pis:
        signal_name_by_ref[(pi_id, 0)] = f"pi{pi_id}"

    ordered_node_ids = sorted(
        node_by_id,
        key=lambda current_id: (node_by_id[current_id]["level"], current_id),  # type: ignore[index]
    )
    for node_id in ordered_node_ids:
        fanout = node_by_id[node_id]["fanout"]  # type: ignore[index]
        for fanout_idx in range(len(fanout)):
            if fanout_idx == 0:
                signal_name_by_ref[(node_id, fanout_idx)] = f"n{node_id}"
            else:
                signal_name_by_ref[(node_id, fanout_idx)] = f"n{node_id}_o{fanout_idx}"

    input_ports = [signal_name_by_ref[(pi_id, 0)] for pi_id in pis]
    output_ports = [f"po{idx}" for idx in range(len(pos))]
    wire_names = [
        signal_name_by_ref[(node_id, fanout_idx)]
        for node_id in ordered_node_ids
        for fanout_idx in range(len(node_by_id[node_id]["fanout"]))  # type: ignore[index]
    ]
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

    for node_id in ordered_node_ids:
        node = node_by_id[node_id]
        fanout = node["fanout"]  # type: ignore[index]
        for fanout_idx in range(len(fanout)):
            signal_name = signal_name_by_ref[(node_id, fanout_idx)]
            expr = _fanout_expr(node_id, fanout_idx, node, signal_name_by_ref)
            lines.append(f"    assign {signal_name} = {expr};")

    for idx, po_id in enumerate(pos):
        lines.append(f"    assign {output_ports[idx]} = {signal_name_by_ref[(po_id, 0)]};")

    lines.append("endmodule")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
