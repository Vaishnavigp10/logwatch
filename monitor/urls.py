from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("api/series/", views.api_series, name="api_series"),
    path("api/live-tick/", views.live_tick, name="live_tick"),
    path("generate/<str:kind>/", views.generate, name="generate"),
    path("detect/", views.run_detect, name="run_detect"),
    path("anomalies/", views.anomalies, name="anomalies"),
    path("anomalies/export/", views.anomalies_export, name="anomalies_export"),
    path("anomalies/<int:pk>/", views.anomaly_detail, name="anomaly_detail"),
    path("anomalies/<int:pk>/acknowledge/", views.acknowledge, name="acknowledge"),
    path("logs/", views.logs, name="logs"),
    path("upload/", views.upload, name="upload"),
    path("reset/", views.reset, name="reset"),
]
