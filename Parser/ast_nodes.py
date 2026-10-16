"""
AST языка Funny.

Все узлы — dataclass'ы, наследники Node (несут позицию line/col).
Сериализация:
    node.to_dict()      -> JSON-совместимый dict ({"node": "Binary", ...})
    to_json(node)       -> строка JSON
    pretty(node)        -> человеко-читаемое дерево
Формат стабилен и пригоден для следующих этапов (T0/T1): тип узла лежит в
поле "node", позиция — в "pos" вида "строка:столбец".
"""

import json
from dataclasses import dataclass, field, fields
from typing import List, Optional


@dataclass
class Node:
    line: int = field(default=0, kw_only=True)
    col: int = field(default=0, kw_only=True)

    def to_dict(self, with_pos: bool = True) -> dict:
        d = {"node": type(self).__name__}
        for f in fields(self):
            if f.name in ("line", "col"):
                continue
            d[f.name] = _ser(getattr(self, f.name), with_pos)
        if with_pos:
            d["pos"] = f"{self.line}:{self.col}"
        return d


def _ser(v, with_pos):
    if isinstance(v, Node):
        return v.to_dict(with_pos)
    if isinstance(v, list):
        return [_ser(x, with_pos) for x in v]
    return v


# ---- верхний уровень ---------------------------------------------------

@dataclass
class Program(Node):
    functions: List["Function"]


@dataclass
class Param(Node):
    name: str
    type: Optional[str]          # "int", "bool", "int[]", "bool[]" или None (тип не указан)


@dataclass
class Function(Node):
    name: str
    params: List[Param]
    returns: List[Param]         # пусто — returns нет; name == "" у анонимного результата
    uses: List[str]
    requires: List["Expr"]
    ensures: List["Expr"]
    body: "Block"


# ---- операторы -----------------------------------------------------------

@dataclass
class Block(Node):
    stmts: List["Stmt"]


@dataclass
class VarDecl(Node):
    type: str
    name: str
    init: Optional["Expr"]


@dataclass
class Assign(Node):
    target: str
    value: "Expr"
    sugar: bool = False          # True: получено из `a[i] = e` (a = store(a, i, e))


@dataclass
class If(Node):
    cond: "Expr"
    then: "Stmt"
    else_: Optional["Stmt"]


@dataclass
class While(Node):
    cond: "Expr"
    invariants: List["Expr"]
    body: "Stmt"


@dataclass
class Assert(Node):
    expr: "Expr"


@dataclass
class Assume(Node):
    expr: "Expr"


@dataclass
class Return(Node):
    value: Optional["Expr"]


@dataclass
class CallStmt(Node):
    call: "Call"


Stmt = Node

# ---- выражения -------------------------------------------------------------

@dataclass
class IntLit(Node):
    value: int


@dataclass
class BoolLit(Node):
    value: bool


@dataclass
class Var(Node):
    name: str


@dataclass
class Unary(Node):
    op: str                      # "-" | "not"
    operand: "Expr"


@dataclass
class Binary(Node):
    op: str
    left: "Expr"
    right: "Expr"


@dataclass
class Index(Node):
    array: "Expr"
    index: "Expr"


@dataclass
class Store(Node):               # функциональное обновление массива (сахар для a[i] = e)
    array: "Expr"
    index: "Expr"
    value: "Expr"


@dataclass
class Call(Node):
    name: str
    args: List["Expr"]


Expr = Node


# ---- вывод ----------------------------------------------------------------

def to_json(node: Node, with_pos: bool = True, indent: int = 2) -> str:
    return json.dumps(node.to_dict(with_pos), ensure_ascii=False, indent=indent)


def pretty(node: Node, with_pos: bool = True) -> str:
    lines: List[str] = []
    _pretty(node, 0, "", lines, with_pos)
    return "\n".join(lines)


def _head(node: Node, with_pos: bool) -> str:
    scal = []
    for f in fields(node):
        if f.name in ("line", "col"):
            continue
        v = getattr(node, f.name)
        if not isinstance(v, (Node, list)):
            scal.append(f"{f.name}={v!r}")
    pos = f" @{node.line}:{node.col}" if with_pos else ""
    return type(node).__name__ + (" " + " ".join(scal) if scal else "") + pos


def _pretty(node, depth, label, out, with_pos):
    pad = "  " * depth
    out.append(f"{pad}{label}{_head(node, with_pos)}")
    for f in fields(node):
        if f.name in ("line", "col"):
            continue
        v = getattr(node, f.name)
        if isinstance(v, Node):
            _pretty(v, depth + 1, f"{f.name}: ", out, with_pos)
        elif isinstance(v, list) and v:
            out.append(f"{pad}  {f.name}:")
            for item in v:
                if isinstance(item, Node):
                    _pretty(item, depth + 2, "", out, with_pos)
                else:
                    out.append(f"{pad}    {item!r}")
