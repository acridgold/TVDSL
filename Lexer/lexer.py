"""
Определения токенов языка Funny и сборка итогового лексера
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple

from automata import combine, subset_construction, DFA
from minimize import build_minimized

# (имя_токена, регулярное_выражение, skip)
TOKEN_DEFS: List[Tuple[str, str, bool]] = [
    ("KW_FUNCTION", "function", False),
    ("KW_RETURNS", "returns", False),
    ("KW_WHILE", "while", False),
    ("KW_IF", "if", False),
    ("KW_ELSE", "else", False),
    ("KW_ASSERT", "assert", False),
    ("KW_ASSUME", "assume", False),
    ("KW_INVARIANT", "invariant", False),
    ("KW_LENGTH", "length", False),

    ("IDENT", "[A-Za-z_][A-Za-z_0-9]*", False),
    ("INT", "0|[1-9][0-9]*", False),

    ("WS", "[ \\t\\r\\n]+", True),
    ("COMMENT", "//[^\\n]*", True),

    ("LPAREN", "\\(", False),
    ("RPAREN", "\\)", False),
    ("LBRACKET", "\\[", False),
    ("RBRACKET", "\\]", False),
    ("LBRACE", "{", False),
    ("RBRACE", "}", False),
    ("COMMA", ",", False),
    ("SEMI", ";", False),

    ("EQEQ", "==", False),
    ("NEQ", "!=", False),
    ("LE", "<=", False),
    ("GE", ">=", False),
    ("LT", "<", False),
    ("GT", ">", False),
    ("ASSIGN", "=", False),

    ("PLUS", "\\+", False),
    ("MINUS", "-", False),
    ("STAR", "\\*", False),
    ("SLASH", "/", False),
]

SKIP_TOKENS = {name for name, _pat, skip in TOKEN_DEFS if skip}


@dataclass
class Token:
    name: str
    value: str
    pos: int


@dataclass
class LexError:
    pos: int
    char: str


@dataclass
class CombinedLexer:
    raw_dfa: DFA
    dfa: DFA  # minimized

    def scan(self, text: str) -> Tuple[List[Token], List[LexError]]:
        tokens: List[Token] = []
        errors: List[LexError] = []
        i = 0
        n = len(text)
        trans = self.dfa.trans
        accept = self.dfa.accept
        alphabet = self.dfa.alphabet
        trap = self.dfa.trap
        start = self.dfa.start

        while i < n:
            state = start
            last_accept: Optional[Tuple[int, str]] = None
            j = i
            while j < n:
                c = text[j]
                if c not in alphabet:
                    nxt = trap
                else:
                    nxt = trans[state][c]
                if nxt == trap:
                    break
                state = nxt
                j += 1
                if state in accept:
                    last_accept = (j, accept[state])

            if last_accept is None:
                errors.append(LexError(pos=i, char=text[i]))
                i += 1
                continue

            end, name = last_accept
            lexeme = text[i:end]
            if name not in SKIP_TOKENS:
                tokens.append(Token(name=name, value=lexeme, pos=i))
            i = end

        return tokens, errors


def build_lexer() -> CombinedLexer:
    token_pairs = [(name, pat) for name, pat, _skip in TOKEN_DEFS]
    tnfa = combine(token_pairs)
    raw_dfa = subset_construction(tnfa)
    min_dfa = build_minimized(raw_dfa)
    return CombinedLexer(raw_dfa=raw_dfa, dfa=min_dfa)


def build_single_dfa(pattern: str) -> DFA:
    """Собрать минимизированный ДКА для ровно одного регулярного выражения
    (используется в тестах на "полное совпадение строки с токеном")."""
    tnfa = combine([("TOK", pattern)])
    raw = subset_construction(tnfa)
    return build_minimized(raw)


def full_match(dfa: DFA, s: str) -> bool:
    """Принимает ли ДКА строку s целиком (используется для юнит-тестов
    отдельных регулярных выражений: '00', '01' и т.д.)."""
    state = dfa.start
    for c in s:
        if c not in dfa.alphabet:
            return False
        state = dfa.trans[state][c]
        if state == dfa.trap:
            return False
    return state in dfa.accept


def classify_first(dfa: DFA, text: str) -> Optional[str]:
    """Имя токена для максимального совпадения от начала text — БЕЗ учёта
    SKIP_TOKENS (то есть WS/COMMENT возвращаются как обычные теги, а не
    молча пропускаются, как в CombinedLexer.scan). None, если text пуст
    или первый же символ уходит в ловушку (нет ни одного совпадения).
    Полезно для тестов уровня "что это вообще за токен", отдельно от
    семантики "выбрасывать ли его из потока"."""
    if not text:
        return None
    state = dfa.start
    last_tag: Optional[str] = None
    for c in text:
        if c not in dfa.alphabet:
            break
        nxt = dfa.trans[state][c]
        if nxt == dfa.trap:
            break
        state = nxt
        if state in dfa.accept:
            last_tag = dfa.accept[state]
    return last_tag

