r"""
Простой парсер регулярных выражений -> AST.

Поддерживаемый синтаксис:
    a          - литеральный символ
    ab         - конкатенация
    a|b        - альтернатива
    a*         - звезда Клини (0 или более)
    a+         - плюс (1 или более)
    a?         - опционально (0 или 1)
    (a|b)c     - группировка
    [abc]      - класс символов (перечисление)
    [a-z]      - класс символов (диапазон), диапазоны и одиночные символы можно смешивать
    [^a-z]     - отрицание класса (universe \ class)
    \n \t \r \\ \( \) \[ \] \| \* \+ \? \. \^ \-  - экранирование

Алфавит для отрицания класса ([^...]) берётся как ASCII 32..126 (печатные
символы), поскольку весь язык Funny описывается печатными ASCII-символами.
"""

from dataclasses import dataclass, field
from typing import FrozenSet, Optional

# "Вселенная" символов, используемая для интерпретации отрицания в классах.
PRINTABLE_UNIVERSE: FrozenSet[str] = frozenset(chr(c) for c in range(32, 127))

ESCAPES = {
    "n": "\n",
    "t": "\t",
    "r": "\r",
    "\\": "\\",
    "(": "(",
    ")": ")",
    "[": "[",
    "]": "]",
    "|": "|",
    "*": "*",
    "+": "+",
    "?": "?",
    ".": ".",
    "^": "^",
    "-": "-",
}


class RegexSyntaxError(ValueError):
    pass


# ---- AST -------------------------------------------------------------

@dataclass(frozen=True)
class Char:
    c: str


@dataclass(frozen=True)
class CharSet:
    chars: FrozenSet[str]


@dataclass(frozen=True)
class Epsilon:
    pass


@dataclass(frozen=True)
class Concat:
    left: object
    right: object


@dataclass(frozen=True)
class Union:
    left: object
    right: object


@dataclass(frozen=True)
class Star:
    inner: object


@dataclass(frozen=True)
class Plus:
    inner: object


@dataclass(frozen=True)
class Optional_:
    inner: object


# ---- Parser ------------------------------------------------------------

class _Parser:
    def __init__(self, s: str):
        self.s = s
        self.i = 0
        self.n = len(s)

    def peek(self) -> Optional[str]:
        return self.s[self.i] if self.i < self.n else None

    def advance(self) -> str:
        c = self.s[self.i]
        self.i += 1
        return c

    def parse(self):
        node = self.parse_union()
        if self.i != self.n:
            raise RegexSyntaxError(
                f"Неожиданный символ {self.s[self.i]!r} на позиции {self.i} в {self.s!r}"
            )
        return node

    def parse_union(self):
        node = self.parse_concat()
        while self.peek() == "|":
            self.advance()
            rhs = self.parse_concat()
            node = Union(node, rhs)
        return node

    def parse_concat(self):
        parts = []
        while self.peek() is not None and self.peek() not in "|)":
            parts.append(self.parse_repeat())
        if not parts:
            return Epsilon()
        node = parts[0]
        for p in parts[1:]:
            node = Concat(node, p)
        return node

    def parse_repeat(self):
        atom = self.parse_atom()
        while self.peek() in ("*", "+", "?"):
            op = self.advance()
            if op == "*":
                atom = Star(atom)
            elif op == "+":
                atom = Plus(atom)
            else:
                atom = Optional_(atom)
        return atom

    def parse_atom(self):
        c = self.peek()
        if c is None:
            raise RegexSyntaxError("Неожиданный конец регулярного выражения")
        if c == "(":
            self.advance()
            node = self.parse_union()
            if self.peek() != ")":
                raise RegexSyntaxError("Ожидалась ')'")
            self.advance()
            return node
        if c == "[":
            return self.parse_class()
        if c == ".":
            self.advance()
            return CharSet(PRINTABLE_UNIVERSE)
        if c == "\\":
            self.advance()
            nc = self.peek()
            if nc is None:
                raise RegexSyntaxError("Экранирование в конце выражения")
            self.advance()
            if nc not in ESCAPES:
                raise RegexSyntaxError(f"Неизвестное экранирование \\{nc}")
            return Char(ESCAPES[nc])
        if c in "*+?|)":
            raise RegexSyntaxError(f"Спецсимвол {c!r} не может начинать атом")
        self.advance()
        return Char(c)

    def parse_class(self):
        assert self.advance() == "["
        negate = False
        if self.peek() == "^":
            self.advance()
            negate = True
        chars = set()
        first = True
        while self.peek() is not None and (self.peek() != "]" or first):
            first = False
            ch = self._class_char()
            if self.peek() == "-" and self.i + 1 < self.n and self.s[self.i + 1] != "]":
                self.advance()  # '-'
                end = self._class_char()
                if ord(end) < ord(ch):
                    raise RegexSyntaxError(f"Некорректный диапазон {ch}-{end}")
                for code in range(ord(ch), ord(end) + 1):
                    chars.add(chr(code))
            else:
                chars.add(ch)
        if self.peek() != "]":
            raise RegexSyntaxError("Незакрытый класс символов, ожидалась ']'")
        self.advance()
        if negate:
            chars = set(PRINTABLE_UNIVERSE) - chars
        return CharSet(frozenset(chars))

    def _class_char(self) -> str:
        c = self.advance()
        if c == "\\":
            nc = self.peek()
            if nc is None:
                raise RegexSyntaxError("Экранирование в конце класса символов")
            self.advance()
            if nc not in ESCAPES:
                raise RegexSyntaxError(f"Неизвестное экранирование \\{nc}")
            return ESCAPES[nc]
        return c


def parse_regex(pattern: str):
    """Разобрать текстовое регулярное выражение в AST."""
    return _Parser(pattern).parse()
