"""Conservative local redirects; the shared prompt handles broader scope decisions.

These patterns only catch explicit unrelated tasks. They are not a semantic
classifier or a guarantee that an AI will follow its instructions. Ambiguous
requests and short follow-ups still reach the fitness coach for clarification.
"""

import re

from .prompts import SCOPE_REFUSAL


SCOPE_REDIRECT = (
    "I'm here for fitness and healthier daily habits. Ask me about movement, "
    "strength, fueling, sleep, recovery, or a habit you'd like to build."
)

# Match the current task itself; fitness words elsewhere must not bypass a clear
# request to write code or choose investments. Keep narrow, transparent examples
# rather than an expanding allowlist of every possible fitness phrase.
# Restrict matches to explicit requests at a sentence/clause start. A contextual
# statement such as "I write code all day" is not a request to generate code.
_REQUEST_START = (
    r"(?:^|[.!?;\n])\s*(?:now\s+)?(?:please\s+)?"
    r"(?:(?:can|could|would|will)\s+you\s+(?:please\s+)?"
    r"|(?:i\s+(?:want|need)|i['’]d\s+like)\s+you\s+to\s+"
    r"|(?:ignore|disregard|forget)\s+[^.!?;\n]{1,60}\s+and\s+)?"
)
_OBJECT_PREFIX = r"(?:(?:me|a|an|the|some|this|that|my|please|new|simple|example)\s+){0,4}"
_UNRELATED_TASKS = tuple(re.compile(_REQUEST_START + pattern, re.IGNORECASE) for pattern in (
    r"\b(?:write|generate|debug|refactor|implement|fix|review)\s+" + _OBJECT_PREFIX
    + r"(?:code|python|javascript|typescript|html|css|sql|regex)\b",
    r"\b(?:build|create|develop)\s+"
    r"(?:(?:a|an|the|new|simple|fitness|health|personal|tracking|custom)\s+){0,4}"
    r"(?:website|web\s*app|software|mobile\s+app)\b",
    r"\b(?:which|what)\s+(?:stocks?|cryptocurrenc(?:y|ies)|crypto|shares?)\b.{0,60}\b(?:buy|invest|trade)\b",
    r"\b(?:recommend|pick|choose)\s+" + _OBJECT_PREFIX + r"(?:stocks?|cryptocurrenc(?:y|ies))\b",
    r"\b(?:write|draft|create)\s+" + _OBJECT_PREFIX
    + r"(?:cover\s+letter|resignation\s+letter|sales\s+email|legal\s+contract)\b",
))


def clearly_out_of_scope(message: str) -> bool:
    """Skip a paid call only for a small set of clearly unrelated task requests."""
    return any(pattern.search(message) for pattern in _UNRELATED_TASKS)


def normalize_scope_reply(answer: str) -> str:
    """Keep the model's internal refusal marker out of public replies and history."""
    return SCOPE_REDIRECT if SCOPE_REFUSAL in answer else answer.strip()
