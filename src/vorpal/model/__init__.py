"""The draft-night model call. SPEC.md section 4."""

from vorpal.model.call import (
    DEGRADED,
    EFFORT,
    MAX_TOKENS,
    MODEL_ID,
    AnthropicTransport,
    StubTransport,
    build_request,
    propose,
    recommend,
    run_stability,
)
from vorpal.model.cassette import CassetteStore, CassetteTransport, request_key
from vorpal.model.tracing import SampleRecorder
from vorpal.model.validate import validate_proposal

__all__ = [
    "DEGRADED",
    "EFFORT",
    "MAX_TOKENS",
    "MODEL_ID",
    "AnthropicTransport",
    "CassetteStore",
    "CassetteTransport",
    "SampleRecorder",
    "StubTransport",
    "build_request",
    "propose",
    "recommend",
    "request_key",
    "run_stability",
    "validate_proposal",
]
