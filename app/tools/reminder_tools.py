import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4


BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
REMINDERS_PATH = DATA_DIR / "reminders.json"


def _now():
    return datetime.now()


def _now_iso():
    return _now().isoformat(timespec="seconds")


def _parse_datetime(value):
    if not value:
        return None

    text = str(value).strip()

    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None

    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)

    return parsed


def _friendly_time(value):
    due_at = _parse_datetime(value)

    if not due_at:
        return str(value or "").strip()

    now = _now()

    if due_at.date() == now.date():
        return due_at.strftime("%I:%M %p").lstrip("0")

    if due_at.date() == (now + timedelta(days=1)).date():
        return "tomorrow at " + due_at.strftime("%I:%M %p").lstrip("0")

    return due_at.strftime("%a %d %b at %I:%M %p").replace(" 0", " ")


def _load_reminders():
    DATA_DIR.mkdir(exist_ok=True)

    if not REMINDERS_PATH.exists():
        _save_reminders([])
        return []

    try:
        with open(REMINDERS_PATH, "r", encoding="utf-8") as file:
            payload = json.load(file)
    except Exception:
        return []

    reminders = payload.get("reminders", []) if isinstance(payload, dict) else payload

    if not isinstance(reminders, list):
        return []

    cleaned = []

    for reminder in reminders:
        if not isinstance(reminder, dict):
            continue

        due_at = str(reminder.get("due_at") or "").strip()

        if not due_at:
            continue

        cleaned.append(
            {
                "id": str(reminder.get("id") or uuid4().hex),
                "text": str(reminder.get("text") or "Reminder").strip() or "Reminder",
                "due_at": due_at,
                "status": str(reminder.get("status") or "pending").strip() or "pending",
                "created_at": str(reminder.get("created_at") or _now_iso()),
                "delivered_at": reminder.get("delivered_at"),
            }
        )

    return cleaned


def _save_reminders(reminders):
    DATA_DIR.mkdir(exist_ok=True)

    with open(REMINDERS_PATH, "w", encoding="utf-8") as file:
        json.dump(reminders, file, indent=2)


def _clean_reminder_text(text):
    clean = " ".join(str(text or "").strip().split())

    if not clean:
        return "Reminder"

    clean = re.sub(
        r"^(?:jarvis\s+)?(?:please\s+)?remind\s+me(?:\s+to)?\s+",
        "",
        clean,
        flags=re.IGNORECASE,
    )
    clean = clean.strip(" .,!?:;")

    return clean or "Reminder"


def _public_reminder(reminder):
    return {
        "id": reminder.get("id"),
        "text": reminder.get("text"),
        "due_at": reminder.get("due_at"),
        "due_label": _friendly_time(reminder.get("due_at")),
        "status": reminder.get("status"),
        "created_at": reminder.get("created_at"),
    }


def create_reminder(reminder_text="", delay_minutes=None, delay_seconds=None, due_at_iso=None):
    """
    Create a real scheduled reminder.
    The voice loop polls pending reminders and speaks them when due.
    """

    due_at = _parse_datetime(due_at_iso)

    if not due_at:
        total_seconds = 0

        if delay_minutes is not None:
            try:
                total_seconds += float(delay_minutes) * 60
            except (TypeError, ValueError):
                pass

        if delay_seconds is not None:
            try:
                total_seconds += float(delay_seconds)
            except (TypeError, ValueError):
                pass

        if total_seconds > 0:
            due_at = _now() + timedelta(seconds=total_seconds)

    if not due_at:
        return {
            "success": False,
            "needs_time": True,
            "message": "When should I remind you?",
            "spoken_message": "When should I remind you?",
        }

    if due_at <= _now():
        return {
            "success": False,
            "message": "That time has already passed.",
            "spoken_message": "That time has already passed.",
        }

    reminders = _load_reminders()
    reminder = {
        "id": uuid4().hex,
        "text": _clean_reminder_text(reminder_text),
        "due_at": due_at.isoformat(timespec="seconds"),
        "status": "pending",
        "created_at": _now_iso(),
        "delivered_at": None,
    }

    reminders.append(reminder)
    reminders.sort(key=lambda item: item.get("due_at", ""))
    _save_reminders(reminders)

    return {
        "success": True,
        "message": f"Reminder set for {_friendly_time(reminder['due_at'])}: {reminder['text']}.",
        "spoken_message": f"Reminder set for {_friendly_time(reminder['due_at'])}.",
        "reminder": _public_reminder(reminder),
    }


def list_reminders(include_delivered=False):
    reminders = _load_reminders()
    include_delivered = bool(include_delivered)
    visible = [
        reminder
        for reminder in reminders
        if include_delivered or reminder.get("status") == "pending"
    ]
    visible.sort(key=lambda item: item.get("due_at", ""))

    if not visible:
        return {
            "success": True,
            "message": "No reminders saved.",
            "spoken_message": "You don't have any reminders.",
            "reminders": [],
            "reminder_count": 0,
        }

    next_reminder = visible[0]
    count = len(visible)

    if count == 1:
        spoken = f"You've got one reminder: {next_reminder['text']} at {_friendly_time(next_reminder['due_at'])}."
    else:
        spoken = f"You've got {count} reminders. Next: {next_reminder['text']} at {_friendly_time(next_reminder['due_at'])}."

    full_list = "; ".join(
        f"{reminder['text']} at {_friendly_time(reminder['due_at'])}"
        for reminder in visible
    )

    return {
        "success": True,
        "message": "Reminders: " + full_list,
        "spoken_message": spoken,
        "reminders": [_public_reminder(reminder) for reminder in visible],
        "reminder_count": count,
    }


def pop_due_reminders(now=None):
    now = now or _now()
    reminders = _load_reminders()
    due = []
    changed = False

    for reminder in reminders:
        if reminder.get("status") != "pending":
            continue

        due_at = _parse_datetime(reminder.get("due_at"))

        if due_at and due_at <= now:
            reminder["status"] = "delivered"
            reminder["delivered_at"] = now.isoformat(timespec="seconds")
            due.append(_public_reminder(reminder))
            changed = True

    if changed:
        _save_reminders(reminders)

    return due
