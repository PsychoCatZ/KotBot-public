import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from conversation import ConversationService

class ConversationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name)/"test.db")
        self.a = ConversationService(self.path)
        self.b = ConversationService(self.path)
    def tearDown(self): self.tmp.cleanup()

    @patch("conversation.ask_kater")
    def test_shared_pair_image_and_clear(self, ask):
        ask.return_value = "reply"
        self.a.respond(1,"hello","image")
        self.b.respond(1,"next")
        self.assertEqual(len(ask.call_args.args[0]),2)
        self.assertEqual(self.b.load_history(1)[0]["image_data_url"],"image")
        self.a.clear_history(1)
        self.assertEqual(self.b.load_history(1),[])

    @patch("conversation.ask_kater", side_effect=RuntimeError("failed"))
    def test_failure_no_partial_write(self, ask):
        with self.assertRaises(RuntimeError): self.a.respond(1,"hello")
        self.assertEqual(self.a.load_history(1),[])

    @patch("conversation.ask_kater", return_value="reply")
    def test_simultaneous_turns_and_limit(self, ask):
        self.a.load_history(1)
        with ThreadPoolExecutor(2) as pool:
            list(pool.map(lambda n: (self.a if n%2 else self.b).respond(1,str(n)),range(12)))
        rows = self.a.load_history(1)
        self.assertEqual(len(rows),20)
        self.assertEqual([r["role"] for r in rows],["user","assistant"]*10)
        self.assertEqual(len(ask.call_args.args[0]),20)
