from django import forms
from .models import Recommendation, ImageAnalysis, Speech


class ImageAnalysisForm(forms.ModelForm):
    image = forms.ImageField(label='책 표지 사진 (png/jpg)')
    question = forms.CharField(
        label='질문',
        max_length=300,
        initial='이 책은 어떤 책이고, 비슷한 책을 추천해줘',
    )

    class Meta:
        model = ImageAnalysis
        fields = ['image', 'question']


class SpeechForm(forms.ModelForm):
    text = forms.CharField(
        label='음성으로 들을 텍스트',
        max_length=2000,
        widget=forms.Textarea(attrs={'rows': 6}),
    )

    class Meta:
        model = Speech
        fields = ['text']


class RecommendationForm(forms.ModelForm):
    # TODO [F701]
    #   1) 아래 use_tier_routing 처럼 request_text 입력 필드를 선언한다.
    #      forms.CharField(label='읽고 싶은 책에 대해 알려주세요', max_length=300,
    #                      widget=forms.Textarea(attrs={
    #                          'rows': 5,
    #                          'placeholder': '예) 출퇴근길에 가볍게 읽을 성장 소설 추천해줘'}))

    use_tier_routing = forms.BooleanField(
        label='요청 난이도에 따라 모델 자동 선택 (심화)',
        required=False,
    )

    class Meta:
        model = Recommendation
        # TODO [F701]
        #   1) fields 에 'request_text' 를 추가한다.
        fields = ['use_tier_routing']
