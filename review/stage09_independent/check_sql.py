"""Synthetic empty-schema validation of fixed independent review SQL."""
import ast
from pathlib import Path
import duckdb
import pyarrow as pa
from safe_geocoding_pipeline.preprocessing.stages import s09_reference_contract as c
from safe_geocoding_pipeline.preprocessing.stages import s08_address_evidence as s08

source = ast.parse(Path(__file__).with_name('review.py').read_text())
with duckdb.connect() as db:
    for name in c.RELATIONS:
        db.register(name, pa.Table.from_pylist([], schema=c.relation_schema(name)))
    for name, schema in [('candidate_evidence', s08.candidate_evidence_schema()), ('source_candidate_map', s08.source_candidate_map_schema()), ('parser_component_evidence', s08.parser_component_evidence_schema())]:
        db.register(name, pa.Table.from_pylist([], schema=schema))
    db.execute('CREATE VIEW stage08_occurrence AS ' + s08.REPRESENTATION_OCCURRENCE_SQL)
    n = 0
    for node in sorted(ast.walk(source), key=lambda x: getattr(x, 'lineno', 0)):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name) and node.func.value.id == 'db' and node.func.attr == 'execute' and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
            db.execute(node.args[0].value)
            n += 1
        elif isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'checks' for t in node.targets):
            for query in ast.literal_eval(node.value).values():
                db.execute(query)
                n += 1
        elif isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'sql' for t in node.targets) and isinstance(node.value, ast.Constant) and '?' in node.value.value:
            db.execute(node.value.value, ['Q04', 'PARSER_POSTCODE', 1])
            n += 1
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ('count', 'aggregates') and len(node.args) > 1 and isinstance(node.args[1], ast.Constant):
            db.execute(node.args[1].value)
            n += 1
    print('SYNTHETIC_EMPTY_SCHEMA_SQL_PASS', n)
