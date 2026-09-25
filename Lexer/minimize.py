"""
Минимизация полностью определённого ДКА по алгоритму Хопкрофта.
"""

from dataclasses import dataclass
from typing import Dict, FrozenSet, List, Set, Tuple

from automata import DFA


def hopcroft_partition(dfa: DFA) -> List[FrozenSet[int]]:
    # Начальное разбиение по тегу (тип токена или None)
    groups: Dict[object, Set[int]] = {}
    for s in dfa.states:
        tag = dfa.accept.get(s)
        groups.setdefault(tag, set()).add(s)

    P: List[FrozenSet[int]] = [frozenset(g) for g in groups.values()]
    W: List[FrozenSet[int]] = list(P)

    # Обратные переходы: symbol -> target -> set(sources)
    rev: Dict[str, Dict[int, Set[int]]] = {sym: {} for sym in dfa.alphabet}
    for s in dfa.states:
        for sym in dfa.alphabet:
            t = dfa.trans[s][sym]
            rev[sym].setdefault(t, set()).add(s)

    while W:
        A = W.pop()
        for sym in dfa.alphabet:
            X: Set[int] = set()
            for t in A:
                X |= rev[sym].get(t, set())
            if not X:
                continue
            newP: List[FrozenSet[int]] = []
            for Y in P:
                inter = Y & X
                diff = Y - X
                if inter and diff:
                    inter_f, diff_f = frozenset(inter), frozenset(diff)
                    newP.append(inter_f)
                    newP.append(diff_f)
                    if Y in W:
                        W.remove(Y)
                        W.append(inter_f)
                        W.append(diff_f)
                    else:
                        if len(inter_f) <= len(diff_f):
                            W.append(inter_f)
                        else:
                            W.append(diff_f)
                else:
                    newP.append(Y)
            P = newP
    return P


def build_minimized(dfa: DFA) -> DFA:
    partition = hopcroft_partition(dfa)

    # Найти класс, содержащий состояние s
    rep_of: Dict[int, int] = {}
    for idx, group in enumerate(partition):
        for s in group:
            rep_of[s] = idx

    new_start = rep_of[dfa.start]
    new_trap = rep_of[dfa.trap]
    new_trans: Dict[int, Dict[str, int]] = {}
    new_accept: Dict[int, str] = {}

    for idx, group in enumerate(partition):
        rep = next(iter(group))
        new_trans[idx] = {sym: rep_of[dfa.trans[rep][sym]] for sym in dfa.alphabet}
        if rep in dfa.accept:
            new_accept[idx] = dfa.accept[rep]

    new_states = list(range(len(partition)))
    return DFA(states=new_states, start=new_start, trans=new_trans,
               accept=new_accept, alphabet=dfa.alphabet, trap=new_trap)
