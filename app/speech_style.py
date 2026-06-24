import re


# =========================
# JARVIS SPEECH STYLE
# Smooths local/tool responses without replacing intent handling.
# =========================

def clean_memory_text(text):
    """
    Cleans technical memory wording.
    """

    text = text.replace("User prefers", "you prefer")
    text = text.replace("User likes", "you like")
    text = text.replace("User wants", "you want")
    text = text.replace("User usually", "you usually")
    text = text.replace("User always", "you always")
    text = text.replace("User never", "you never")

    return text


def _normalise_encoding_artifacts(text):
    replacements = {
        "\ufffd": "'",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2013": "-",
        "\u2014": "-",
        "\u00e2\u20ac\u2122": "'",
        "\u00e2\u20ac\u02dc": "'",
        "\u00e2\u20ac\u0153": '"',
        "\u00e2\u20ac\ufffd": '"',
        "\u00e2\u20ac\u201c": "-",
        "\u00e2\u20ac\u201d": "-",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    return text


def _normalise_whitespace(text):
    text = _normalise_encoding_artifacts(str(text or ""))
    return " ".join(text.strip().split())


def _with_period(text):
    text = _normalise_whitespace(text)

    if not text:
        return ""

    if text.endswith((".", "!", "?")):
        return text

    return text + "."


def _lower_first(text):
    text = text.strip()

    if not text:
        return text

    return text[0].lower() + text[1:]


def _natural_failure(text):
    detail = _normalise_whitespace(text)
    match = re.match(
        r"^(failed to|i could not|i couldn't|unable to)\s+(.+)$",
        detail,
        flags=re.IGNORECASE,
    )

    if match:
        prefix = match.group(1).lower()
        detail = match.group(2).strip(" .")

        if prefix == "failed to":
            detail = f"I couldn't {_lower_first(detail)}"
        elif prefix == "unable to":
            detail = f"I couldn't {_lower_first(detail)}"
        elif prefix == "i could not":
            detail = f"I couldn't {_lower_first(detail)}"
        else:
            detail = f"I couldn't {_lower_first(detail)}"
    else:
        detail = detail.strip(" .")

    if not detail:
        return "That didn't work."

    return f"That didn't work. {_with_period(detail)}"


def _light_contractions(text):
    replacements = [
        ("I could not", "I couldn't"),
        ("I cannot", "I can't"),
        ("I do not", "I don't"),
        ("you are", "you're"),
        ("You are", "You're"),
        ("it is", "it's"),
        ("It is", "It's"),
    ]

    for old, new in replacements:
        text = text.replace(old, new)

    return text


def _rewrite_generic_status_reply(text):
    clean = _normalise_whitespace(text)
    lowered = clean.lower().strip()

    generic_health_patterns = [
        r"^i(?: am|'m) functioning (?:well|fine|properly|normally)\b.*",
        r"^i(?: am|'m) doing (?:well|fine|good|okay|ok)\b.*",
        r"^i(?: am|'m) (?:fine|good|okay|ok)\b.*",
        r"^all systems (?:are )?(?:operational|online|running)\b.*",
        r"^i(?: am|'m) ready to assist\b.*",
    ]

    if any(re.match(pattern, lowered) for pattern in generic_health_patterns):
        if "how about you" in lowered or "what about you" in lowered:
            return "All good. What are we working on?"

        return "All good."

    if re.match(r"^(awaiting|waiting for) your next (command|instruction)\.?$", lowered):
        return "I'm listening."

    return clean


def _trim_voice_response(text, max_chars=420):
    clean = _normalise_whitespace(text)

    if len(clean) <= max_chars:
        return clean

    boundary = max(
        clean.rfind(". ", 0, max_chars),
        clean.rfind("? ", 0, max_chars),
        clean.rfind("! ", 0, max_chars),
    )

    if boundary >= 120:
        return clean[: boundary + 1].strip()

    return clean[:max_chars].rstrip(" ,;:-") + "."


def polish_spoken_response(response, max_chars=420):
    """
    Final spoken-output pass before TTS.
    Keeps wording natural without changing intent or adding canned routing logic.
    """

    text = humanise_jarvis_response(response)
    text = _rewrite_generic_status_reply(text)
    text = _light_contractions(text)
    text = _trim_voice_response(text, max_chars=max_chars)

    return text or "Done."


def humanise_jarvis_response(response):
    """
    Converts raw tool responses into smoother spoken responses.
    """

    if not response:
        return "Done."

    text = _normalise_whitespace(response)

    if not text:
        return "Done."

    lowered = text.lower().strip(" .")

    if (
        (lowered.startswith("command") and "completed" in lowered)
        or (lowered.startswith("operation") and "completed" in lowered)
        or (lowered.startswith("function") and "executed" in lowered)
        or (lowered.startswith("request") and "processed" in lowered)
        or (lowered.startswith("task") and "completed" in lowered)
    ):
        return "Done."

    if lowered.startswith(("failed to ", "i could not ", "i couldn't ", "unable to ")):
        return _natural_failure(text)

    if lowered.startswith("tool execution failed:"):
        detail = text.split(":", 1)[1].strip() if ":" in text else ""
        return _natural_failure(detail)

    # -------------------------
    # Memory responses
    # -------------------------
    if text.startswith("I'll remember that:"):
        memory = text.replace("I'll remember that:", "", 1).strip()
        memory = clean_memory_text(memory)

        if memory:
            return f"Got it. I'll keep that in mind: {memory}"

        return "Got it. I'll keep that in mind."

    if text.startswith("I already remember that"):
        return "I already had that saved."

    if text.startswith("Here is what I remember:"):
        memory = text.replace("Here is what I remember:", "", 1).strip()
        memory = memory.replace("preferences:", "")
        memory = memory.replace("user_profile:", "")
        memory = memory.replace("aliases:", "")
        memory = memory.replace("workflow_rules:", "")
        memory = memory.replace("jarvis_rules:", "")
        memory = memory.replace("notes:", "")
        memory = clean_memory_text(memory)
        memory = _normalise_whitespace(memory)

        if memory:
            return f"I remember that {_lower_first(memory)}"

        return "I don't have much saved yet."

    if text.startswith("I do not have any memories"):
        return "I don't have anything saved yet."

    if text.startswith("Forgot:"):
        forgotten = text.replace("Forgot:", "", 1).strip()
        forgotten = clean_memory_text(forgotten)

        if forgotten:
            return f"Done. I forgot {forgotten}."

        return "Done. I forgot that."

    # -------------------------
    # Routine responses
    # -------------------------
    if text.startswith("Saved routine:"):
        routine = text.replace("Saved routine:", "", 1).strip().rstrip(".")
        return f"Done. I saved {routine}."

    if text.startswith("Deleted routine:"):
        routine = text.replace("Deleted routine:", "", 1).strip().rstrip(".")
        return f"Done. I deleted {routine}."

    if text.startswith("Saved routines:"):
        routines = text.replace("Saved routines:", "", 1).strip()
        return f"Saved routines: {routines}."

    # -------------------------
    # App opening and searches
    # -------------------------
    if text.startswith("Opening "):
        return _with_period(text)

    if text.startswith("Searching the web for"):
        query = text.replace("Searching the web for", "", 1).strip().rstrip(".")
        return f"Searching for {query}."

    if text.startswith("Searching YouTube for"):
        query = text.replace("Searching YouTube for", "", 1).strip().rstrip(".")
        return f"Searching YouTube for {query}."

    # -------------------------
    # Volume
    # -------------------------
    volume_down_match = re.search(r"Volume decreased(?: from \d+% to| to) (\d+)%", text)
    if volume_down_match:
        new_volume = volume_down_match.group(1)
        return f"Done. Volume's down to {new_volume} percent."

    volume_up_match = re.search(r"Volume increased(?: from \d+% to| to) (\d+)%", text)
    if volume_up_match:
        new_volume = volume_up_match.group(1)
        return f"Done. Volume's up to {new_volume} percent."

    if text == "Volume muted.":
        return "Muted."

    if text == "Volume unmuted.":
        return "Unmuted."

    # -------------------------
    # Common local responses
    # -------------------------
    if text == "Your to-do list is ready.":
        return "To-do list is ready."

    if text.startswith("CPU is at"):
        return text.replace("CPU is at", "Right now, CPU is at", 1)

    return _light_contractions(text)
