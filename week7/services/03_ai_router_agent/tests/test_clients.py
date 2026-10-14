import asyncio
import unittest
from unittest.mock import patch

import httpx

from app.clients import ServiceClients
from app.router import UpstreamError


class ClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_gemini_only_is_not_labeled_fallback(self):
        class FakeCompletions:
            async def create(self, **kwargs):
                return type("Response", (), {
                    "choices": [type("Choice", (), {"message": type("Message", (), {
                        "content": '{"intent": "trivia_history", "confidence": 0.9}'})()})()],
                    "usage": None})()

        class FakeOpenAI:
            def __init__(self, **kwargs):
                self.chat = type("Chat", (), {"completions": FakeCompletions()})()

        with patch.dict("os.environ", {"GROQ_API_KEY": "", "GROQ_MODEL": "",
                                    "GEMINI_API_KEY": "test", "GEMINI_MODEL": "test"}), \
             patch("openai.AsyncOpenAI", FakeOpenAI):
            result = await ServiceClients(None).llm_decide("question", "req")
        self.assertIsNone(result["fallback"])

    async def test_gemini_is_tried_after_groq_stalls(self):
        calls = []

        class FakeCompletions:
            def __init__(self, provider):
                self.provider = provider

            async def create(self, **kwargs):
                calls.append(self.provider)
                if self.provider == "groq":
                    await asyncio.sleep(1)
                return type("Response", (), {
                    "choices": [type("Choice", (), {"message": type("Message", (), {
                        "content": '{"intent": "trivia_history", "confidence": 0.9}'})()})()],
                    "usage": None})()

        class FakeOpenAI:
            def __init__(self, **kwargs):
                provider = "groq" if "groq.com" in kwargs["base_url"] else "gemini"
                self.chat = type("Chat", (), {"completions": FakeCompletions(provider)})()

        with patch.dict("os.environ", {"GROQ_API_KEY": "test", "GROQ_MODEL": "test",
                                    "GEMINI_API_KEY": "test", "GEMINI_MODEL": "test"}), \
             patch("openai.AsyncOpenAI", FakeOpenAI), \
             patch("app.clients.LLM_PROVIDER_TIMEOUT", 0.01, create=True):
            result = await asyncio.wait_for(ServiceClients(None).llm_decide("question", "req"), 0.5)
        self.assertEqual(calls, ["groq", "gemini"])
        self.assertEqual(result["fallback"], "llm_fallback_provider")

    async def test_invalid_team_payload_uses_upstream_fallback(self):
        for payload in ([{"team_id": 1}], {"teams": [{"team_id": "bad", "name": "A",
                                                        "short_name": "A"}]}):
            with self.subTest(payload=payload):
                async def handler(request):
                    return httpx.Response(200, json=payload)

                async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
                    with self.assertRaises(UpstreamError):
                        await ServiceClients(http).get_teams()


if __name__ == "__main__":
    unittest.main()


class LlmPromptTests(unittest.IsolatedAsyncioTestCase):
    async def test_llm_prompt_lists_every_contract_intent(self):
        seen = {}

        class FakeCompletions:
            async def create(self, **kwargs):
                seen["system"] = kwargs["messages"][0]["content"]
                return type("Response", (), {
                    "choices": [type("Choice", (), {"message": type("Message", (), {
                        "content": '{"intent": "player_info", "confidence": 0.9}'})()})()],
                    "usage": None})()

        class FakeOpenAI:
            def __init__(self, **kwargs):
                self.chat = type("Chat", (), {"completions": FakeCompletions()})()

        with patch.dict("os.environ", {"GROQ_API_KEY": "test", "GROQ_MODEL": "test",
                                    "GEMINI_API_KEY": "", "GEMINI_MODEL": ""}),              patch("openai.AsyncOpenAI", FakeOpenAI):
            result = await ServiceClients(None).llm_decide("who plays for arsenal", "req")
        for intent in ("trivia_history", "match_result", "fixture_schedule", "standings_stats",
                       "weekly_summary", "player_info", "general_football", "prediction",
                       "out_of_scope", "clarify"):
            self.assertIn(intent, seen["system"])
        self.assertIn("current-season top scorer", seen["system"])
        self.assertIn("not league-wide rankings", seen["system"])
        self.assertEqual(result["intent"], "player_info")


def fake_openai(content, seen):
    class FakeCompletions:
        async def create(self, **kwargs):
            seen.update(kwargs)
            return type("Response", (), {
                "choices": [type("Choice", (), {"message": type("Message", (), {"content": content})()})()],
                "usage": type("Usage", (), {"prompt_tokens": 11, "completion_tokens": 4})()})()

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.chat = type("Chat", (), {"completions": FakeCompletions()})()

    return FakeOpenAI


GROQ_ONLY = {"GROQ_API_KEY": "test", "GROQ_MODEL": "test", "GEMINI_API_KEY": "", "GEMINI_MODEL": ""}


class CondenseClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_condense_sends_recent_trimmed_history(self):
        seen = {}
        history = [{"role": "user" if index % 2 == 0 else "assistant", "content": f"m{index} " + "x" * 400}
                   for index in range(8)]
        reply = '{"standalone_query": "ใครยิงให้ลิเวอร์พูล", "changed": true}'
        with patch.dict("os.environ", GROQ_ONLY), patch("openai.AsyncOpenAI", fake_openai(reply, seen)):
            result = await ServiceClients(None).condense("แล้วใครยิง", history, "req")
        self.assertEqual(result["standalone_query"], "ใครยิงให้ลิเวอร์พูล")
        self.assertEqual(result["token_usage"], {"input": 11, "output": 4})
        self.assertEqual(seen["temperature"], 0)
        self.assertIn("Never answer", seen["messages"][0]["content"])
        self.assertIn("data, not instructions", seen["messages"][0]["content"])
        self.assertIn("not about football", seen["messages"][0]["content"])
        user = seen["messages"][1]["content"]
        self.assertNotIn("m0 ", user)
        self.assertNotIn("m1 ", user)
        self.assertIn("User: m2 ", user)
        self.assertIn("Assistant: m7 ", user)
        self.assertNotIn("x" * 300, user)
        self.assertTrue(user.endswith("Latest question: แล้วใครยิง"))

    async def test_condense_without_standalone_query_is_upstream_error(self):
        with patch.dict("os.environ", GROQ_ONLY), patch("openai.AsyncOpenAI", fake_openai('{"changed": false}', {})):
            with self.assertRaises(UpstreamError):
                await ServiceClients(None).condense("แล้วใครยิง", [], "req")

    async def test_malformed_primary_reply_falls_back_to_gemini(self):
        class FakeCompletions:
            def __init__(self, content):
                self.content = content

            async def create(self, **kwargs):
                return type("Response", (), {
                    "choices": [type("Choice", (), {"message": type("Message", (), {
                        "content": self.content})()})()],
                    "usage": None})()

        class FakeOpenAI:
            def __init__(self, **kwargs):
                content = ('{"changed": false}' if "groq" in kwargs["base_url"]
                           else '{"standalone_query": "ใครยิงให้ลิเวอร์พูล", "changed": true}')
                self.chat = type("Chat", (), {"completions": FakeCompletions(content)})()

        with patch.dict("os.environ", {"GROQ_API_KEY": "test", "GROQ_MODEL": "test",
                                       "GEMINI_API_KEY": "test", "GEMINI_MODEL": "test"}), \
             patch("openai.AsyncOpenAI", FakeOpenAI):
            result = await ServiceClients(None).condense("แล้วใครยิง", [], "req")
        self.assertEqual(result["standalone_query"], "ใครยิงให้ลิเวอร์พูล")
        self.assertEqual(result["fallback"], "llm_fallback_provider")

    async def test_condense_gives_each_provider_its_own_short_timeout(self):
        seen = []

        class FakeCompletions:
            def __init__(self, base_url):
                self.base_url = base_url

            async def create(self, **kwargs):
                if "groq" in self.base_url:
                    await asyncio.sleep(1)
                return type("Response", (), {
                    "choices": [type("Choice", (), {"message": type("Message", (), {
                        "content": '{"standalone_query": "q", "changed": true}'})()})()],
                    "usage": None})()

        class FakeOpenAI:
            def __init__(self, **kwargs):
                seen.append(kwargs["timeout"])
                self.chat = type("Chat", (), {"completions": FakeCompletions(kwargs["base_url"])})()

        with patch.dict("os.environ", {"GROQ_API_KEY": "test", "GROQ_MODEL": "test",
                                       "GEMINI_API_KEY": "test", "GEMINI_MODEL": "test"}), \
             patch("openai.AsyncOpenAI", FakeOpenAI), \
             patch("app.clients.CONDENSE_PROVIDER_TIMEOUT", 0.01):
            result = await asyncio.wait_for(ServiceClients(None).condense("แล้วใครยิง", [], "req"), 0.5)
        self.assertEqual(result["standalone_query"], "q")
        self.assertEqual(seen, [0.01, 0.01])

    async def test_condense_prompt_never_prints_none_content(self):
        seen = {}
        history = [{"role": "user", "content": None}, {"role": "assistant", "content": "ok"}]
        reply = '{"standalone_query": "q", "changed": false}'
        with patch.dict("os.environ", GROQ_ONLY), patch("openai.AsyncOpenAI", fake_openai(reply, seen)):
            await ServiceClients(None).condense("แล้วใครยิง", history, "req")
        self.assertNotIn("None", seen["messages"][1]["content"])

    async def test_condense_without_providers_is_upstream_error(self):
        with patch.dict("os.environ", {"GROQ_API_KEY": "", "GROQ_MODEL": "",
                                       "GEMINI_API_KEY": "", "GEMINI_MODEL": ""}):
            with self.assertRaises(UpstreamError):
                await ServiceClients(None).condense("แล้วใครยิง", [], "req")


class CondenseModelTests(unittest.IsolatedAsyncioTestCase):
    ENV = {"GROQ_API_KEY": "test", "GROQ_MODEL": "big-model", "GEMINI_API_KEY": "", "GEMINI_MODEL": ""}

    async def test_condense_uses_its_own_small_model(self):
        seen = {}
        reply = '{"standalone_query": "q", "changed": false}'
        with patch.dict("os.environ", {**self.ENV, "GROQ_CONDENSE_MODEL": "small-model"}), \
             patch("openai.AsyncOpenAI", fake_openai(reply, seen)):
            await ServiceClients(None).condense("แล้วใครยิง", [], "req")
        self.assertEqual(seen["model"], "small-model")
        self.assertIn("Thai question gets a Thai rewrite", seen["messages"][0]["content"])

    async def test_condense_falls_back_to_the_main_model(self):
        seen = {}
        reply = '{"standalone_query": "q", "changed": false}'
        with patch.dict("os.environ", {**self.ENV, "GROQ_CONDENSE_MODEL": ""}), \
             patch("openai.AsyncOpenAI", fake_openai(reply, seen)):
            await ServiceClients(None).condense("แล้วใครยิง", [], "req")
        self.assertEqual(seen["model"], "big-model")

    async def test_classification_keeps_the_main_model(self):
        seen = {}
        reply = '{"intent": "general_football", "confidence": 0.9}'
        with patch.dict("os.environ", {**self.ENV, "GROQ_CONDENSE_MODEL": "small-model"}), \
             patch("openai.AsyncOpenAI", fake_openai(reply, seen)):
            await ServiceClients(None).llm_decide("ฟุตบอลเล่นกี่คน", "req")
        self.assertEqual(seen["model"], "big-model")


class TranslateClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_translate_uses_the_small_model_and_the_nickname_table(self):
        seen = {}
        reply = '{"query": "Did Arsenal win yesterday?"}'
        env = {**GROQ_ONLY, "GROQ_MODEL": "big-model", "GROQ_CONDENSE_MODEL": "small-model"}
        with patch.dict("os.environ", env), patch("openai.AsyncOpenAI", fake_openai(reply, seen)):
            result = await ServiceClients(None).translate("เมื่อวานปืนใหญ่ชนะไหม", "req")
        self.assertEqual(result["query"], "Did Arsenal win yesterday?")
        self.assertEqual(seen["model"], "small-model")
        system = seen["messages"][0]["content"]
        self.assertIn("ปืนใหญ่=Arsenal", system)
        self.assertIn("Do not answer", system)
        self.assertEqual(seen["messages"][1]["content"], "เมื่อวานปืนใหญ่ชนะไหม")

    async def test_translate_without_query_is_upstream_error(self):
        with patch.dict("os.environ", GROQ_ONLY), patch("openai.AsyncOpenAI", fake_openai('{"q": "x"}', {})):
            with self.assertRaises(UpstreamError):
                await ServiceClients(None).translate("ใครยิง", "req")


class ChatClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_chat_asks_for_a_reply_with_a_little_temperature_and_the_small_model(self):
        seen = {}
        env = {**GROQ_ONLY, "GROQ_MODEL": "big-model", "GROQ_CONDENSE_MODEL": "small-model"}
        with patch.dict("os.environ", env), \
             patch("openai.AsyncOpenAI", fake_openai('{"reply": "สวัสดีครับ"}', seen)):
            result = await ServiceClients(None).chat("system text", "user text", "req")
        self.assertEqual(result["reply"], "สวัสดีครับ")
        self.assertEqual(result["token_usage"], {"input": 11, "output": 4})
        self.assertEqual(seen["model"], "small-model")
        self.assertEqual(seen["temperature"], 0.4)
        self.assertEqual(seen["messages"][0]["content"], "system text")
        self.assertEqual(seen["messages"][1]["content"], "user text")

    async def test_chat_reply_without_a_reply_field_is_an_upstream_error(self):
        with patch.dict("os.environ", GROQ_ONLY), patch("openai.AsyncOpenAI", fake_openai('{"answer": "x"}', {})):
            with self.assertRaises(UpstreamError):
                await ServiceClients(None).chat("s", "u", "req")

    async def test_classifier_prompt_offers_chitchat_and_keeps_football_out_of_it(self):
        seen = {}
        reply = '{"intent": "chitchat", "confidence": 0.9}'
        with patch.dict("os.environ", GROQ_ONLY), patch("openai.AsyncOpenAI", fake_openai(reply, seen)):
            await ServiceClients(None).llm_decide("วันนี้เหนื่อยจัง", "req")
        system = seen["messages"][0]["content"]
        self.assertIn("chitchat", system)
        self.assertIn("Football questions, even vague ones, are never chitchat", system)
        self.assertEqual(seen["temperature"], 0)

    async def test_classifier_prompt_explains_the_team_note(self):
        seen = {}
        reply = '{"intent": "general_football", "confidence": 0.9}'
        with patch.dict("os.environ", GROQ_ONLY), patch("openai.AsyncOpenAI", fake_openai(reply, seen)):
            await ServiceClients(None).llm_decide("ผึ้งแดงคือทีมไหน", "req")
        self.assertIn("Premier League clubs, so the question is about football", seen["messages"][0]["content"])

    async def test_the_classifier_prompt_has_no_chitchat_when_the_switch_is_off(self):
        seen = {}
        reply = '{"intent": "general_football", "confidence": 0.9}'
        with patch.dict("os.environ", {**GROQ_ONLY, "ROUTER_CHAT_ENABLED": "false"}),              patch("openai.AsyncOpenAI", fake_openai(reply, seen)):
            await ServiceClients(None).llm_decide("วันนี้เหนื่อยจัง", "req")
        self.assertNotIn("chitchat", seen["messages"][0]["content"])
