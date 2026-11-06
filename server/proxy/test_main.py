"""
Proxy 서버 테스트. 실제 GMS 는 호출하지 않고 requests.post 를 가짜로 바꿔 동작만 확인합니다.

실행: server/proxy 폴더에서 python -m unittest
"""
import unittest
from unittest.mock import patch

import main
from schemas import ChatRequest


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
        self.post.side_effect = [chat_reply("추천 답변")]
        messages = [{"role": "user", "content": "소설 추천해줘"}]

        result = main.chat_completions(ChatRequest(messages=messages))

        self.assertEqual(result["content"], "추천 답변")
        self.assertEqual(self.sent()["model"], "gpt-5-nano")
        self.assertEqual(self.sent()["messages"], messages)
        self.assertTrue(self.called_url().endswith("/chat/completions"))


if __name__ == "__main__":
    unittest.main()
