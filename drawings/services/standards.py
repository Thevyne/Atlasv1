"""Illuminance requirements by room type. These are reasonable common
defaults (broadly in line with standards like EN 12464-1) -- check the
actual code that applies in your jurisdiction before relying on them for
a real design.
"""

REQUIRED_LUX_BY_ROOM_TYPE = {
    "office": 500,
    "bedroom": 500,
    "living_room": 500,
    "kitchen": 500,
    "bathroom": 150,
    "corridor": 100,
    "classroom": 500,
    "storage": 100,
    "other": 150,
    "stairs":150,
    "hallways":150,
}

# Keyword fallback for classifying a free-text room label without calling
# any external API. Tried first in room_classifier.classify_room_type --
# the AI fallback there only kicks in if nothing here matches.
ROOM_TYPE_KEYWORDS = {
    "office": ["office", "study"],
    "bedroom": ["bedroom", "bed room", "master"],
    "living_room": ["living", "lounge", "family room"],
    "kitchen": ["kitchen", "pantry"],
    "bathroom": ["bath", "toilet", "wc", "restroom"],
    "corridor": ["corridor", "hallway", "hall"],
    "classroom": ["classroom", "class room", "lecture"],
    "storage": ["storage", "store", "closet"],
}


def get_required_lux(room_type):
    return REQUIRED_LUX_BY_ROOM_TYPE.get(room_type, REQUIRED_LUX_BY_ROOM_TYPE["other"])


def classify_by_keyword(label_text):
    """Cheap, no-API classification. Returns None if nothing matches, so
    the caller can decide whether to fall back to AI classification or
    just default to 'other'."""
    if not label_text:
        return None
    lowered = label_text.lower()
    for room_type, keywords in ROOM_TYPE_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            return room_type
    return None
