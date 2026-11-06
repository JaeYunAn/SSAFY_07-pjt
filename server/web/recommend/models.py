from django.db import models


class ImageAnalysis(models.Model):
    image = models.ImageField(upload_to='uploads/')
    question = models.CharField(max_length=300, default='이 책은 어떤 책이고, 비슷한 책을 추천해줘')
    content = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class Speech(models.Model):
    text = models.TextField(max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)


class Recommendation(models.Model):
    # TODO [F701] 도서 취향을 입력받는 request_text 필드를 TextField(max_length=300) 로 정의한다.

    use_tier_routing = models.BooleanField(default=False)
    route = models.CharField(max_length=50, blank=True)
    content = models.TextField(blank=True)
    model_used = models.CharField(max_length=50, blank=True)
    image = models.ImageField(upload_to='images/', blank=True)
    score = models.IntegerField(null=True, blank=True)
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
