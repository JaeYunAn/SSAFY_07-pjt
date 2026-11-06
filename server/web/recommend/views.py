"""
화면 처리. 뷰 하나가 화면 하나를 담당합니다.

각 뷰 위에 (제공) 또는 TODO 가 적혀 있습니다.
  (제공)  — 그대로 사용합니다. 수정하지 않습니다.
  TODO   — 함수 안의 # TODO [F7xx] 아래 번호 1) 2) 3) … 순서대로 작성합니다.
           작성할 때는 위쪽의 (제공) 뷰를 그대로 따라 쓰면 됩니다.

모든 뷰가 같은 모양입니다.
  1) POST 이면 ModelForm 으로 검증, 아니면 빈 폼을 만들어 입력 화면을 보여줌
  2) payload 를 만들어 requests.post 로 Proxy 서버(FastAPI)를 호출
  3) response.status_code 를 확인 (403 → rejected.html, 200 이 아니면 error.html)   ← F706
  4) response.json() 의 값을 객체에 담아 save() 하고 결과 화면을 렌더링
"""
import base64
import uuid
import requests
from django.conf import settings
from django.core.files.base import ContentFile
from django.shortcuts import render
from .forms import RecommendationForm, ImageAnalysisForm, SpeechForm

RECOMMEND_SYSTEM_PROMPT = '''
너는 친절한 도서 추천 도우미이다. 사용자의 취향과 상황에 맞는 책을 2~3권 추천하고,
각 책마다 제목, 저자, 추천 이유를 한두 문장으로 설명한다. 한국어로 답한다.
'''


# ---------------------------------------------------------------- F701 입력 검증
def recommend_form(request):
    """입력 검증만 확인하는 화면. 검증을 통과하면 저장하고 입력값을 그대로 보여줍니다."""
    # TODO [F701]
    #   1) saved = None 으로 시작한다.
    #   2) POST 이면 form = RecommendationForm(request.POST) 를 만들고,
    #      form.is_valid() 를 통과하면 saved = form.save() 로 저장한다.
    #      (검증에 실패하면 form 에 오류 메시지가 들어 있어 같은 화면에 표시된다)
    #   3) GET 이면 form = RecommendationForm() 으로 빈 폼을 만든다.
    #   4) context = {'title': '입력 검증', 'form': form, 'saved': saved} 를 만들어
    #      render(request, 'recommend/input_form.html', context) 를 반환한다.
    pass


# ---------------------------------------------------------------- F702 텍스트 추천 (제공, F709 심화 추가)
def text_recommend(request):
    if request.method == 'POST':
        form = RecommendationForm(request.POST)
        if form.is_valid():
            result = form.save(commit=False)

            # 1) Proxy 서버에 추천 생성을 요청한다
            payload = {
                'messages': [
                    {'role': 'developer', 'content': RECOMMEND_SYSTEM_PROMPT},
                    {'role': 'user', 'content': result.request_text},
                ],
                'use_tier_routing': result.use_tier_routing,     # F710
            }
            response = requests.post(settings.PROXY_URL + '/chat/completions', json=payload, timeout=180)

            # 2) 응답 코드를 확인한다 (F706)
            if response.status_code == 403:
                context = {'user_input': result.request_text}
                return render(request, 'recommend/rejected.html', context, status=403)
            if response.status_code != 200:
                context = {'user_input': result.request_text, 'status_code': response.status_code}
                return render(request, 'recommend/error.html', context, status=503)

            # 3) 결과를 객체에 담는다
            data = response.json()
            result.content = data['content']
            result.model_used = data['model_used']               # F710 (제공)

            # TODO [F709]
            #   1) 위 payload 를 복사해 'use_tier_routing' 대신 'answer': result.content 를 넣는다.
            #   2) settings.PROXY_URL + '/chat/score' 로 requests.post 한다.
            #   3) response.status_code 가 200 이면 data = response.json() 에서
            #      result.score = data['score'], result.reason = data['reason'] 로 담는다.
            #      (화면 표시는 result_text.html 에 준비되어 있음)

            result.save()
            context = {
                'title': '텍스트 추천 생성',
                'user_input': result.request_text,
                'result': result,
            }
            return render(request, 'recommend/result_text.html', context)
    else:
        form = RecommendationForm()
    context = {
        'title': '텍스트 추천 생성',
        'form': form,
    }
    return render(request, 'recommend/input_form.html', context)


# ---------------------------------------------------------------- F704 라우트 결정 (제공)
def decide_route(request):
    if request.method == 'POST':
        form = RecommendationForm(request.POST)
        if form.is_valid():
            result = form.save(commit=False)

            payload = {'prompt': result.request_text}
            response = requests.post(settings.PROXY_URL + '/decide-route', json=payload, timeout=180)

            if response.status_code != 200:
                context = {'user_input': result.request_text, 'status_code': response.status_code}
                return render(request, 'recommend/error.html', context, status=503)

            data = response.json()
            result.route = data['route']
            result.content = f'결정된 route: {result.route}'
            result.save()
            context = {
                'title': '라우트 결정',
                'user_input': result.request_text,
                'result': result,
            }
            return render(request, 'recommend/result_text.html', context)
    else:
        form = RecommendationForm()
    context = {
        'title': '라우트 결정',
        'form': form,
    }
    return render(request, 'recommend/input_form.html', context)


# ---------------------------------------------------------------- F705 이미지 생성 (제공, F712 심화 추가)
def image_recommend(request):
    if request.method == 'POST':
        form = RecommendationForm(request.POST)
        if form.is_valid():
            result = form.save(commit=False)

            payload = {'prompt': result.request_text}
            response = requests.post(settings.PROXY_URL + '/images/generations', json=payload, timeout=180)

            if response.status_code == 403:
                context = {'user_input': result.request_text}
                return render(request, 'recommend/rejected.html', context, status=403)
            if response.status_code != 200:
                context = {'user_input': result.request_text, 'status_code': response.status_code}
                return render(request, 'recommend/error.html', context, status=503)

            data = response.json()
            image_base64 = data['image_base64']                  # jpeg 파일의 base64 문자열

            # TODO [F712]
            #   1) image_bytes = base64.b64decode(image_base64) 로 디코딩한다.
            #   2) result.image.save(f'{uuid.uuid4()}.jpg', ContentFile(image_bytes), save=False) 로 저장한다.
            #      (uuid: 겹치지 않는 파일 이름. result_image.html 은 result.image 가 있으면 그것을 먼저 보여준다)

            result.save()
            context = {
                'title': '이미지 생성',
                'result': result,
                'image_base64': image_base64,      # F705: 화면에서 data URI 로 바로 표시
            }
            return render(request, 'recommend/result_image.html', context)
    else:
        form = RecommendationForm()
    context = {
        'title': '이미지 생성',
        'form': form,
    }
    return render(request, 'recommend/input_form.html', context)


# ---------------------------------------------------------------- F707 이미지 분석 (제공)
def image_analysis(request):
    if request.method == 'POST':
        form = ImageAnalysisForm(request.POST, request.FILES)
        if form.is_valid():
            result = form.save()                       # 업로드된 사진이 media/uploads/ 에 저장됨

            # 업로드된 파일을 base64 문자열로 바꾼다
            result.image.open('rb')
            image_base64 = base64.b64encode(result.image.read()).decode('utf-8')

            payload = {'image_base64': image_base64, 'question': result.question}
            response = requests.post(settings.PROXY_URL + '/images/analysis', json=payload, timeout=180)

            if response.status_code == 403:
                context = {'user_input': result.question}
                return render(request, 'recommend/rejected.html', context, status=403)
            if response.status_code != 200:
                context = {'user_input': result.question, 'status_code': response.status_code}
                return render(request, 'recommend/error.html', context, status=503)

            data = response.json()
            result.content = data['content']
            result.save()
            context = {
                'title': '이미지 분석',
                'user_input': result.question,
                'result': result,
                'uploaded': result.image,
            }
            return render(request, 'recommend/result_text.html', context)
    else:
        form = ImageAnalysisForm()
    context = {
        'title': '이미지 분석',
        'form': form,
    }
    return render(request, 'recommend/upload_form.html', context)


# ---------------------------------------------------------------- F708 API 흐름 제어
def recommend_flow(request):
    """하나의 입력으로 라우트 결정 → 실행 → 결과 정리까지."""
    # 위의 F704, F702, F705 뷰를 이어 붙이는 모양이다.
    # TODO [F708]
    #   1) POST 이면 form = RecommendationForm(request.POST) 를 만들고,
    #      is_valid() 를 통과하면 result = form.save(commit=False)
    #   2) F704 와 같은 방법으로 '/decide-route' 를 호출해 result.route = data['route'] 를 담는다.
    #      (200 이 아니면 error.html, status=503)
    #   3) image_base64 = '' 로 두고, result.route 가 '/images/generations' 이면
    #      F705 와 같은 payload 로 '/images/generations' 를, 아니면
    #      F702 와 같은 payload 로 '/chat/completions' 를 호출한다.
    #   4) 응답 코드를 확인한다. 403 이면 rejected.html(status=403),
    #      200 이 아니면 error.html(status=503).
    #   5) data = response.json() 에서 이미지면 image_base64 = data['image_base64'] 를,
    #      아니면 result.content 와 result.model_used 를 담는다.
    #   6) result.save() 후 context 에 'title', 'result', 'image_base64' 를 담아
    #      'recommend/recommend_flow.html' 을 반환한다.
    #   7) GET 이면 빈 폼으로 'recommend/input_form.html' 을 반환한다.
    pass   # form 정의


# ---------------------------------------------------------------- F711 TTS (심화)
# 이 항목은 FastAPI 엔드포인트(generate_speech)부터 Django 화면(result_audio.html)까지
# 기능 하나를 새로 추가하는 경험입니다. Django 쪽 뷰를 직접 작성하고, 결과 템플릿(result_audio.html)에 <audio> 태그를 넣습니다.
def tts(request):
    # 위의 (제공) 뷰들과 같은 모양으로 작성한다.
    # TODO [F711]
    #   1) POST 이면 form = SpeechForm(request.POST) 를 만들고, is_valid() 를 통과하면 result = form.save()
    #   2) payload = {'text': result.text} 를 settings.PROXY_URL + '/generate-speech' 로 requests.post 한다.
    #   3) response.status_code 가 200 이 아니면 error.html 을 반환한다. (status=503)
    #   4) audio_data = response.json()['audio_data'] 를 꺼내
    #      context 에 'title', 'result', 'audio_data' 를 담아 'recommend/result_audio.html' 을 반환한다.
    #   5) GET 이면 form = SpeechForm() 으로 'recommend/input_form.html' 을 반환한다.
    pass   # form 정의
