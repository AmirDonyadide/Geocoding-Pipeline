class Phase03Error(Exception):
    """Privacy-safe Phase 3 failure with a stable code."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(code)
        self.code = code
        self.detail = detail[:500]


class ReferenceNotReadyError(Phase03Error):
    """Production reference artifacts are absent or not approved."""
