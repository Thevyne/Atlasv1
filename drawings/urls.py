from django.urls import path

from . import views

app_name = "drawings"

urlpatterns = [
    path("upload/", views.upload_view, name="upload"),
    path("", views.home, name="home"),
    path("status/<int:drawing_id>/", views.status_view, name="status"),
    path("review/<int:drawing_id>/", views.review_rooms_view, name="review_rooms"),
    path("trace/<int:drawing_id>/", views.trace_rooms_view, name="trace_rooms"),
    path("atlas/<int:drawing_id>/",          views.atlas_view,             name="atlas"),
    path("atlas/<int:drawing_id>/api/",      views.atlas_api_view,         name="atlas_api"),
    path("atlas/<int:drawing_id>/preview/",  views.atlas_preview_view,     name="atlas_preview"),
    path("atlas/status/<str:task_id>/",      views.atlas_task_status_view, name="atlas_status"),
    path("chat/", views.chat_view, name="chat"),
    path("chat/<int:drawing_id>/", views.chat_view, name="chat_drawing"),
    path("chat/api/", views.chat_api_view, name="chat_api"),
    path("result/<int:drawing_id>/", views.result_view, name="result"),
]
