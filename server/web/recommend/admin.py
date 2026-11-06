from django.contrib import admin
from .models import Recommendation, ImageAnalysis, Speech

admin.site.register(Recommendation)
admin.site.register(ImageAnalysis)
admin.site.register(Speech)
