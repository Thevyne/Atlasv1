"""Optional AI-assisted room type classification.

Keyword matching (standards.classify_by_keyword) handles the common cases
for free and runs first. This module is only used as a fallback for
ambiguous labels, and only if ENABLE_AI_ROOM_CLASSIFICATION is True in
settings and an ANTHROPIC_API_KEY is configured in the environment. The
rest of the pipeline does not depend on this -- if this fails or is
disabled, rooms just default to "other" and you (or your reviewer) fix
the type on the review screen.
"""
import json
import logging

from django.conf import settings

from . import standards

logger = logging.getLogger(__name__)

VALID_ROOM_TYPES = list(standards.REQUIRED_LUX_BY_ROOM_TYPE.keys())


def classify_room_type(label_text):
    """Returns a room_type string. Never raises -- falls back to 'other'
    if classification isn't possible or the AI call fails."""
    keyword_match = standards.classify_by_keyword(label_text)
    if keyword_match:
        return keyword_match

    if not label_text or not getattr(settings, "ENABLE_AI_ROOM_CLASSIFICATION", False):
        return "other"

    try:
        return _classify_with_ai(label_text)
    except Exception:
        logger.exception("AI room classification failed for label %r", label_text)
        return "other"


def _classify_with_ai(label_text):
    import anthropic

    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment
    prompt = (
        "Classify this architectural room label into exactly one of these "
        f"categories: {VALID_ROOM_TYPES}. "
        f'Label: "{label_text}". '
        'Respond with only a JSON object, no other text: {"room_type": "<category>"}'
    )

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=50,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text.strip()
    result = json.loads(text)
    room_type = result.get("room_type", "other")
    return room_type if room_type in VALID_ROOM_TYPES else "other"
