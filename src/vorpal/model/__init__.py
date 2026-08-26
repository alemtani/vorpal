"""The draft-night model call. SPEC.md section 4."""

from vorpal.model.call import (
    MODEL_ID,
    AnthropicTransport,
    StubTransport,
    recommend,
    run_stability,
)
from vorpal.model.validate import validate_proposal

__all__ = [
    "MODEL_ID",
    "AnthropicTransport",
    "StubTransport",
    "recommend",
    "run_stability",
    "validate_proposal",
]
