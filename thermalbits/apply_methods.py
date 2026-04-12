"""Transformation methods for ThermalBits overview circuits."""

from __future__ import annotations

import heapq
from collections import defaultdict
from copy import deepcopy
from typing import Callable

from .generate_overview import _state_overview

DEPTH_ORIENTED = "depth_oriented"
ENERGY_ORIENTED = "energy_oriented"

_SUPPORTED_OPS = {"&", "|", "^", "M", "-"}
_FORWARD_LIMIT = 2

Overview = dict[str, object]
Node = dict[str, object]
NodeLookup = dict[int, Node]
SelectionPolicy = Callable[[list[int]], list[int]]
Transformation = Callable[[Overview], Overview]


def _normalize_method(method: object) -> str:
    """Return a registry key from a public constant or string-like enum value."""

    if isinstance(method, str):
        normalized = method
    else:
        value = getattr(method, "value", None)
        if not isinstance(value, str):
            raise ValueError(
                "method must be a registered string constant, such as DEPTH_ORIENTED"
            )
        normalized = value
    return normalized.strip().lower()


def _require_int_list(field_name: str, values: object) -> list[int]:
    """Validate a top-level integer list field."""

    if not isinstance(values, list):
        raise ValueError(f"Overview field '{field_name}' must be a list")
    if not all(isinstance(value, int) for value in values):
        raise ValueError(f"Overview field '{field_name}' must contain only integers")
    return list(values)


def _fanin_list(node: Node) -> list[list[int]]:
    fanin = node.get("fanin")
    if not isinstance(fanin, list):
        raise ValueError(f"Node {node.get('id')} field 'fanin' must be a list")

    parsed: list[list[int]] = []
    for item in fanin:
        if not isinstance(item, list) or len(item) != 2:
            raise ValueError(f"Node {node.get('id')} has invalid fanin entry: {item}")
        source_id, output_index = item
        if not isinstance(source_id, int) or not isinstance(output_index, int):
            raise ValueError(f"Node {node.get('id')} has non-integer fanin entry: {item}")
        if output_index < 0:
            raise ValueError(
                f"Node {node.get('id')} has invalid fanin output index: {output_index}"
            )
        parsed.append(item)
    return parsed


def _fanout_list(node: Node) -> list[dict[str, object]]:
    fanout = node.get("fanout")
    if not isinstance(fanout, list) or not fanout:
        raise ValueError(f"Node {node.get('id')} field 'fanout' must be a non-empty list")

    parsed: list[dict[str, object]] = []
    for fanout_idx, item in enumerate(fanout):
        if not isinstance(item, dict):
            raise ValueError(
                f"Node {node.get('id')} has invalid fanout entry at index {fanout_idx}"
            )
        input_raw = item.get("input")
        invert_raw = item.get("invert")
        op = item.get("op")
        if not isinstance(input_raw, list) or not isinstance(invert_raw, list):
            raise ValueError(
                f"Node {node.get('id')} fanout[{fanout_idx}] must contain list fields 'input' and 'invert'"
            )
        if len(input_raw) != len(invert_raw):
            raise ValueError(
                f"Node {node.get('id')} fanout[{fanout_idx}] fields 'input' and 'invert' must have the same length"
            )
        if op not in _SUPPORTED_OPS:
            raise ValueError(
                f"Unsupported node operator for id {node.get('id')} fanout[{fanout_idx}]: {op}"
            )
        for input_idx in input_raw:
            if not isinstance(input_idx, int) or input_idx < 0:
                raise ValueError(
                    f"Node {node.get('id')} fanout[{fanout_idx}] has invalid input index: {input_idx}"
                )
        for invert_flag in invert_raw:
            if invert_flag not in (0, 1):
                raise ValueError(
                    f"Node {node.get('id')} fanout[{fanout_idx}] has invalid invert flag: {invert_flag}"
                )
        parsed.append(item)
    return parsed


def _node_level(node: Node) -> int:
    level = node.get("level", 0)
    if not isinstance(level, int):
        raise ValueError(f"Node {node.get('id')} field 'level' must be an integer")
    return level


def _wire_fanout_count(node: Node) -> int:
    """Count wire (op='-') fanout entries on a node."""
    return sum(1 for entry in node.get("fanout", []) if entry.get("op") == "-")


def _build_node_lookup(nodes_raw: object) -> NodeLookup:
    """Validate the node list and return nodes indexed by id."""

    if not isinstance(nodes_raw, list):
        raise ValueError("Overview field 'nodes' must be a list")

    node_by_id: NodeLookup = {}
    for raw_node in nodes_raw:
        if not isinstance(raw_node, dict):
            raise ValueError("Each node must be an object")
        node_id = raw_node.get("id")
        if not isinstance(node_id, int):
            raise ValueError("Each node must contain integer field 'id'")
        if node_id in node_by_id:
            raise ValueError(f"Duplicated node id in overview: {node_id}")

        _fanin_list(raw_node)
        fanout = _fanout_list(raw_node)
        fanin = raw_node["fanin"]
        for fanout_idx, fanout_entry in enumerate(fanout):
            input_indices = fanout_entry["input"]
            if any(input_idx >= len(fanin) for input_idx in input_indices):
                raise ValueError(
                    f"Node {node_id} fanout[{fanout_idx}] references invalid fanin index"
                )
        _node_level(raw_node)

        suport = raw_node.get("suport", [])
        if not isinstance(suport, list) or not all(isinstance(value, int) for value in suport):
            raise ValueError(f"Node {node_id} field 'suport' must be a list of integers")

        node_by_id[node_id] = raw_node

    return node_by_id


def _state_overview_like(self) -> Overview:
    """Return a deep copy of the current ThermalBits state as an overview-like dict."""

    return deepcopy(_state_overview(self))


def _build_children_index(nodes: list[Node], node_by_id: NodeLookup) -> dict[int, list[int]]:
    """Map each node id to the ids of internal nodes that consume it via non-wire fanouts.

    Connections through wire (op='-') fanouts represent forwarded signals and
    are excluded, matching the reference algorithm's 'ignore forward edges'.
    """

    node_ids = {int(node["id"]) for node in nodes}
    children: dict[int, set[int]] = {node_id: set() for node_id in node_ids}

    for node in nodes:
        child_id = int(node["id"])
        for source_id, output_index in _fanin_list(node):
            if source_id not in node_ids:
                continue
            source_fanouts = node_by_id[source_id].get("fanout", [])
            if output_index < len(source_fanouts) and source_fanouts[output_index].get("op") == "-":
                continue
            children[source_id].add(child_id)

    return {node_id: sorted(children[node_id]) for node_id in sorted(children)}


def _ranked_children(
    node_id: int,
    children_index: dict[int, list[int]],
    node_by_id: NodeLookup,
) -> list[tuple[int, list[int]]]:
    """Group direct children by level in ascending order."""

    grouped: dict[int, list[int]] = defaultdict(list)
    for child_id in children_index.get(node_id, []):
        grouped[_node_level(node_by_id[child_id])].append(child_id)
    return [
        (level, sorted(grouped[level]))
        for level in sorted(grouped)
    ]


def _choose(
    grouped_children: list[int],
    outputs: set[int],
    node_by_id: NodeLookup,
    policy: SelectionPolicy,
) -> list[int]:
    """Filter terminal/full nodes and delegate the final selection to the method policy."""

    valid_children = [
        child_id
        for child_id in grouped_children
        if child_id not in outputs and _wire_fanout_count(node_by_id[child_id]) < _FORWARD_LIMIT
    ]
    return policy(valid_children)


def _add_wire_fanout(node: Node, local_fanin_idx: int) -> int:
    """
    Garante que *node* tenha um fanout WIRE (op="-") que repassa o input
    local_fanin_idx sem inversao.  Retorna o indice do fanout (novo ou existente).
    """
    for i, entry in enumerate(_fanout_list(node)):
        if (
            entry.get("op") == "-"
            and entry.get("input") == [local_fanin_idx]
            and entry.get("invert") == [0]
        ):
            return i
    new_idx = len(node["fanout"])
    node["fanout"].append({"op": "-", "input": [local_fanin_idx], "invert": [0]})
    return new_idx


def _normalize_node_fanin(node: Node) -> None:
    """Collapse duplicate fanin references and update local input indices."""

    fanin = _fanin_list(node)
    if not fanin:
        return

    deduped_fanin: list[list[int]] = []
    ref_to_index: dict[tuple[int, int], int] = {}
    index_remap: dict[int, int] = {}

    for old_index, ref in enumerate(fanin):
        key = (ref[0], ref[1])
        new_index = ref_to_index.get(key)
        if new_index is None:
            new_index = len(deduped_fanin)
            ref_to_index[key] = new_index
            deduped_fanin.append([ref[0], ref[1]])
        index_remap[old_index] = new_index

    if len(deduped_fanin) == len(fanin):
        return

    node["fanin"] = deduped_fanin
    for fanout_entry in _fanout_list(node):
        input_indices = fanout_entry["input"]
        fanout_entry["input"] = [index_remap[input_idx] for input_idx in input_indices]


def _make_chain(
    node_id: int,
    choices: list[int],
    outputs: set[int],
    node_by_id: NodeLookup,
) -> None:
    """
    Constroi uma cadeia de fanouts a partir de node_id.

    choices[0] mantem a ligacao direta com node_id.
    Para cada choices[i] (i >= 1): adiciona um fanout WIRE em choices[i-1]
    que repassa o sinal de node_id, e recabeia choices[i] para ler desse WIRE.
    Os outputs sao recabeados para o ultimo WIRE da cadeia.

    carry_fanin_idx rastreia, em cada passo, qual indice LOCAL no no anterior
    carrega o sinal repassado de node_id.
    """
    if not choices:
        return

    previous_id = node_id
    # indice local no `previous_id` que carrega o sinal de node_id
    carry_fanin_idx: int | None = None

    for index, child_id in enumerate(choices):
        child_node = node_by_id[child_id]
        child_fanin = _fanin_list(child_node)

        if index == 0:
            # choices[0] le node_id diretamente; apenas localiza o indice de carry.
            for k, (src, _out) in enumerate(child_fanin):
                if src == node_id:
                    carry_fanin_idx = k
                    break
        else:
            if carry_fanin_idx is None:
                previous_id = child_id
                continue

            prev_node = node_by_id[previous_id]

            # Adiciona WIRE no no anterior que repassa o sinal de node_id.
            wire_idx = _add_wire_fanout(prev_node, carry_fanin_idx)

            # Recabeia child: todas as entradas [node_id, *] → [previous_id, wire_idx].
            for ref in child_fanin:
                if ref[0] == node_id:
                    ref[0] = previous_id
                    ref[1] = wire_idx

            _normalize_node_fanin(child_node)

            # Atualiza carry para a proxima iteracao: acha o indice local
            # de [previous_id, wire_idx] no fanin normalizado.
            carry_fanin_idx = None
            for k, (src, out) in enumerate(_fanin_list(child_node)):
                if src == previous_id and out == wire_idx:
                    carry_fanin_idx = k
                    break

        previous_id = child_id

    # Recabeia os outputs para o ultimo WIRE da cadeia.
    last_choice_id = choices[-1]
    last_choice_node = node_by_id[last_choice_id]

    for output_id in sorted(
        outputs,
        key=lambda oid: (_node_level(node_by_id[oid]), oid),
    ):
        output_node = node_by_id[output_id]
        output_fanin = _fanin_list(output_node)

        if carry_fanin_idx is None or not any(src == node_id for src, _ in output_fanin):
            continue

        wire_idx = _add_wire_fanout(last_choice_node, carry_fanin_idx)

        for ref in output_fanin:
            if ref[0] == node_id:
                ref[0] = last_choice_id
                ref[1] = wire_idx

        _normalize_node_fanin(output_node)


def _recompute_levels_and_support(nodes: list[Node], pis: list[int]) -> None:
    """Rebuild topological levels and PI supports after rewiring."""

    node_by_id = _build_node_lookup(nodes)
    pi_set = set(pis)
    node_ids = set(node_by_id)

    children_by_id: dict[int, set[int]] = {node_id: set() for node_id in node_ids}
    indegree: dict[int, int] = {}

    for node_id, node in node_by_id.items():
        predecessors: set[int] = set()
        for source_id, output_index in _fanin_list(node):
            if source_id in pi_set:
                if output_index != 0:
                    raise ValueError(
                        f"Node {node_id} references primary input {source_id} with invalid output index {output_index}"
                    )
                continue
            if source_id not in node_ids:
                raise ValueError(f"Node {node_id} references unknown fanin id: {source_id}")
            if output_index >= len(_fanout_list(node_by_id[source_id])):
                raise ValueError(
                    f"Node {node_id} references node {source_id} output index {output_index}, but that node has only {len(_fanout_list(node_by_id[source_id]))} outputs"
                )
            predecessors.add(source_id)
            children_by_id[source_id].add(node_id)
        indegree[node_id] = len(predecessors)

    ready: list[int] = [node_id for node_id, count in indegree.items() if count == 0]
    heapq.heapify(ready)

    level_by_id: dict[int, int] = {}
    support_by_id: dict[int, list[int]] = {}
    processed = 0

    while ready:
        node_id = heapq.heappop(ready)
        node = node_by_id[node_id]

        max_level = 0
        support_set: set[int] = set()
        for source_id, _output_index in _fanin_list(node):
            if source_id in pi_set:
                support_set.add(source_id)
            else:
                max_level = max(max_level, level_by_id[source_id])
                support_set.update(support_by_id[source_id])

        node["level"] = max_level + 1 if _fanin_list(node) else 0
        node["suport"] = sorted(support_set)
        level_by_id[node_id] = int(node["level"])
        support_by_id[node_id] = list(node["suport"])
        processed += 1

        for child_id in sorted(children_by_id[node_id]):
            indegree[child_id] -= 1
            if indegree[child_id] == 0:
                heapq.heappush(ready, child_id)

    if processed != len(node_by_id):
        raise ValueError("Transformation created a cycle in the circuit overview")

    nodes.sort(key=lambda node: int(node["id"]))


def _select_depth_oriented(valid_children: list[int]) -> list[int]:
    """Pick one valid child from a single level group."""

    return valid_children[:1]


def _select_energy_oriented(valid_children: list[int]) -> list[int]:
    """Pick every valid child from a single level group."""

    return list(valid_children)


def _build_chain(overview: Overview, policy: SelectionPolicy) -> Overview:
    """Apply a chain-building policy over the whole circuit."""

    pis = _require_int_list("pis", overview.get("pis"))
    pos = _require_int_list("pos", overview.get("pos"))
    overview["pis"] = pis
    overview["pos"] = pos

    node_by_id = _build_node_lookup(overview.get("nodes"))
    if set(node_by_id) & set(pis):
        overlap = sorted(set(node_by_id) & set(pis))
        raise ValueError(f"Primary inputs and nodes share IDs: {overlap}")
    for output_id in pos:
        if output_id not in set(pis) | set(node_by_id):
            raise ValueError(f"Overview output id has no source signal: {output_id}")

    nodes = list(node_by_id.values())
    po_set = set(pos)
    ordered_node_ids = sorted(node_by_id, key=lambda current_id: (_node_level(node_by_id[current_id]), current_id))

    for node_id in ordered_node_ids:
        while True:
            _recompute_levels_and_support(nodes, pis)
            children_index = _build_children_index(nodes, node_by_id)
            outputs = {
                child_id
                for child_id in children_index.get(node_id, [])
                if child_id in po_set
            }
            choices: list[int] = []
            for _level, grouped_children in _ranked_children(node_id, children_index, node_by_id):
                choices.extend(_choose(grouped_children, outputs, node_by_id, policy))

            ordered_choices = sorted(
                set(choices),
                key=lambda child_id: (_node_level(node_by_id[child_id]), child_id),
            )
            if len(ordered_choices) <= 1:
                break

            _make_chain(node_id, ordered_choices, outputs, node_by_id)

    _recompute_levels_and_support(nodes, pis)
    overview["nodes"] = nodes
    return overview


def _apply_depth_oriented(overview: Overview) -> Overview:
    """Apply the depth-oriented chain selection policy."""

    return _build_chain(overview, _select_depth_oriented)


def _apply_energy_oriented(overview: Overview) -> Overview:
    """Apply the energy-oriented chain selection policy."""

    return _build_chain(overview, _select_energy_oriented)


METHOD_REGISTRY: dict[str, Transformation] = {
    DEPTH_ORIENTED: _apply_depth_oriented,
    ENERGY_ORIENTED: _apply_energy_oriented,
}


def apply(self, method: object):
    """Apply a registered transformation method to the current circuit."""

    if not self.node:
        raise ValueError(
            "Circuit has no nodes. Run generate_overview() before apply()."
        )

    method_key = _normalize_method(method)
    transform = METHOD_REGISTRY.get(method_key)
    if transform is None:
        available = ", ".join(sorted(METHOD_REGISTRY))
        raise ValueError(
            f"Unknown apply method {method!r}. Available methods: {available}"
        )

    overview = _state_overview_like(self)
    transformed = transform(overview)

    self.file_name = str(transformed["file_name"])
    self.pi = list(transformed["pis"])
    self.po = list(transformed["pos"])
    self.node = list(transformed["nodes"])
    self.entropy = None
    return self


__all__ = [
    "DEPTH_ORIENTED",
    "ENERGY_ORIENTED",
    "METHOD_REGISTRY",
    "apply",
]
