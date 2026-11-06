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
    request_text = models.TextField(max_length=300)     # F701: 사용자가 입력한 도서 취향
    use_tier_routing = models.BooleanField(default=False)
    route = models.CharField(max_length=50, blank=True)
    content = models.TextField(blank=True)
    model_used = models.CharField(max_length=50, blank=True)
    image = models.ImageField(upload_to='images/', blank=True)
    score = models.IntegerField(null=True, blank=True)
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
