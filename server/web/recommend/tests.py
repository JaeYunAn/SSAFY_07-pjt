"""
Django 쪽 테스트. Proxy 서버는 띄우지 않고 requests.post 를 가짜로 바꿔 화면 흐름만 확인합니다.

실행: server/web 폴더에서 python manage.py test
"""
from django.test import TestCase
from django.urls import reverse

from .models import Recommendation


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
