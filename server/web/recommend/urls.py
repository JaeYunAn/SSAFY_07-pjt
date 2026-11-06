from django.urls import path
from . import views

app_name = 'recommend'
urlpatterns = [
    path('', views.recommend_form, name='form'),            # F701
    path('text/', views.text_recommend, name='text'),       # F702, F709, F710
    path('route/', views.decide_route, name='route'),       # F704
    path('image/', views.image_recommend, name='image'),    # F705, F712
    path('analyze/', views.image_analysis, name='analyze'), # F707
    path('flow/', views.recommend_flow, name='flow'),       # F708
    path('tts/', views.tts, name='tts'),                    # F711
]
