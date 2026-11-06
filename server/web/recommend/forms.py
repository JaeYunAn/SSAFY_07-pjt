from django import forms
from .models import Recommendation, ImageAnalysis, Speech


class ImageAnalysisForm(forms.ModelForm):
    ALLOWED_TYPES = ('image/png', 'image/jpeg')
    MAX_SIZE = 10 * 1024 * 1024     # 10MB

    image = forms.ImageField(
        label='책 표지 사진 (png/jpg)',
        widget=forms.ClearableFileInput(attrs={'accept': 'image/png,image/jpeg'}),
    )
    question = forms.CharField(
        label='질문',
        max_length=300,
        initial='이 책은 어떤 책이고, 비슷한 책을 추천해줘',
    )

    class Meta:
        model = ImageAnalysis
        fields = ['image', 'question']

    def clean_image(self):
        image = self.cleaned_data['image']
        # content_type 은 브라우저가 보낸 값이 아니라 Pillow 가 파일 내용으로 확인한 값이다
        if image.content_type not in self.ALLOWED_TYPES:
            raise forms.ValidationError('PNG 또는 JPG 사진만 올릴 수 있습니다.')
        if image.size > self.MAX_SIZE:
            raise forms.ValidationError('10MB 이하의 사진만 올릴 수 있습니다.')
        return image


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
    request_text = forms.CharField(
        label='읽고 싶은 책에 대해 알려주세요',
        max_length=300,     # 서버 검증과 함께 입력창의 maxlength 속성도 만들어 준다
        widget=forms.Textarea(attrs={
            'rows': 5,
            'placeholder': '예) 출퇴근길에 가볍게 읽을 성장 소설 추천해줘',
        }),
    )
    use_tier_routing = forms.BooleanField(
        label='요청 난이도에 따라 모델 자동 선택 (심화)',
        required=False,
    )

    class Meta:
        model = Recommendation
        fields = ['request_text', 'use_tier_routing']
