import json
import difflib
import re
from pathlib import Path


# =========================
# JARVIS ROUTINE TOOLS
# Lets Jarvis create/update/list routines in data/routines.json
# =========================

BASE_DIR = Path(__file__).resolve().parents[2]
ROUTINES_PATH = BASE_DIR / "data" / "routines.json"


SUPPORTED_STEP_TYPES = [
    "url",
    "app",
    "volume",
    "wait",
    "message",
]


def load_routines_file():
    """
    Load routines from C:\\Jarvis\\data\\routines.json.
    """

    if not ROUTINES_PATH.exists():
        ROUTINES_PATH.parent.mkdir(exist_ok=True)
        ROUTINES_PATH.write_text("{}", encoding="utf-8")
        return {}

    try:
        with open(ROUTINES_PATH, "r", encoding="utf-8") as file:
            return json.load(file)

    except Exception as error:
        print(f"Failed to load routines file: {error}")
        return {}


def save_routines_file(routines):
    """
    Save routines to C:\\Jarvis\\data\\routines.json.
    """

    try:
        ROUTINES_PATH.parent.mkdir(exist_ok=True)

        with open(ROUTINES_PATH, "w", encoding="utf-8") as file:
            json.dump(routines, file, indent=2)

        return {
            "success": True,
            "message": "Routines saved.",
        }

    except Exception as error:
        return {
            "success": False,
            "message": f"I couldn't save routines: {error}",
        }


def make_routine_key(routine_name):
    """
    Converts routine names into safe keys.

    Example:
    'Trading Prep' -> 'trading_prep'
    """

    clean = routine_name.lower().strip()
    clean = re.sub(r"[^a-z0-9\s_]", "", clean)
    clean = re.sub(r"\s+", "_", clean)

    return clean


def _normalise_lookup_text(text):
    clean = str(text or "").lower()
    clean = clean.replace("&", " and ")
    clean = re.sub(r"[^a-z0-9]+", " ", clean)

    ignored_words = {
        "a",
        "an",
        "the",
        "my",
        "routine",
        "routines",
        "called",
        "named",
        "trigger",
        "phrase",
    }

    words = [
        word
        for word in clean.split()
        if word and word not in ignored_words
    ]

    return {
        "spaced": " ".join(words),
        "compact": "".join(words),
        "words": set(words),
    }


def _routine_display_name(routine_key, routine_data):
    if isinstance(routine_data, dict):
        return str(routine_data.get("display_name") or routine_key).strip()

    return str(routine_key).strip()


def _routine_lookup_values(routine_key, routine_data):
    values = [routine_key, _routine_display_name(routine_key, routine_data)]

    if isinstance(routine_data, dict):
        values.extend(routine_data.get("trigger_phrases") or [])

    return [
        str(value).strip()
        for value in values
        if str(value or "").strip()
    ]


def _routine_similarity(query, candidate):
    query_data = _normalise_lookup_text(query)
    candidate_data = _normalise_lookup_text(candidate)

    if not query_data["compact"] or not candidate_data["compact"]:
        return 0.0

    char_score = difflib.SequenceMatcher(
        None,
        query_data["compact"],
        candidate_data["compact"],
    ).ratio()

    if query_data["words"] and candidate_data["words"]:
        overlap = len(query_data["words"] & candidate_data["words"])
        token_score = overlap / max(len(query_data["words"]), len(candidate_data["words"]))
    else:
        token_score = 0.0

    return max(char_score, (char_score * 0.75) + (token_score * 0.25))


def _find_exact_routine_key(routines, routine_name):
    wanted = _normalise_lookup_text(routine_name)["compact"]

    if not wanted:
        return None

    for routine_key, routine_data in routines.items():
        for value in _routine_lookup_values(routine_key, routine_data):
            if _normalise_lookup_text(value)["compact"] == wanted:
                return routine_key

    return None


def find_routine_key(routines, routine_name):
    wanted = _normalise_lookup_text(routine_name)["compact"]

    if not wanted:
        return None, "missing", []

    exact_key = _find_exact_routine_key(routines, routine_name)

    if exact_key:
        return exact_key, "exact", []

    scored = []

    for routine_key, routine_data in routines.items():
        score = max(
            _routine_similarity(routine_name, value)
            for value in _routine_lookup_values(routine_key, routine_data)
        )

        if score >= 0.64:
            scored.append((score, routine_key))

    scored.sort(reverse=True)

    if not scored:
        return None, "not_found", []

    top_score, top_key = scored[0]
    second_score = scored[1][0] if len(scored) > 1 else 0.0

    if top_score >= 0.88 and top_score - second_score >= 0.06:
        return top_key, "fuzzy", []

    return None, "close_match", [routine_key for _, routine_key in scored[:3]]


def normalise_trigger_phrases(routine_name, trigger_phrases):
    """
    Ensures routines have sensible trigger phrases.
    """

    routine_name_clean = routine_name.lower().strip()

    default_triggers = [
        routine_name_clean,
        f"start {routine_name_clean}",
        f"open {routine_name_clean}",
        f"run {routine_name_clean}",
    ]

    final_triggers = []

    for phrase in default_triggers + (trigger_phrases or []):
        phrase = phrase.lower().strip()

        if phrase and phrase not in final_triggers:
            final_triggers.append(phrase)

    return final_triggers


def validate_steps(steps):
    """
    Validates and cleans routine steps.
    """

    cleaned_steps = []

    if not isinstance(steps, list):
        return cleaned_steps

    for step in steps:
        if not isinstance(step, dict):
            continue

        step_type = str(step.get("type", "")).lower().strip()
        label = str(step.get("label", "")).strip()
        value = step.get("value")

        if step_type not in SUPPORTED_STEP_TYPES:
            continue

        if value is None or str(value).strip() == "":
            continue

        value = str(value).strip()

        if not label:
            label = value

        # Basic safety checks
        if step_type == "url":
            if not value.startswith("http://") and not value.startswith("https://"):
                value = "https://" + value

        if step_type == "volume":
            if value not in ["up", "down", "mute"]:
                continue

        cleaned_steps.append(
            {
                "type": step_type,
                "label": label,
                "value": value,
            }
        )

    return cleaned_steps


def create_or_update_routine(routine_name, display_name=None, trigger_phrases=None, steps=None):
    """
    Creates or updates a routine in routines.json.

    Example steps:
    [
        {"type": "url", "label": "TradingView", "value": "https://www.tradingview.com/"},
        {"type": "app", "label": "Chrome", "value": "chrome"},
        {"type": "volume", "label": "Volume down", "value": "down"}
    ]
    """

    if not routine_name or not routine_name.strip():
        return {
            "success": False,
            "message": "What should I call the routine?",
        }

    routines = load_routines_file()

    routine_key = _find_exact_routine_key(
        routines,
        display_name or routine_name,
    ) or make_routine_key(routine_name)
    clean_steps = validate_steps(steps or [])

    if not clean_steps:
        return {
            "success": False,
            "message": "I need at least one valid step for that routine.",
        }

    display_name = display_name or routine_name.strip()

    routines[routine_key] = {
        "display_name": display_name,
        "trigger_phrases": normalise_trigger_phrases(routine_name, trigger_phrases or []),
        "steps": clean_steps,
    }

    save_result = save_routines_file(routines)

    if not save_result.get("success"):
        return save_result

    return {
        "success": True,
        "message": f"Saved routine: {display_name}.",
        "spoken_message": f"Done. I saved {display_name}.",
        "routine_key": routine_key,
        "routine": routines[routine_key],
    }


def list_routines():
    """
    Lists saved routines.
    """

    routines = load_routines_file()

    if not routines:
        return {
            "success": True,
            "message": "No routines saved yet.",
            "spoken_message": "No routines saved yet.",
            "routines": [],
        }

    routine_names = [
        _routine_display_name(routine_key, routine_data)
        for routine_key, routine_data in routines.items()
    ]

    return {
        "success": True,
        "message": "Saved routines: " + ", ".join(routine_names),
        "spoken_message": f"You've got {len(routine_names)} routines saved. I can read them or show them.",
        "routines": [
            {
                "key": routine_key,
                "display_name": _routine_display_name(routine_key, routine_data),
                "trigger_phrases": routine_data.get("trigger_phrases", [])
                if isinstance(routine_data, dict) else [],
            }
            for routine_key, routine_data in routines.items()
        ],
        "routine_names": routine_names,
        "routine_count": len(routine_names),
    }


def delete_routine(routine_name):
    """
    Deletes a routine by name.
    """

    if not routine_name or not routine_name.strip():
        return {
            "success": False,
            "message": "Which routine should I delete?",
        }

    routines = load_routines_file()
    routine_key, match_type, candidates = find_routine_key(routines, routine_name)

    if not routine_key:
        suggestions = [
            _routine_display_name(candidate_key, routines[candidate_key])
            for candidate_key in candidates
            if candidate_key in routines
        ]

        if suggestions:
            message = "Do you mean " + ", ".join(suggestions[:3]) + "?"
        else:
            message = f"I couldn't find a routine called {routine_name}."

        return {
            "success": False,
            "message": message,
            "spoken_message": message,
            "needs_confirmation": bool(suggestions),
            "suggestions": suggestions,
            "match_type": match_type,
        }

    display_name = _routine_display_name(routine_key, routines[routine_key])
    del routines[routine_key]

    save_result = save_routines_file(routines)

    if not save_result.get("success"):
        return save_result

    return {
        "success": True,
        "message": f"Deleted routine: {display_name}.",
        "spoken_message": f"Done. I deleted {display_name}.",
        "routine_key": routine_key,
        "match_type": match_type,
    }


def preview_delete_all_routines():
    routines = load_routines_file()
    routine_names = [
        _routine_display_name(routine_key, routine_data)
        for routine_key, routine_data in routines.items()
    ]

    return {
        "routine_count": len(routine_names),
        "routine_names": routine_names,
    }


def delete_all_routines(confirmed=False):
    routines = load_routines_file()
    routine_count = len(routines)

    if routine_count == 0:
        return {
            "success": True,
            "message": "No routines saved yet.",
            "spoken_message": "No routines saved yet.",
            "deleted_count": 0,
        }

    if not confirmed:
        return {
            "success": False,
            "needs_confirmation": True,
            "message": f"This will delete {routine_count} routines. Confirm?",
            "spoken_message": f"This will delete {routine_count} routines. Confirm?",
            "routine_count": routine_count,
            "routine_names": [
                _routine_display_name(routine_key, routine_data)
                for routine_key, routine_data in routines.items()
            ],
        }

    save_result = save_routines_file({})

    if not save_result.get("success"):
        return save_result

    return {
        "success": True,
        "message": f"Deleted {routine_count} routines.",
        "spoken_message": "Done. I deleted the routines.",
        "deleted_count": routine_count,
    }
