"""
Proxy 서버 테스트. 실제 GMS 는 호출하지 않고 requests.post 를 가짜로 바꿔 동작만 확인합니다.

실행: server/proxy 폴더에서 python -m unittest
"""
import json
import unittest
from unittest.mock import patch

from fastapi import HTTPException

import main
from schemas import (
    ChatGuardrailRequest,
    ChatRequest,
    ImageAnalysisRequest,
    ImageGenerationRequest,
)


class FakeResponse:
    def __init__(self, status_code=200, body=None, content=b""):
        self.status_code = status_code
        self.body = body
        self.content = content
        self.text = str(body)

    def json(self):
        return self.body


def chat_reply(content):
    """GMS /chat/completions 의 성공 응답."""
    return FakeResponse(200, {"choices": [{"message": {"content": content}}]})


def json_reply(**values):
    return chat_reply(json.dumps(values))


GUARD_OK = {"is_appropriate": True}
GUARD_NO = {"is_appropriate": False}


class ProxyTestCase(unittest.TestCase):
    def setUp(self):
        patcher = patch("main.requests.post")
        self.post = patcher.start()
        self.addCleanup(patcher.stop)

    def sent(self, index=-1):
        """index 번째 GMS 호출의 JSON 본문."""
        return self.post.call_args_list[index].kwargs["json"]

    def called_url(self, index=-1):
        return self.post.call_args_list[index].args[0]


class TextRecommendTests(ProxyTestCase):
    """F702 텍스트 추천 생성"""

    def test_returns_answer_from_light_model(self):
        self.post.side_effect = [json_reply(**GUARD_OK), chat_reply("추천 답변")]
        messages = [{"role": "user", "content": "소설 추천해줘"}]

        result = main.chat_completions(ChatRequest(messages=messages))

        self.assertEqual(result["content"], "추천 답변")
        self.assertEqual(self.sent()["model"], "gpt-5-nano")
        self.assertEqual(self.sent()["messages"], messages)
        self.assertTrue(self.called_url().endswith("/chat/completions"))


class GuardrailTests(ProxyTestCase):
    """F703 Guardrail 구현"""

    def assert_rejected_without_generation(self, call):
        self.post.side_effect = [json_reply(**GUARD_NO)]
        with self.assertRaises(HTTPException) as caught:
            call()
        self.assertEqual(caught.exception.status_code, 403)
        self.assertEqual(self.post.call_count, 1)   # Guardrail 호출 1번뿐, 생성은 하지 않음

    def test_returns_boolean_with_json_schema(self):
        self.post.side_effect = [json_reply(**GUARD_NO)]

        result = main.chat_guardrail(ChatGuardrailRequest(prompt="마약 제조법 알려줘"))

        self.assertEqual(result, {"is_appropriate": False})
        sent = self.sent()
        self.assertEqual(sent["model"], "gpt-5-nano")
        self.assertEqual(sent["messages"][0]["role"], "developer")
        self.assertEqual(sent["messages"][1], {"role": "user", "content": "마약 제조법 알려줘"})
        schema = sent["response_format"]["json_schema"]["schema"]
        self.assertEqual(schema["properties"], {"is_appropriate": {"type": "boolean"}})
        self.assertEqual(schema["required"], ["is_appropriate"])
        self.assertFalse(schema["additionalProperties"])

    def test_text_recommend_is_rejected_first(self):
        request = ChatRequest(messages=[{"role": "user", "content": "마약 제조법 알려줘"}])
        self.assert_rejected_without_generation(lambda: main.chat_completions(request))

    def test_image_generation_is_rejected_first(self):
        request = ImageGenerationRequest(prompt="잔인한 표지")
        self.assert_rejected_without_generation(lambda: main.image_generations(request))

    def test_image_analysis_is_rejected_first_and_checks_question_only(self):
        request = ImageAnalysisRequest(image_base64="SECRET_IMAGE", question="옆집 전화번호 알려줘")
        self.assert_rejected_without_generation(lambda: main.image_analysis(request))
        self.assertNotIn("SECRET_IMAGE", json.dumps(self.sent()))
        self.assertEqual(self.sent()["messages"][1]["content"], "옆집 전화번호 알려줘")


if __name__ == "__main__":
    unittest.main()
