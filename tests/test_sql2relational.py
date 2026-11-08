from sql2relational import main, sql_to_algebra, sql_to_latex


def test_select_where_becomes_projection_over_selection():
    assert sql_to_algebra("SELECT name, salary FROM employees WHERE dept_id = 5;") == (
        "π_{name, salary}(σ_{dept_id = 5}(employees))"
    )


def test_join_on_becomes_theta_join():
    sql = "SELECT title FROM movies JOIN directors ON movies.dir_id = directors.id WHERE year > 2020"
    assert sql_to_algebra(sql) == "π_{title}(σ_{year > 2020}((movies ⨝_{movies.dir_id = directors.id} directors)))"


def test_limit_has_no_algebra_form_so_stays_as_parenthesized_sql():
    assert sql_to_algebra("SELECT * FROM circuit LIMIT 10 OFFSET 5") == "(OFFSET 5)((LIMIT 10)(circuit))"


def test_group_by_and_having_become_grouping_then_selection():
    sql = "SELECT label, AVG(fidelity) FROM circuit GROUP BY label HAVING COUNT(*) > 2"
    assert sql_to_algebra(sql) == (
        "π_{label, AVG(fidelity)}(σ_{COUNT(*) > 2}(γ_{label, AVG(fidelity), COUNT(*)}(circuit)))"
    )


def test_aggregate_without_group_by_is_grouping_with_no_keys():
    assert sql_to_algebra("SELECT COUNT(*) FROM gate") == "π_{COUNT(*)}(γ_{COUNT(*)}(gate))"


def test_each_join_kind_gets_its_operator():
    sql = (
        "SELECT * FROM a LEFT JOIN b ON a.id = b.id RIGHT JOIN c USING (id) FULL OUTER JOIN d ON a.x = d.x"
        " NATURAL JOIN e CROSS JOIN f, g"
    )
    assert sql_to_algebra(sql) == (
        "((((((a ⟕_{a.id = b.id} b) ⟖_{id} c) ⟗_{a.x = d.x} d) ⨝ e) ✕ f) ✕ g)"
    )


def test_join_with_no_algebra_form_stays_as_parenthesized_sql():
    assert sql_to_algebra("SELECT * FROM a LEFT SEMI JOIN b ON a.id = b.id") == "(a (LEFT SEMI JOIN b ON a.id = b.id))"


def test_aliases_distinct_and_order_by():
    sql = "SELECT DISTINCT c.label AS digit FROM circuit AS c ORDER BY digit DESC"
    assert sql_to_algebra(sql) == "τ_{digit DESC}(δ(π_{c.label → digit}(ρ_{c}(circuit))))"


def test_subquery_in_from_is_translated_recursively():
    sql = "SELECT n FROM (SELECT COUNT(*) AS n FROM gate GROUP BY circuit_id) AS counts WHERE n > 100"
    assert sql_to_algebra(sql) == (
        "π_{n}(σ_{n > 100}(ρ_{counts}(π_{COUNT(*) → n}(γ_{circuit_id, COUNT(*)}(gate)))))"
    )


def test_set_operations():
    assert sql_to_algebra("SELECT a FROM r UNION SELECT a FROM s") == "(π_{a}(r) ∪ π_{a}(s))"
    assert sql_to_algebra("SELECT a FROM r INTERSECT SELECT a FROM s") == "(π_{a}(r) ∩ π_{a}(s))"
    assert sql_to_algebra("SELECT a FROM r EXCEPT SELECT a FROM s") == "(π_{a}(r) − π_{a}(s))"


def test_union_all_and_trailing_limit_stay_as_parenthesized_sql():
    sql = "SELECT a FROM r UNION ALL SELECT a FROM s ORDER BY a LIMIT 3"
    assert sql_to_algebra(sql) == "(LIMIT 3)(τ_{a}((π_{a}(r) (UNION ALL) π_{a}(s))))"


def test_cte_becomes_assignment():
    sql = "WITH big AS (SELECT * FROM circuit WHERE num_qubits > 8) SELECT label FROM big"
    assert sql_to_algebra(sql) == "big ← σ_{num_qubits > 8}(circuit); π_{label}(big)"


def test_statements_with_no_algebra_form_are_parenthesized_sql():
    assert sql_to_algebra("INSERT INTO circuit VALUES (1, 2, 0.5, 10)") == "(INSERT INTO circuit VALUES (1, 2, 0.5, 10))"
    assert sql_to_algebra("SELECT 1 + 1") == "(SELECT 1 + 1)"


def test_window_function_is_not_grouping():
    sql = "SELECT gate_type, COUNT(*) OVER (PARTITION BY circuit_id) FROM gate"
    assert sql_to_algebra(sql) == "π_{gate_type, COUNT(*) OVER (PARTITION BY circuit_id)}(gate)"


def test_latex_uses_operator_commands_and_text_for_sql():
    assert sql_to_latex("SELECT name FROM employees WHERE dept_id = 5") == (
        r"\pi_{\text{name}}(\sigma_{\text{dept\_id = 5}}(\text{employees}))"
    )


def test_latex_escapes_sql_and_keeps_unmapped_clauses_as_text():
    assert sql_to_latex("SELECT * FROM t WHERE a < 1 AND s LIKE '50%' LIMIT 3") == (
        r"(\text{LIMIT 3})(\sigma_{\text{a \textless{} 1 AND s LIKE '50\%'}}(\text{t}))"
    )


def test_latex_defines_outer_join_macros_only_when_used():
    assert sql_to_latex("SELECT * FROM a NATURAL JOIN b") == r"(\text{a} \bowtie \text{b})"
    latex = sql_to_latex("SELECT * FROM a LEFT JOIN b ON a.id = b.id")
    assert latex.startswith(r"\providecommand")
    assert latex.endswith(r"(\text{a} \leftouterjoin_{\text{a.id = b.id}} \text{b})")


def test_cli_prints_one_latex_line_per_statement_in_file(tmp_path, capsys):
    path = tmp_path / "q.sql"
    path.write_text("-- digits\nSELECT label FROM circuit;\n\nSELECT * FROM gate LIMIT 2;\n")
    main([str(path)])
    assert capsys.readouterr().out == (
        "\\pi_{\\text{label}}(\\text{circuit})\n(\\text{LIMIT 2})(\\text{gate})\n"
    )
