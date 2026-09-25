#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Рисует ДКА картинкой через graphviz — для отчёта.

Полный ДКА лексера имеет ~76 состояний x 98 символов алфавита — рисовать
все 98 рёбер на каждое состояние нечитаемо. Поэтому:

  1. Рёбра с одним и тем же (откуда, куда) объединяются в одно ребро с
     компактной подписью вида "a-z, 0-9, _" вместо 98 отдельных стрелок.
  2. Ловушка (trap) по умолчанию не рисуется — на неё и так ведут все
     "недостающие" переходы из любого состояния, рисование этого захламляет
     граф. Вместо этого в подписи графа поясняется, что все не показанные
     переходы ведут в ловушку. Показать ловушку явно можно флагом --show-trap.

Использование:
    python3 draw_dfa.py                         # весь ДКА лексера (минимизированный)
    python3 draw_dfa.py --token INT             # ДКА только для одного токена
    python3 draw_dfa.py --token INT --show-trap # + явно нарисовать ловушку
    python3 draw_dfa.py --raw                   # ДКА до минимизации (для сравнения)
    python3 draw_dfa.py --out out/dfa            # свой путь (без расширения)
"""

import argparse
import os

import graphviz

from automata import combine, subset_construction, DFA
from minimize import build_minimized
from lexer import TOKEN_DEFS


def compress_label(chars) -> str:
    """Сжать множество символов в компактную подпись ребра: подряд идущие
    по коду символы схлопываются в диапазон "a-z", остальное перечисляется."""
    names = {
        " ": "␣", "\t": "\\t", "\r": "\\r", "\n": "\\n",
        '"': '\\"', "\\": "\\\\",
    }

    def show(c: str) -> str:
        return names.get(c, c)

    codes = sorted(ord(c) for c in chars)
    if not codes:
        return ""
    runs = []
    start = prev = codes[0]
    for code in codes[1:]:
        if code == prev + 1:
            prev = code
            continue
        runs.append((start, prev))
        start = prev = code
    runs.append((start, prev))

    parts = []
    for a, b in runs:
        if b - a >= 2:
            parts.append(f"{show(chr(a))}-{show(chr(b))}")
        elif b - a == 1:
            parts.append(show(chr(a)))
            parts.append(show(chr(b)))
        else:
            parts.append(show(chr(a)))
    return ", ".join(parts)


def build_graph(dfa: DFA, title: str, show_trap: bool = False) -> graphviz.Digraph:
    g = graphviz.Digraph(
        "DFA",
        graph_attr={
            "rankdir": "LR",
            "label": title,
            "labelloc": "t",
            "fontsize": "16",
            "fontname": "Helvetica",
        },
        node_attr={"fontname": "Helvetica", "fontsize": "11"},
        edge_attr={"fontname": "Helvetica", "fontsize": "10"},
    )

    hidden = set() if show_trap else {dfa.trap}

    # невидимая точка входа -> стартовое состояние
    g.node("__start__", shape="point", width="0.01")
    g.edge("__start__", str(dfa.start))

    for s in dfa.states:
        if s in hidden:
            continue
        if s in dfa.accept:
            g.node(
                str(s),
                label=f"{s}\\n{dfa.accept[s]}",
                shape="doublecircle",
                style="filled",
                fillcolor="#eaf6ea",
            )
        elif s == dfa.trap:
            g.node(str(s), label=f"{s}\\n(ловушка)", shape="circle",
                   style="filled", fillcolor="#f6eaea")
        else:
            g.node(str(s), label=str(s), shape="circle")

    for s in dfa.states:
        if s in hidden:
            continue
        by_target = {}
        for sym, t in dfa.trans[s].items():
            if t in hidden:
                continue
            by_target.setdefault(t, set()).add(sym)
        for t, chars in by_target.items():
            g.edge(str(s), str(t), label=compress_label(chars))

    return g


def full_lexer_dfa(minimized: bool = True) -> DFA:
    token_pairs = [(name, pat) for name, pat, _skip in TOKEN_DEFS]
    tnfa = combine(token_pairs)
    raw = subset_construction(tnfa)
    return build_minimized(raw) if minimized else raw


def single_token_dfa(name: str, minimized: bool = True) -> DFA:
    pat = next(p for n, p, _s in TOKEN_DEFS if n == name)
    tnfa = combine([(name, pat)])
    raw = subset_construction(tnfa)
    return build_minimized(raw) if minimized else raw


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--token", help="нарисовать ДКА только для одного токена (см. имена в lexer.TOKEN_DEFS), например INT, IDENT, WS")
    ap.add_argument("--raw", action="store_true", help="рисовать ДКА до минимизации вместо минимизированного")
    ap.add_argument("--show-trap", action="store_true", help="явно нарисовать состояние-ловушку и переходы в неё")
    ap.add_argument("--out", default=None, help="путь для вывода без расширения (по умолчанию dfa_<token|full>[_raw])")
    ap.add_argument("--format", default="png", help="формат вывода graphviz: png, svg, pdf ...")
    args = ap.parse_args()

    if args.token:
        dfa = single_token_dfa(args.token, minimized=not args.raw)
        title = f"ДКА токена {args.token}" + (" (до минимизации)" if args.raw else " (минимизированный)")
        default_out = f"dfa_{args.token.lower()}" + ("_raw" if args.raw else "")
    else:
        dfa = full_lexer_dfa(minimized=not args.raw)
        title = "ДКА лексера Funny, все токены" + (" (до минимизации)" if args.raw else " (минимизированный)")
        default_out = "dfa_full" + ("_raw" if args.raw else "")

    if not args.show_trap:
        title += "\\n(переходы в ловушку не показаны)"

    out_path = args.out or default_out
    g = build_graph(dfa, title, show_trap=args.show_trap)
    rendered = g.render(out_path, format=args.format, cleanup=True)
    print(f"Состояний в картинке: {len(dfa.states) - (0 if args.show_trap else 1)}")
    print(f"Сохранено: {rendered}")


if __name__ == "__main__":
    main()
