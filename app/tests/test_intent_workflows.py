import os
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("OPENAI_API_KEY", "test-key")

from ai_brain import JarvisBrain
from router import get_forced_tool_name
from tools import system_tools
from tools.youtube_tools import play_youtube_video


class AppResolverTests(unittest.TestCase):
    def test_random_app_detection_uses_sets_without_crashing(self):
        self.assertFalse(system_tools._looks_like_safe_random_app_request("example browser"))
        self.assertTrue(system_tools._looks_like_safe_random_app_request("open a random app"))

    @patch("tools.system_tools._open_discovered_app")
    @patch("tools.system_tools._find_installed_app")
    def test_open_application_opens_generic_discovered_app_categories(
        self,
        find_installed_app,
        open_discovered_app,
    ):
        open_discovered_app.return_value = {
            "launch_method": "mock",
            "resolved_path": "C:\\Apps\\Example.exe",
        }
        cases = [
            (
                "Example Desktop",
                {
                    "name": "Example Desktop",
                    "path": Path("C:/Apps/ExampleDesktop.exe"),
                    "kind": "executable",
                    "source": "test",
                    "score": 100,
                },
            ),
            (
                "Example Browser",
                {
                    "name": "Example Browser",
                    "path": Path("C:/Apps/ExampleBrowser.exe"),
                    "kind": "executable",
                    "source": "test",
                    "score": 100,
                },
            ),
            (
                "Example Store App",
                {
                    "name": "Example Store App",
                    "path": Path("C:/Apps/ExampleStore.appref-ms"),
                    "kind": "shortcut",
                    "source": "test",
                    "score": 100,
                },
            ),
        ]

        for app_name, candidate in cases:
            with self.subTest(app_name=app_name):
                find_installed_app.return_value = (candidate, ["test"], [])

                result = system_tools.open_application(app_name)

                self.assertTrue(result["success"])
                self.assertEqual(result["source"], "app_discovery")
                open_discovered_app.assert_called_with(candidate)

    @patch("tools.system_tools._open_url")
    def test_open_application_opens_generic_website_url(self, open_url):
        open_url.return_value = {
            "launch_method": "webbrowser",
            "resolved_path": "https://example.com",
        }

        result = system_tools.open_application("example.com")

        self.assertTrue(result["success"])
        self.assertEqual(result["launch_method"], "website_url")

    @patch("tools.system_tools._find_installed_app")
    def test_open_application_unknown_app_reports_no_match(self, find_installed_app):
        find_installed_app.return_value = (None, ["test"], [])

        result = system_tools.open_application("not a real app")

        self.assertFalse(result["success"])
        self.assertIn("couldn't find", result["message"].lower())


class IntentRoutingTests(unittest.TestCase):
    def test_visible_action_routes_to_screen_action(self):
        self.assertEqual(
            get_forced_tool_name("can you please click a random video on the screen"),
            "act_on_screen",
        )

    def test_visual_observation_routes_to_screen_analysis(self):
        self.assertEqual(
            get_forced_tool_name("can you please look at the screen"),
            "analyse_screen",
        )

    def test_polite_app_open_routes_to_open_application(self):
        self.assertEqual(
            get_forced_tool_name("can you please open up example browser"),
            "open_application",
        )

    def test_video_play_request_routes_to_youtube_workflow(self):
        self.assertEqual(
            get_forced_tool_name("find me a funny video and play it"),
            "play_youtube_video",
        )

    def test_visible_results_choice_routes_to_screen_action(self):
        self.assertEqual(
            get_forced_tool_name("pick something funny from these results"),
            "act_on_screen",
        )


class ToolBackedSpeechGuardTests(unittest.TestCase):
    def test_toolless_action_confirmation_is_replaced(self):
        brain = JarvisBrain.__new__(JarvisBrain)

        guarded = brain._guard_toolless_action_response(
            "Can you open the browser?",
            "Opening the browser now.",
        )

        self.assertIsNotNone(guarded)
        self.assertIn("haven't done that", guarded)

    def test_non_action_answer_is_not_replaced(self):
        brain = JarvisBrain.__new__(JarvisBrain)

        guarded = brain._guard_toolless_action_response(
            "How do I open a browser?",
            "Use the Start menu or a pinned shortcut.",
        )

        self.assertIsNone(guarded)


class YouTubeWorkflowTests(unittest.TestCase):
    @patch("tools.youtube_tools._act_on_visible_youtube_results")
    @patch("tools.youtube_tools.time.sleep")
    @patch("tools.youtube_tools.search_youtube")
    def test_play_youtube_video_searches_then_clicks_visible_result(
        self,
        search_youtube,
        sleep,
        act_on_visible_youtube_results,
    ):
        search_youtube.return_value = {
            "success": True,
            "query": "funny cars",
            "url": "https://www.youtube.com/results?search_query=funny+cars",
        }
        act_on_visible_youtube_results.return_value = {
            "success": True,
            "clicked": True,
            "target": "Example funny cars video",
        }

        result = play_youtube_video(
            query="funny cars",
            selection_preference="random",
        )

        self.assertTrue(result["success"])
        self.assertTrue(result["clicked"])
        self.assertEqual(result["workflow"], "youtube_screen_action")
        search_youtube.assert_called_once_with("funny cars")
        sleep.assert_called_once()
        act_on_visible_youtube_results.assert_called_once_with("funny cars", "random")

    @patch("tools.youtube_tools._act_on_visible_youtube_results")
    @patch("tools.youtube_tools.search_youtube")
    def test_play_youtube_video_can_choose_from_current_visible_results(
        self,
        search_youtube,
        act_on_visible_youtube_results,
    ):
        act_on_visible_youtube_results.return_value = {
            "success": True,
            "clicked": True,
            "target": "Visible result",
        }

        result = play_youtube_video(selection_preference="funny")

        self.assertTrue(result["success"])
        self.assertTrue(result["clicked"])
        search_youtube.assert_not_called()
        act_on_visible_youtube_results.assert_called_once_with("", "funny")


if __name__ == "__main__":
    unittest.main()
