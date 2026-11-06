"""
Proxy 서버 테스트. 실제 GMS 는 호출하지 않고 requests.post 를 가짜로 바꿔 동작만 확인합니다.

실행: server/proxy 폴더에서 python -m unittest
"""
import base64
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import requests
from fastapi import HTTPException

import main
from schemas import (
    ChatGuardrailRequest,
    ChatRequest,
    ChatScoreRequest,
    DecideRouteRequest,
    GenerateSpeechRequest,
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


class ApiKeyTests(ProxyTestCase):
    """NF702 API Key 관리"""
    project_root = Path(main.__file__).resolve().parents[2]

    def test_key_is_read_from_environment_and_sent_only_to_gms(self):
        self.assertIn('os.getenv("GMS_KEY")', Path(main.__file__).read_text(encoding="utf-8"))
        self.post.return_value = FakeResponse(200, {})

        main.gms_post("/chat/completions", {})

        self.assertEqual(self.post.call_args.kwargs["headers"], main.HEADERS)
        self.assertEqual(main.HEADERS["Authorization"], f"Bearer {main.GMS_KEY}")

    def test_env_file_is_ignored_and_example_has_no_real_key(self):
        ignore_rules = (self.project_root / ".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertIn(".env", ignore_rules)
        example = (Path(main.__file__).parent / ".env.example").read_text(encoding="utf-8")
        self.assertIn("GMS_KEY=여기에_GMS_키", example)

    def test_real_key_never_appears_in_source_files(self):
        if not main.GMS_KEY:
            self.skipTest("이 환경에는 GMS_KEY 가 없음")
        sources = [
            path for path in (self.project_root / "server").rglob("*")
            if path.is_file()
            and path.name != ".env"
            and path.suffix in {".py", ".html", ".css", ".js", ".txt", ".md", ".example", ".sample"}
        ]
        self.assertTrue(sources)
        for path in sources:
            self.assertNotIn(main.GMS_KEY, path.read_text(encoding="utf-8"), path)


class TimeoutTests(ProxyTestCase):
    """NF704 호출 시간 제한 — FastAPI → GMS 는 120초"""

    def test_every_gms_call_has_timeout(self):
        self.post.side_effect = [
            json_reply(**GUARD_OK),
            json_reply(tier="simple"),
            chat_reply("추천 답변"),
            json_reply(route="/chat/completions"),
            FakeResponse(200, content=b"mp3-bytes"),
        ]
        messages = [{"role": "user", "content": "소설 추천해줘"}]

        main.chat_completions(ChatRequest(messages=messages, use_tier_routing=True))
        main.decide_route(DecideRouteRequest(prompt="소설 추천해줘"))
        main.generate_speech(GenerateSpeechRequest(text="문장"))

        self.assertEqual(self.post.call_count, 5)
        for call in self.post.call_args_list:
            self.assertEqual(call.kwargs["timeout"], 120)


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


class DecideRouteTests(ProxyTestCase):
    """F704 라우트 결정"""

    def test_returns_route_limited_by_enum(self):
        self.post.side_effect = [json_reply(route="/images/generations")]

        result = main.decide_route(DecideRouteRequest(prompt="표지 그려줘"))

        self.assertEqual(result, {"route": "/images/generations"})
        schema = self.sent()["response_format"]["json_schema"]["schema"]
        self.assertEqual(schema["properties"]["route"]["enum"], ["/chat/completions", "/images/generations"])
        self.assertEqual(self.post.call_count, 1)   # Guardrail 은 생성 API 안에서만 실행한다


class ImageGenerationTests(ProxyTestCase):
    """F705 이미지 생성 API"""

    def test_returns_base64_after_guardrail(self):
        self.post.side_effect = [
            json_reply(**GUARD_OK),
            FakeResponse(200, {"data": [{"b64_json": "QUJD"}]}),
        ]

        result = main.image_generations(ImageGenerationRequest(prompt="등대 표지"))

        self.assertEqual(result, {"image_base64": "QUJD"})
        self.assertTrue(self.called_url().endswith("/images/generations"))
        sent = self.sent()
        self.assertEqual(sent["model"], "gpt-image-1-mini")
        self.assertIn("등대 표지", sent["prompt"])
        self.assertEqual(
            (sent["size"], sent["quality"], sent["output_format"]),
            ("1024x1024", "low", "jpeg"),
        )


class CommonErrorTests(ProxyTestCase):
    """F706 공통 에러 처리"""

    def assert_model_server_error(self, call):
        with self.assertRaises(HTTPException) as caught:
            call()
        self.assertEqual(caught.exception.status_code, 503)
        self.assertEqual(caught.exception.detail, "model server error")

    def test_non_200_becomes_503(self):
        self.post.return_value = FakeResponse(401, {"error": "invalid key"})
        self.assert_model_server_error(lambda: main.gms_post("/chat/completions", {}))

    def test_timeout_and_connection_failure_become_503(self):
        for failure in (requests.Timeout("slow"), requests.ConnectionError("down")):
            self.post.side_effect = failure
            self.assert_model_server_error(lambda: main.gms_post("/chat/completions", {}))

    def test_guardrail_failure_blocks_generation(self):
        """Guardrail 판단이 실패하면 안전을 위해 생성하지 않고 503 을 돌려준다."""
        self.post.return_value = FakeResponse(500, {"error": "down"})
        request = ChatRequest(messages=[{"role": "user", "content": "소설 추천해줘"}])

        self.assert_model_server_error(lambda: main.chat_completions(request))
        self.assertEqual(self.post.call_count, 1)

    def test_broken_guardrail_answer_blocks_generation(self):
        self.post.return_value = chat_reply('{"is_appropriate": tr')
        request = ImageGenerationRequest(prompt="표지")

        self.assert_model_server_error(lambda: main.image_generations(request))
        self.assertEqual(self.post.call_count, 1)

    def test_empty_answer_becomes_503(self):
        self.post.side_effect = [json_reply(**GUARD_OK), chat_reply(None)]
        request = ChatRequest(messages=[{"role": "user", "content": "소설 추천해줘"}])

        self.assert_model_server_error(lambda: main.chat_completions(request))

    def test_model_refusal_is_inappropriate(self):
        refusal = FakeResponse(200, {"choices": [{"message": {"content": None, "refusal": "거부"}}]})
        self.post.return_value = refusal

        result = main.chat_guardrail(ChatGuardrailRequest(prompt="부적절한 요청"))

        self.assertEqual(result, {"is_appropriate": False})


class ImageAnalysisTests(ProxyTestCase):
    """F707 이미지 분석 구현"""

    def test_sends_image_and_question_together(self):
        self.post.side_effect = [json_reply(**GUARD_OK), chat_reply("장르는 해양 소설입니다.")]
        request = ImageAnalysisRequest(image_base64="QUJD", question="어떤 책일까?", mime_type="image/jpeg")

        result = main.image_analysis(request)

        self.assertEqual(result, {"content": "장르는 해양 소설입니다."})
        sent = self.sent()
        self.assertEqual(sent["model"], "gpt-5-nano")
        self.assertEqual(sent["messages"][0]["role"], "developer")
        self.assertIn("표지", sent["messages"][0]["content"])
        image_part, text_part = sent["messages"][1]["content"]
        self.assertEqual(image_part, {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,QUJD"}})
        self.assertEqual(text_part, {"type": "text", "text": "어떤 책일까?"})


class ScoreTests(ProxyTestCase):
    """F709 텍스트 응답 점수 계산"""
    messages = [
        {"role": "developer", "content": "추천 지시문"},
        {"role": "user", "content": "성장 소설 추천해줘"},
    ]

    def score(self, **reply):
        self.post.side_effect = [json_reply(**reply)]
        return main.chat_score(ChatScoreRequest(messages=self.messages, answer="데미안을 추천합니다."))

    def test_returns_score_and_reason_as_json(self):
        result = self.score(score=90, reason="조건을 충족합니다.")

        self.assertEqual(result, {"score": 90, "reason": "조건을 충족합니다."})
        sent = self.sent()
        self.assertEqual(sent["model"], "gpt-5-nano")
        properties = sent["response_format"]["json_schema"]["schema"]["properties"]
        self.assertEqual(properties["score"], {"type": "integer"})
        self.assertEqual(properties["reason"], {"type": "string"})

    def test_sends_request_and_answer_without_recommend_instruction(self):
        self.score(score=90, reason="이유")

        contents = [message["content"] for message in self.sent()["messages"]]
        self.assertIn("성장 소설 추천해줘", contents)
        self.assertIn("답변: 데미안을 추천합니다.", contents)
        self.assertNotIn("추천 지시문", contents)

    def test_score_is_kept_between_0_and_100(self):
        self.assertEqual(self.score(score=130, reason="이유")["score"], 100)
        self.assertEqual(self.score(score=-5, reason="이유")["score"], 0)


class ModelTierTests(ProxyTestCase):
    """F710 모델 등급 라우팅"""
    messages = [{"role": "user", "content": "비 오는 날 읽기 좋은, 위로가 되는 에세이"}]

    def recommend(self, *replies, use_tier_routing=True):
        self.post.side_effect = [json_reply(**GUARD_OK), *replies, chat_reply("추천 답변")]
        request = ChatRequest(messages=self.messages, use_tier_routing=use_tier_routing)
        return main.chat_completions(request)

    def test_complex_request_uses_mini(self):
        result = self.recommend(json_reply(tier="complex"))

        self.assertEqual(result["model_used"], "gpt-5-mini")
        self.assertEqual(self.sent(-1)["model"], "gpt-5-mini")
        self.assertEqual(self.sent(1)["model"], "gpt-5-nano")   # 판단 자체는 nano 가 맡는다
        tier = self.sent(1)["response_format"]["json_schema"]["schema"]["properties"]["tier"]
        self.assertEqual(tier["enum"], ["simple", "complex"])

    def test_simple_request_uses_nano(self):
        result = self.recommend(json_reply(tier="simple"))

        self.assertEqual(result["model_used"], "gpt-5-nano")
        self.assertEqual(self.sent(-1)["model"], "gpt-5-nano")

    def test_routing_off_skips_tier_decision(self):
        result = self.recommend(use_tier_routing=False)

        self.assertEqual(result["model_used"], "gpt-5-nano")
        self.assertEqual(self.post.call_count, 2)   # Guardrail + 생성


class SpeechTests(ProxyTestCase):
    """F711 TTS 기능 구현"""

    def test_returns_audio_bytes_as_base64(self):
        self.post.return_value = FakeResponse(200, content=b"mp3-bytes")

        result = main.generate_speech(GenerateSpeechRequest(text="데미안을 추천합니다."))

        self.assertEqual(result["audio_data"], base64.b64encode(b"mp3-bytes").decode())
        self.assertTrue(self.called_url().endswith("/audio/speech"))
        self.assertEqual(
            self.sent(),
            {"model": "gpt-4o-mini-tts", "input": "데미안을 추천합니다.", "voice": "nova", "response_format": "mp3"},
        )
        self.assertEqual(self.post.call_count, 1)   # Guardrail 대상이 아니다

    def test_failure_becomes_503(self):
        self.post.return_value = FakeResponse(500, {"error": "down"})

        with self.assertRaises(HTTPException) as caught:
            main.generate_speech(GenerateSpeechRequest(text="문장"))
        self.assertEqual(caught.exception.status_code, 503)


if __name__ == "__main__":
    unittest.main()
