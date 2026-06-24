import json
import difflib
import re
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from ui_state import open_widget as open_hud_widget
from ui_state import update_widget_content


BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
TODO_PATH = DATA_DIR / "todo.json"
TODO_WIDGET_ID = "todo_widget"


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _normalise_text(text):
    return " ".join(str(text or "").strip().lower().split())


def _clean_task_text(task_text):
    raw = " ".join(str(task_text or "").strip().split())

    if not raw:
        return "", "empty"

    text = raw.replace("\u2019", "'").replace("`", "'")
    text = re.sub(
        r"\b(?:what(?:'s| is)\s+it\s+called|what(?:'s| is)\s+the\s+word|you\s+know|uh+|um+)\b",
        " ",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\s+", " ", text).strip(" ,.!?:;")

    text = re.sub(
        r"^(?:jarvis\s+)?(?:please\s+)?(?:add|put|save|create|make)\s+(?:a\s+)?(?:task\s+)?",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"^(?:remind\s+me\s+to|remember\s+to)\s+",
        "",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"\s+(?:to|on|in)\s+(?:my|the|a)?\s*(?:to[- ]?do\s+list|todo\s+list|task\s+list|tasks?|list)$",
        "",
        text,
        flags=re.IGNORECASE,
    )

    if "todo" in raw.lower() or "to-do" in raw.lower() or "to do" in raw.lower():
        text = re.sub(
            r"\s+to\s+(?:my|the)\s+(?:notes?|notebook|list)$",
            "",
            text,
            flags=re.IGNORECASE,
        )

    text = re.sub(
        r"\b([a-z0-9][a-z0-9\s'-]*?\bnotes?)\s+to\s+(?:my|the)\s+notes?$",
        r"\1",
        text,
        flags=re.IGNORECASE,
    )

    segments = [
        segment.strip(" ,.!?:;")
        for segment in re.split(r"[,;]", text)
        if segment.strip(" ,.!?:;")
    ]

    meaningful_segments = [
        segment
        for segment in segments
        if not re.search(r"\b(?:todo|to-do|task list|list)$", segment, flags=re.IGNORECASE)
    ]

    if meaningful_segments:
        text = max(meaningful_segments, key=len)

    text = re.sub(
        r"\b([a-z0-9][a-z0-9\s'-]*?\bnotes?)\s+to\s+(?:my|the)\s+notes?$",
        r"\1",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(r"\s+", " ", text).strip(" ,.!?:;")

    if not text:
        return "", "empty"

    if re.search(r"\b(?:what|called|todo|to-do)$", text, flags=re.IGNORECASE):
        return "", "low_confidence"

    return text[:1].upper() + text[1:], "cleaned"


def _normalise_match_text(text):
    clean = str(text or "").lower()
    clean = clean.replace("&", " and ")
    clean = re.sub(r"[^a-z0-9]+", " ", clean)

    filler_words = {
        "a",
        "an",
        "the",
        "to",
        "my",
        "from",
        "on",
        "in",
        "for",
        "please",
        "task",
        "todo",
        "to-do",
        "list",
    }

    words = [
        word
        for word in clean.split()
        if word and word not in filler_words
    ]

    spaced = " ".join(words)

    return {
        "spaced": spaced,
        "compact": "".join(words),
        "words": set(words),
    }


def _task_similarity(task_ref, task_text):
    ref = _normalise_match_text(task_ref)
    task = _normalise_match_text(task_text)

    if not ref["compact"] or not task["compact"]:
        return 0.0

    char_score = difflib.SequenceMatcher(
        None,
        ref["compact"],
        task["compact"],
    ).ratio()

    if ref["words"] and task["words"]:
        overlap = len(ref["words"] & task["words"])
        token_score = overlap / max(len(ref["words"]), len(task["words"]))
    else:
        token_score = 0.0

    return max(char_score, (char_score * 0.75) + (token_score * 0.25))


def _load_tasks():
    DATA_DIR.mkdir(exist_ok=True)

    if not TODO_PATH.exists():
        _save_tasks([])
        return []

    try:
        with open(TODO_PATH, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception:
        return []

    tasks = payload.get("tasks", []) if isinstance(payload, dict) else payload

    if not isinstance(tasks, list):
        return []

    normalised_tasks = []

    for task in tasks:
        if not isinstance(task, dict):
            continue

        text = str(task.get("text", "")).strip()

        if not text:
            continue

        normalised_tasks.append(
            {
                "id": str(task.get("id") or uuid4().hex),
                "text": text,
                "done": bool(task.get("done", False)),
                "created_at": str(task.get("created_at") or _now()),
            }
        )

    return normalised_tasks


def _save_tasks(tasks):
    DATA_DIR.mkdir(exist_ok=True)

    with open(TODO_PATH, "w", encoding="utf-8") as f:
        json.dump(tasks, f, indent=2)


def _sync_widget(tasks, open_widget=False):
    content = {
        "tasks": tasks,
    }

    if open_widget:
        open_hud_widget(
            widget_id=TODO_WIDGET_ID,
            widget_type="todo",
            title="TO-DO LIST",
            content=content,
        )
        return

    update_widget_content(TODO_WIDGET_ID, content)


def _public_task(task, index):
    return {
        "index": index,
        "id": task.get("id"),
        "text": task.get("text"),
        "done": bool(task.get("done")),
        "created_at": task.get("created_at"),
    }


def _match_task(tasks, task_ref, include_done=True):
    clean_ref = _normalise_text(task_ref)

    if not clean_ref:
        return None, "missing", []

    if clean_ref.isdigit():
        index = int(clean_ref) - 1

        if 0 <= index < len(tasks):
            return index, "index", []

    id_matches = [
        index for index, task in enumerate(tasks)
        if _normalise_text(task.get("id")) == clean_ref
    ]

    if len(id_matches) == 1:
        return id_matches[0], "id", []

    candidates = []

    for index, task in enumerate(tasks):
        if not include_done and task.get("done"):
            continue

        clean_text = _normalise_text(task.get("text"))

        if clean_ref == clean_text:
            return index, "exact_text", []

        if clean_ref in clean_text or clean_text in clean_ref:
            candidates.append(index)

    if len(candidates) == 1:
        return candidates[0], "partial_text", []

    scored_candidates = []

    for index, task in enumerate(tasks):
        if not include_done and task.get("done"):
            continue

        score = _task_similarity(task_ref, task.get("text", ""))

        if score >= 0.64:
            scored_candidates.append((score, index))

    scored_candidates.sort(reverse=True)

    if scored_candidates:
        top_score, top_index = scored_candidates[0]
        second_score = scored_candidates[1][0] if len(scored_candidates) > 1 else 0.0

        if top_score >= 0.88 and top_score - second_score >= 0.06:
            return top_index, "fuzzy_text", []

        close_candidates = [
            index
            for score, index in scored_candidates[:3]
        ]

        return None, "close_match", close_candidates

    return None, "ambiguous" if candidates else "not_found", candidates


def create_todo_list(reset_existing=False, confirmed=False, open_widget=True):
    """
    Ensures the internal Jarvis to-do list exists. Resetting existing tasks is
    treated as confirmation-required unless explicitly confirmed.
    """

    tasks = _load_tasks()
    reset_existing = bool(reset_existing)
    confirmed = bool(confirmed)

    if reset_existing and tasks and not confirmed:
        return {
            "success": False,
            "needs_confirmation": True,
            "message": "I can reset it, but I need confirmation first.",
            "spoken_message": "I can reset it, but I need confirmation first.",
            "task_count": len(tasks),
        }

    if reset_existing and confirmed:
        tasks = []
        _save_tasks(tasks)

    _sync_widget(tasks, open_widget=bool(open_widget))

    return {
        "success": True,
        "message": "To-do list is ready.",
        "spoken_message": "To-do list is ready.",
        "tasks": [_public_task(task, index + 1) for index, task in enumerate(tasks)],
        "task_count": len(tasks),
    }


def add_todo_task(task_text, open_widget=True):
    task_text, cleanup_status = _clean_task_text(task_text)

    if not task_text:
        return {
            "success": False,
            "needs_clarification": True,
            "message": "What should I call that task?",
            "spoken_message": "What should I call that task?",
            "cleanup_status": cleanup_status,
        }

    tasks = _load_tasks()

    duplicate = next(
        (
            task for task in tasks
            if _normalise_text(task.get("text")) == _normalise_text(task_text)
            and not task.get("done")
        ),
        None,
    )

    if duplicate:
        _sync_widget(tasks, open_widget=bool(open_widget))
        return {
            "success": True,
            "message": "That task is already on your list.",
            "spoken_message": "That task is already on your list.",
            "task": duplicate,
            "duplicate": True,
        }

    task = {
        "id": uuid4().hex,
        "text": task_text,
        "done": False,
        "created_at": _now(),
    }
    tasks.append(task)
    _save_tasks(tasks)
    _sync_widget(tasks, open_widget=bool(open_widget))

    return {
        "success": True,
        "message": f"Added {task_text} to your to-do list.",
        "spoken_message": f"Added {task_text} to your to-do list.",
        "task": task,
        "task_count": len(tasks),
        "cleanup_status": cleanup_status,
    }


def preview_clear_all_todo_tasks(include_completed=True):
    tasks = _load_tasks()
    include_completed = bool(include_completed)
    visible = [
        task
        for task in tasks
        if include_completed or not task.get("done")
    ]

    return {
        "task_count": len(visible),
        "tasks": [_public_task(task, index + 1) for index, task in enumerate(visible)],
    }


def clear_all_todo_tasks(confirmed=False, include_completed=True, open_widget=True):
    tasks = _load_tasks()
    include_completed = bool(include_completed)
    confirmed = bool(confirmed)

    remaining_tasks = []
    deleted_tasks = []

    for task in tasks:
        if include_completed or not task.get("done"):
            deleted_tasks.append(task)
        else:
            remaining_tasks.append(task)

    if not deleted_tasks:
        _sync_widget(tasks, open_widget=bool(open_widget))
        return {
            "success": True,
            "message": "Your to-do list is already empty.",
            "spoken_message": "Your to-do list is already empty.",
            "deleted_count": 0,
            "tasks": [],
        }

    if not confirmed:
        return {
            "success": False,
            "needs_confirmation": True,
            "message": f"This will delete {len(deleted_tasks)} to-do tasks. Confirm?",
            "spoken_message": f"This will delete {len(deleted_tasks)} to-do tasks. Confirm?",
            "task_count": len(deleted_tasks),
            "tasks": [_public_task(task, index + 1) for index, task in enumerate(deleted_tasks)],
        }

    _save_tasks(remaining_tasks)
    _sync_widget(remaining_tasks, open_widget=bool(open_widget))

    return {
        "success": True,
        "message": f"Deleted {len(deleted_tasks)} to-do tasks.",
        "spoken_message": "Done. I cleared your to-do list.",
        "deleted_count": len(deleted_tasks),
        "deleted_tasks": deleted_tasks,
    }


def list_todo_tasks(include_completed=False, open_widget=True):
    tasks = _load_tasks()
    include_completed = bool(include_completed)
    visible_tasks = [
        task for task in tasks
        if include_completed or not task.get("done")
    ]

    _sync_widget(tasks, open_widget=bool(open_widget))

    if not visible_tasks:
        return {
            "success": True,
            "message": "Your to-do list is empty.",
            "spoken_message": "Your to-do list is empty.",
            "tasks": [],
            "task_count": 0,
        }

    preview = ", ".join(task.get("text", "") for task in visible_tasks[:3])
    extra_count = max(0, len(visible_tasks) - 3)

    if extra_count:
        spoken = f"You have {len(visible_tasks)} tasks, including {preview}, and {extra_count} more."
    else:
        spoken = f"You have {len(visible_tasks)} tasks: {preview}."

    return {
        "success": True,
        "message": spoken,
        "spoken_message": spoken,
        "tasks": [_public_task(task, index + 1) for index, task in enumerate(tasks)],
        "task_count": len(visible_tasks),
    }


def complete_todo_task(task_ref, open_widget=True):
    tasks = _load_tasks()
    index, match_type, candidates = _match_task(tasks, task_ref, include_done=False)

    if index is None:
        return _task_match_failure(task_ref, tasks, match_type, candidates)

    tasks[index]["done"] = True
    _save_tasks(tasks)
    _sync_widget(tasks, open_widget=bool(open_widget))

    return {
        "success": True,
        "message": f"Marked {tasks[index]['text']} done.",
        "spoken_message": f"Marked {tasks[index]['text']} done.",
        "task": _public_task(tasks[index], index + 1),
        "match_type": match_type,
    }


def remove_todo_task(task_ref, open_widget=True):
    tasks = _load_tasks()
    index, match_type, candidates = _match_task(tasks, task_ref, include_done=True)

    if index is None:
        return _task_match_failure(task_ref, tasks, match_type, candidates)

    task = tasks.pop(index)
    _save_tasks(tasks)
    _sync_widget(tasks, open_widget=bool(open_widget))

    return {
        "success": True,
        "message": f"Removed {task['text']} from your to-do list.",
        "spoken_message": f"Removed {task['text']} from your to-do list.",
        "removed_task": task,
        "match_type": match_type,
    }


def _task_match_failure(task_ref, tasks, match_type, candidates):
    top_matches = [
        _public_task(tasks[index], index + 1)
        for index in candidates[:3]
        if 0 <= index < len(tasks)
    ]

    if match_type == "ambiguous":
        message = "I found more than one matching task. Which one should I use?"
    elif match_type == "close_match" and top_matches:
        message = f"Do you mean '{top_matches[0]['text']}'?"
    else:
        message = "I couldn't find that task on your to-do list."

    return {
        "success": False,
        "message": message,
        "spoken_message": message,
        "needs_confirmation": match_type == "close_match",
        "suggested_task": top_matches[0] if match_type == "close_match" and top_matches else None,
        "task_ref": task_ref,
        "match_type": match_type,
        "top_matches": top_matches,
    }
