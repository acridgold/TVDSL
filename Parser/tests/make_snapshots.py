#!/usr/bin/env python3
"""Перегенерировать эталонные AST (snapshots/*.json) для programs/ok_*.fun.
Запуск:  python3 tests/make_snapshots.py   (после ручной проверки diff'а!)"""
import glob, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from funny_parser import parse

for path in sorted(glob.glob(os.path.join(HERE, "programs", "ok_*.fun"))):
    name = os.path.splitext(os.path.basename(path))[0]
    res = parse(open(path, encoding="utf-8").read())
    assert res.ok, (name, [str(d) for d in res.diagnostics])
    out = os.path.join(HERE, "snapshots", name + ".json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(res.program.to_dict(), f, ensure_ascii=False, indent=2)
        f.write("\n")
    print("wrote", out)
