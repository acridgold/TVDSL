"""
Построение НКА (эпсилон-НКА) из AST регулярного выражения по алгоритму
Томпсона.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from regex_ast import Char, CharSet, Epsilon, Concat, Union, Star, Plus, Optional_


@dataclass
class NFA:
    start: int
    accept: int
    trans: Dict[int, List[Tuple[Optional[str], int]]] = field(default_factory=dict)
    num_states: int = 0

    def add_state(self) -> int:
        sid = self.num_states
        self.num_states += 1
        self.trans[sid] = []
        return sid

    def add_edge(self, src: int, symbol: Optional[str], dst: int) -> None:
        self.trans[src].append((symbol, dst))

    def states(self):
        return range(self.num_states)


class _Builder:
    """Строит один общий NFA (общий счётчик состояний) из набора AST."""

    def __init__(self):
        self.trans: Dict[int, List[Tuple[Optional[str], int]]] = {}
        self.n = 0

    def new_state(self) -> int:
        sid = self.n
        self.n += 1
        self.trans[sid] = []
        return sid

    def edge(self, src: int, symbol: Optional[str], dst: int) -> None:
        self.trans[src].append((symbol, dst))

    def build(self, node) -> Tuple[int, int]:
        """Возвращает (start, accept) для фрагмента, соответствующего node."""
        if isinstance(node, Epsilon):
            s, a = self.new_state(), self.new_state()
            self.edge(s, None, a)
            return s, a
        if isinstance(node, Char):
            s, a = self.new_state(), self.new_state()
            self.edge(s, node.c, a)
            return s, a
        if isinstance(node, CharSet):
            s, a = self.new_state(), self.new_state()
            if not node.chars:
                raise ValueError("Пустой класс символов")
            for c in node.chars:
                self.edge(s, c, a)
            return s, a
        if isinstance(node, Concat):
            s1, a1 = self.build(node.left)
            s2, a2 = self.build(node.right)
            self.edge(a1, None, s2)
            return s1, a2
        if isinstance(node, Union):
            s = self.new_state()
            s1, a1 = self.build(node.left)
            s2, a2 = self.build(node.right)
            a = self.new_state()
            self.edge(s, None, s1)
            self.edge(s, None, s2)
            self.edge(a1, None, a)
            self.edge(a2, None, a)
            return s, a
        if isinstance(node, Star):
            s = self.new_state()
            a = self.new_state()
            s1, a1 = self.build(node.inner)
            self.edge(s, None, s1)
            self.edge(s, None, a)
            self.edge(a1, None, s1)
            self.edge(a1, None, a)
            return s, a
        if isinstance(node, Plus):
            return self._plus(node.inner)
        if isinstance(node, Optional_):
            s = self.new_state()
            a = self.new_state()
            s1, a1 = self.build(node.inner)
            self.edge(s, None, s1)
            self.edge(s, None, a)
            self.edge(a1, None, a)
            return s, a
        raise TypeError(f"Неизвестный узел AST: {node!r}")

    def _plus(self, inner) -> Tuple[int, int]:
        # a+ = a затем (a)*
        s1, a1 = self.build(inner)
        s = self.new_state()
        a = self.new_state()
        s2, a2 = self.build(inner)
        self.edge(s, None, s1)
        self.edge(a1, None, s2)
        self.edge(a1, None, a)
        self.edge(a2, None, s2)
        self.edge(a2, None, a)
        return s, a


def build_nfa_from_ast(node) -> NFA:
    b = _Builder()
    s, a = b.build(node)
    return NFA(start=s, accept=a, trans=b.trans, num_states=b.n)


def build_nfa(pattern: str) -> NFA:
    from regex_ast import parse_regex
    ast = parse_regex(pattern)
    return build_nfa_from_ast(ast)
