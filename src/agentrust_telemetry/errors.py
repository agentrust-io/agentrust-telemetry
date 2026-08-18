class EventValidationError(ValueError):
    """The normalized event is invalid or violates the privacy profile."""


class ContextMismatchError(EventValidationError):
    """Supplied trace identifiers disagree with the active OTel context."""


class ProjectionError(RuntimeError):
    """A configured telemetry projection failed."""


class PropagationError(ValueError):
    """AgentTrust propagation metadata is missing or unsafe."""
