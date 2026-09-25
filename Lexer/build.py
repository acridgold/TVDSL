#!/usr/bin/env python3
"""
Запуск:
    python3 build.py                       # только статистика + table.json
    python3 build.py --scan somefile.fun   # + токенизация файла
    python3 build.py --out custom.json     # изменить путь выгрузки
"""

import argparse
import json
import sys

from automata import combine, subset_construction
from minimize import build_minimized
from lexer import TOKEN_DEFS, build_lexer


def export_table(dfa, path: str) -> None:
    data = {
        "alphabet": sorted(dfa.alphabet),
        "start": dfa.start,
        "trap": dfa.trap,
        "states": dfa.states,
        "accepting": {str(s): name for s, name in dfa.accept.items()},
        "transitions": {
            str(s): {sym: t for sym, t in row.items()}
            for s, row in dfa.trans.items()
        },
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scan", help="файл для токенизации лексером")
    ap.add_argument("--out", default="table.json", help="путь для выгрузки таблицы переходов минимизированного ДКА")
    ap.add_argument("--raw-out", default=None, help="также выгрузить неминимизированный ДКА")
    args = ap.parse_args()

    token_pairs = [(name, pat) for name, pat, _skip in TOKEN_DEFS]
    tnfa = combine(token_pairs)
    raw_dfa = subset_construction(tnfa)
    min_dfa = build_minimized(raw_dfa)

    print(f"Токенов определено:        {len(TOKEN_DEFS)}")
    print(f"Символов в алфавите:       {len(raw_dfa.alphabet)}")
    print(f"Состояний ДКА (до min.):   {len(raw_dfa.states)}")
    print(f"Состояний ДКА (после min.):{len(min_dfa.states)}")
    print(f"Сокращение:                {len(raw_dfa.states) - len(min_dfa.states)} состояний")

    export_table(min_dfa, args.out)
    print(f"Таблица переходов (минимизированная) выгружена в {args.out}")

    if args.raw_out:
        export_table(raw_dfa, args.raw_out)
        print(f"Таблица переходов (до минимизации) выгружена в {args.raw_out}")

    if args.scan:
        with open(args.scan, "r", encoding="utf-8") as f:
            text = f.read()
        lexer = build_lexer()
        tokens, errors = lexer.scan(text)
        print(f"\n--- Токены ({len(tokens)}) ---")
        for t in tokens:
            print(f"{t.pos:5d}  {t.name:12s} {t.value!r}")
        if errors:
            print(f"\n--- Ошибки ({len(errors)}) ---", file=sys.stderr)
            for e in errors:
                print(f"поз. {e.pos}: недопустимый символ {e.char!r}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
