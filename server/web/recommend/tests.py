"""
Django 쪽 테스트. Proxy 서버는 띄우지 않고 requests.post 를 가짜로 바꿔 화면 흐름만 확인합니다.

실행: server/web 폴더에서 python manage.py test
"""
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from .models import Recommendation


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
        self.post.return_value = FakeResponse(200, {'content': '데미안을 추천합니다.', 'model_used': 'gpt-5-nano'})

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
