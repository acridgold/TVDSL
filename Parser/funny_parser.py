"""
Синтаксический анализатор языка Funny: LL(1), рекурсивный спуск,
режим паники для восстановления после ошибок.

Грамматика — в grammar.txt. Публичный API:

    result = parse(text)
    result.program        # ast_nodes.Program (может быть частичным при ошибках)
    result.diagnostics    # список Diagnostic (лексические + синтаксические), по позиции
    result.ok             # True, если ошибок нет

Гарантия завершения: каждая итерация любого цикла разбора либо потребляет
хотя бы один токен, либо выходит из цикла (см. parse_block / parse_program),
поэтому на любом входе парсер завершается.
"""
import os
import sys
from dataclasses import dataclass
from typing import List, Optional

from ast_nodes import (
    Assert, Assign, Assume, Binary, Block, BoolLit, Call, CallStmt, Function,
    If, Index, IntLit, Node, Param, Program, Return, Store, Unary, Var,
    VarDecl, While,
)

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "Lexer"))
from lexer import Token, build_lexer

# Как называть ожидаемый токен в сообщениях
EXPECT_TEXT = {
    "IDENT": "идентификатор",
    "LPAREN": "'('", "RPAREN": "')'", "LBRACKET": "'['", "RBRACKET": "']'",
    "LBRACE": "'{'", "RBRACE": "'}'", "SEMI": "';'", "ASSIGN": "'='",
    "COMMA": "','", "COLON": "':'",
}

CMP_OPS = {"EQEQ", "NEQ", "LT", "LE", "GT", "GE"}
STMT_START = {"LBRACE", "KW_IF", "KW_WHILE", "KW_ASSERT", "KW_ASSUME",
              "KW_RETURN", "KW_INT", "KW_BOOL"}
OPEN_BRACKET = {"LPAREN": "(", "LBRACKET": "[", "LBRACE": "{"}


@dataclass
class Diagnostic:
    line: int
    col: int
    message: str
    kind: str = "syntax"        # "syntax" | "lexical"

    def __str__(self) -> str:
        return f"{self.line}:{self.col}: ошибка: {self.message}"


@dataclass
class ParseResult:
    program: Program
    diagnostics: List[Diagnostic]
    tokens: List[Token]

    @property
    def ok(self) -> bool:
        return not self.diagnostics


class ParseError(Exception):
    def __init__(self, message: str, index: int, pos=None):
        super().__init__(message)
        self.message = message
        self.index = index          # индекс токена, на котором споткнулись
        self.pos = pos              # (line, col), если позиция отличается от позиции токена


def describe(tok: Token) -> str:
    return "конец файла" if tok.name == "EOF" else f"'{tok.value}'"


class Parser:
    def __init__(self, tokens: List[Token], end_line: int, end_col: int, end_pos: int):
        self.toks = list(tokens) + [Token("EOF", "", end_pos, end_line, end_col)]
        self.i = 0
        self.diags: List[Diagnostic] = []
        self._last_err_index = -1

    # ---- примитивы -------------------------------------------------------

    def peek(self, k: int = 0) -> Token:
        return self.toks[min(self.i + k, len(self.toks) - 1)]

    def at(self, *names: str) -> bool:
        return self.peek().name in names

    def advance(self) -> Token:
        t = self.peek()
        if t.name != "EOF":
            self.i += 1
        return t

    def match(self, name: str) -> Optional[Token]:
        return self.advance() if self.at(name) else None

    def expect(self, name: str, what: Optional[str] = None,
               opener: Optional[Token] = None) -> Token:
        if self.at(name):
            return self.advance()
        want = what or EXPECT_TEXT.get(name, name)
        found = describe(self.peek())
        if opener is not None:
            raise ParseError(
                f"не закрыта '{opener.value}' (открыта в {opener.line}:{opener.col}): "
                f"ожидалось {want}, найдено {found}", self.i)
        pos = None
        if name == "SEMI" and self.i > 0:       # пропущенная ';' — сразу после предыдущего токена
            prev = self.toks[self.i - 1]
            pos = (prev.line, prev.col + len(prev.value))
        raise ParseError(f"ожидалось {want}, найдено {found}", self.i, pos)

    def fail(self, message: str) -> "ParseError":
        return ParseError(message, self.i)

    def report(self, e: ParseError) -> None:
        # не засыпаем пользователя каскадом ошибок на одном и том же токене
        if e.index == self._last_err_index:
            return
        self._last_err_index = e.index
        t = self.toks[e.index]
        line, col = e.pos if e.pos else (t.line, t.col)
        self.diags.append(Diagnostic(line, col, e.message))

    # ---- программа ---------------------------------------------------------

    def parse_program(self) -> Program:
        first = self.peek()
        functions: List[Function] = []
        while not self.at("EOF"):
            if self.at("KW_FUNCTION"):
                functions.append(self.parse_function())
            else:
                self.report(self.fail(
                    f"ожидалось 'function', найдено {describe(self.peek())}"))
                while not self.at("EOF", "KW_FUNCTION"):    # пропускаем весь мусор разом
                    self.advance()
        if not functions and not self.diags:
            e = self.peek()
            self.diags.append(Diagnostic(
                e.line, e.col, "пустая программа: ожидалась хотя бы одна функция"))
        return Program(functions, line=first.line, col=first.col)

    # ---- функция ---------------------------------------------------------

    def parse_function(self) -> Function:
        kw = self.advance()                                 # 'function'
        name, params, returns = "", [], []
        uses: List[str] = []
        requires: List[Node] = []
        ensures: List[Node] = []
        try:
            name = self.expect("IDENT", "имя функции").value
            lp = self.expect("LPAREN")
            params = self.parse_params()
            self.expect("RPAREN", opener=lp)
            if self.match("KW_RETURNS"):
                returns = self.parse_returns()
            while self.at("KW_USES", "KW_REQUIRES", "KW_ENSURES"):
                clause = self.advance()
                if clause.name == "KW_USES":
                    uses.append(self.expect("IDENT").value)
                    while self.match("COMMA"):
                        uses.append(self.expect("IDENT").value)
                elif clause.name == "KW_REQUIRES":
                    requires.append(self.parse_expr())
                else:
                    ensures.append(self.parse_expr())
            if not self.at("LBRACE"):
                raise self.fail(f"ожидалось '{{' (тело функции), найдено {describe(self.peek())}")
        except ParseError as e:
            self.report(e)
            while not self.at("LBRACE", "KW_FUNCTION", "EOF"):   # синхронизация: к телу или следующей функции
                self.advance()
        body = self.parse_block() if self.at("LBRACE") else Block([], line=self.peek().line, col=self.peek().col)
        return Function(name, params, returns, uses, requires, ensures, body,
                        line=kw.line, col=kw.col)

    def parse_params(self) -> List[Param]:
        params: List[Param] = []
        if self.at("RPAREN"):
            return params
        params.append(self.parse_param())
        while self.match("COMMA"):
            params.append(self.parse_param())
        return params

    def parse_param(self) -> Param:
        name = self.expect("IDENT", "имя параметра")
        ty = None
        if self.match("COLON"):
            ty = self.parse_type()
        return Param(name.value, ty, line=name.line, col=name.col)

    def parse_type(self) -> str:
        if not self.at("KW_INT", "KW_BOOL"):
            raise self.fail(f"ожидался тип ('int' или 'bool'), найдено {describe(self.peek())}")
        ty = self.advance().value
        if self.at("LBRACKET"):
            lb = self.advance()
            self.expect("RBRACKET", opener=lb)
            ty += "[]"
        return ty

    def parse_returns(self) -> List[Param]:
        if self.at("LPAREN"):
            lp = self.advance()
            res = self.parse_params()
            if not res:
                raise self.fail("в 'returns (...)' ожидался хотя бы один результат")
            self.expect("RPAREN", opener=lp)
            return res
        t = self.peek()
        return [Param("", self.parse_type(), line=t.line, col=t.col)]

    # ---- операторы --------------------------------------------------------------

    def parse_block(self) -> Block:
        lb = self.expect("LBRACE")
        stmts: List[Node] = []
        while not self.at("RBRACE", "EOF", "KW_FUNCTION"):
            start = self.i
            try:
                stmts.append(self.parse_stmt())
            except ParseError as e:
                self.report(e)
                self.sync_stmt()
                if self.i == start:                         # гарантия прогресса
                    self.advance()
        if self.at("RBRACE"):
            self.advance()
        else:
            t = self.peek()
            self.diags.append(Diagnostic(
                t.line, t.col,
                f"не закрыта '{{' (открыта в {lb.line}:{lb.col}): ожидалась '}}', найдено {describe(t)}"))
        return Block(stmts, line=lb.line, col=lb.col)

    def sync_stmt(self) -> None:
        """Режим паники: пропускаем токены до границы оператора."""
        while not self.at("EOF"):
            n = self.peek().name
            if n == "SEMI":
                self.advance()
                return
            if n in STMT_START or n in ("RBRACE", "KW_FUNCTION"):
                return
            self.advance()

    def parse_stmt(self) -> Node:
        t = self.peek()
        n = t.name
        if n == "LBRACE":
            return self.parse_block()
        if n == "KW_IF":
            self.advance()
            lp = self.expect("LPAREN")
            cond = self.parse_expr()
            self.expect("RPAREN", opener=lp)
            then = self.parse_stmt()
            els = self.parse_stmt() if self.match("KW_ELSE") else None   # else — к ближайшему if
            return If(cond, then, els, line=t.line, col=t.col)
        if n == "KW_WHILE":
            self.advance()
            lp = self.expect("LPAREN")
            cond = self.parse_expr()
            self.expect("RPAREN", opener=lp)
            invs: List[Node] = []
            while self.match("KW_INVARIANT"):
                invs.append(self.parse_expr())
            body = self.parse_stmt()
            return While(cond, invs, body, line=t.line, col=t.col)
        if n in ("KW_ASSERT", "KW_ASSUME"):
            self.advance()
            e = self.parse_expr()
            self.expect("SEMI")
            return (Assert if n == "KW_ASSERT" else Assume)(e, line=t.line, col=t.col)
        if n == "KW_RETURN":
            self.advance()
            v = None if self.at("SEMI") else self.parse_expr()
            self.expect("SEMI")
            return Return(v, line=t.line, col=t.col)
        if n in ("KW_INT", "KW_BOOL"):
            ty = self.parse_type()
            name = self.expect("IDENT", "имя переменной")
            init = self.parse_expr() if self.match("ASSIGN") else None
            self.expect("SEMI")
            return VarDecl(ty, name.value, init, line=t.line, col=t.col)
        if n == "IDENT":
            nxt = self.peek(1)
            if nxt.name == "ASSIGN":
                self.advance(); self.advance()
                v = self.parse_expr()
                self.expect("SEMI")
                return Assign(t.value, v, line=t.line, col=t.col)
            if nxt.name == "LBRACKET":
                self.advance()
                lb = self.advance()
                idx = self.parse_expr()
                self.expect("RBRACKET", opener=lb)
                self.expect("ASSIGN", "'=' после a[i]")
                v = self.parse_expr()
                self.expect("SEMI")
                store = Store(Var(t.value, line=t.line, col=t.col), idx, v, line=lb.line, col=lb.col)
                return Assign(t.value, store, sugar=True, line=t.line, col=t.col)
            if nxt.name == "LPAREN":
                call = self.parse_call(t)
                self.expect("SEMI")
                return CallStmt(call, line=t.line, col=t.col)
            self.advance()
            raise self.fail(
                f"после идентификатора '{t.value}' ожидалось '=', '[' или '(', найдено {describe(self.peek())}")
        if n == "KW_ELSE":
            raise self.fail("'else' без соответствующего 'if'")
        raise self.fail(f"ожидался оператор, найдено {describe(t)}")

    def parse_call(self, name_tok: Token) -> Call:
        self.advance()                                       # имя
        lp = self.expect("LPAREN")
        args: List[Node] = []
        if not self.at("RPAREN"):
            args.append(self.parse_expr())
            while self.match("COMMA"):
                args.append(self.parse_expr())
        self.expect("RPAREN", opener=lp)
        return Call(name_tok.value, args, line=name_tok.line, col=name_tok.col)

    # ---- выражения (приоритеты снизу вверх: or < and < not < cmp < +- < */ < унарный - < [] ) ----

    def parse_expr(self) -> Node:
        return self.parse_or()

    def parse_or(self) -> Node:
        left = self.parse_and()
        while self.at("KW_OR"):
            op = self.advance()
            left = Binary("or", left, self.parse_and(), line=op.line, col=op.col)
        return left

    def parse_and(self) -> Node:
        left = self.parse_not()
        while self.at("KW_AND"):
            op = self.advance()
            left = Binary("and", left, self.parse_not(), line=op.line, col=op.col)
        return left

    def parse_not(self) -> Node:
        if self.at("KW_NOT"):
            op = self.advance()
            return Unary("not", self.parse_not(), line=op.line, col=op.col)
        return self.parse_cmp()

    def parse_cmp(self) -> Node:
        left = self.parse_add()
        if self.at(*CMP_OPS):
            op = self.advance()
            left = Binary(op.value, left, self.parse_add(), line=op.line, col=op.col)
            if self.at(*CMP_OPS):
                raise self.fail("операторы сравнения неассоциативны: используйте скобки")
        return left

    def parse_add(self) -> Node:
        left = self.parse_mul()
        while self.at("PLUS", "MINUS"):
            op = self.advance()
            left = Binary(op.value, left, self.parse_mul(), line=op.line, col=op.col)
        return left

    def parse_mul(self) -> Node:
        left = self.parse_unary()
        while self.at("STAR", "SLASH"):
            op = self.advance()
            left = Binary(op.value, left, self.parse_unary(), line=op.line, col=op.col)
        return left

    def parse_unary(self) -> Node:
        if self.at("MINUS"):
            op = self.advance()
            return Unary("-", self.parse_unary(), line=op.line, col=op.col)
        return self.parse_postfix()

    def parse_postfix(self) -> Node:
        node = self.parse_primary()
        while self.at("LBRACKET"):
            lb = self.advance()
            idx = self.parse_expr()
            self.expect("RBRACKET", opener=lb)
            node = Index(node, idx, line=lb.line, col=lb.col)
        return node

    def parse_primary(self) -> Node:
        t = self.peek()
        n = t.name
        if n == "INT":
            self.advance()
            return IntLit(int(t.value), line=t.line, col=t.col)
        if n in ("KW_TRUE", "KW_FALSE"):
            self.advance()
            return BoolLit(n == "KW_TRUE", line=t.line, col=t.col)
        if n == "IDENT":
            if self.peek(1).name == "LPAREN":
                return self.parse_call(t)
            self.advance()
            return Var(t.value, line=t.line, col=t.col)
        if n == "KW_LENGTH":
            if self.peek(1).name != "LPAREN":
                self.advance()
                raise self.fail(f"после 'length' ожидалась '(', найдено {describe(self.peek())}")
            return self.parse_call(t)
        if n == "LPAREN":
            lp = self.advance()
            e = self.parse_expr()
            self.expect("RPAREN", opener=lp)
            return e
        raise self.fail(f"ожидалось выражение, найдено {describe(t)}")


# ---- публичный API ---------------------------------------------------------------

_LEXER = None


def _lexer():
    global _LEXER
    if _LEXER is None:
        _LEXER = build_lexer()
    return _LEXER


def parse(text: str) -> ParseResult:
    tokens, lex_errors = _lexer().scan(text)
    lines = text.split("\n")
    end_line = len(lines)
    end_col = len(lines[-1]) + 1
    parser = Parser(tokens, end_line, end_col, len(text))
    program = parser.parse_program()
    diags = [Diagnostic(e.line, e.col, f"недопустимый символ {e.char!r}", "lexical")
             for e in lex_errors] + parser.diags
    diags.sort(key=lambda d: (d.line, d.col))
    return ParseResult(program, diags, tokens)
