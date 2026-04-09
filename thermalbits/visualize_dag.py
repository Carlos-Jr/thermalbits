from collections import defaultdict
from collections.abc import Iterable, Sequence

from .generate_overview import _state_overview


def _parse_level_window(level_window: Sequence[int] | None) -> tuple[int, int] | None:
    if level_window is None:
        return None
    if len(level_window) != 2:
        raise ValueError("level_window must contain exactly two integers: [start, end]")
    start, end = level_window
    if not isinstance(start, int) or not isinstance(end, int):
        raise ValueError("level_window values must be integers")
    if start > end:
        raise ValueError("level_window start must be <= end")
    return start, end


def _node_role(node_id: int, pis: set[int], pos: set[int]) -> str:
    if node_id in pis and node_id in pos:
        return "input_output"
    if node_id in pis:
        return "input"
    if node_id in pos:
        return "output"
    return "internal"


def _node_color(role: str) -> str:
    if role == "input":
        return "#4DA3D9"
    if role == "output":
        return "#F39C4A"
    if role == "input_output":
        return "#A173D1"
    return "#C9CED4"


_FANOUT_EDGE_COLORS = (
    "#000000",  # fanout 0 -> black
    "#D62728",  # fanout 1 -> red
    "#1F77B4",  # fanout 2 -> blue
    "#2CA02C",  # fanout 3 -> green
    "#9467BD",  # fanout 4 -> purple
    "#FF7F0E",  # fanout 5 -> orange
    "#17BECF",  # fanout 6 -> cyan
    "#8C564B",  # fanout 7 -> brown
)


def _fanout_color(output_index: int) -> str:
    if output_index < 0:
        output_index = 0
    return _FANOUT_EDGE_COLORS[output_index % len(_FANOUT_EDGE_COLORS)]


def _node_marker(node_id: int, node_kind_by_id: dict[int, str], pis: set[int]) -> str:
    if node_id in pis:
        return "o"
    node_kind = node_kind_by_id.get(node_id)
    if node_kind == "&":
        return "s"
    if node_kind == "|":
        return "D"
    if node_kind == "^":
        return "X"
    if node_kind == "M":
        return "^"
    if node_kind == "multi":
        return "P"
    return "o"


def _gate_label(
    node_id: int,
    node_kind_by_id: dict[int, str],
    fanout_count_by_id: dict[int, int],
    pis: set[int],
    pos: set[int],
) -> str:
    role = _node_role(node_id, pis, pos)
    if role == "input":
        return f"PI {node_id}"
    if role == "input_output":
        return f"PI/PO {node_id}"
    gate = node_kind_by_id.get(node_id, "")
    if gate == "&":
        gate_name = "AND"
    elif gate == "|":
        gate_name = "OR"
    elif gate == "^":
        gate_name = "XOR"
    elif gate == "M":
        gate_name = "MAJ"
    elif gate == "-":
        gate_name = "WIRE"
    elif gate == "multi":
        gate_name = f"NODE x{fanout_count_by_id.get(node_id, 0)}"
    else:
        gate_name = "NODE"
    if role == "output":
        return f"{gate_name} {node_id}\nPO"
    return f"{gate_name} {node_id}"


def _group_by_level(
    node_ids: Iterable[int],
    level_by_id: dict[int, int],
) -> list[tuple[int, list[int]]]:
    grouped: dict[int, list[int]] = defaultdict(list)
    for node_id in node_ids:
        grouped[level_by_id[node_id]].append(node_id)
    return [(level, sorted(grouped[level])) for level in sorted(grouped)]


def _build_positions(
    grouped_levels: list[tuple[int, list[int]]],
    orientation: str,
) -> tuple[dict[int, tuple[float, float]], dict[int, float], tuple[float, float, float, float]]:
    pos: dict[int, tuple[float, float]] = {}
    axis_by_level: dict[int, float] = {}

    level_gap = 4.0
    node_gap = 1.8
    max_span = 0.0

    for level_idx, (level, node_ids) in enumerate(grouped_levels):
        axis_value = level_idx * level_gap
        axis_by_level[level] = axis_value

        count = len(node_ids)
        for i, node_id in enumerate(node_ids):
            offset = (i - (count - 1) / 2.0) * node_gap
            if orientation == "horizontal":
                x, y = axis_value, -offset
            else:
                x, y = offset, -axis_value
            pos[node_id] = (x, y)
            max_span = max(max_span, abs(offset))

    if orientation == "horizontal":
        x_min = -1.8
        x_max = (len(grouped_levels) - 1) * level_gap + 1.8 if grouped_levels else 1.8
        y_min = -(max_span + 2.2)
        y_max = max_span + 2.2
    else:
        x_min = -(max_span + 2.2)
        x_max = max_span + 2.2
        y_min = -((len(grouped_levels) - 1) * level_gap + 1.8) if grouped_levels else -1.8
        y_max = 1.8

    return pos, axis_by_level, (x_min, x_max, y_min, y_max)


def visualize_dag(
    self,
    output_path: str,
    orientation: str = "horizontal",
    level_window: Sequence[int] | None = None,
    figsize: tuple[float, float] = (14.0, 8.0),
    dpi: int = 180,
) -> None:
    """
    Renderiza o circuito como um grafo direcionado aciclico (DAG) em imagem.

    Args:
        output_path: Caminho da imagem de saida (ex.: dag.png, dag.svg, dag.pdf).
        orientation: "horizontal" (niveis da esquerda para direita) ou
            "vertical" (niveis de cima para baixo).
        level_window: Faixa de niveis [inicio, fim] para renderizacao parcial.
            Ex.: [4, 10].
        figsize: Tamanho da figura em polegadas.
        dpi: Resolucao da figura.
    """
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise ImportError(
            "matplotlib is required for DAG visualization. Install it with: pip install matplotlib"
        ) from exc

    if orientation not in ("horizontal", "vertical"):
        raise ValueError("orientation must be 'horizontal' or 'vertical'")

    parsed_window = _parse_level_window(level_window)

    overview = _state_overview(self)
    pis_raw = overview["pis"]
    pos_raw = overview["pos"]
    nodes_raw = overview["nodes"]

    if not isinstance(pis_raw, list) or not all(isinstance(v, int) for v in pis_raw):
        raise ValueError("Overview field 'pis' must be a list of integers")
    if not isinstance(pos_raw, list) or not all(isinstance(v, int) for v in pos_raw):
        raise ValueError("Overview field 'pos' must be a list of integers")
    if not isinstance(nodes_raw, list):
        raise ValueError("Overview field 'nodes' must be a list")

    pis = set(pis_raw)
    pos = set(pos_raw)

    node_kind_by_id: dict[int, str] = {}
    fanout_count_by_id: dict[int, int] = {}
    edge_set: set[tuple[int, int, int, bool]] = set()
    node_ids = set(pis) | set(pos)

    level_by_id: dict[int, int] = {}
    for node in nodes_raw:
        if not isinstance(node, dict):
            raise ValueError("Each node must be an object")
        node_id = node.get("id")
        fanin = node.get("fanin")
        fanout = node.get("fanout")
        node_level = node.get("level", 0)

        if not isinstance(node_id, int):
            raise ValueError("Each node must contain integer field 'id'")
        if not isinstance(fanin, list):
            raise ValueError(f"Node {node_id} fanin must be a list")
        if not isinstance(fanout, list) or not fanout:
            raise ValueError(f"Node {node_id} fanout must be a non-empty list")
        if not isinstance(node_level, int):
            raise ValueError(f"Node {node_id} field 'level' must be an integer")

        fanout_ops: list[str] = []
        invert_by_fanin: dict[int, set[bool]] = defaultdict(set)
        for fanout_idx, fanout_entry in enumerate(fanout):
            if not isinstance(fanout_entry, dict):
                raise ValueError(
                    f"Node {node_id} has invalid fanout entry at index {fanout_idx}"
                )
            op = fanout_entry.get("op")
            if op not in ("&", "|", "^", "M", "-"):
                raise ValueError(
                    f"Unsupported node operator for id {node_id} fanout[{fanout_idx}]: {op}"
                )
            input_raw = fanout_entry.get("input")
            invert_raw = fanout_entry.get("invert")
            if not isinstance(input_raw, list) or not isinstance(invert_raw, list):
                raise ValueError(
                    f"Node {node_id} fanout[{fanout_idx}] must contain list fields 'input' and 'invert'"
                )
            if len(input_raw) != len(invert_raw):
                raise ValueError(
                    f"Node {node_id} fanout[{fanout_idx}] fields 'input' and 'invert' must have the same length"
                )
            for local_idx, inv in zip(input_raw, invert_raw):
                invert_by_fanin[local_idx].add(bool(inv))
            fanout_ops.append(op)

        node_kind_by_id[node_id] = fanout_ops[0] if len(fanout_ops) == 1 else "multi"
        fanout_count_by_id[node_id] = len(fanout_ops)
        level_by_id[node_id] = node_level
        node_ids.add(node_id)

        for fanin_idx, item in enumerate(fanin):
            if not isinstance(item, list) or len(item) != 2:
                raise ValueError(f"Node {node_id} has invalid fanin entry: {item}")
            src, output_index = item
            if not isinstance(src, int) or not isinstance(output_index, int) or output_index < 0:
                raise ValueError(f"Node {node_id} has invalid fanin literal: {item}")
            invert_variants = invert_by_fanin.get(fanin_idx) or {False}
            for inverted in invert_variants:
                edge_set.add((src, node_id, output_index, inverted))
            node_ids.add(src)

    for node_id in node_ids:
        if node_id not in level_by_id:
            level_by_id[node_id] = 0

    if not node_ids:
        raise ValueError("Overview has no nodes to visualize")

    if parsed_window is None:
        visible_ids = set(node_ids)
        range_start = min(level_by_id.values())
        range_end = max(level_by_id.values())
    else:
        range_start, range_end = parsed_window
        visible_ids = {
            node_id
            for node_id in node_ids
            if range_start <= level_by_id[node_id] <= range_end
        }
        if not visible_ids:
            raise ValueError(
                f"No nodes found in level window [{range_start}, {range_end}]"
            )

    grouped = _group_by_level(visible_ids, level_by_id)
    pos_by_id, axis_by_level, (x_min, x_max, y_min, y_max) = _build_positions(
        grouped, orientation
    )

    incoming_hidden: dict[int, int] = defaultdict(int)
    outgoing_hidden: dict[int, int] = defaultdict(int)
    visible_edges: list[tuple[int, int, int, bool]] = []
    for src, dst, out_idx, inverted in sorted(edge_set):
        src_visible = src in visible_ids
        dst_visible = dst in visible_ids
        if src_visible and dst_visible:
            visible_edges.append((src, dst, out_idx, inverted))
            continue
        if dst_visible and level_by_id[src] < range_start:
            incoming_hidden[dst] += 1
        if src_visible and level_by_id[dst] > range_end:
            outgoing_hidden[src] += 1

    fig, ax = plt.subplots(figsize=figsize, dpi=dpi)

    for level, axis_value in axis_by_level.items():
        if orientation == "horizontal":
            ax.axvline(axis_value, color="#5F6B7A", linestyle="--", linewidth=1.0, alpha=0.35)
            ax.text(
                axis_value,
                y_max - 0.25,
                f"L{level}",
                ha="center",
                va="top",
                fontsize=9,
                color="#2C3E50",
            )
        else:
            y = -axis_value
            ax.axhline(y, color="#5F6B7A", linestyle="--", linewidth=1.0, alpha=0.35)
            ax.text(
                x_min + 0.25,
                y,
                f"L{level}",
                ha="left",
                va="bottom",
                fontsize=9,
                color="#2C3E50",
            )

    for src, dst, out_idx, inverted in visible_edges:
        x0, y0 = pos_by_id[src]
        x1, y1 = pos_by_id[dst]
        ax.annotate(
            "",
            xy=(x1, y1),
            xytext=(x0, y0),
            arrowprops={
                "arrowstyle": "->",
                "linewidth": 1.2,
                "color": _fanout_color(out_idx),
                "linestyle": "--" if inverted else "-",
                "alpha": 0.85,
                "shrinkA": 15,
                "shrinkB": 15,
            },
        )

    if orientation == "horizontal":
        left_stub_x = x_min + 0.4
        right_stub_x = x_max - 0.4
        for dst, count in incoming_hidden.items():
            x1, y1 = pos_by_id[dst]
            ax.annotate(
                "",
                xy=(x1 - 0.35, y1),
                xytext=(left_stub_x, y1),
                arrowprops={
                    "arrowstyle": "->",
                    "linewidth": 1.0,
                    "color": "#7F8C8D",
                    "linestyle": ":",
                    "alpha": 0.75,
                },
            )
            ax.text(left_stub_x - 0.1, y1 + 0.15, f"+{count}", fontsize=8, ha="right", va="bottom")
        for src, count in outgoing_hidden.items():
            x0, y0 = pos_by_id[src]
            ax.annotate(
                "",
                xy=(right_stub_x, y0),
                xytext=(x0 + 0.35, y0),
                arrowprops={
                    "arrowstyle": "->",
                    "linewidth": 1.0,
                    "color": "#7F8C8D",
                    "linestyle": ":",
                    "alpha": 0.75,
                },
            )
            ax.text(right_stub_x + 0.1, y0 + 0.15, f"+{count}", fontsize=8, ha="left", va="bottom")
    else:
        top_stub_y = y_max - 0.4
        bottom_stub_y = y_min + 0.4
        for dst, count in incoming_hidden.items():
            x1, y1 = pos_by_id[dst]
            ax.annotate(
                "",
                xy=(x1, y1 + 0.35),
                xytext=(x1, top_stub_y),
                arrowprops={
                    "arrowstyle": "->",
                    "linewidth": 1.0,
                    "color": "#7F8C8D",
                    "linestyle": ":",
                    "alpha": 0.75,
                },
            )
            ax.text(x1 + 0.12, top_stub_y + 0.05, f"+{count}", fontsize=8, ha="left", va="bottom")
        for src, count in outgoing_hidden.items():
            x0, y0 = pos_by_id[src]
            ax.annotate(
                "",
                xy=(x0, bottom_stub_y),
                xytext=(x0, y0 - 0.35),
                arrowprops={
                    "arrowstyle": "->",
                    "linewidth": 1.0,
                    "color": "#7F8C8D",
                    "linestyle": ":",
                    "alpha": 0.75,
                },
            )
            ax.text(x0 + 0.12, bottom_stub_y - 0.05, f"+{count}", fontsize=8, ha="left", va="top")

    marker_groups: dict[str, list[int]] = defaultdict(list)
    for node_id in visible_ids:
        marker_groups[_node_marker(node_id, node_kind_by_id, pis)].append(node_id)

    for marker, ids in marker_groups.items():
        xs = [pos_by_id[node_id][0] for node_id in ids]
        ys = [pos_by_id[node_id][1] for node_id in ids]
        colors = [_node_color(_node_role(node_id, pis, pos)) for node_id in ids]
        ax.scatter(
            xs,
            ys,
            s=950,
            c=colors,
            marker=marker,
            edgecolors="#1F2933",
            linewidths=1.0,
            zorder=3,
        )

    for node_id in visible_ids:
        x, y = pos_by_id[node_id]
        ax.text(
            x,
            y,
            _gate_label(node_id, node_kind_by_id, fanout_count_by_id, pis, pos),
            ha="center",
            va="center",
            fontsize=8,
            color="#111827",
            zorder=4,
        )

    all_levels = set(level_by_id.values())
    hidden_before = sorted(level for level in all_levels if level < range_start)
    hidden_after = sorted(level for level in all_levels if level > range_end)

    info_lines: list[str] = []
    if hidden_before:
        info_lines.append(
            f"Niveis ocultos anteriores: {hidden_before[0]}..{hidden_before[-1]}"
        )
    if hidden_after:
        info_lines.append(
            f"Niveis ocultos posteriores: {hidden_after[0]}..{hidden_after[-1]}"
        )
    if parsed_window is not None:
        info_lines.append(f"Faixa exibida: {range_start}..{range_end}")
    if info_lines:
        ax.text(
            x_min + 0.25,
            y_min + 0.25,
            "\n".join(info_lines),
            ha="left",
            va="bottom",
            fontsize=9,
            color="#374151",
            bbox={"boxstyle": "round,pad=0.3", "fc": "#F7F9FB", "ec": "#CBD5E1", "alpha": 0.9},
        )

    title_orientation = "Horizontal" if orientation == "horizontal" else "Vertical"
    ax.set_title(f"Circuit DAG ({title_orientation})", fontsize=12, color="#0F172A")
    ax.set_xlim(x_min, x_max)
    ax.set_ylim(y_min, y_max)
    ax.set_aspect("equal", adjustable="box")
    ax.axis("off")
    fig.tight_layout()
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)
