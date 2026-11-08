import argparse
import re
import sys
from pathlib import Path

import sqlglot
from sqlglot import exp

# Clauses translated below; any other clause present is emitted as (its SQL).
MAPPED = {"expressions", "from_", "joins", "where", "group", "having", "order", "with_"}
SET_MAPPED = {"this", "expression", "distinct", "order", "with_"}
SET_OPS = {"union": "∪", "intersect": "∩", "except": "−"}
JOIN_OPS = {"": "⨝", "LEFT": "⟕", "RIGHT": "⟖", "FULL": "⟗"}

# SQL text is wrapped in these private-use marks while building, so LaTeX output can escape it apart from operators.
OPEN, CLOSE = "", ""
FRAGMENT = re.compile(f"{OPEN}(.*?){CLOSE}", re.DOTALL)
LATEX_OPS = {
    "π": r"\pi", "σ": r"\sigma", "γ": r"\gamma", "τ": r"\tau", "ρ": r"\rho", "δ": r"\delta",
    "⨝": r"\bowtie", "⟕": r"\leftouterjoin", "⟖": r"\rightouterjoin", "⟗": r"\fullouterjoin",
    "✕": r"\times", "∪": r"\cup", "∩": r"\cap", "−": "-", "→": r"\rightarrow", "←": r"\leftarrow",
}
LATEX_TEXT = str.maketrans({
    "\\": r"\textbackslash{}", "{": r"\{", "}": r"\}", "$": r"\$", "&": r"\&", "#": r"\#", "%": r"\%",
    "_": r"\_", "^": r"\^{}", "~": r"\~{}", "<": r"\textless{}", ">": r"\textgreater{}", "|": r"\textbar{}",
})
# Outer joins have no standard LaTeX symbol; these draw ⟕ ⟖ ⟗ from \bowtie plus rules.
OUTER_JOIN_MACROS = "\n".join([
    r"\providecommand{\ojoin}{\setbox0=\hbox{$\bowtie$}\rule[-.02ex]{.25em}{.4pt}\llap{\rule[\ht0]{.25em}{.4pt}}}",
    r"\providecommand{\leftouterjoin}{\mathbin{\ojoin\mkern-5.8mu\bowtie}}",
    r"\providecommand{\rightouterjoin}{\mathbin{\bowtie\mkern-5.8mu\ojoin}}",
    r"\providecommand{\fullouterjoin}{\mathbin{\ojoin\mkern-5.8mu\bowtie\mkern-5.8mu\ojoin}}",
])


def sql_to_algebra(sql: str) -> str:
    """Translate one SQL statement to relational algebra; parts with no RA form stay as parenthesized SQL."""
    return re.sub(f"[{OPEN}{CLOSE}]", "", _query(sqlglot.parse_one(sql)))


def sql_to_latex(sql: str) -> str:
    """LaTeX for every statement in sql, one per line, with SQL fragments set as \\text."""
    lines = [_latex(_query(e)) for e in sqlglot.parse(sql) if e]
    if any("outerjoin" in line for line in lines):
        lines.insert(0, OUTER_JOIN_MACROS)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Print the relational algebra of each statement in a SQL file as LaTeX.")
    parser.add_argument("file", type=Path, help="SQL file")
    args = parser.parse_args(argv)
    try:
        print(sql_to_latex(args.file.read_text()))
    except (OSError, sqlglot.errors.ParseError) as e:
        sys.exit(f"error: {e}")


def _latex(ra: str) -> str:
    parts = FRAGMENT.split(ra)  # odd indexes are SQL fragments
    return "".join(
        rf"\text{{{p.translate(LATEX_TEXT)}}}" if i % 2 else re.sub("|".join(LATEX_OPS), lambda m: LATEX_OPS[m[0]], p)
        for i, p in enumerate(parts)
    )


def _txt(s: str) -> str:
    return f"{OPEN}{s}{CLOSE}"


def _sql(e: exp.Expression) -> str:
    return _txt(e.sql(comments=False))


def _query(e: exp.Expression) -> str:
    with_ = e.args.get("with_")
    if with_ and with_.args.get("recursive"):  # RA has no recursion
        return f"({_sql(e)})"
    if isinstance(e, exp.SetOperation) and not any(e.args.get(k) for k in ("by_name", "side", "kind", "on")):
        op = SET_OPS[e.key] if e.args.get("distinct") else f"({_txt(e.key.upper() + ' ALL')})"
        ra, mapped = f"({_query(e.this)} {op} {_query(e.expression)})", SET_MAPPED
    elif isinstance(e, exp.Select) and e.args.get("from_"):
        ra, mapped = _select(e)
    else:
        return f"({_sql(e)})"
    if order := e.args.get("order"):
        ra = f"τ_{{{_list(order.expressions)}}}({ra})"
    for key, value in e.args.items():
        if key not in mapped and value:
            ra = f"({_sql(value)})({ra})"
    lets = "".join(f"{_txt(cte.alias)} ← {_query(cte.this)}; " for cte in with_.expressions) if with_ else ""
    return lets + ra


def _select(e: exp.Select) -> tuple[str, set[str]]:
    ra = _relation(e.args["from_"].this)
    for j in e.args.get("joins") or []:
        ra = f"({ra} {_join(j)})"
    if where := e.args.get("where"):
        ra = f"σ_{{{_sql(where.this)}}}({ra})"
    having = e.args.get("having")
    keys = e.args["group"].expressions if e.args.get("group") else []
    aggs = [a for c in [*e.expressions, having] if c for a in c.find_all(exp.AggFunc) if not isinstance(a.parent, exp.Window)]
    if keys or aggs:
        ra = f"γ_{{{_list(keys + aggs)}}}({ra})"
    if having:
        ra = f"σ_{{{_sql(having.this)}}}({ra})"
    if not e.is_star:
        ra = f"π_{{{', '.join(map(_column, e.expressions))}}}({ra})"
    if (distinct := e.args.get("distinct")) and not distinct.args.get("on"):  # DISTINCT ON has no RA form
        return f"δ({ra})", MAPPED | {"distinct"}
    return ra, MAPPED


def _list(es: list[exp.Expression]) -> str:
    return _txt(", ".join(dict.fromkeys(e.sql(comments=False) for e in es)))


def _column(c: exp.Expression) -> str:
    return f"{_sql(c.this)} → {_txt(c.alias)}" if isinstance(c, exp.Alias) else _sql(c)


def _join(j: exp.Join) -> str:
    on, using = j.args.get("on"), j.args.get("using")
    cond = _sql(on) if on else _list(using) if using else None
    op = JOIN_OPS.get(j.side)
    if op is None or j.kind not in ("", "INNER", "OUTER", "CROSS") or j.method not in ("", "NATURAL"):
        return f"({_txt(j.sql(comments=False).strip())})"
    if j.method == "NATURAL":
        return f"{op} {_relation(j.this)}"
    if cond and j.kind != "CROSS":
        return f"{op}_{{{cond}}} {_relation(j.this)}"
    if op == "⨝":  # comma, CROSS JOIN, or JOIN without a condition
        return f"✕ {_relation(j.this)}"
    return f"({_txt(j.sql(comments=False).strip())})"


def _relation(e: exp.Expression) -> str:
    alias = e.args.get("alias")
    if isinstance(e, exp.Subquery):
        ra = _query(e.this)
    elif isinstance(e, exp.Table):
        bare = e.copy()
        bare.set("alias", None)
        ra = _sql(bare)
    else:
        return f"({_sql(e)})"
    return f"ρ_{{{_sql(alias)}}}({ra})" if alias else ra
