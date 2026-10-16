import glob
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import pytest

from ast_nodes import (Assert, Assign, Binary, Block, BoolLit, Call, CallStmt, If, Index,
                       IntLit, Return, Store, Unary, Var, VarDecl, While, pretty, to_json)
from funny_parser import parse


def parse_ok(src):
    res = parse(src)
    assert res.ok, [str(d) for d in res.diagnostics]
    return res.program


def body_of(src):
    return parse_ok(src).functions[0].body.stmts


def expr_of(text):
    """Разобрать выражение, обернув его в `x = <text>;`."""
    stmt = body_of("function f() { x = %s; }" % text)[0]
    return stmt.value


def shape(e):
    """Компактное S-выражение для проверки структуры."""
    if isinstance(e, IntLit):
        return e.value
    if isinstance(e, BoolLit):
        return e.value
    if isinstance(e, Var):
        return e.name
    if isinstance(e, Unary):
        return (e.op, shape(e.operand))
    if isinstance(e, Binary):
        return (e.op, shape(e.left), shape(e.right))
    if isinstance(e, Index):
        return ("idx", shape(e.array), shape(e.index))
    if isinstance(e, Call):
        return (e.name,) + tuple(shape(a) for a in e.args)
    raise AssertionError(e)


# ---------------------------------------------------------------------
# 1. Позитивные программы: снимки AST (структура + позиции)
# ---------------------------------------------------------------------

PROGRAMS = sorted(glob.glob(os.path.join(HERE, "programs", "ok_*.fun")))


@pytest.mark.parametrize("path", PROGRAMS, ids=[os.path.basename(p) for p in PROGRAMS])
def test_ast_matches_snapshot(path):
    name = os.path.splitext(os.path.basename(path))[0]
    snap_path = os.path.join(HERE, "snapshots", name + ".json")
    assert os.path.exists(snap_path), f"нет эталона {snap_path}; запустите tests/make_snapshots.py"
    res = parse(open(path, encoding="utf-8").read())
    assert res.ok, [str(d) for d in res.diagnostics]
    expected = json.load(open(snap_path, encoding="utf-8"))
    assert res.program.to_dict() == expected


def test_at_least_five_positive_programs():
    assert len(PROGRAMS) >= 5


# ---------------------------------------------------------------------
# 2. Конструкции языка
# ---------------------------------------------------------------------

def test_function_header_full():
    prog = parse_ok(
        "function g(a: int[], b: bool) returns (r: int, ok: bool) uses h, k "
        "requires a[0] > 0 ensures r > 0 ensures ok { }")
    f = prog.functions[0]
    assert f.name == "g"
    assert [(p.name, p.type) for p in f.params] == [("a", "int[]"), ("b", "bool")]
    assert [(p.name, p.type) for p in f.returns] == [("r", "int"), ("ok", "bool")]
    assert f.uses == ["h", "k"]
    assert len(f.requires) == 1 and len(f.ensures) == 2


def test_returns_anonymous_type_and_untyped_params():
    f = parse_ok("function f(n) returns int { }").functions[0]
    assert f.params[0].type is None
    assert [(p.name, p.type) for p in f.returns] == [("", "int")]


def test_empty_contracts_and_empty_body():
    f = parse_ok("function f() { }").functions[0]
    assert f.requires == [] and f.ensures == [] and f.returns == []
    assert f.body.stmts == []


def test_multiple_functions():
    prog = parse_ok("function a() { } function b() { } function c() { }")
    assert [f.name for f in prog.functions] == ["a", "b", "c"]


def test_statements_kinds():
    stmts = body_of(
        "function f() { int x = 1; x = 2; assert x > 0; assume true; "
        "while (x < 3) x = x + 1; if (x) x = 0; helper(x, 1); return x; return; { } }")
    kinds = [type(s).__name__ for s in stmts]
    assert kinds == ["VarDecl", "Assign", "Assert", "Assume", "While", "If",
                     "CallStmt", "Return", "Return", "Block"]
    assert stmts[7].value is not None and stmts[8].value is None


def test_var_decl_without_init():
    s = body_of("function f() { bool b; }")[0]
    assert isinstance(s, VarDecl) and s.init is None and s.type == "bool"


def test_while_invariants():
    w = body_of("function f() { while (i < n) invariant i >= 0 invariant i <= n { i = i + 1; } }")[0]
    assert isinstance(w, While) and len(w.invariants) == 2
    assert isinstance(w.body, Block)


def test_dangling_else_binds_to_nearest_if():
    s = body_of("function f() { if (a) if (b) x = 1; else x = 2; }")[0]
    assert isinstance(s, If) and s.else_ is None          # внешний if — без else
    assert isinstance(s.then, If) and s.then.else_ is not None


# ---------------------------------------------------------------------
# 3. Массивы: обращение a[i] и обновление как сахар
# ---------------------------------------------------------------------

def test_array_read():
    assert shape(expr_of("a[i + 1]")) == ("idx", "a", ("+", "i", 1))


def test_array_nested_index():
    assert shape(expr_of("a[b[0]]")) == ("idx", "a", ("idx", "b", 0))


def test_array_update_is_desugared_to_functional_store():
    s = body_of("function f(a: int[]) { a[i] = e + 1; }")[0]
    assert isinstance(s, Assign) and s.target == "a" and s.sugar is True
    st = s.value
    assert isinstance(st, Store)
    assert shape(st.array) == "a" and shape(st.index) == "i" and shape(st.value) == ("+", "e", 1)


def test_plain_assign_is_not_sugar():
    s = body_of("function f() { x = 1; }")[0]
    assert s.sugar is False


# ---------------------------------------------------------------------
# 4. Приоритеты и ассоциативность
# ---------------------------------------------------------------------

@pytest.mark.parametrize("src,expected", [
    ("1 + 2 * 3", ("+", 1, ("*", 2, 3))),
    ("1 * 2 + 3", ("+", ("*", 1, 2), 3)),
    ("1 - 2 - 3", ("-", ("-", 1, 2), 3)),                  # левая ассоциативность
    ("8 / 4 / 2", ("/", ("/", 8, 4), 2)),
    ("(1 + 2) * 3", ("*", ("+", 1, 2), 3)),
    ("-a * b", ("*", ("-", "a"), "b")),                    # унарный минус сильнее *
    ("- - a", ("-", ("-", "a"))),
    ("a + 1 < b * 2", ("<", ("+", "a", 1), ("*", "b", 2))),
    ("a < b and c < d", ("and", ("<", "a", "b"), ("<", "c", "d"))),
    ("a or b and c", ("or", "a", ("and", "b", "c"))),      # and сильнее or
    ("a and b and c", ("and", ("and", "a", "b"), "c")),
    ("a or b or c", ("or", ("or", "a", "b"), "c")),
    ("not a and b", ("and", ("not", "a"), "b")),           # not сильнее and
    ("not not a", ("not", ("not", "a"))),
    ("not a == b", ("not", ("==", "a", "b"))),             # not слабее сравнения
    ("a[0] + 1", ("+", ("idx", "a", 0), 1)),
    ("-a[0]", ("-", ("idx", "a", 0))),
    ("length(a) - 1", ("-", ("length", "a"), 1)),
    ("f(1, g(2), x + 1)", ("f", 1, ("g", 2), ("+", "x", 1))),
    ("true == false", ("==", True, False)),
])
def test_expression_precedence(src, expected):
    assert shape(expr_of(src)) == expected


@pytest.mark.parametrize("op", ["==", "!=", "<", "<=", ">", ">="])
def test_comparison_operators_all_parse(op):
    assert shape(expr_of(f"a {op} b")) == (op, "a", "b")


def test_comparison_is_non_associative():
    res = parse("function f() { x = 1 < 2 < 3; }")
    assert not res.ok
    assert "неассоциативны" in res.diagnostics[0].message


# ---------------------------------------------------------------------
# 5. Позиции в AST (интеграция с лексером)
# ---------------------------------------------------------------------

def test_node_positions():
    src = "function f() {\n    x = a + b;\n}"
    prog = parse_ok(src)
    f = prog.functions[0]
    assert (f.line, f.col) == (1, 1)
    assign = f.body.stmts[0]
    assert (assign.line, assign.col) == (2, 5)
    plus = assign.value
    assert (plus.line, plus.col) == (2, 11)                # позиция оператора
    assert (plus.left.line, plus.left.col) == (2, 9)
    assert (plus.right.line, plus.right.col) == (2, 13)


def test_positions_with_crlf_and_tabs():
    src = "function f() {\r\n\tx = 1;\r\n}"
    assign = parse_ok(src).functions[0].body.stmts[0]
    assert (assign.line, assign.col) == (2, 2)


def test_comments_and_whitespace_are_ignored():
    prog = parse_ok("// header\nfunction f() { // inline\n  x = 1; // tail\n}\n// end")
    assert len(prog.functions) == 1


# ---------------------------------------------------------------------
# 6. Вывод AST
# ---------------------------------------------------------------------

def test_json_roundtrip_is_valid_and_has_node_types():
    prog = parse_ok("function f() { x = 1 + 2; }")
    data = json.loads(to_json(prog))
    assert data["node"] == "Program"
    assign = data["functions"][0]["body"]["stmts"][0]
    assert assign["node"] == "Assign" and assign["pos"] == "1:16"
    assert assign["value"]["node"] == "Binary" and assign["value"]["op"] == "+"


def test_json_without_positions():
    data = json.loads(to_json(parse_ok("function f() { }"), with_pos=False))
    assert "pos" not in json.dumps(data)


def test_pretty_tree_contains_structure():
    text = pretty(parse_ok("function f() { x = 1; }"), with_pos=False)
    assert "Function name='f'" in text and "Assign target='x'" in text and "IntLit value=1" in text


# ---------------------------------------------------------------------
# 7. Негативные тесты: (имя, исходник, [(строка, столбец, подстрока сообщения)])
# ---------------------------------------------------------------------

NEGATIVE = [
    ("пустой ввод", "", [(1, 1, "пустая программа")]),
    ("только пробелы и комментарий", "  // nothing\n", [(2, 1, "пустая программа")]),
    ("незакрытая круглая скобка в выражении",
     "function f() {\n  x = (1 + 2;\n  y = 3;\n}",
     [(2, 13, "не закрыта '(' (открыта в 2:7)")]),
    ("незакрытая круглая скобка в условии",
     "function f() { if (x > 0 { x = 1; } }",
     [(1, 26, "не закрыта '(' (открыта в 1:19)")]),
    ("незакрытая скобка параметров",
     "function f(a: int { }",
     [(1, 19, "не закрыта '(' (открыта в 1:11)")]),
    ("незакрытая квадратная скобка",
     "function f(a: int[]) { a[0 = 1; }",
     [(1, 28, "не закрыта '[' (открыта в 1:25)")]),
    ("незакрытая фигурная скобка",
     "function f() {\n  x = 1;\n",
     [(3, 1, "не закрыта '{' (открыта в 1:14)")]),
    ("две незакрытые фигурные скобки",
     "function f() { while (x) { x = 1;\n",
     [(2, 1, "(открыта в 1:26)"), (2, 1, "(открыта в 1:14)")]),
    ("лишняя закрывающая фигурная",
     "function f() { x = 1; } }",
     [(1, 25, "ожидалось 'function', найдено '}'")]),
    ("лишние токены после программы",
     "function f() { } x = 1;",
     [(1, 18, "ожидалось 'function', найдено 'x'")]),
    ("лишний токен в операторе",
     "function f() { x = 1 2; }",
     [(1, 21, "ожидалось ';', найдено '2'")]),
    ("пропущена точка с запятой",
     "function f() {\n  x = 1\n  y = 2;\n}",
     [(2, 8, "ожидалось ';', найдено 'y'")]),
    ("неверный оператор",
     "function f() { x = 1 +* 2; }",
     [(1, 23, "ожидалось выражение, найдено '*'")]),
    ("оператор без правого операнда",
     "function f() { x = 1 + ; }",
     [(1, 24, "ожидалось выражение, найдено ';'")]),
    ("присваивание без выражения",
     "function f() { x = ; }",
     [(1, 20, "ожидалось выражение")]),
    ("else без if",
     "function f() { else x = 1; }",
     [(1, 16, "'else' без соответствующего 'if'")]),
    ("if без скобок",
     "function f() { if x > 0 x = 1; }",
     [(1, 19, "ожидалось '('")]),
    ("нет тела функции",
     "function f()",
     [(1, 13, "ожидалось '{'")]),
    ("нет имени функции",
     "function () { }",
     [(1, 10, "ожидалось имя функции")]),
    ("неверный тип параметра",
     "function f(a: , b) { }",
     [(1, 15, "ожидался тип")]),
    ("пустой returns ()",
     "function f() returns () { }",
     [(1, 23, "хотя бы один результат")]),
    ("оператор вместо идентификатора",
     "function f() { x y; }",
     [(1, 18, "ожидалось '=', '[' или '('")]),
    ("мусор в начале программы",
     "x = 1; function f() { }",
     [(1, 1, "ожидалось 'function', найдено 'x'")]),
    ("недопустимый символ",
     "function f() { x = 1 @; }",
     [(1, 22, "недопустимый символ '@'")]),
    ("кириллица вне алфавита",
     "function f() { переменная = 1; }",
     [(1, 16, "недопустимый символ 'п'")]),
    ("не закрыта функция перед следующей",
     "function f() { x = 1;\nfunction g() { y = 2; }",
     [(2, 1, "не закрыта '{' (открыта в 1:14)")]),
]


@pytest.mark.parametrize("name,src,expected", NEGATIVE, ids=[n[0] for n in NEGATIVE])
def test_negative_programs(name, src, expected):
    res = parse(src)
    assert not res.ok, "ошибка должна быть обнаружена"
    got = [(d.line, d.col, d.message) for d in res.diagnostics]
    for (line, col, part) in expected:
        assert any(l == line and c == col and part in m for (l, c, m) in got), \
            f"не найдена диагностика {line}:{col} ~ {part!r}; получено: {got}"


def test_diagnostics_are_sorted_by_position_and_readable():
    res = parse("function f() { x = 1 @ 2;\n y = (3; }")
    positions = [(d.line, d.col) for d in res.diagnostics]
    assert positions == sorted(positions)
    for d in res.diagnostics:
        assert str(d).startswith(f"{d.line}:{d.col}: ошибка: ")


def test_no_cascade_duplicates_on_same_token():
    res = parse("function f() { x = ; }")
    assert len(res.diagnostics) == 1


# ---------------------------------------------------------------------
# 8. Восстановление: после ошибки разбор продолжается
# ---------------------------------------------------------------------

def test_recovery_keeps_parsing_next_statements():
    res = parse("function f() { x = ; y = 2; assert y > 0; }")
    assert len(res.diagnostics) == 1
    kinds = [type(s).__name__ for s in res.program.functions[0].body.stmts]
    assert kinds == ["Assign", "Assert"]                    # сломанный оператор отброшен


def test_recovery_reports_multiple_independent_errors():
    res = parse("function f() { x = ; y = 2; z = 1 + ; w = 3; }")
    assert [(d.line, d.col) for d in res.diagnostics] == [(1, 20), (1, 37)]
    assert len(res.program.functions[0].body.stmts) == 2


def test_recovery_continues_with_next_function():
    res = parse("function f( { x = 1; }\nfunction g() { y = 2; }")
    assert not res.ok
    assert [f.name for f in res.program.functions] == ["f", "g"]


def test_recovery_inside_nested_blocks():
    res = parse("function f() { while (x) { a = ; b = 1; } c = 2; }")
    w = res.program.functions[0].body.stmts[0]
    assert len(res.diagnostics) == 1
    assert len(w.body.stmts) == 1 and len(res.program.functions[0].body.stmts) == 2


# ---------------------------------------------------------------------
# 9. Парсер не зацикливается и не падает на произвольном вводе
# ---------------------------------------------------------------------

VOCAB = ["function", "returns", "uses", "requires", "ensures", "while", "if", "else",
         "assert", "assume", "invariant", "length", "return", "true", "false", "not",
         "and", "or", "int", "bool", "x", "y", "f", "0", "1", "42", "(", ")", "[", "]",
         "{", "}", ",", ";", ":", "+", "-", "*", "/", "==", "!=", "<=", ">=", "<", ">",
         "=", "@", "ф"]


def test_parser_terminates_on_random_token_soup():
    rnd = random.Random(12345)
    for _ in range(1500):
        n = rnd.randint(0, 40)
        src = " ".join(rnd.choice(VOCAB) for _ in range(n))
        res = parse(src)                                    # не должно зависать/падать
        assert res.program is not None


def test_parser_terminates_on_mutated_valid_programs():
    rnd = random.Random(777)
    base = open(os.path.join(HERE, "programs", "ok_arrays.fun"), encoding="utf-8").read().split()
    for _ in range(600):
        toks = list(base)
        for _ in range(rnd.randint(1, 4)):
            op = rnd.choice(["drop", "dup", "swap", "insert"])
            i = rnd.randrange(len(toks))
            if op == "drop":
                del toks[i]
            elif op == "dup":
                toks.insert(i, toks[i])
            elif op == "swap" and len(toks) > 1:
                j = rnd.randrange(len(toks))
                toks[i], toks[j] = toks[j], toks[i]
            else:
                toks.insert(i, rnd.choice(VOCAB))
            if not toks:
                toks = ["x"]
        parse(" ".join(toks))


@pytest.mark.parametrize("src", [")", "}", "]", ";", "{{{{", "((((", "function", "function function",
                                  "function f(", "function f() {", "else else else", "@@@@", "\x80"])
def test_parser_terminates_on_pathological_inputs(src):
    res = parse(src)
    assert not res.ok


def test_parser_handles_long_input():
    body = "x = x + 1; " * 5000
    res = parse("function f() { %s }" % body)
    assert res.ok and len(res.program.functions[0].body.stmts) == 5000
