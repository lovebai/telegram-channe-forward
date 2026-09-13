import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import requests
import main
from telegram.error import BadRequest


class ErrorTests(unittest.TestCase):
    def test_error_details_redact_secrets(self):
        config = {"bot_token": "123:secret", "proxy": "http://user:password@localhost:7890"}
        error = RuntimeError("Failed 123:secret http://user:password@localhost:7890 https://cdn.example/a?secret=yes\nnext")
        detail = main.describe_error(error, config)
        self.assertIn("RuntimeError: Failed", detail)
        for secret in ("123:secret", "password", "cdn.example", "\n"):
            self.assertNotIn(secret, detail)

    def test_bad_request_reason_and_hint(self):
        error = BadRequest("Chat not found")
        self.assertIn("Chat not found", main.describe_error(error, {}))
        self.assertIn("target_channel", main.error_hint(error))


class HistoryTests(unittest.TestCase):
    @staticmethod
    def response(*numbers):
        return Mock(text=''.join(f'<div class="tgme_widget_message" data-post="abc/{n}"></div>' for n in numbers))

    def test_resume_pages_exclude_boundary_and_deduplicate(self):
        session = Mock()
        session.get.side_effect = [self.response(22169, 22174, 22178), self.response(22178, 22183), self.response(22183)]
        posts = main.fetch_posts(session, 'abc', 22169, 30)
        self.assertEqual([p[0] for p in posts], [22174, 22178, 22183])
        self.assertEqual([call.kwargs['params'] for call in session.get.call_args_list],
                         [{'after': 22169}, {'after': 22178}, {'after': 22183}])

    def test_first_start_only_loads_recent_page(self):
        session = Mock()
        session.get.return_value = self.response(100, 105)
        self.assertEqual([p[0] for p in main.fetch_posts(session, 'abc', 0, 30)], [100, 105])
        session.get.assert_called_once()
        self.assertEqual(session.get.call_args.kwargs['params'], {})

    def test_page_budget_and_gaps(self):
        session = Mock()
        session.get.side_effect = [self.response(n) for n in [30, 50, 80, 100, 150]]
        self.assertEqual([p[0] for p in main.fetch_posts(session, 'abc', 20, 30)], [30, 50, 80, 100, 150])
        self.assertEqual(session.get.call_count, 5)

    def test_later_page_failure_keeps_fetched_posts(self):
        session = Mock()
        session.get.side_effect = [self.response(21), requests.Timeout()]
        self.assertEqual([p[0] for p in main.fetch_posts(session, 'abc', 20, 30)], [21])

    def test_first_page_failure_propagates(self):
        session = Mock()
        session.get.side_effect = requests.Timeout()
        with self.assertRaises(requests.Timeout):
            main.fetch_posts(session, 'abc', 20, 30)


class ParsingTests(unittest.TestCase):
    def test_media_order_duplicates_and_video_source(self):
        html = '''<div class="tgme_widget_message" data-post="abc/12">
        <a class="tgme_widget_message_photo_wrap" style="background-image:url('https://x/a.jpg')"></a>
        <video><source src="https://x/v.mp4"></video>
        <a class="tgme_widget_message_photo_wrap" style="background-image:url('https://x/a.jpg')"></a>
        </div><div class="tgme_widget_message" data-post="abc/11"><video src="https://x/b.mp4"></video></div>
        <div class="tgme_widget_message" data-post="other/13"></div>'''
        posts = main.parse_posts(html, "abc", 10)
        self.assertEqual([p[0] for p in posts], [11, 12])
        self.assertEqual(posts[1][1], [("photo", "https://x/a.jpg"), ("video", "https://x/v.mp4")])
        self.assertFalse(posts[1][2])
        self.assertEqual(main.parse_posts(html, "abc", 12), [])

    def test_missing_video_url(self):
        self.assertEqual(main.parse_posts('<div class="tgme_widget_message" data-post="abc/1"><video></video></div>', "abc", 0), [(1, [], True)])

    def test_config_and_state(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.json"
            config = {"bot_token": "123:test", "target_channel": -100123, "source_channels": ["@ABC", "abc", "def"], "proxy": "socks5://localhost:1080"}
            path.write_text(json.dumps(config))
            loaded = main.load_config(path)
            self.assertEqual(loaded["source_channels"], ["abc", "def"])
            state_path = loaded["state_file"]
            (Path(folder) / "last_id.txt").write_text("42")
            self.assertEqual(main.load_state(state_path, loaded["source_channels"]), {"abc": 42})
            main.save_state(state_path, {"abc": 43, "def": 2})
            self.assertEqual(main.load_state(state_path, []), {"abc": 43, "def": 2})
            config["check_interval"] = 0
            path.write_text(json.dumps(config))
            with self.assertRaises(ValueError):
                main.load_config(path)


class ForwardTests(unittest.IsolatedAsyncioTestCase):
    async def test_bad_request_logs_reason_without_advancing(self):
        bot = AsyncMock()
        bot.send_video.side_effect = BadRequest("Chat not found")
        config = {"source_channels": ["a"], "target_channel": "@target", "request_timeout": 30}
        state = {"a": 1}
        with patch("main.fetch_posts", return_value=[(2, [("video", "https://x/v")], False)]):
            with self.assertLogs("main", level="WARNING") as logs:
                await main.poll_once(bot, Mock(), config, state)
        self.assertIn("Chat not found", " ".join(logs.output))
        self.assertEqual(state, {"a": 1})

    async def test_url_failure_uploads_downloaded_album(self):
        bot = AsyncMock()
        bot.send_media_group.side_effect = [BadRequest('Failed to send message #1: webpage_curl_failed'), None]
        with patch('main.download_media', return_value=b'image bytes') as download:
            await main.send_post(bot, '@target', [('photo', 'https://x/a'), ('photo', 'https://x/b')], Mock())
        self.assertEqual(download.call_count, 2)
        self.assertEqual(bot.send_media_group.await_count, 2)
        self.assertTrue(all(item.media.input_file_content == b'image bytes' for item in bot.send_media_group.call_args.kwargs['media']))

    async def test_permission_error_does_not_download(self):
        bot = AsyncMock()
        bot.send_video.side_effect = BadRequest('Chat not found')
        with patch('main.download_media') as download:
            with self.assertRaises(BadRequest):
                await main.send_post(bot, '@target', [('video', 'https://x/v')], Mock())
        download.assert_not_called()

    async def test_single_photo_skipped_video_sent(self):
        bot = AsyncMock()
        await main.send_post(bot, "@target", [("photo", "https://x/a")])
        bot.send_photo.assert_not_called()
        bot.send_media_group.assert_not_called()
        await main.send_post(bot, "@target", [("video", "https://x/v")])
        bot.send_video.assert_awaited_once()

    async def test_mixed_and_large_album(self):
        bot = AsyncMock()
        await main.send_post(bot, "@target", [("photo", "https://x/a"), ("video", "https://x/v")])
        self.assertEqual([item.type for item in bot.send_media_group.call_args.kwargs["media"]], ["photo", "video"])
        bot.reset_mock()
        await main.send_post(bot, "@target", [("photo", f"https://x/{i}") for i in range(11)])
        self.assertEqual(len(bot.send_media_group.call_args.kwargs["media"]), 10)
        bot.send_photo.assert_awaited_once()

    async def test_failure_does_not_advance_and_other_channel_continues(self):
        with tempfile.TemporaryDirectory() as folder:
            config = {"source_channels": ["a", "b"], "target_channel": "@target", "request_timeout": 30, "state_file": Path(folder) / "state.json"}
            state = {"a": 1}
            bot = AsyncMock()
            bot.send_video.side_effect = RuntimeError("send failure")
            with patch("main.fetch_posts", side_effect=[[(2, [("video", "https://x/v")], False), (3, [], False)], [(5, [("photo", "https://x/p")], False)]]):
                await main.poll_once(bot, Mock(), config, state)
            self.assertEqual(state, {"a": 1, "b": 5})
            self.assertEqual(main.load_state(config["state_file"], []), state)

    async def test_fetch_failure_isolated(self):
        with tempfile.TemporaryDirectory() as folder:
            config = {"source_channels": ["a", "b"], "target_channel": "@target", "request_timeout": 30, "state_file": Path(folder) / "state.json"}
            state = {}
            with patch("main.fetch_posts", side_effect=[requests.Timeout(), [(7, [], False)]]):
                await main.poll_once(AsyncMock(), Mock(), config, state)
            self.assertEqual(state, {"b": 7})


if __name__ == "__main__":
    unittest.main()
