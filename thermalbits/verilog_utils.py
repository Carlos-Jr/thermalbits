"""Helpers for parsing a simple Verilog subset and computing gate metadata."""
import re
from collections.abc import Iterable, Sequence


_PLAIN_SIGNAL_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_$]*\Z")
_ESCAPED_SIGNAL_RE = re.compile(r"\\[^\s]+\Z")
_BINARY_CONST_RE = re.compile(r"([0-9]+)'[bB]([01xXzZ]+)\Z")
_EXPR_TOKEN_RE = re.compile(
    r"""\s*(
        ~|\&|\||\(|\)|
        \\[^\s]+|
        [A-Za-z_][A-Za-z0-9_$]*|
        [0-9]+'[bB][01xXzZ]+
    )""",
    re.VERBOSE,
)


def _strip_comments(text: str) -> str:
    text = re.sub(r"//.*?$", "", text, flags=re.MULTILINE)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return text


def _is_signal_name(token: str) -> bool:
    return bool(_PLAIN_SIGNAL_RE.fullmatch(token) or _ESCAPED_SIGNAL_RE.fullmatch(token))


def _is_const_token(token: str) -> bool:
    return bool(_BINARY_CONST_RE.fullmatch(token))


def _parse_const_token(token: str) -> int:
    match = _BINARY_CONST_RE.fullmatch(token)
    if not match:
        raise ValueError(f"Unsupported constant literal: {token}")
    width = int(match.group(1))
    bits = match.group(2).lower()
    if width != 1 or len(bits) != 1:
        raise ValueError(f"Only 1-bit binary constants are supported: {token}")
    if bits not in ("0", "1"):
        raise ValueError(f"Unsupported constant value (only 0/1): {token}")
    return int(bits)


def parse_signal_list(decl_line: str) -> list[str]:
    """
    Recebe algo como 'input pi0, pi1;' e retorna ['pi0', 'pi1'].
    Aceita que a lista possa ter quebras de linha antes do ';'.
    """
    decl_line = decl_line.strip()
    decl_line = re.sub(r"^(input|output|wire)\b", "", decl_line).strip()
    decl_line = decl_line.rstrip(" ;")
    names = [s.strip() for s in decl_line.replace("\n", " ").split(",")]

    out: list[str] = []
    for name in names:
        if not name:
            continue
        cleaned = name
        # Suporte basico a qualificadores comuns em declaracoes de portas/fios.
        while True:
            updated = re.sub(r"^(wire|reg|logic|signed|unsigned)\b\s*", "", cleaned)
            if updated == cleaned:
                break
            cleaned = updated.strip()
        cleaned = re.sub(r"^\[[^\]]+\]\s*", "", cleaned).strip()
        if " " in cleaned:
            cleaned = cleaned.split()[-1]
        if cleaned:
            out.append(cleaned)
    return out


def parse_verilog(text: str):
    """
    Parser simples para um subset de Verilog:
      - input ...
      - output ...
      - wire ...
      - assign <dest> = <expr>;
    """
    text = _strip_comments(text)

    inputs: list[str] = []
    for m_in in re.finditer(r"\binput\b\s+([^;]+);", text, re.MULTILINE | re.DOTALL):
        inputs.extend(parse_signal_list("input " + m_in.group(1) + ";"))

    outputs: list[str] = []
    for m_out in re.finditer(r"\boutput\b\s+([^;]+);", text, re.MULTILINE | re.DOTALL):
        outputs.extend(parse_signal_list("output " + m_out.group(1) + ";"))

    wires: list[str] = []
    for m_w in re.finditer(r"\bwire\b\s+([^;]+);", text, re.MULTILINE | re.DOTALL):
        wires.extend(parse_signal_list("wire " + m_w.group(1) + ";"))

    assigns: list[tuple[str, str]] = []
    for m_a in re.finditer(r"\bassign\b\s+(.+?)\s*=\s*([^;]+);", text, re.MULTILINE | re.DOTALL):
        dest = m_a.group(1).strip()
        expr = m_a.group(2).strip()
        if not _is_signal_name(dest):
            raise ValueError(f"Unsupported assignment destination: {dest}")
        assigns.append((dest, expr))

    return inputs, outputs, wires, assigns


def _tokenize_expr(expr: str) -> list[str]:
    expr = expr.strip()
    if not expr:
        raise ValueError("Expression is empty")

    tokens: list[str] = []
    pos = 0
    while pos < len(expr):
        match = _EXPR_TOKEN_RE.match(expr, pos)
        if not match:
            snippet = expr[pos : pos + 20]
            raise ValueError(f"Unsupported token in expression near: {snippet!r}")
        tokens.append(match.group(1))
        pos = match.end()
    return tokens


def _top_level_binary_ops(tokens: Sequence[str]) -> list[str]:
    ops: list[str] = []
    depth = 0
    for token in tokens:
        if token == "(":
            depth += 1
        elif token == ")":
            depth -= 1
            if depth < 0:
                raise ValueError("Invalid expression syntax: unbalanced parentheses")
        elif depth == 0 and token in ("&", "|"):
            ops.append(token)

    if depth != 0:
        raise ValueError("Invalid expression syntax: unbalanced parentheses")
    return ops


def _is_outer_parenthesized(tokens: Sequence[str]) -> bool:
    if len(tokens) < 2 or tokens[0] != "(" or tokens[-1] != ")":
        return False

    depth = 0
    for idx, token in enumerate(tokens):
        if token == "(":
            depth += 1
        elif token == ")":
            depth -= 1
            if depth < 0:
                raise ValueError("Invalid expression syntax: unbalanced parentheses")
            if depth == 0 and idx < len(tokens) - 1:
                return False

    if depth != 0:
        raise ValueError("Invalid expression syntax: unbalanced parentheses")
    return True


def _strip_outer_parentheses(tokens: Sequence[str]) -> list[str]:
    tokens = list(tokens)
    while _is_outer_parenthesized(tokens):
        tokens = tokens[1:-1]
    return tokens


def extract_deps(expr: str, known_signals: Sequence[str]) -> list[str]:
    """Extrai variaveis usadas na expressao, filtrando por sinais conhecidos."""
    known_set = set(known_signals)
    deps: list[str] = []
    seen = set()
    for token in _tokenize_expr(expr):
        if token in known_set and token not in seen:
            seen.add(token)
            deps.append(token)
    return deps


def compute_levels(
    inputs: list[str],
    assigns: list[tuple[str, str]],
    all_signals: list[str],
) -> dict[str, int]:
    """
    Computa o nivel logico de cada sinal atribuido:
      - Entradas no nivel 0
      - Para cada 'dest = expr', nivel(dest) = 1 + max(nivel(dos sinais usados em expr))
    """
    level: dict[str, int] = {}
    for inp in inputs:
        level[inp] = 0

    assigns_left = assigns.copy()
    changed = True
    while assigns_left and changed:
        changed = False
        still_left = []
        for dest, expr in assigns_left:
            deps = extract_deps(expr, all_signals)
            if all(d in level for d in deps):
                level[dest] = 1 + max(level[d] for d in deps) if deps else 1
                changed = True
            else:
                still_left.append((dest, expr))
        assigns_left = still_left

    for signal_name in all_signals:
        if signal_name not in level:
            level[signal_name] = 0

    return level


def _parse_gate_literal_tokens(tokens: Sequence[str]) -> tuple[str, int]:
    inv = 0
    current = _strip_outer_parentheses(tokens)
    while current and current[0] == "~":
        inv ^= 1
        current = current[1:]
        current = _strip_outer_parentheses(current)

    if len(current) != 1:
        raise ValueError("Literals must be a signal name optionally prefixed by '~'")

    token = current[0]
    if _is_signal_name(token) or _is_const_token(token):
        return token, inv
    raise ValueError("Literals must be a signal name optionally prefixed by '~'")


def _collect_gate_literals(
    tokens: Sequence[str],
    op_symbol: str,
    out_literals: list[tuple[str, int]],
) -> None:
    current = _strip_outer_parentheses(tokens)
    top_ops = _top_level_binary_ops(current)
    if top_ops:
        if set(top_ops) != {op_symbol}:
            raise ValueError(
                f"Mixed operators are not supported in one assignment: expected only '{op_symbol}'"
            )

        depth = 0
        start = 0
        for idx, token in enumerate(current):
            if token == "(":
                depth += 1
            elif token == ")":
                depth -= 1
            elif depth == 0 and token == op_symbol:
                _collect_gate_literals(current[start:idx], op_symbol, out_literals)
                start = idx + 1

        _collect_gate_literals(current[start:], op_symbol, out_literals)
        return

    signal_name, inv = _parse_gate_literal_tokens(current)
    out_literals.append((signal_name, inv))


def _literal_const_value(literal: tuple[str, int]) -> int | None:
    signal_name, inv = literal
    if not _is_const_token(signal_name):
        return None
    return _parse_const_token(signal_name) ^ inv


def _pick_anchor_signal(
    known_signals: Sequence[str],
    forbidden: Sequence[str],
) -> str:
    forbidden_set = set(forbidden)
    for signal_name in known_signals:
        if signal_name in forbidden_set:
            continue
        if _is_signal_name(signal_name):
            return signal_name
    raise ValueError(
        "Cannot represent a constant assignment without at least one existing signal"
    )


def _const_to_gate(value: int, anchor_signal: str) -> tuple[str, list[tuple[str, int]]]:
    if value not in (0, 1):
        raise ValueError(f"Invalid constant bit value: {value}")
    if value == 1:
        return "|", [(anchor_signal, 0), (anchor_signal, 1)]
    return "&", [(anchor_signal, 0), (anchor_signal, 1)]


def extract_gate_from_expr(
    expr: str,
    known_signals: Sequence[str],
    output_signal: str,
) -> tuple[str, list[tuple[str, int]]]:
    """
    Extrai um fanout simples de uma expressao:
      - Apenas '&', '|' e '~' sao permitidos
      - '~' so pode aparecer diretamente em um literal
      - Cada atribuicao deve resultar em uma unica saida simples

    Se a expressao tiver apenas um literal, ela e tratada como um fio:
      x -> "-"
      ~x -> "-" com inversao local
    """
    tokens = _strip_outer_parentheses(_tokenize_expr(expr))

    top_ops = _top_level_binary_ops(tokens)
    gate_op = "&"
    if top_ops:
        unique_ops = set(top_ops)
        if len(unique_ops) != 1:
            raise ValueError("Gate expressions only allow '&' and '|' binary operators")
        gate_op = top_ops[0]

    literals: list[tuple[str, int]] = []
    _collect_gate_literals(tokens, gate_op, literals)

    if len(literals) not in (1, 2):
        raise ValueError(
            f"Assignments must have exactly 1 or 2 literals: {expr}"
        )

    # Simplificacao local para permitir constantes 1-bit (ex.: 1'b1).
    simplified_literal: tuple[str, int] | None = None
    simplified_const: int | None = None

    if len(literals) == 1:
        simplified_literal = literals[0]
    else:
        left_const = _literal_const_value(literals[0])
        right_const = _literal_const_value(literals[1])

        if left_const is not None and right_const is not None:
            simplified_const = left_const & right_const if gate_op == "&" else left_const | right_const
        elif left_const is not None or right_const is not None:
            const_value = left_const if left_const is not None else right_const
            other_literal = literals[1] if left_const is not None else literals[0]
            if gate_op == "&":
                if const_value == 0:
                    simplified_const = 0
                else:
                    simplified_literal = other_literal
            else:
                if const_value == 1:
                    simplified_const = 1
                else:
                    simplified_literal = other_literal

    if simplified_literal is not None:
        signal_name, inv = simplified_literal
        if _is_const_token(signal_name):
            const_value = _parse_const_token(signal_name) ^ inv
            anchor_signal = _pick_anchor_signal(known_signals, forbidden=[output_signal])
            return _const_to_gate(const_value, anchor_signal)
        return "-", [(signal_name, inv)]
    elif simplified_const is not None:
        anchor_signal = _pick_anchor_signal(known_signals, forbidden=[output_signal])
        return _const_to_gate(simplified_const, anchor_signal)

    known_set = set(known_signals)
    for signal_name, _ in literals:
        if signal_name not in known_set:
            raise ValueError(f"Unknown signal in expression: {signal_name}")
    return gate_op, literals


def build_gates(
    assigns: Sequence[tuple[str, str]],
    known_signals: Sequence[str],
) -> list[dict[str, object]]:
    gates: list[dict[str, object]] = []
    for dest, expr in assigns:
        gate_op, fanin = extract_gate_from_expr(expr, known_signals, output_signal=dest)
        signal_inputs: list[str] = []
        seen_inputs = set()
        for signal_name, _ in fanin:
            if signal_name in seen_inputs:
                continue
            seen_inputs.add(signal_name)
            signal_inputs.append(signal_name)
        gates.append(
            {
                "output": dest,
                "op": gate_op,
                "fanin": fanin,
                "signal_inputs": signal_inputs,
                "expr": expr,
            }
        )
    return gates


def build_drivers(gates: Iterable[dict[str, object]]) -> dict[str, list[str]]:
    drivers: dict[str, list[str]] = {}
    for gate in gates:
        output = gate["output"]  # type: ignore[index]
        inputs = gate["signal_inputs"]  # type: ignore[index]
        drivers[output] = list(inputs)
    return drivers


def compute_cone_for_gate(
    gate_output: str,
    inputs: Sequence[str],
    drivers: dict[str, list[str]],
) -> list[str]:
    cone_set = set()
    visited = set()
    stack = [gate_output]
    input_set = set(inputs)

    while stack:
        signal = stack.pop()
        if signal in visited:
            continue
        visited.add(signal)

        if signal in input_set:
            cone_set.add(signal)
            continue

        if signal in drivers:
            stack.extend(drivers[signal])

    return [inp for inp in inputs if inp in cone_set]


def load_verilog(verilog_path: str):
    with open(verilog_path, "r", encoding="utf-8") as f:
        text = f.read()
    return parse_verilog(text)
