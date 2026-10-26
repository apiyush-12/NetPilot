"""Input validation for the NetPilot AI investigator."""

import re
import unicodedata


class InputGuardrailError(ValueError):
    """Raised when an AI question violates an input rule."""


# Detect direct modification requests targeting network resources.
WRITE_REQUEST = re.compile(
    r"^\s*(?:please\s+)?"
    r"(?:stop|start|restart|reset|delete|disable|enable|change|modify|configure)\s+"
    r"(?:the\s+)?"
    r"(?:router(?:-[ab])?|client|server|lab|docker|containers?|routes?|routing|gateways?|ip\s+forwarding)\b",
    re.IGNORECASE,
)

# Detect direct requests to reveal credentials.
SECRET_REQUEST = re.compile(
    r"^\s*(?:please\s+)?"
    r"(?:show|print|reveal|display|give\s+me)\b"
    r".{0,100}\b(?:api[\s_-]*key|password|secret|token)\b",
    re.IGNORECASE | re.DOTALL,
)

# Prevent accidentally sending these assigned credentials to Groq.
SECRET_VALUE = re.compile(
    r"\b(?:GROQ_API_KEY|MISTRAL_API_KEY|NETPILOT_CONTROL_TOKEN)"
    r"\s*=\s*\S+",
    re.IGNORECASE,
)


def validate_question(question: str) -> str:
    """Validate a question before invoking the AI model."""

    if not isinstance(question, str):
        raise InputGuardrailError(
            "Question must be text."
        )

    question = question.strip()

    if not 5 <= len(question) <= 1000:
        raise InputGuardrailError(
            "Question must contain 5 to 1000 characters."
        )

    if any(
        unicodedata.category(char) == "Cc"
        and char not in "\n\t"
        for char in question
    ):
        raise InputGuardrailError(
            "Question contains invalid control characters."
        )

    if SECRET_VALUE.search(question):
        raise InputGuardrailError(
            "Do not include credentials in AI questions."
        )

    if SECRET_REQUEST.search(question):
        raise InputGuardrailError(
            "AI Operations cannot reveal credentials."
        )

    if WRITE_REQUEST.search(question):
        raise InputGuardrailError(
            "AI Operations is read-only. "
            "Network configuration changes are not permitted."
        )

    return question