"""요청/응답의 모양. main.py 가 이 모양대로 JSON 을 검사합니다."""
from pydantic import BaseModel, Field


# F702 텍스트 추천 / F710 모델 등급 라우팅
class ChatRequest(BaseModel):
    messages: list[dict] = Field(min_length=1)  # [{"role": "user", "content": "..."}, ...]
    use_tier_routing: bool = False  # F710: True 면 요청 난이도에 따라 모델을 고름


class ChatResponse(BaseModel):
    content: str
    model_used: str = ""


# F703 Guardrail
class ChatGuardrailRequest(BaseModel):
    prompt: str


class ChatGuardrailResponse(BaseModel):
    is_appropriate: bool


# F704 라우트 결정
class DecideRouteRequest(BaseModel):
    prompt: str


class DecideRouteResponse(BaseModel):
    route: str


# F705 이미지 생성 (Django 는 이 base64 를 F705 에서는 화면에 바로, F712 에서는 media 파일로 저장해 사용)
class ImageGenerationRequest(BaseModel):
    prompt: str


class ImageGenerationResponse(BaseModel):
    image_base64: str               # jpeg 파일을 base64 로 인코딩한 문자열


# F707 이미지 분석
class ImageAnalysisRequest(BaseModel):
    image_base64: str               # /docs 에서는 직접 넣기 어려우므로 웹 화면(F707)에서 확인
    question: str
    mime_type: str = "image/png"    # data URI 에 쓰는 이미지 형식 (jpg 업로드면 image/jpeg)


class ImageAnalysisResponse(BaseModel):
    content: str


# F709 텍스트 응답 점수 계산
class ChatScoreRequest(BaseModel):
    messages: list[dict]
    answer: str


class ChatScoreResponse(BaseModel):
    score: int
    reason: str


# F711 TTS
class GenerateSpeechRequest(BaseModel):
    text: str


class GenerateSpeechResponse(BaseModel):
    audio_data: str
