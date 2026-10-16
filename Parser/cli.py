#!/usr/bin/env python3
"""
CLI парсера Funny.

    python3 cli.py program.fun                # AST деревом
    python3 cli.py program.fun --format json  # AST в JSON
    python3 cli.py program.fun --no-pos       # без позиций в выводе AST
    python3 cli.py program.fun --tokens       # + список токенов с позициями
    echo 'function f() { }' | python3 cli.py - # чтение из stdin

Диагностика ошибок печатается в stderr в формате `строка:столбец: ошибка: ...`.
Код возврата: 0 — ошибок нет, 1 — есть ошибки, 2 — файл не прочитан.
"""

import argparse
import sys

from ast_nodes import pretty, to_json
from funny_parser import parse


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file", help="файл с программой на Funny ('-' — stdin)")
    ap.add_argument("--format", choices=["tree", "json"], default="tree")
    ap.add_argument("--no-pos", action="store_true", help="не печатать позиции узлов в AST")
    ap.add_argument("--tokens", action="store_true", help="напечатать токены с позициями")
    args = ap.parse_args(argv)

    try:
        text = sys.stdin.read() if args.file == "-" else open(args.file, encoding="utf-8").read()
    except OSError as e:
        print(f"не удалось прочитать файл: {e}", file=sys.stderr)
        return 2

    res = parse(text)

    if args.tokens:
        for t in res.tokens:
            print(f"{t.line:4d}:{t.col:<4d} {t.name:12s} {t.value!r}")
        print()

    with_pos = not args.no_pos
    print(to_json(res.program, with_pos) if args.format == "json" else pretty(res.program, with_pos))

    for d in res.diagnostics:
        print(d, file=sys.stderr)
    return 0 if res.ok else 1


if __name__ == "__main__":
    sys.exit(main())
