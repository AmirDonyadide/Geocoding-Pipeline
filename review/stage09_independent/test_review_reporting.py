"""Regression for real DuckDB sum serialization and sanitized failure reporting."""
import json
from decimal import Decimal
import duckdb
import pytest
import review


def test_actual_duckdb_integer_sum_is_portable():
    with duckdb.connect() as db:
        rows = db.execute('select sum(i) n from range(3) t(i)').to_arrow_table().to_pylist()
    assert isinstance(rows[0]['n'], Decimal)
    assert json.loads(json.dumps(review.portable({'rows': rows}))) == {'rows': [{'n': 3}]}


@pytest.mark.parametrize('value', [Decimal('1.5'), Decimal('NaN'), b'synthetic-private', object()])
def test_unsupported_report_types_do_not_leak_values(value):
    with pytest.raises((ValueError, TypeError)) as error:
        review.portable(value)
    assert str(error.value) in ('REVIEW_NONINTEGRAL_AGGREGATE', 'REVIEW_REPORT_TYPE_NOT_ALLOWLISTED')


def test_failure_receipt_survives_unserializable_report(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(review, 'OUT', tmp_path, raising=False)
    monkeypatch.setattr(review, 'REPORT', {'bad': object()})
    review.failure_report(TypeError('synthetic-private must never be emitted'))
    data = (tmp_path/'harness_failure.json').read_text()
    assert 'synthetic-private' not in data
    assert json.loads(data)['harness_exception_type'] == 'TypeError'
    assert capsys.readouterr().out == 'REVIEW_HARNESS_INCOMPLETE TypeError\n'


def test_failure_reporting_io_fault_does_not_escape(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(review, 'OUT', tmp_path, raising=False)
    def broken(*args):
        raise OSError('synthetic-private')
    monkeypatch.setattr(review.io, 'write_json', broken)
    review.failure_report(TypeError('synthetic-private'))
    captured=capsys.readouterr()
    assert captured.out == 'REVIEW_HARNESS_INCOMPLETE TypeError\n'
    assert captured.err == ''
