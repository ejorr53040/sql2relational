# sql2relational

Translate SQL statements into relational algebra, as Unicode text or LaTeX. Parsing is done by
[sqlglot](https://github.com/tobymao/sqlglot), so any statement it can read is accepted.
Anything with no relational algebra form (`LIMIT`, `UNION ALL`, `INSERT`, ...) is kept as SQL in parentheses.

## Usage

```sh
uv run sql2relational queries.sql
```

prints one LaTeX expression per statement in the file. Wrap each in `$…$` or `\[…\]`; it needs `amsmath` for `\text`.

```sql
SELECT label, COUNT(*) AS n FROM circuit WHERE fidelity > 0.9 GROUP BY label ORDER BY n DESC LIMIT 5;
```

```latex
(\text{LIMIT 5})(\tau_{\text{n DESC}}(\pi_{\text{label}, \text{COUNT(*)} \rightarrow \text{n}}(\gamma_{\text{label, COUNT(*)}}(\sigma_{\text{fidelity \textgreater{} 0.9}}(\text{circuit})))))
```

From Python:

```python
from sql2relational import sql_to_algebra, sql_to_latex

sql_to_algebra("SELECT * FROM circuit LIMIT 10")  # '(LIMIT 10)(circuit)'
```

## Mapping

| SQL | Relational algebra |
| --- | --- |
| `WHERE`, `HAVING` | σ |
| `SELECT` list (`AS x` → `→ x`) | π |
| `GROUP BY`, aggregates | γ |
| `DISTINCT` | δ |
| `ORDER BY` | τ |
| table / subquery alias | ρ |
| `JOIN … ON` / `USING`, `NATURAL JOIN` | ⨝ |
| `LEFT` / `RIGHT` / `FULL` outer join | ⟕ ⟖ ⟗ |
| `CROSS JOIN`, comma | ✕ |
| `UNION`, `INTERSECT`, `EXCEPT` | ∪ ∩ − |
| `WITH name AS (…)` | `name ← …;` |
| everything else | `(SQL)` |

Subqueries in `FROM` are translated recursively; subqueries inside a condition stay as SQL.
Outer joins have no standard LaTeX symbol, so when one appears the output starts with
`\providecommand` definitions that draw them.

## Development

```sh
uv run pytest
```
