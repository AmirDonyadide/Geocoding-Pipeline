from __future__ import annotations


class Phase02FileError(Exception):
    """Privacy-safe file-level failure with a stable diagnostic code."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail[:500]
