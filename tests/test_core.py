import unittest
from unittest.mock import patch, Mock
import kater_core

class CoreTests(unittest.TestCase):
    def result(self, content, finish="stop"):
        return Mock(json=lambda: {"choices": [{"message": {"content": content}, "finish_reason": finish}]})

    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-only"})
    @patch("kater_core.requests.post")
    def test_empty_length_retries(self, post):
        post.side_effect = [self.result("", "length"), self.result("ответ")]
        self.assertEqual(kater_core.ask_kater([], "вопрос"), "ответ")
        self.assertEqual(post.call_count, 2)

    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-only"})
    @patch("kater_core.requests.post")
    def test_empty_never_returned(self, post):
        post.return_value = self.result("", "length")
        with self.assertRaises(RuntimeError): kater_core.ask_kater([], "вопрос")
        self.assertEqual(post.call_count, 2)

    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-only"})
    @patch("kater_core.requests.post")
    def test_history_filters_empty_and_old_images(self, post):
        post.return_value = self.result("ok")
        kater_core.ask_kater([{"role":"assistant","content":""},
            {"role":"user","content":"old","image_data_url":"private"}], "new", "current")
        msgs = post.call_args.kwargs["json"]["messages"]
        self.assertEqual(msgs[1], {"role":"user","content":"old"})
        self.assertEqual(msgs[2]["content"][1]["image_url"]["url"], "current")

if __name__ == "__main__": unittest.main()
