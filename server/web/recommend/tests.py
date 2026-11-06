"""
Django 쪽 테스트. Proxy 서버는 띄우지 않고 requests.post 를 가짜로 바꿔 화면 흐름만 확인합니다.

실행: server/web 폴더에서 python manage.py test
"""
import base64
import io
import shutil
import tempfile
from unittest.mock import patch

import requests
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from .models import ImageAnalysis, Recommendation

TEST_MEDIA_ROOT = tempfile.mkdtemp(prefix='recommend-test-media-')


def tearDownModule():
    shutil.rmtree(TEST_MEDIA_ROOT, ignore_errors=True)


def image_file(name='cover.png', image_format='PNG'):
    buffer = io.BytesIO()
    Image.new('RGB', (4, 4), 'navy').save(buffer, image_format)
    return SimpleUploadedFile(name, buffer.getvalue())


class FakeResponse:
    def __init__(self, status_code=200, body=None):
        self.status_code = status_code
        self.body = body or {}

    def json(self):
        return self.body


class ProxyMockTestCase(TestCase):
    """requests.post 를 가짜로 바꾼 테스트의 공통 부분."""

    def setUp(self):
        patcher = patch('recommend.views.requests.post')
        self.post = patcher.start()
        self.addCleanup(patcher.stop)

    def called_paths(self):
        return [call.args[0].rsplit('/api/v1', 1)[1] for call in self.post.call_args_list]

    def sent(self, index=-1):
        return self.post.call_args_list[index].kwargs['json']


class InputValidationTests(TestCase):
    """F701 입력 검증"""
    url_name = 'recommend:form'

    def post(self, text):
        return self.client.post(reverse(self.url_name), {'request_text': text})

    def test_get_shows_empty_form_with_maxlength(self):
        response = self.client.get(reverse(self.url_name))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'recommend/input_form.html')
        self.assertContains(response, 'maxlength="300"')

    def test_empty_value_shows_error_and_saves_nothing(self):
        for text in ('', '    '):
            response = self.post(text)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, '필수 항목입니다')
        self.assertEqual(Recommendation.objects.count(), 0)

    def test_over_300_characters_is_rejected(self):
        response = self.post('가' * 301)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].errors['request_text'])
        self.assertEqual(Recommendation.objects.count(), 0)

    def test_exactly_300_characters_is_saved(self):
        response = self.post('가' * 300)
        self.assertEqual(response.context['saved'].request_text, '가' * 300)
        self.assertEqual(Recommendation.objects.count(), 1)

    def test_valid_input_is_saved_and_shown_on_same_page(self):
        response = self.post('출퇴근길에 가볍게 읽을 성장 소설을 추천해줘')
        self.assertTemplateUsed(response, 'recommend/input_form.html')
        self.assertContains(response, '입력 검증을 통과했습니다')
        self.assertContains(response, '출퇴근길에 가볍게 읽을 성장 소설을 추천해줘')


class TextRecommendTests(ProxyMockTestCase):
    """F702 텍스트 추천 생성"""

    def test_shows_and_saves_recommendation(self):
        self.post.side_effect = [
            FakeResponse(200, {'content': '데미안을 추천합니다.', 'model_used': 'gpt-5-nano'}),
            FakeResponse(503),      # 점수 계산(F709)은 이 테스트의 관심사가 아니다
        ]

        response = self.client.post(reverse('recommend:text'), {'request_text': '성장 소설 추천해줘'})

        self.assertTemplateUsed(response, 'recommend/result_text.html')
        self.assertContains(response, '데미안을 추천합니다.')
        self.assertContains(response, 'gpt-5-nano')
        self.assertEqual(self.called_paths()[0], '/chat/completions')
        self.assertEqual(self.sent(0)['messages'][-1], {'role': 'user', 'content': '성장 소설 추천해줘'})
        self.assertEqual(Recommendation.objects.get().content, '데미안을 추천합니다.')

    def test_invalid_form_does_not_call_proxy(self):
        response = self.client.post(reverse('recommend:text'), {'request_text': ''})

        self.assertTemplateUsed(response, 'recommend/input_form.html')
        self.post.assert_not_called()


class ScoreScreenTests(ProxyMockTestCase):
    """F709 텍스트 응답 점수 계산"""
    answer = FakeResponse(200, {'content': '데미안을 추천합니다.', 'model_used': 'gpt-5-nano'})

    def recommend(self, score_response):
        self.post.side_effect = [self.answer, score_response]
        return self.client.post(reverse('recommend:text'), {'request_text': '성장 소설 추천해줘'})

    def test_score_is_saved_and_shown(self):
        response = self.recommend(FakeResponse(200, {'score': 90, 'reason': '조건을 충족합니다.'}))

        self.assertEqual(self.called_paths(), ['/chat/completions', '/chat/score'])
        self.assertEqual(self.sent(1)['answer'], '데미안을 추천합니다.')
        self.assertEqual(self.sent(1)['messages'][-1]['content'], '성장 소설 추천해줘')
        self.assertContains(response, '답변 점수 90 / 100')
        self.assertContains(response, '조건을 충족합니다.')
        saved = Recommendation.objects.get()
        self.assertEqual((saved.score, saved.reason), (90, '조건을 충족합니다.'))

    def test_score_failure_still_shows_recommendation(self):
        for failure in (FakeResponse(503), requests.Timeout('slow')):
            response = self.recommend(failure)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, '데미안을 추천합니다.')
            self.assertNotContains(response, '답변 점수')


class ModelTierScreenTests(ProxyMockTestCase):
    """F710 모델 등급 라우팅 — 체크박스 값 전달과 사용된 모델명 표시"""

    def recommend(self, **fields):
        self.post.side_effect = [
            FakeResponse(200, {'content': '답변', 'model_used': 'gpt-5-mini'}),
            FakeResponse(503),
        ]
        return self.client.post(reverse('recommend:text'), {'request_text': '에세이 추천', **fields})

    def test_checked_box_turns_on_routing_and_shows_model(self):
        response = self.recommend(use_tier_routing='on')

        self.assertIs(self.sent(0)['use_tier_routing'], True)
        self.assertContains(response, 'gpt-5-mini')

    def test_unchecked_box_keeps_routing_off(self):
        self.recommend()

        self.assertIs(self.sent(0)['use_tier_routing'], False)


class GuardrailScreenTests(ProxyMockTestCase):
    """F703 Guardrail 구현 — Proxy 가 403 을 돌려주면 거절 화면을 보여주고 저장하지 않는다"""

    def test_403_shows_rejected_page(self):
        self.post.return_value = FakeResponse(403, {'detail': 'inappropriate request'})

        response = self.client.post(reverse('recommend:text'), {'request_text': '마약 제조법 알려줘'})

        self.assertEqual(response.status_code, 403)
        self.assertTemplateUsed(response, 'recommend/rejected.html')
        self.assertContains(response, '적절한 요청이 아닙니다', status_code=403)
        self.assertEqual(Recommendation.objects.count(), 0)


class DecideRouteScreenTests(ProxyMockTestCase):
    """F704 라우트 결정"""

    def test_shows_decided_route(self):
        self.post.return_value = FakeResponse(200, {'route': '/images/generations'})

        response = self.client.post(reverse('recommend:route'), {'request_text': '표지 그려줘'})

        self.assertTemplateUsed(response, 'recommend/result_text.html')
        self.assertContains(response, '결정된 route: /images/generations')
        self.assertEqual(self.called_paths(), ['/decide-route'])
        self.assertEqual(Recommendation.objects.get().route, '/images/generations')


class ImageGenerationScreenTests(ProxyMockTestCase):
    """F705 이미지 생성 API"""

    def test_shows_image_as_data_uri(self):
        self.post.return_value = FakeResponse(200, {'image_base64': 'QUJD'})

        response = self.client.post(reverse('recommend:image'), {'request_text': '등대 표지'})

        self.assertTemplateUsed(response, 'recommend/result_image.html')
        self.assertContains(response, 'data:image/jpeg;base64,QUJD')
        self.assertEqual(self.sent(), {'prompt': '등대 표지'})


class CommonErrorScreenTests(ProxyMockTestCase):
    """F706 공통 에러 처리 — 모든 호출 화면이 같은 방식으로 안내한다"""
    text_views = ('recommend:text', 'recommend:route', 'recommend:image')

    def test_503_shows_retry_notice_with_status_code(self):
        self.post.return_value = FakeResponse(503, {'detail': 'model server error'})
        for name in self.text_views:
            response = self.client.post(reverse(name), {'request_text': '소설 추천해줘'})
            self.assertEqual(response.status_code, 503)
            self.assertTemplateUsed(response, 'recommend/error.html')
            self.assertContains(response, '잠시 후 다시 시도해 주세요', status_code=503)
            self.assertContains(response, 'Proxy 서버 응답 코드: 503', status_code=503)
        self.assertEqual(Recommendation.objects.count(), 0)

    def test_500_is_also_error_page(self):
        self.post.return_value = FakeResponse(500)

        response = self.client.post(reverse('recommend:text'), {'request_text': '소설 추천해줘'})

        self.assertContains(response, 'Proxy 서버 응답 코드: 500', status_code=503)

    def test_proxy_down_or_timeout_shows_notice_instead_of_crash(self):
        for failure in (requests.ConnectionError('down'), requests.Timeout('slow')):
            self.post.side_effect = failure
            response = self.client.post(reverse('recommend:text'), {'request_text': '소설 추천해줘'})
            self.assertTemplateUsed(response, 'recommend/error.html')
            self.assertContains(response, 'Proxy 서버에 연결하지 못했습니다', status_code=503)


class RecommendFlowTests(ProxyMockTestCase):
    """F708 API 흐름 제어"""

    def flow(self, *responses, text='소설 추천해줘'):
        self.post.side_effect = list(responses)
        return self.client.post(reverse('recommend:flow'), {'request_text': text})

    def test_text_route_runs_text_recommend(self):
        response = self.flow(
            FakeResponse(200, {'route': '/chat/completions'}),
            FakeResponse(200, {'content': '데미안을 추천합니다.', 'model_used': 'gpt-5-nano'}),
        )

        self.assertTemplateUsed(response, 'recommend/recommend_flow.html')
        self.assertContains(response, '데미안을 추천합니다.')
        self.assertEqual(self.called_paths(), ['/decide-route', '/chat/completions'])
        self.assertEqual(Recommendation.objects.get().route, '/chat/completions')

    def test_image_route_runs_image_generation(self):
        response = self.flow(
            FakeResponse(200, {'route': '/images/generations'}),
            FakeResponse(200, {'image_base64': 'QUJD'}),
        )

        self.assertTemplateUsed(response, 'recommend/recommend_flow.html')
        self.assertContains(response, 'data:image/jpeg;base64,QUJD')
        self.assertEqual(self.called_paths(), ['/decide-route', '/images/generations'])

    def test_403_goes_to_rejected_page(self):
        response = self.flow(
            FakeResponse(200, {'route': '/chat/completions'}),
            FakeResponse(403, {'detail': 'inappropriate request'}),
        )

        self.assertEqual(response.status_code, 403)
        self.assertTemplateUsed(response, 'recommend/rejected.html')
        self.assertEqual(Recommendation.objects.count(), 0)

    def test_503_while_generating_goes_to_error_page(self):
        response = self.flow(FakeResponse(200, {'route': '/images/generations'}), FakeResponse(503))

        self.assertEqual(response.status_code, 503)
        self.assertTemplateUsed(response, 'recommend/error.html')

    def test_route_failure_stops_before_generation(self):
        response = self.flow(FakeResponse(503))

        self.assertTemplateUsed(response, 'recommend/error.html')
        self.assertEqual(self.called_paths(), ['/decide-route'])

    def test_django_never_calls_guardrail_directly(self):
        self.flow(
            FakeResponse(200, {'route': '/chat/completions'}),
            FakeResponse(200, {'content': '답변', 'model_used': 'gpt-5-nano'}),
        )

        self.assertNotIn('/chat/guardrail', self.called_paths())

    def test_get_shows_one_input_form(self):
        response = self.client.get(reverse('recommend:flow'))

        self.assertTemplateUsed(response, 'recommend/input_form.html')
        self.post.assert_not_called()


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class ImageAnalysisScreenTests(ProxyMockTestCase):
    """F707 이미지 분석 구현"""

    def post_cover(self, cover, question='어떤 책일까?'):
        return self.client.post(reverse('recommend:analyze'), {'image': cover, 'question': question})

    def test_sends_base64_and_shows_result(self):
        self.post.return_value = FakeResponse(200, {'content': '해양 소설로 보입니다.'})
        cover = image_file('cover.jpg', 'JPEG')
        original = cover.read()
        cover.seek(0)

        response = self.post_cover(cover)

        self.assertTemplateUsed(response, 'recommend/result_text.html')
        self.assertContains(response, '해양 소설로 보입니다.')
        sent = self.sent()
        self.assertEqual(base64.b64decode(sent['image_base64']), original)
        self.assertEqual(sent['mime_type'], 'image/jpeg')
        self.assertEqual(sent['question'], '어떤 책일까?')
        saved = ImageAnalysis.objects.get()
        self.assertEqual(saved.content, '해양 소설로 보입니다.')
        self.assertEqual(saved.image.read(), original)
        self.assertContains(response, saved.image.url)

    def test_rejected_upload_is_not_kept(self):
        self.post.return_value = FakeResponse(403)

        response = self.post_cover(image_file())

        self.assertTemplateUsed(response, 'recommend/rejected.html')
        self.assertEqual(ImageAnalysis.objects.count(), 0)

    def test_non_image_and_unsupported_format_are_blocked_before_proxy(self):
        not_image = SimpleUploadedFile('cover.png', b'this is not an image')
        response = self.post_cover(not_image)
        self.assertTrue(response.context['form'].errors['image'])

        response = self.post_cover(image_file('cover.gif', 'GIF'))
        self.assertIn('PNG 또는 JPG', response.context['form'].errors['image'][0])

        self.post.assert_not_called()

    def test_missing_file_shows_error(self):
        response = self.client.post(reverse('recommend:analyze'), {'question': '어떤 책일까?'})

        self.assertTemplateUsed(response, 'recommend/upload_form.html')
        self.assertContains(response, '필수 항목입니다')
