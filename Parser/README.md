# Парсер Funny: LL(1), рекурсивный спуск + интеграция с лексером HW1

Python 3.10+, без внешних зависимостей (для тестов нужен `pytest`).
Ветка: **LL(1)**, восстановление после ошибок — **режим паники**.

```
текст ─► lexer.py (HW1: regex→НКА→ДКА→min-ДКА, + позиции line/col)
      ─► funny_parser.py (рекурсивный спуск, panic mode)
      ─► ast_nodes.py (AST: дерево / JSON)  +  список диагностик «строка:столбец»
```

## Структура

| Файл | Назначение |
|---|---|
| `regex_ast.py`, `thompson.py`, `automata.py`, `minimize.py` | движок HW1 (без изменений) |
| `lexer.py` | лексер HW1 + **позиции токенов** + новые токены (см. ниже) |
| `funny_parser.py` | парсер, `parse(text) -> ParseResult` |
| `ast_nodes.py` | узлы AST, `to_json`, `pretty` |
| `cli.py` | командная строка |
| `grammar.txt` | финальная грамматика, приоритеты, обоснование LL(1), допущения |
| `tests/test_parser.py` | 99 тестов парсера (позитивные, негативные, снимки AST, фаззинг) |
| `../Lexer/tests/test_lexer.py` | тесты лексера (HW1 + позиции) |
| `tests/programs/ok_*.fun`, `tests/snapshots/*.json` | позитивные программы и эталонные AST |
| `examples/` | `fib.fun` (верная), `errors.fun` (с ошибками) |
| `REPORT.md` | краткий отчёт |

## Запуск

```bash
python3 cli.py examples/fib.fun                 # AST деревом
python3 cli.py examples/fib.fun --format json   # AST в JSON
python3 cli.py examples/fib.fun --no-pos        # без позиций
python3 cli.py examples/fib.fun --tokens        # + токены с позициями
python3 cli.py examples/errors.fun              # диагностика в stderr, код возврата 1
echo 'function f() { }' | python3 cli.py -      # stdin
```

Пример диагностики (`examples/errors.fun`):

```
2:15: ошибка: не закрыта '(' (открыта в 2:9): ожидалось ')', найдено ';'
3:15: ошибка: ожидалось выражение, найдено '*'
4:18: ошибка: ожидалось ';', найдено 'return'
```

Как библиотека:

```python
from funny_parser import parse
from ast_nodes import to_json, pretty

res = parse(open("examples/fib.fun").read())
if res.ok:
    print(to_json(res.program))
else:
    for d in res.diagnostics:      # d.line, d.col, d.message
        print(d)
```

## Тесты

```bash
pip install pytest
python3 -m pytest tests -q          # 267 тестов
```

Эталонные AST (`tests/snapshots`) пересоздаются командой
`python3 tests/make_snapshots.py` — **только после ручной проверки diff'а**.
Парсер дополнительно проверен на ~2000 случайных/мутированных входах:
он завершается всегда (каждая итерация цикла потребляет токен).

## Формат AST

Каждый узел — JSON-объект `{"node": "<Тип>", ..., "pos": "строка:столбец"}`.
Типы: `Program, Function, Param, Block, VarDecl, Assign, If, While, Assert,
Assume, Return, CallStmt` (операторы) и `IntLit, BoolLit, Var, Unary, Binary,
Index, Store, Call` (выражения). Обновление `a[i] = e` — это
`Assign(sugar=true, value=Store(a, i, e))`, т.е. функциональное копирование.

## Что изменено в лексере относительно HW1

* `Token` и `LexError` получили `line`, `col` (1-based; CRLF и табы учтены).
* Новые ключевые слова: `uses requires ensures return true false not and or int bool`;
  новый токен `COLON` (`:`). Из-за этого в `../Lexer/tests/test_lexer.py` ожидания для `int`
  и `return` изменены с `IDENT` на `KW_INT`/`KW_RETURN`.
* Алфавит по-прежнему ASCII: **кириллица в комментариях даёт лексическую ошибку**
  (по ТЗ HW1). Комментарии в `.fun`-файлах пишите латиницей.

## Допущения и отклонения

Файл `docs/funny.ru.md` и презентации P03/P04 мне были недоступны (папка Drive
не открылась), поэтому синтаксис построен по тексту задания. Полный список
допущений — в конце `grammar.txt`; главное: необязательный тип параметра,
`while (c) invariant e ... body`, логика словами `and/or/not`, сравнения
неассоциативны, `else` — к ближайшему `if`. Если эталонная грамматика
отличается, правки локальны: `TOKEN_DEFS` в `lexer.py` и соответствующий
метод `parse_*` в `funny_parser.py`.
