"""
- Объединение нескольких НКА (по одному на тип токена) в один НКА с
  эпсилон-переходами из общего старта и тегами на принимающих состояниях.
- Subset construction: эпсилон-НКА -> ДКА.
- Достраивание ДКА до полностью определённого (с явной "ловушкой" / dead
  state) на заданном алфавите.
"""

from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Optional, Set, Tuple

from thompson import NFA

TRAP = "TRAP"


@dataclass
class TaggedNFA:
    """Объединение нескольких именованных НКА в один, с приоритетами."""
    start: int
    trans: Dict[int, List[Tuple[Optional[str], int]]] = field(default_factory=dict)
    num_states: int = 0
    # accept_state -> (token_name, priority)   меньший приоритет = важнее
    tags: Dict[int, Tuple[str, int]] = field(default_factory=dict)
    alphabet: FrozenSet[str] = frozenset()


def combine(token_defs) -> TaggedNFA:
    """
    token_defs: список (name, pattern, priority) в порядке приоритета
    (индекс в списке используется как приоритет, если priority не задан).
    """
    from thompson import build_nfa

    trans: Dict[int, List[Tuple[Optional[str], int]]] = {}
    n = 0

    def new_state():
        nonlocal n
        sid = n
        n += 1
        trans[sid] = []
        return sid

    start = new_state()
    tags: Dict[int, Tuple[str, int]] = {}
    alphabet: Set[str] = set()

    for priority, (name, pattern) in enumerate(token_defs):
        nfa = build_nfa(pattern)
        offset = n
        n += nfa.num_states
        for sid in range(nfa.num_states):
            trans[offset + sid] = [
                (sym, offset + dst) for (sym, dst) in nfa.trans[sid]
            ]
        for sid in range(nfa.num_states):
            for sym, _dst in nfa.trans[sid]:
                if sym is not None:
                    alphabet.add(sym)
        trans[start].append((None, offset + nfa.start))
        tags[offset + nfa.accept] = (name, priority)

    return TaggedNFA(start=start, trans=trans, num_states=n, tags=tags,
                      alphabet=frozenset(alphabet))


def epsilon_closure(trans, states: Set[int]) -> FrozenSet[int]:
    stack = list(states)
    seen = set(states)
    while stack:
        s = stack.pop()
        for sym, dst in trans.get(s, []):
            if sym is None and dst not in seen:
                seen.add(dst)
                stack.append(dst)
    return frozenset(seen)


@dataclass
class DFA:
    states: List[int]                       # 0..N-1, TRAP state included as an int id
    start: int
    trans: Dict[int, Dict[str, int]]         # complete: every state x every alphabet symbol
    accept: Dict[int, str]                   # state -> token name  (only accepting states)
    alphabet: FrozenSet[str]
    trap: int


def subset_construction(tnfa: TaggedNFA) -> DFA:
    alphabet = tnfa.alphabet
    start_set = epsilon_closure(tnfa.trans, {tnfa.start})

    set_to_id: Dict[FrozenSet[int], int] = {}
    trans: Dict[int, Dict[str, int]] = {}
    accept: Dict[int, str] = {}

    def state_id(s: FrozenSet[int]) -> int:
        if s not in set_to_id:
            set_to_id[s] = len(set_to_id)
        return set_to_id[s]

    start_id = state_id(start_set)
    worklist = [start_set]
    seen = {start_set}

    while worklist:
        cur = worklist.pop()
        cur_id = state_id(cur)
        trans.setdefault(cur_id, {})

        best = None  # (priority, name)
        for nstate in cur:
            if nstate in tnfa.tags:
                name, prio = tnfa.tags[nstate]
                if best is None or prio < best[0]:
                    best = (prio, name)
        if best is not None:
            accept[cur_id] = best[1]

        for sym in alphabet:
            move = set()
            for nstate in cur:
                for s2, dst in tnfa.trans.get(nstate, []):
                    if s2 == sym:
                        move.add(dst)
            if not move:
                continue
            closure = epsilon_closure(tnfa.trans, move)
            trans[cur_id][sym] = state_id(closure)
            if closure not in seen:
                seen.add(closure)
                worklist.append(closure)

    # Достраиваем до полностью определённого ДКА: добавляем явную ловушку.
    trap_id = len(set_to_id)
    trans[trap_id] = {sym: trap_id for sym in alphabet}
    for sid in list(trans.keys()):
        if sid == trap_id:
            continue
        for sym in alphabet:
            if sym not in trans[sid]:
                trans[sid][sym] = trap_id

    states = list(range(trap_id + 1))
    return DFA(states=states, start=start_id, trans=trans, accept=accept,
               alphabet=alphabet, trap=trap_id)
