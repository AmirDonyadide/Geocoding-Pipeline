from __future__ import annotations

import ast
import inspect
from importlib.metadata import version

import safe_geocoding_pipeline


def test_runtime_version_is_derived_from_distribution_metadata() -> None:
    assert safe_geocoding_pipeline.__version__ == version(
        safe_geocoding_pipeline.DISTRIBUTION_NAME
    )

    module = ast.parse(inspect.getsource(safe_geocoding_pipeline))
    version_assignments = [
        statement
        for statement in module.body
        if isinstance(statement, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "__version__"
            for target in statement.targets
        )
    ]
    assert len(version_assignments) == 1
    assert isinstance(version_assignments[0].value, ast.Call)
