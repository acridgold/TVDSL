import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from Lexer.lexer import build_lexer, build_single_dfa, TOKEN_DEFS, full_match, classify_first

PATTERNS = {name: pat for name, pat, _skip in TOKEN_DEFS}


@pytest.fixture(scope="module")
def lexer():
    return build_lexer()


@pytest.fixture(scope="module")
def int_dfa():
    return build_single_dfa(PATTERNS["INT"])


@pytest.fixture(scope="module")
def ident_dfa():
    return build_single_dfa(PATTERNS["IDENT"])


@pytest.fixture(scope="module")
def ws_dfa():
    return build_single_dfa(PATTERNS["WS"])


def names(tokens):
    return [t.name for t in tokens]


def pairs(tokens):
    return [(t.name, t.value) for t in tokens]


# ---------------------------------------------------------------------
# 1. Пустая строка
# ---------------------------------------------------------------------

def test_empty_string_scan(lexer):
    tokens, errors = lexer.scan("")
    assert tokens == []
    assert errors == []


def test_empty_string_not_int_not_ident(int_dfa, ident_dfa):
    assert full_match(int_dfa, "") is False
    assert full_match(ident_dfa, "") is False


# ---------------------------------------------------------------------
# 2. Строки только из пробелов/табов/CRLF
# ---------------------------------------------------------------------

@pytest.mark.parametrize("s", [" ", "\t", "\r\n", "   \t\t\r\n\n  "])
def test_whitespace_only_is_skipped(lexer, s):
    tokens, errors = lexer.scan(s)
    assert tokens == []
    assert errors == []


@pytest.mark.parametrize("s", [" ", "\t", "\r\n", "     "])
def test_whitespace_only_matches_ws_regex(ws_dfa, s):
    assert full_match(ws_dfa, s) is True


# ---------------------------------------------------------------------
# 3. Числа: 0, 00, 01 (отрицательный пример), и т.п.
# ---------------------------------------------------------------------

@pytest.mark.parametrize("s,expected", [
    ("0", True),
    ("1", True),
    ("9", True),
    ("10", True),
    ("123", True),
    ("00", False),   # ведущий ноль запрещён
    ("01", False),
    ("007", False),
    ("", False),
    ("1a", False),
])
def test_int_full_match(int_dfa, s, expected):
    assert full_match(int_dfa, s) is expected


def test_lexer_splits_leading_zero_sequence_into_two_ints(lexer):
    # "01" не является единым INT-токеном: лексер (maximal munch) обязан
    # остановиться после "0" и начать новый токен с "1".
    tokens, errors = lexer.scan("01")
    assert errors == []
    assert pairs(tokens) == [("INT", "0"), ("INT", "1")]


def test_lexer_00_splits_into_two_zero_tokens(lexer):
    tokens, errors = lexer.scan("00")
    assert errors == []
    assert pairs(tokens) == [("INT", "0"), ("INT", "0")]


# ---------------------------------------------------------------------
# 4. Идентификаторы с '_'
# ---------------------------------------------------------------------

@pytest.mark.parametrize("s,expected", [
    ("x", True),
    ("_", True),
    ("_x", True),
    ("x_1", True),
    ("__init__", True),
    ("1x", False),
    ("", False),
    ("a b", False),
    ("a-b", False),
])
def test_ident_full_match(ident_dfa, s, expected):
    assert full_match(ident_dfa, s) is expected


def test_lexer_tokenizes_underscore_identifiers(lexer):
    tokens, errors = lexer.scan("_foo bar_1 __x__")
    assert errors == []
    assert pairs(tokens) == [
        ("IDENT", "_foo"), ("IDENT", "bar_1"), ("IDENT", "__x__"),
    ]


# ---------------------------------------------------------------------
# 5. Ключевые слова (`function`, `returns`, `while`, `if`, `else`,
#    `assert`, `assume`, `invariant`, `length`)
# ---------------------------------------------------------------------

KEYWORDS = {
    "function": "KW_FUNCTION",
    "returns": "KW_RETURNS",
    "while": "KW_WHILE",
    "if": "KW_IF",
    "else": "KW_ELSE",
    "assert": "KW_ASSERT",
    "assume": "KW_ASSUME",
    "invariant": "KW_INVARIANT",
    "length": "KW_LENGTH",
}


@pytest.mark.parametrize("word,tag", list(KEYWORDS.items()))
def test_keywords_recognized_as_keywords_not_ident(lexer, word, tag):
    tokens, errors = lexer.scan(word)
    assert errors == []
    assert pairs(tokens) == [(tag, word)]


@pytest.mark.parametrize("word", ["iffy", "elsewhere", "whilex", "lengths", "assertion"])
def test_keyword_prefixes_are_still_identifiers(lexer, word):
    # Приоритет ключевых слов не должен "откусывать" префикс у более
    # длинного идентификатора — maximal munch обязан выбрать IDENT целиком.
    tokens, errors = lexer.scan(word)
    assert errors == []
    assert pairs(tokens) == [("IDENT", word)]


# ---------------------------------------------------------------------
# 6. Разделители/операторы
# ---------------------------------------------------------------------

OPERATORS = {
    "(": "LPAREN", ")": "RPAREN", "[": "LBRACKET", "]": "RBRACKET",
    "{": "LBRACE", "}": "RBRACE", ",": "COMMA", ";": "SEMI",
    "+": "PLUS", "-": "MINUS", "*": "STAR", "/": "SLASH",
    "==": "EQEQ", "!=": "NEQ", "<=": "LE", ">=": "GE",
    "<": "LT", ">": "GT", "=": "ASSIGN",
}


@pytest.mark.parametrize("op,tag", list(OPERATORS.items()))
def test_single_operator(lexer, op, tag):
    tokens, errors = lexer.scan(op)
    assert errors == []
    assert pairs(tokens) == [(tag, op)]


def test_operators_maximal_munch_two_char_over_one_char(lexer):
    # "==" должен разбираться как один EQEQ, а не как два ASSIGN подряд.
    tokens, errors = lexer.scan("== != <= >= = < >")
    assert errors == []
    assert names(tokens) == ["EQEQ", "NEQ", "LE", "GE", "ASSIGN", "LT", "GT"]


def test_all_delimiters_in_sequence(lexer):
    tokens, errors = lexer.scan("()[]{},;")
    assert errors == []
    assert names(tokens) == [
        "LPAREN", "RPAREN", "LBRACKET", "RBRACKET",
        "LBRACE", "RBRACE", "COMMA", "SEMI",
    ]


# ---------------------------------------------------------------------
# 7. Комментарии `//...` до конца строки
# ---------------------------------------------------------------------

def test_ascii_only_line_comment_is_skipped(lexer):
    tokens, errors = lexer.scan("x = 1; // trailing comment until EOL\ny = 2;")
    assert errors == []
    assert pairs(tokens) == [
        ("IDENT", "x"), ("ASSIGN", "="), ("INT", "1"), ("SEMI", ";"),
        ("IDENT", "y"), ("ASSIGN", "="), ("INT", "2"), ("SEMI", ";"),
    ]


def test_comment_does_not_consume_newline(lexer):
    tokens, errors = lexer.scan("// comment\nx")
    assert errors == []
    assert pairs(tokens) == [("IDENT", "x")]


def test_comment_full_match_stops_before_newline():
    comment_dfa = build_single_dfa(PATTERNS["COMMENT"])
    assert full_match(comment_dfa, "// abc") is True
    assert full_match(comment_dfa, "//") is True
    assert full_match(comment_dfa, "// abc\n") is False  # содержит \n целиком
    assert full_match(comment_dfa, "/ abc") is False


# ---------------------------------------------------------------------
# 8. Выход за алфавит (non-ASCII) должен попадать в ловушку
# ---------------------------------------------------------------------

@pytest.mark.parametrize("bad", ["ф", "я", "€", "ü", "中"])
def test_non_ascii_char_is_lex_error(lexer, bad):
    tokens, errors = lexer.scan(bad)
    assert tokens == []
    assert len(errors) == 1
    assert errors[0].char == bad
    assert errors[0].pos == 0


def test_non_ascii_inside_otherwise_valid_program_is_reported(lexer):
    tokens, errors = lexer.scan("x = ф;")
    error_chars = [e.char for e in errors]
    assert "ф" in error_chars
    # лексер восстанавливается и продолжает разбор после ошибки
    assert ("SEMI", ";") in pairs(tokens)


def test_non_ascii_never_matches_any_single_token_dfa(ident_dfa, int_dfa, ws_dfa):
    for dfa in (ident_dfa, int_dfa, ws_dfa):
        assert full_match(dfa, "ф") is False


# ---------------------------------------------------------------------
# 9. Комплексный тест: целая программа на Funny
# ---------------------------------------------------------------------

def test_full_program(lexer):
    program = (
        "function fib(n) returns int {\n"
        "    assume n >= 0;\n"
        "    x = 0;\n"
        "    y = 1;\n"
        "    while (n != 0) {\n"
        "        z = x + y;\n"
        "        x = y;\n"
        "        y = z;\n"
        "        n = n - 1;\n"
        "    }\n"
        "    assert x >= 0; // sanity\n"
        "    return x;\n"
        "}\n"
    )
    tokens, errors = lexer.scan(program)
    assert errors == []
    expected_head = [
        ("KW_FUNCTION", "function"), ("IDENT", "fib"), ("LPAREN", "("),
        ("IDENT", "n"), ("RPAREN", ")"), ("KW_RETURNS", "returns"),
        ("KW_INT", "int"), ("LBRACE", "{"),
        ("KW_ASSUME", "assume"), ("IDENT", "n"), ("GE", ">="), ("INT", "0"), ("SEMI", ";"),
    ]
    assert pairs(tokens)[: len(expected_head)] == expected_head
    # HW2: "return" и "int" стали ключевыми словами
    assert ("KW_RETURN", "return") in pairs(tokens)
    assert ("KW_ASSERT", "assert") in pairs(tokens)


# ---------------------------------------------------------------------
# 10. Свойства построенного минимизированного ДКА
# ---------------------------------------------------------------------

def test_minimized_dfa_not_larger_than_raw(lexer):
    assert len(lexer.dfa.states) <= len(lexer.raw_dfa.states)


def test_dfa_is_total_function(lexer):
    dfa = lexer.dfa
    for s in dfa.states:
        for sym in dfa.alphabet:
            assert sym in dfa.trans[s]


def test_trap_state_is_a_sink_and_non_accepting(lexer):
    dfa = lexer.dfa
    assert dfa.trap not in dfa.accept
    for sym in dfa.alphabet:
        assert dfa.trans[dfa.trap][sym] == dfa.trap


def test_word_prefixes_of_keywords_do_not_prematurely_accept(lexer):
    # "el" — префикс "else", не должен приниматься ни как что-то, кроме
    # части идентификатора при продолжении.
    tokens, errors = lexer.scan("el")
    assert errors == []
    assert pairs(tokens) == [("IDENT", "el")]


# ---------------------------------------------------------------------
# 11. Табличные тесты классификации первого токена
# ---------------------------------------------------------------------
#
# В отличие от lexer.scan() (который выбрасывает WS/COMMENT из потока),
# classify_first() отвечает на более базовый вопрос: "каким токеном ДКА
# вообще классифицирует максимальное совпадение от начала строки", не
# заботясь о том, skip этот токен или нет — поэтому WS/COMMENT здесь
# ожидаются как обычные теги, а не отбрасываются.

FIRST_TOKEN_TESTS = [
    # (вход, ожидаемый первый токен | None, комментарий)
    ("", None, "пустая строка"),
    ("   \t\r\n", "WS", "только пробелы"),

    ("0", "INT", "ноль"),
    ("00", "INT", "00 — INT(0) + INT(0)"),
    ("01", "INT", "01 — INT(0) + INT(1), как один INT невалиден"),
    ("42", "INT", "двузначное"),
    ("100", "INT", "трёхзначное"),

    ("foo", "IDENT", "простой IDENT"),
    ("foo_bar", "IDENT", "IDENT с _"),
    ("_x", "IDENT", "IDENT с _ в начале"),
    ("_1", "IDENT", "IDENT с цифрой"),

    ("function", "KW_FUNCTION", "kw"),
    ("returns", "KW_RETURNS", "kw"),
    ("while", "KW_WHILE", "kw"),
    ("if", "KW_IF", "kw"),
    ("else", "KW_ELSE", "kw"),
    ("assert", "KW_ASSERT", "kw"),
    ("assume", "KW_ASSUME", "kw"),
    ("invariant", "KW_INVARIANT", "kw"),
    ("length", "KW_LENGTH", "kw"),

    ("functio", "IDENT", "префикс kw -> IDENT"),
    ("iff", "IDENT", "префикс kw + доп. символ -> IDENT"),

    ("(", "LPAREN", "("), (")", "RPAREN", ")"),
    ("[", "LBRACKET", "["), ("]", "RBRACKET", "]"),
    ("{", "LBRACE", "{"), ("}", "RBRACE", "}"),
    (",", "COMMA", ","), (";", "SEMI", ";"),
    ("+", "PLUS", "+"), ("-", "MINUS", "-"), ("*", "STAR", "*"), ("/", "SLASH", "/"),
    ("==", "EQEQ", "=="), ("!=", "NEQ", "!="),
    ("<=", "LE", "<="), (">=", "GE", ">="),
    ("<", "LT", "<"), (">", "GT", ">"), ("=", "ASSIGN", "="),
    ("===", "EQEQ", "maximal munch: EQEQ(==) захватывает 2 символа, третий '=' уже не его"),

    ("// comment", "COMMENT", "комментарий до конца строки"),
    ("//", "COMMENT", "пустой комментарий"),

    ("π", None, "non-ASCII -> trap"),
    ("@", None, "мусорный ASCII (не входит ни в один токен) -> trap"),
    ("\x80", None, "байт вне печатного ASCII -> trap"),
    ("1π", "INT", "1 корректно, π -> trap после — но на первый токен это не влияет"),
]


@pytest.mark.parametrize("text,expected,comment", FIRST_TOKEN_TESTS,
                          ids=[t[2] for t in FIRST_TOKEN_TESTS])
def test_first_token_classification(lexer, text, expected, comment):
    assert classify_first(lexer.dfa, text) == expected, comment


# ---------------------------------------------------------------------
# 12. Класс символов — порядок элементов внутри [...] не должен влиять
#     на результат (это множество, а не последовательность): "0-9_" и
#     "_0-9" внутри класса обязаны давать одинаковый по поведению автомат.
# ---------------------------------------------------------------------

CHAR_CLASS_ORDER_PROBES = [
    "x", "_", "_1", "foo_bar", "1x", "", "a b", "__init__", "Z9_a", "abc123",
]


@pytest.fixture(scope="module")
def ident_dfa_reordered():
    # тот же язык, что и IDENT, но порядок внутри второго класса другой:
    # "A-Za-z0-9_" вместо "A-Za-z_0-9"
    return build_single_dfa("[A-Za-z_][A-Za-z0-9_]*")


@pytest.mark.parametrize("s", CHAR_CLASS_ORDER_PROBES)
def test_char_class_element_order_does_not_change_language(ident_dfa, ident_dfa_reordered, s):
    assert full_match(ident_dfa, s) == full_match(ident_dfa_reordered, s)


def test_char_class_element_order_does_not_change_dfa_size(ident_dfa, ident_dfa_reordered):
    # раз языки идентичны, минимизированные ДКА должны быть изоморфны —
    # в частности, иметь одинаковое число состояний и один и тот же алфавит.
    assert len(ident_dfa.states) == len(ident_dfa_reordered.states)
    assert ident_dfa.alphabet == ident_dfa_reordered.alphabet


# ---------------------------------------------------------------------
# 13. INT: "0|[1-9][0-9]*" vs "0|[1-9][0-9]*|00*" — лишняя альтернатива
#     00* меняет язык (разрешает многонулевые числа "00", "000", ...),
#     хотя выглядит как безобидное расширение. Тест фиксирует ГДЕ именно
#     расходятся два автомата, а не просто "они разные".
# ---------------------------------------------------------------------

@pytest.fixture(scope="module")
def int_dfa_with_multi_zero_alt():
    # намеренно "испорченный" вариант INT: альтернатива 00* добавляет
    # любую непустую строку из одних нулей в язык.
    return build_single_dfa("0|[1-9][0-9]*|00*")


@pytest.mark.parametrize("s", ["00", "000", "0000", "00000"])
def test_extra_00_star_alt_now_accepts_multi_zero_strings(int_dfa, int_dfa_with_multi_zero_alt, s):
    # в оригинальном INT такие строки НЕ матчатся целиком (ведущий ноль
    # запрещён), а в "испорченном" варианте — матчатся.
    assert full_match(int_dfa, s) is False
    assert full_match(int_dfa_with_multi_zero_alt, s) is True


@pytest.mark.parametrize("s", ["0", "1", "9", "10", "90", "01", "007", "1x", ""])
def test_extra_00_star_alt_does_not_change_anything_else(int_dfa, int_dfa_with_multi_zero_alt, s):
    # на всех остальных строках (включая "01"/"007" — там после нулей
    # идёт ненулевая цифра, а 00* матчит только сплошные нули) поведение
    # обоих автоматов должно совпадать.
    assert full_match(int_dfa, s) == full_match(int_dfa_with_multi_zero_alt, s)


# ---------------------------------------------------------------------
# 14. HW2: позиции токенов (line/col) и новые токены
# ---------------------------------------------------------------------

def test_token_positions_line_col(lexer):
    tokens, _ = lexer.scan("x = 1;\n  y\r\n\tz")
    got = [(t.value, t.line, t.col) for t in tokens]
    assert got == [("x", 1, 1), ("=", 1, 3), ("1", 1, 5), (";", 1, 6),
                   ("y", 2, 3), ("z", 3, 2)]


def test_lex_error_positions(lexer):
    _, errors = lexer.scan("ab\n  @")
    assert [(e.char, e.line, e.col) for e in errors] == [("@", 2, 3)]


@pytest.mark.parametrize("word,tag", [
    ("uses", "KW_USES"), ("requires", "KW_REQUIRES"), ("ensures", "KW_ENSURES"),
    ("return", "KW_RETURN"), ("true", "KW_TRUE"), ("false", "KW_FALSE"),
    ("not", "KW_NOT"), ("and", "KW_AND"), ("or", "KW_OR"),
    ("int", "KW_INT"), ("bool", "KW_BOOL"), (":", "COLON"),
])
def test_hw2_tokens(lexer, word, tag):
    tokens, errors = lexer.scan(word)
    assert errors == [] and pairs(tokens) == [(tag, word)]
