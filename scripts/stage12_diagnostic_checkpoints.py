"""Compatibility exports for the reusable bounded supplementary writer.

Historical standalone diagnostic launchers import this before adding src to
sys.path. Preserve that stdlib-only use without changing their launcher order.
"""

try:
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_public_checkpoints as _implementation,
    )
except ModuleNotFoundError as error:
    if error.name != "safe_geocoding_pipeline":
        raise
    import importlib.util
    from pathlib import Path

    _source = (
        Path(__file__).resolve().parents[1]
        / "src/safe_geocoding_pipeline/preprocessing/stages/s12_public_checkpoints.py"
    )
    _spec = importlib.util.spec_from_file_location(
        "stage12_public_checkpoints_compat", _source
    )
    _implementation = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_implementation)

CheckpointError = _implementation.CheckpointError
Checkpoints = _implementation.Checkpoints
read_prefix = _implementation.read_prefix
_canonical = _implementation._canonical
os = _implementation.os

__all__ = ["CheckpointError", "Checkpoints", "read_prefix", "_canonical", "os"]
