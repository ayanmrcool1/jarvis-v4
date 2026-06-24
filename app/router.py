import string
import json

from session_state import PendingIntentManager, PendingConfirmationManager
from skills.app_skill import looks_like_multi_step_open_command
from skills.volume_skill import handle_volume_command
from skills.system_skill import handle_system_command
from skills.routine_skill import handle_routine_command
from skills.screen_skill import handle_screen_command
from tools.system_tools import APP_ALIASES, APP_DISPLAY_NAMES, BROWSER_APP_NAMES
from tools.todo_tools import preview_clear_all_todo_tasks
from tools.routine_tools import preview_delete_all_routines
from tools.memory_tools import preview_clear_all_memories
from tools.user_profile_tools import preview_reset_user_profile
from tools.tool_registry import execute_tool_call


# =========================
# JARVIS ROUTER
# Local fast path first.
# If local misses, AI tool brain decides what to do.
# =========================

def normalize_text(text):
    """
    Normalizes speech text for routing.
    """

    if not text:
        return ""

    clean_text = text.lower().strip()
    clean_text = clean_text.translate(str.maketrans("", "", string.punctuation))
    clean_text = " ".join(clean_text.split())

    return clean_text


def get_forced_tool_name(clean_text):
    """
    Forces the AI to call a tool only for obvious executable commands.

    This is NOT the main intelligence layer.
    Main intelligence is handled by stream_ask_with_tools() after local misses.
    """

    if looks_like_capability_gap_summary_request(clean_text):
        return "summarize_capability_gaps"

    if looks_like_reminder_list_request(clean_text):
        return "list_reminders"

    if looks_like_reminder_creation_request(clean_text):
        return "create_reminder"

    # -------------------------
    # Browser tab/app closing tools
    # -------------------------
    if looks_like_current_tab_close(clean_text):
        return "close_current_browser_tab"

    if looks_like_matching_tab_close(clean_text):
        return "close_browser_tabs_matching"

    if looks_like_app_close_command(clean_text):
        return "close_application"

    # -------------------------
    # Screen / vision tools
    # -------------------------
    screenshot_signals = [
        "take screenshot",
        "take a screenshot",
        "screenshot",
        "screenshot this",
        "capture screen",
        "capture my screen",
    ]

    active_window_signals = [
        "what window",
        "what window am i on",
        "active window",
        "what app am i on",
        "what app is open",
        "what application am i on",
        "what window is this",
    ]

    if any(signal in clean_text for signal in screenshot_signals):
        return "take_screenshot"

    if any(signal in clean_text for signal in active_window_signals):
        return "get_active_window_info"

    if looks_like_screen_analysis_request(clean_text):
        return "analyse_screen"

    # Memory and routine-management intent is deliberately left to the AI brain.

    # -------------------------
    # App opening tools
    # -------------------------
    visible_search_prefixes = [
        "open a search for ",
        "open search for ",
        "open up a search for ",
        "open up search for ",
        "open up an image of ",
        "open up a picture of ",
        "open up a photo of ",
        "open up images of ",
        "open up pictures of ",
        "open up photos of ",
        "open an image of ",
        "open a picture of ",
        "open a photo of ",
        "open images of ",
        "open pictures of ",
        "open photos of ",
        "pull up an image of ",
        "pull up a picture of ",
        "pull up a photo of ",
        "pull up images of ",
        "pull up pictures of ",
        "pull up photos of ",
    ]

    if any(clean_text.startswith(prefix) for prefix in visible_search_prefixes):
        return "search_web"

    open_keywords = [
        "open ",
        "launch ",
        "bring up ",
    ]

    for keyword in open_keywords:
        if clean_text.startswith(keyword):
            if looks_like_multi_step_open_command(clean_text):
                return None

            return "open_application"

    # -------------------------
    # Search tools
    # -------------------------
    protected_show_requests = [
        "show me memory",
        "show me memories",
        "show me routine",
        "show me routines",
        "show me my memory",
        "show me my memories",
        "show me my routine",
        "show me my routines",
        "show me the screen",
        "show me my screen",
        "show me this screen",
    ]

    if any(clean_text.startswith(prefix) for prefix in protected_show_requests):
        return None

    search_keywords = [
        "search for ",
        "google for ",
        "google search for ",
        "google search ",
        "pull up results for ",
        "show me results for ",
        "search ",
        "google ",
    ]

    for keyword in sorted(set(search_keywords), key=len, reverse=True):
        if clean_text.startswith(keyword):
            return "search_web"

    # -------------------------
    # Volume tools
    # -------------------------
    if looks_like_volume_command(clean_text):
        return "set_volume"

    # -------------------------
    # System stats tools
    # -------------------------
    if looks_like_system_stats_command(clean_text):
        return "get_system_stats"

    # -------------------------
    # Terminal tools
    # -------------------------
    if clean_text.startswith(("run command ", "run terminal command ", "run powershell command ")):
        return "run_terminal_command"

    return None


def _strip_polite_prefix(clean_text):
    stripped = clean_text

    for prefix in [
        "jarvis can you please ",
        "jarvis could you please ",
        "can you please ",
        "could you please ",
        "jarvis can you ",
        "jarvis could you ",
        "can you ",
        "could you ",
        "please ",
        "jarvis ",
    ]:
        if stripped.startswith(prefix):
            return stripped[len(prefix):].strip()

    return stripped


def _words(clean_text):
    return set(str(clean_text or "").split())


def looks_like_screen_analysis_request(clean_text):
    stripped = _strip_polite_prefix(clean_text)
    words = _words(stripped)

    if not words:
        return False

    screen_refs = {
        "screen",
        "monitor",
        "display",
        "window",
        "page",
        "this",
        "that",
        "here",
        "visible",
    }
    visual_verbs = {
        "see",
        "look",
        "read",
        "analyse",
        "analyze",
        "inspect",
        "check",
        "review",
        "explain",
    }
    visual_nouns = {
        "error",
        "warning",
        "popup",
        "chart",
        "image",
        "picture",
        "code",
    }

    asks_visual_question = stripped.startswith(("what ", "whats ", "what is ", "can you ", "could you "))
    has_reference = bool(words.intersection(screen_refs) or words.intersection(visual_nouns))
    has_visual_action = bool(words.intersection(visual_verbs))

    if has_reference and has_visual_action:
        return True

    if stripped.startswith("what can you see"):
        return True

    if asks_visual_question and has_reference:
        return True

    if "on my screen" in stripped or "on the screen" in stripped:
        return True

    return False


def looks_like_reminder_creation_request(clean_text):
    words = _words(clean_text)

    if "remind" not in words and "reminder" not in words and "reminders" not in words:
        return False

    list_terms = {"list", "show", "what", "which", "current", "active", "have"}

    if words.intersection(list_terms):
        return False

    time_terms = {
        "minute",
        "minutes",
        "hour",
        "hours",
        "tomorrow",
        "today",
        "tonight",
        "morning",
        "afternoon",
        "evening",
        "at",
        "in",
        "later",
    }

    return "remind" in words or bool(words.intersection(time_terms))


def looks_like_reminder_list_request(clean_text):
    words = _words(clean_text)

    if not words.intersection({"reminder", "reminders"}):
        return False

    return bool(words.intersection({"what", "list", "show", "have", "current", "active"}))


def looks_like_bulk_todo_delete(clean_text):
    words = _words(clean_text)
    delete_terms = {"delete", "remove", "clear", "wipe", "empty"}
    bulk_terms = {"all", "every", "everything", "entire"}
    todo_terms = {"todo", "todos", "to-do", "tasks", "task", "list"}

    return bool(
        words.intersection(delete_terms)
        and words.intersection(bulk_terms)
        and words.intersection(todo_terms)
    )


def looks_like_bulk_routine_delete(clean_text):
    words = _words(clean_text)
    delete_terms = {"delete", "remove", "clear", "wipe"}
    bulk_terms = {"all", "every", "everything", "entire"}
    routine_terms = {"routine", "routines"}

    return bool(
        words.intersection(delete_terms)
        and words.intersection(bulk_terms)
        and words.intersection(routine_terms)
    )


def looks_like_bulk_memory_clear(clean_text):
    words = _words(clean_text)
    delete_terms = {"delete", "remove", "clear", "wipe", "forget", "reset"}
    bulk_terms = {"all", "every", "everything", "entire"}
    memory_terms = {"memory", "memories", "remembered"}

    return bool(
        words.intersection(delete_terms)
        and (
            words.intersection(bulk_terms)
            or "clear memory" in clean_text
            or "reset memory" in clean_text
        )
        and words.intersection(memory_terms)
    )


def looks_like_profile_reset(clean_text):
    words = _words(clean_text)
    reset_terms = {"delete", "remove", "clear", "wipe", "reset"}
    bulk_terms = {"all", "every", "everything", "entire"}
    profile_terms = {"profile", "preferences", "personalisation", "personalization", "details"}

    return bool(
        words.intersection(reset_terms)
        and (
            words.intersection(bulk_terms)
            or words.intersection({"reset", "clear", "wipe"})
            or "reset profile" in clean_text
            or "clear profile" in clean_text
        )
        and words.intersection(profile_terms)
    )


def _confirmation_prompt_for_clear_todos():
    preview = preview_clear_all_todo_tasks(include_completed=True)
    count = int(preview.get("task_count", 0))

    if count <= 0:
        return None

    return f"This will delete {count} to-do tasks. Confirm?"


def _confirmation_prompt_for_delete_routines():
    preview = preview_delete_all_routines()
    count = int(preview.get("routine_count", 0))

    if count <= 0:
        return None

    return f"This will delete {count} routines. Confirm?"


def _confirmation_prompt_for_clear_memories():
    preview = preview_clear_all_memories()
    count = int(preview.get("memory_count", 0))

    if count <= 0:
        return None

    return f"This will delete {count} saved memories. Confirm?"


def _confirmation_prompt_for_reset_profile():
    preview = preview_reset_user_profile()
    count = int(preview.get("detail_count", 0))

    if count <= 0:
        return None

    return f"This will delete {count} profile details. Confirm?"


def _close_target(clean_text):
    stripped = _strip_polite_prefix(clean_text)

    for prefix in [
        "close down ",
        "close the whole ",
        "close whole ",
        "close the entire ",
        "close entire ",
        "close the ",
        "close ",
        "quit ",
        "exit ",
    ]:
        if stripped.startswith(prefix):
            return stripped[len(prefix):].strip()

    return ""


def _normalise_close_app_target(target):
    clean = str(target or "").strip()
    clean = clean.replace("the ", "")

    for word in ["whole", "entire", "full", "app", "application", "window", "windows"]:
        clean = clean.replace(f" {word}", "")
        clean = clean.replace(f"{word} ", "")

    clean = " ".join(clean.split())

    return APP_ALIASES.get(clean, clean)


def _looks_like_explicit_whole_app_close(clean_text):
    words = _words(clean_text)
    return bool(words.intersection({"whole", "entire", "app", "application", "window"}))


def _ambiguous_browser_close_target(clean_text):
    target = _normalise_close_app_target(_close_target(clean_text))

    if not target:
        return ""

    if target in BROWSER_APP_NAMES and not _looks_like_explicit_whole_app_close(clean_text):
        return target

    return ""


def looks_like_current_tab_close(clean_text):
    stripped = _strip_polite_prefix(clean_text)

    current_tab_phrases = {
        "close this tab",
        "close current tab",
        "close current browser tab",
        "close the current tab",
        "close the current browser tab",
        "close the tab",
        "close tab",
    }

    return stripped in current_tab_phrases


def looks_like_matching_tab_close(clean_text):
    stripped = _strip_polite_prefix(clean_text)

    if "tab" not in stripped and "tabs" not in stripped:
        return False

    return stripped.startswith(
        (
            "close all ",
            "close every ",
            "close any ",
        )
    )


def looks_like_app_close_command(clean_text):
    target = _close_target(clean_text)

    if not target:
        return False

    if "tab" in target or "tabs" in target:
        return False

    protected_targets = {
        "widget",
        "widgets",
        "hud",
        "chat",
        "to do",
        "todo",
        "to-do",
        "system stats",
        "system status",
    }

    if target in protected_targets:
        return False

    normalised_target = _normalise_close_app_target(target)

    known_targets = set(APP_ALIASES) | set(APP_DISPLAY_NAMES) | {
        "browser",
        "the browser",
        "window",
        "this window",
    }

    return target in known_targets or normalised_target in known_targets


def looks_like_volume_command(clean_text):
    if clean_text in ["mute", "unmute"]:
        return True

    if clean_text.startswith(
        (
            "mute ",
            "unmute ",
            "volume ",
            "turn volume ",
            "set volume ",
            "lower volume",
            "raise volume",
            "increase volume",
            "decrease volume",
        )
    ):
        return True

    if "volume" in clean_text:
        return any(
            word in clean_text
            for word in ["up", "down", "lower", "raise", "increase", "decrease", "mute", "unmute"]
        )

    return False


def looks_like_system_stats_command(clean_text):
    display_intent_prefixes = (
        "show ",
        "show me ",
        "display ",
        "open ",
        "pull up ",
        "bring up ",
    )

    if clean_text.startswith(display_intent_prefixes):
        return False

    direct_phrases = [
        "system stats",
        "system status",
        "computer stats",
        "computer status",
        "performance stats",
        "cpu usage",
        "ram usage",
        "memory usage",
        "battery level",
        "battery percentage",
        "disk usage",
    ]

    return any(phrase in clean_text for phrase in direct_phrases)


def looks_like_capability_gap_summary_request(clean_text):
    if not clean_text:
        return False

    if "capability gap" in clean_text or "capability gaps" in clean_text:
        return True

    question_or_report_terms = [
        "what",
        "which",
        "show",
        "list",
        "summarize",
        "summarise",
        "tell me",
        "recent",
    ]

    limitation_terms = [
        "cant",
        "cannot",
        "couldnt",
        "unable",
        "not able",
        "limitations",
        "limits",
        "failed",
        "failures",
        "needs improvement",
    ]

    jarvis_terms = [
        "you",
        "your",
        "jarvis",
    ]

    asks_about_limits = any(term in clean_text for term in question_or_report_terms)
    mentions_limits = any(term in clean_text for term in limitation_terms)
    mentions_jarvis = any(term in clean_text for term in jarvis_terms)

    return asks_about_limits and mentions_limits and mentions_jarvis


class JarvisRouter:
    """
    Main command router.

    Correct architecture:
    1. Local skill handlers catch obvious instant executable commands first.
    2. Forced tool routing handles very obvious tool intent.
    3. If still not handled, AI tool-streaming brain decides:
       - call a function, or
       - answer normally.
    """

    def __init__(self, brain):
        self.brain = brain
        self.pending_intents = PendingIntentManager()
        self.pending_confirmations = PendingConfirmationManager()

        self.local_skill_handlers = [
            handle_screen_command,
            handle_routine_command,
            handle_system_command,
            handle_volume_command,
        ]

    def handle(self, transcription):
        """
        Main routing function.

        Returns:
        - type: 'text' or 'stream'
        - response: normal text response
        - stream: streamed AI/tool response
        - source: where the response came from
        """

        clean_text = normalize_text(transcription)

        print(f"Router clean text: {clean_text}")

        confirmation_result = self.pending_confirmations.resolve_with(
            transcription,
            clean_text,
        )

        if confirmation_result:
            status = confirmation_result.get("status")

            if status in ["cancelled", "still_pending"]:
                return {
                    "type": "text",
                    "response": confirmation_result.get("message", "Please confirm first."),
                    "source": "pending_confirmation",
                }

            if status == "confirmed":
                return self._run_confirmed_tool(confirmation_result)

        pending_result = self.pending_intents.resolve_with(transcription, clean_text)

        if pending_result:
            status = pending_result.get("status")

            if status in ["cancelled", "still_missing"]:
                return {
                    "type": "text",
                    "response": pending_result.get("message", "No problem."),
                    "source": "pending_intent",
                }

            if status == "resolved":
                print(f"Router completed pending intent: {pending_result.get('tool_name')}")

                return {
                    "type": "stream",
                    "stream": self.brain.stream_ask_with_tools(
                        pending_result.get("user_text", transcription),
                        forced_tool_name=pending_result.get("tool_name"),
                    ),
                    "source": "pending_intent_stream",
                }

        pending = self.pending_intents.create_from_incomplete_request(
            transcription,
            clean_text,
        )

        if pending:
            print(f"Router created pending intent: {pending.get('pending_intent_type')}")

            return {
                "type": "text",
                "response": pending.get("prompt", "What should I use?"),
                "source": "pending_intent",
            }

        destructive_confirmation = self._create_destructive_confirmation(
            transcription,
            clean_text,
        )

        if destructive_confirmation:
            return {
                "type": "text",
                "response": destructive_confirmation.get("prompt"),
                "source": "pending_confirmation",
            }

        browser_close_confirmation = self._create_browser_close_confirmation(
            transcription,
            clean_text,
        )

        if browser_close_confirmation:
            return {
                "type": "text",
                "response": browser_close_confirmation.get("prompt"),
                "source": "pending_confirmation",
            }

        # -------------------------
        # 1. Local fast path
        # -------------------------
        for handler in self.local_skill_handlers:
            try:
                result = handler(transcription, clean_text)

                if result and result.get("handled"):
                    print(f"Router matched: {result.get('source')}")

                    return {
                        "type": "text",
                        "response": result.get("response", "Done."),
                        "source": result.get("source", "local_skill"),
                    }

            except Exception as error:
                print(f"Local router error in {handler.__name__}: {error}")

        # -------------------------
        # 2. Forced AI tool path for obvious intent
        # -------------------------
        forced_tool_name = get_forced_tool_name(clean_text)

        if forced_tool_name:
            print(f"Router forcing AI tool: {forced_tool_name}")

            return {
                "type": "stream",
                "stream": self.brain.stream_ask_with_tools(
                    transcription,
                    forced_tool_name=forced_tool_name,
                ),
                "source": "ai_forced_tool_stream",
            }

        # -------------------------
        # 3. Main AI tool brain fallback
        # -------------------------
        print("Router using AI tool streaming brain.")

        return {
            "type": "stream",
            "stream": self.brain.stream_ask_with_tools(transcription),
            "source": "ai_tool_stream",
        }

    def _create_destructive_confirmation(self, transcription, clean_text):
        if looks_like_bulk_todo_delete(clean_text):
            prompt = _confirmation_prompt_for_clear_todos()

            if not prompt:
                return None

            return self.pending_confirmations.create(
                action_type="clear_all_todo_tasks",
                tool_name="clear_all_todo_tasks",
                arguments={
                    "confirmed": True,
                    "include_completed": True,
                    "open_widget": True,
                },
                prompt=prompt,
                description=transcription,
            )

        if looks_like_bulk_routine_delete(clean_text):
            prompt = _confirmation_prompt_for_delete_routines()

            if not prompt:
                return None

            return self.pending_confirmations.create(
                action_type="delete_all_routines",
                tool_name="delete_all_routines",
                arguments={"confirmed": True},
                prompt=prompt,
                description=transcription,
            )

        if looks_like_bulk_memory_clear(clean_text):
            prompt = _confirmation_prompt_for_clear_memories()

            if not prompt:
                return None

            return self.pending_confirmations.create(
                action_type="clear_all_memories",
                tool_name="clear_all_memories",
                arguments={"confirmed": True},
                prompt=prompt,
                description=transcription,
            )

        if looks_like_profile_reset(clean_text):
            prompt = _confirmation_prompt_for_reset_profile()

            if not prompt:
                return None

            return self.pending_confirmations.create(
                action_type="reset_user_profile",
                tool_name="reset_user_profile",
                arguments={"confirmed": True},
                prompt=prompt,
                description=transcription,
            )

        return None

    def _create_browser_close_confirmation(self, transcription, clean_text):
        target = _ambiguous_browser_close_target(clean_text)

        if not target:
            return None

        display_name = APP_DISPLAY_NAMES.get(target, target.title())

        return self.pending_confirmations.create(
            action_type="close_application",
            tool_name="close_application",
            arguments={
                "app_name": target,
                "confirmed": True,
            },
            prompt=(
                f"Do you mean the whole {display_name} window? "
                "Say yes to close it, or ask for the tab instead."
            ),
            description=transcription,
        )

    def _run_confirmed_tool(self, confirmation_result):
        tool_name = confirmation_result.get("tool_name")
        arguments = confirmation_result.get("arguments", {})

        print(f"Router running confirmed action: {tool_name}")

        result = execute_tool_call(tool_name, json.dumps(arguments))
        response = None

        if hasattr(self.brain, "_direct_tool_response"):
            response = self.brain._direct_tool_response(tool_name, result)

        if not response and isinstance(result, dict):
            response = result.get("spoken_message") or result.get("message")

        return {
            "type": "text",
            "response": response or "Done.",
            "source": "pending_confirmation",
            "tool_result": result,
        }
