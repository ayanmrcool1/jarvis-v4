import re
import time
import urllib.parse
import urllib.request
import webbrowser


# =========================
# JARVIS YOUTUBE TOOLS
# =========================

YOUTUBE_BASE = "https://www.youtube.com"
YOUTUBE_SEARCH_URL = "https://www.youtube.com/results?search_query="
YOUTUBE_RESULTS_LOAD_WAIT_SECONDS = 2.5


def _clean_query(query):
    """
    Cleans natural speech into a usable YouTube query.
    """

    if not query:
        return ""

    query = " ".join(str(query).strip().split())

    starter_phrases = [
        "find me",
        "find a",
        "find",
        "search for",
        "search",
        "choose a",
        "choose",
        "pick a",
        "pick",
        "play a",
        "play",
    ]

    remove_phrases = [
        "put it on",
        "put one on",
        "and play it",
        "play it",
        "play one",
        "on youtube",
        "youtube",
        "a youtube video about",
        "youtube video about",
        "a video about",
        "video about",
        "a youtube video",
        "youtube video",
        "a video",
        "video",
        "videos",
        "a video on",
        "video on",
        "a video of",
        "video of",
        "for me",
        "please",
    ]

    clean = query.lower()

    changed = True

    while changed:
        changed = False

        for phrase in starter_phrases:
            prefix = f"{phrase} "

            if clean.startswith(prefix):
                clean = clean.replace(prefix, " ", 1).strip()
                changed = True

    for phrase in sorted(remove_phrases, key=len, reverse=True):
        pattern = r"\b" + re.escape(phrase) + r"\b"
        clean = re.sub(pattern, " ", clean)

    clean = " ".join(clean.split())

    return clean


def _clean_selection_preference(selection_preference):
    clean = _clean_query(selection_preference)
    return clean


def _infer_selection_preference(*texts):
    preference_words = {
        "funny",
        "random",
        "best",
        "good",
        "great",
        "popular",
        "interesting",
        "relevant",
        "short",
    }
    found = []

    for text in texts:
        clean = _clean_query(text)
        words = set(clean.split())

        for preference in preference_words:
            if preference in words and preference not in found:
                found.append(preference)

    return " ".join(found)


def _fallback_query_from_preference(selection_preference):
    clean_preference = _clean_selection_preference(selection_preference)

    if not clean_preference:
        return ""

    return f"{clean_preference} videos"


def _youtube_search_url(query):
    encoded_query = urllib.parse.quote_plus(query)
    return f"{YOUTUBE_SEARCH_URL}{encoded_query}"


def search_youtube(query):
    """
    Open YouTube search results directly.
    Example:
    search_youtube("rocket league gameplay retals")
    """

    clean_query = _clean_query(query)

    if not clean_query:
        return {
            "success": False,
            "message": "What do you want me to search on YouTube?",
        }

    url = _youtube_search_url(clean_query)

    try:
        webbrowser.open(url)

        return {
            "success": True,
            "query": clean_query,
            "url": url,
            "message": f"Searching YouTube for {clean_query}.",
        }

    except Exception as error:
        return {
            "success": False,
            "message": f"I couldn't search YouTube: {error}",
        }


def _fetch_youtube_search_page(query):
    """
    Downloads YouTube search HTML so Jarvis can extract a likely first video.
    """

    url = _youtube_search_url(query)

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0 Safari/537.36"
            )
        },
    )

    with urllib.request.urlopen(request, timeout=8) as response:
        return response.read().decode("utf-8", errors="ignore")


def _extract_first_video_id(html):
    """
    Extracts the first normal YouTube video ID from search HTML.
    """

    if not html:
        return None

    patterns = [
        r'"videoId":"([a-zA-Z0-9_-]{11})"',
        r"watch\?v=([a-zA-Z0-9_-]{11})",
    ]

    seen = set()

    for pattern in patterns:
        for video_id in re.findall(pattern, html):
            if video_id in seen:
                continue

            seen.add(video_id)

            if len(video_id) == 11:
                return video_id

    return None


def _build_youtube_screen_action_instruction(query, selection_preference):
    preference = _clean_selection_preference(selection_preference)
    clean_query = _clean_query(query)

    if clean_query:
        base = (
            "Inspect the visible YouTube results for this search and choose a real visible video "
            f"matching: {clean_query}."
        )
    else:
        base = "Inspect the current visible YouTube page/results and choose a real visible video."

    if preference:
        base += f" Prefer a result that is {preference}."

    return (
        f"{base} Open/play the selected video and verify that playback or the watch page starts."
    )


def _act_on_visible_youtube_results(query, selection_preference):
    try:
        from tools.screen_action_tools import act_on_screen

        return act_on_screen(
            instruction=_build_youtube_screen_action_instruction(
                query,
                selection_preference,
            ),
            allow_click=True,
        )

    except Exception as error:
        return {
            "success": False,
            "clicked": False,
            "message": f"I couldn't use the screen action workflow: {error}",
            "screen_action_unavailable": True,
        }


def _format_screen_action_play_result(query, selection_preference, search_result, action_result):
    result = dict(action_result or {})
    result["workflow"] = "youtube_screen_action"
    result["query"] = _clean_query(query)
    result["selection_preference"] = _clean_selection_preference(selection_preference)

    if search_result:
        result["search_url"] = search_result.get("url")

    if result.get("success") and result.get("clicked"):
        target = result.get("target")
        result["message"] = (
            f"Playing {target}."
            if target
            else "Playing a YouTube video."
        )
        return result

    if not result.get("message"):
        result["message"] = "I found the YouTube page, but I couldn't verify a video click."

    return result


def _play_first_youtube_result_direct(query):
    clean_query = _clean_query(query)

    if not clean_query:
        return {
            "success": False,
            "message": "What video should I play?",
        }

    try:
        html = _fetch_youtube_search_page(clean_query)
        video_id = _extract_first_video_id(html)

        if video_id:
            url = f"{YOUTUBE_BASE}/watch?v={video_id}&autoplay=1"
            webbrowser.open(url)

            return {
                "success": True,
                "query": clean_query,
                "video_id": video_id,
                "url": url,
                "workflow": "youtube_direct_fallback",
                "message": f"Playing a YouTube video for {clean_query}.",
            }

        search_url = _youtube_search_url(clean_query)
        webbrowser.open(search_url)

        return {
            "success": True,
            "query": clean_query,
            "url": search_url,
            "workflow": "youtube_direct_fallback",
            "message": f"I couldn't pick a video directly, so I opened YouTube results for {clean_query}.",
        }

    except Exception as error:
        search_url = _youtube_search_url(clean_query)

        try:
            webbrowser.open(search_url)

            return {
                "success": True,
                "query": clean_query,
                "url": search_url,
                "workflow": "youtube_direct_fallback",
                "message": f"I opened YouTube results for {clean_query}.",
                "warning": str(error),
            }

        except Exception as fallback_error:
            return {
                "success": False,
                "message": f"I couldn't open YouTube: {fallback_error}",
            }


def play_youtube_video(query=None, selection_preference=None):
    """
    Search/select a YouTube video, click it through the visible page, and verify playback.
    Falls back to direct video opening only if screen action is unavailable.
    """

    clean_query = _clean_query(query)
    clean_preference = _clean_selection_preference(selection_preference)

    if not clean_preference:
        clean_preference = _infer_selection_preference(query)

    if not clean_query and not clean_preference:
        return {
            "success": False,
            "message": "What video should I play?",
        }

    search_result = None

    if clean_query:
        search_result = search_youtube(clean_query)

        if not search_result.get("success"):
            return search_result

        time.sleep(YOUTUBE_RESULTS_LOAD_WAIT_SECONDS)

    action_result = _act_on_visible_youtube_results(clean_query, clean_preference)

    if action_result.get("success") and action_result.get("clicked"):
        return _format_screen_action_play_result(
            clean_query,
            clean_preference,
            search_result,
            action_result,
        )

    if action_result.get("screen_action_unavailable") and clean_query:
        fallback_result = _play_first_youtube_result_direct(clean_query)
        fallback_result["screen_action_error"] = action_result.get("message")
        return fallback_result

    if not clean_query and clean_preference:
        fallback_query = _fallback_query_from_preference(clean_preference)

        if fallback_query:
            return play_youtube_video(
                query=fallback_query,
                selection_preference=clean_preference,
            )

    return _format_screen_action_play_result(
        clean_query,
        clean_preference,
        search_result,
        action_result,
    )
