"""Depth-oriented and energy-oriented fanout-chain optimizations."""

from __future__ import annotations

import heapq
from collections import defaultdict, deque
from copy import deepcopy
from typing import Callable

DEPTH_ORIENTED = "depth_oriented"
ENERGY_ORIENTED = "energy_oriented"

_SUPPORTED_OPS = {"&", "|", "^", "M", "-"}

Overview = dict[str, object]
Node = dict[str, object]
NodeLookup = dict[int, Node]
SourceRef = tuple[int, int]
SelectionPolicy = Callable[[list[int]], list[int]]
ChildrenIndex = dict[SourceRef, set[int]]
NodeChildrenIndex = dict[int, set[int]]
NodePredecessorIndex = dict[int, set[int]]


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


def _source_level(source_ref: SourceRef, node_by_id: NodeLookup) -> int:
    """Return the topological level of a source signal."""

    source_id, _output_index = source_ref
    source_node = node_by_id.get(source_id)
    if source_node is None:
        return 0
    return _node_level(source_node)


def _source_refs(pis: list[int], node_by_id: NodeLookup) -> list[SourceRef]:
    """Return PI outputs and non-wire node outputs that may feed chains."""

    refs: list[SourceRef] = [(pi_id, 0) for pi_id in pis]
    for node_id in sorted(node_by_id):
        for output_index, fanout_entry in enumerate(node_by_id[node_id]["fanout"]):
            if fanout_entry.get("op") != "-":
                refs.append((node_id, output_index))
    return refs


def _build_children_index(
    nodes: list[Node],
    pis: list[int],
    node_by_id: NodeLookup,
) -> ChildrenIndex:
    """Map each source signal to the internal nodes that consume it.

    Connections through wire (op='-') fanouts represent forwarded signals and
    are excluded, matching the reference algorithm's 'ignore forward edges'.
    Primary outputs in this schema are regular node ids, so they remain eligible
    as children.
    """

    valid_sources = set(_source_refs(pis, node_by_id))
    children: ChildrenIndex = {source_ref: set() for source_ref in valid_sources}

    for node in nodes:
        child_id = int(node["id"])
        for source_id, output_index in node["fanin"]:
            source_ref = (source_id, output_index)
            if source_ref in valid_sources:
                children[source_ref].add(child_id)

    return children


def _ranked_children(
    source_ref: SourceRef,
    children_index: ChildrenIndex,
    node_by_id: NodeLookup,
) -> list[tuple[int, list[int]]]:
    """Group direct children by level in ascending order."""

    grouped: dict[int, list[int]] = defaultdict(list)
    for child_id in children_index.get(source_ref, []):
        grouped[_node_level(node_by_id[child_id])].append(child_id)
    return [
        (level, sorted(grouped[level]))
        for level in sorted(grouped)
    ]


def _choose(
    grouped_children: list[int],
    used_children: set[int],
    policy: SelectionPolicy,
) -> list[int]:
    """Filter already-used children and delegate final selection to the policy."""

    valid_children = [
        child_id
        for child_id in grouped_children
        if child_id not in used_children
    ]
    return policy(valid_children)


def _add_wire_fanout(node: Node, local_fanin_idx: int) -> int:
    """
    Garante que *node* tenha um fanout WIRE (op="-") que repassa o input
    local_fanin_idx sem inversao.  Retorna o indice do fanout (novo ou existente).
    """
    fanout = node["fanout"]
    for i, entry in enumerate(fanout):
        if (
            entry.get("op") == "-"
            and entry.get("input") == [local_fanin_idx]
            and entry.get("invert") == [0]
        ):
            return i

    new_idx = len(fanout)
    fanout.append({"op": "-", "input": [local_fanin_idx], "invert": [0]})
    return new_idx


def _normalize_node_fanin(node: Node) -> None:
    """Collapse duplicate fanin references and update local input indices."""

    fanin = node["fanin"]
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
    for fanout_entry in node["fanout"]:
        input_indices = fanout_entry["input"]
        fanout_entry["input"] = [index_remap[input_idx] for input_idx in input_indices]


def _make_chain(
    source_ref: SourceRef,
    choices: list[int],
    node_by_id: NodeLookup,
) -> tuple[bool, set[int]]:
    """
    Constroi uma cadeia de fanouts a partir de source_ref.

    choices[0] mantem a ligacao direta com source_ref.
    Para cada choices[i] (i >= 1): adiciona um fanout WIRE em choices[i-1]
    que repassa o sinal de source_ref, e recabeia choices[i] para ler desse WIRE.

    carry_fanin_idx rastreia, em cada passo, qual indice LOCAL no no anterior
    carrega o sinal repassado de source_ref.
    """
    if not choices:
        return False, set()

    changed = False
    rewired_children: set[int] = set()
    previous_id: int | None = None
    # indice local no `previous_id` que carrega o sinal de source_ref
    carry_fanin_idx: int | None = None

    for index, child_id in enumerate(choices):
        child_node = node_by_id[child_id]
        child_fanin = child_node["fanin"]

        if index == 0:
            # choices[0] le source_ref diretamente; apenas localiza o indice de carry.
            for k, (src, _out) in enumerate(child_fanin):
                if (src, _out) == source_ref:
                    carry_fanin_idx = k
                    break
        else:
            if previous_id is None or carry_fanin_idx is None:
                previous_id = child_id
                continue

            prev_node = node_by_id[previous_id]

            # Adiciona WIRE no no anterior que repassa o sinal de source_ref.
            wire_idx = _add_wire_fanout(prev_node, carry_fanin_idx)

            # Recabeia child: entradas source_ref -> [previous_id, wire_idx].
            for ref in child_fanin:
                if (ref[0], ref[1]) == source_ref:
                    ref[0] = previous_id
                    ref[1] = wire_idx
                    changed = True
                    rewired_children.add(child_id)

            _normalize_node_fanin(child_node)

            # Atualiza carry para a proxima iteracao: acha o indice local
            # de [previous_id, wire_idx] no fanin normalizado.
            carry_fanin_idx = None
            for k, (src, out) in enumerate(child_node["fanin"]):
                if src == previous_id and out == wire_idx:
                    carry_fanin_idx = k
                    break

        previous_id = child_id
    return changed, rewired_children


def _node_predecessor_ids(
    node: Node,
    pi_set: set[int],
    node_by_id: NodeLookup,
) -> set[int]:
    node_id = int(node["id"])
    predecessors: set[int] = set()

    for source_id, output_index in node["fanin"]:
        if source_id in pi_set:
            if output_index != 0:
                raise ValueError(
                    f"Node {node_id} references primary input {source_id} with invalid output index {output_index}"
                )
            continue
        source_node = node_by_id.get(source_id)
        if source_node is None:
            raise ValueError(f"Node {node_id} references unknown fanin id: {source_id}")
        source_fanout_count = len(source_node["fanout"])
        if output_index >= source_fanout_count:
            raise ValueError(
                f"Node {node_id} references node {source_id} output index {output_index}, but that node has only {source_fanout_count} outputs"
            )
        predecessors.add(source_id)

    return predecessors


def _build_dependency_index(
    nodes: list[Node],
    pis: list[int],
    node_by_id: NodeLookup,
) -> tuple[NodeChildrenIndex, NodePredecessorIndex]:
    """Build node dependency indexes without revalidating the whole schema."""

    pi_set = set(pis)
    children_by_id: NodeChildrenIndex = {node_id: set() for node_id in node_by_id}
    predecessors_by_id: NodePredecessorIndex = {}

    for node in nodes:
        node_id = int(node["id"])
        predecessors = _node_predecessor_ids(node, pi_set, node_by_id)
        predecessors_by_id[node_id] = predecessors
        for source_id in predecessors:
            children_by_id[source_id].add(node_id)

    return children_by_id, predecessors_by_id


def _build_node_children_and_indegree(
    nodes: list[Node],
    pis: list[int],
    node_by_id: NodeLookup,
) -> tuple[NodeChildrenIndex, dict[int, int]]:
    children_by_id, predecessors_by_id = _build_dependency_index(nodes, pis, node_by_id)
    indegree = {
        node_id: len(predecessors)
        for node_id, predecessors in predecessors_by_id.items()
    }
    return children_by_id, indegree


def _topological_node_ids(
    children_by_id: NodeChildrenIndex,
    indegree: dict[int, int],
) -> list[int]:
    ready: list[int] = [node_id for node_id, count in indegree.items() if count == 0]
    heapq.heapify(ready)

    ordered: list[int] = []
    while ready:
        node_id = heapq.heappop(ready)
        ordered.append(node_id)

        for child_id in children_by_id[node_id]:
            indegree[child_id] -= 1
            if indegree[child_id] == 0:
                heapq.heappush(ready, child_id)

    if len(ordered) != len(indegree):
        raise ValueError("Transformation created a cycle in the circuit overview")
    return ordered


def _rebuild_level_state(
    nodes: list[Node],
    pis: list[int],
    node_by_id: NodeLookup,
) -> tuple[int, NodeChildrenIndex, NodePredecessorIndex]:
    children_by_id, predecessors_by_id = _build_dependency_index(nodes, pis, node_by_id)
    indegree = {
        node_id: len(predecessors)
        for node_id, predecessors in predecessors_by_id.items()
    }
    ordered_ids = _topological_node_ids(children_by_id, indegree)

    pi_set = set(pis)
    max_depth = 0
    for node_id in ordered_ids:
        node = node_by_id[node_id]
        level = _computed_node_level(node, pi_set, node_by_id)
        node["level"] = level
        if level > max_depth:
            max_depth = level

    return max_depth, children_by_id, predecessors_by_id


def _computed_node_level(
    node: Node,
    pi_set: set[int],
    node_by_id: NodeLookup,
) -> int:
    fanin = node["fanin"]
    if not fanin:
        return 0

    max_predecessor_level = 0
    for source_id, _output_index in fanin:
        if source_id in pi_set:
            continue
        source_level = int(node_by_id[source_id]["level"])
        if source_level > max_predecessor_level:
            max_predecessor_level = source_level
    return max_predecessor_level + 1


def _refresh_dependency_index_for_nodes(
    node_ids: set[int],
    pis: list[int],
    node_by_id: NodeLookup,
    children_by_id: NodeChildrenIndex,
    predecessors_by_id: NodePredecessorIndex,
) -> None:
    pi_set = set(pis)
    for node_id in node_ids:
        old_predecessors = predecessors_by_id[node_id]
        new_predecessors = _node_predecessor_ids(
            node_by_id[node_id],
            pi_set,
            node_by_id,
        )

        for removed_id in old_predecessors - new_predecessors:
            children_by_id[removed_id].discard(node_id)
        for added_id in new_predecessors - old_predecessors:
            children_by_id[added_id].add(node_id)

        predecessors_by_id[node_id] = new_predecessors


def _propagate_levels(
    start_ids: set[int],
    pis: list[int],
    node_by_id: NodeLookup,
    children_by_id: NodeChildrenIndex,
    current_depth: int,
) -> int:
    pi_set = set(pis)
    queue = deque(
        sorted(start_ids, key=lambda node_id: (_node_level(node_by_id[node_id]), node_id))
    )
    queued = set(start_ids)
    max_depth = current_depth

    while queue:
        node_id = queue.popleft()
        queued.discard(node_id)

        node = node_by_id[node_id]
        old_level = int(node["level"])
        new_level = _computed_node_level(node, pi_set, node_by_id)
        if new_level == old_level:
            continue

        node["level"] = new_level
        if new_level > max_depth:
            max_depth = new_level

        for child_id in children_by_id[node_id]:
            if child_id not in queued:
                queue.append(child_id)
                queued.add(child_id)

    return max_depth


def _recompute_levels_and_support(
    nodes: list[Node],
    pis: list[int],
    node_by_id: NodeLookup,
) -> int:
    """Rebuild topological levels and PI supports after rewiring."""

    pi_set = set(pis)
    children_by_id, indegree = _build_node_children_and_indegree(nodes, pis, node_by_id)
    ordered_ids = _topological_node_ids(children_by_id, indegree)

    level_by_id: dict[int, int] = {}
    support_by_id: dict[int, set[int]] = {}
    max_depth = 0

    for node_id in ordered_ids:
        node = node_by_id[node_id]
        fanin = node["fanin"]

        max_predecessor_level = 0
        support_set: set[int] = set()
        for source_id, _output_index in fanin:
            if source_id in pi_set:
                support_set.add(source_id)
            else:
                source_level = level_by_id[source_id]
                if source_level > max_predecessor_level:
                    max_predecessor_level = source_level
                support_set.update(support_by_id[source_id])

        level = max_predecessor_level + 1 if fanin else 0
        node["level"] = level
        node["suport"] = sorted(support_set)
        level_by_id[node_id] = level
        support_by_id[node_id] = support_set
        if level > max_depth:
            max_depth = level

    nodes.sort(key=lambda node: int(node["id"]))
    return max_depth


def _select_depth_oriented(valid_children: list[int]) -> list[int]:
    """Pick one valid child from a single level group."""

    return valid_children[:1]


def _select_energy_oriented(valid_children: list[int]) -> list[int]:
    """Pick every valid child from a single level group."""

    return list(valid_children)


def _current_depth(nodes: list[Node]) -> int:
    """Return the current maximum node level."""

    return max((_node_level(node) for node in nodes), default=0)


def _snapshot_nodes(node_ids: set[int], node_by_id: NodeLookup) -> dict[int, Node]:
    return {node_id: deepcopy(node_by_id[node_id]) for node_id in node_ids}


def _restore_nodes(snapshot: dict[int, Node], node_by_id: NodeLookup) -> None:
    for node_id, saved_node in snapshot.items():
        node = node_by_id[node_id]
        node.clear()
        node.update(deepcopy(saved_node))


def _build_chain(
    overview: Overview,
    policy: SelectionPolicy,
    *,
    preserve_depth: bool,
) -> Overview:
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
    max_allowed_depth = _current_depth(nodes) if preserve_depth else None
    children_index = _build_children_index(nodes, pis, node_by_id)
    ordered_source_refs = sorted(
        children_index,
        key=lambda source_ref: (
            _source_level(source_ref, node_by_id),
            source_ref[0],
            source_ref[1],
        ),
        reverse=True,
    )
    current_depth, node_children_by_id, predecessors_by_id = _rebuild_level_state(
        nodes,
        pis,
        node_by_id,
    )

    for source_ref in ordered_source_refs:
        used_children: set[int] = set()

        while True:
            choices: list[int] = []
            for _level, grouped_children in _ranked_children(
                source_ref,
                children_index,
                node_by_id,
            ):
                choices.extend(_choose(grouped_children, used_children, policy))

            ordered_choices = sorted(
                set(choices),
                key=lambda child_id: (_node_level(node_by_id[child_id]), child_id),
            )
            if len(ordered_choices) <= 1:
                break

            snapshot = (
                _snapshot_nodes(set(ordered_choices), node_by_id)
                if max_allowed_depth is not None
                else None
            )
            changed, rewired_children = _make_chain(
                source_ref,
                ordered_choices,
                node_by_id,
            )
            if not changed:
                used_children.update(ordered_choices)
                break

            _refresh_dependency_index_for_nodes(
                rewired_children,
                pis,
                node_by_id,
                node_children_by_id,
                predecessors_by_id,
            )
            current_depth = _propagate_levels(
                rewired_children,
                pis,
                node_by_id,
                node_children_by_id,
                current_depth,
            )
            if max_allowed_depth is not None and current_depth > max_allowed_depth:
                if snapshot is None:
                    raise AssertionError("missing snapshot for depth-preserving rollback")
                _restore_nodes(snapshot, node_by_id)
                current_depth, node_children_by_id, predecessors_by_id = _rebuild_level_state(
                    nodes,
                    pis,
                    node_by_id,
                )
                break

            children_index[source_ref].difference_update(rewired_children)
            used_children.update(ordered_choices)

    _recompute_levels_and_support(nodes, pis, node_by_id)
    overview["nodes"] = nodes
    return overview


def apply_depth_oriented(overview: Overview) -> Overview:
    """Apply the depth-oriented chain selection policy."""

    return _build_chain(overview, _select_depth_oriented, preserve_depth=True)


def apply_energy_oriented(overview: Overview) -> Overview:
    """Apply the energy-oriented chain selection policy."""

    return _build_chain(overview, _select_energy_oriented, preserve_depth=False)


__all__ = [
    "DEPTH_ORIENTED",
    "ENERGY_ORIENTED",
    "apply_depth_oriented",
    "apply_energy_oriented",
]
