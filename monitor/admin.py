from django.contrib import admin

from .models import Anomaly, LogEntry


@admin.register(LogEntry)
class LogEntryAdmin(admin.ModelAdmin):
    list_display = ("timestamp", "level", "service", "ip", "message")
    list_filter = ("level", "service")
    search_fields = ("message", "ip")


@admin.register(Anomaly)
class AnomalyAdmin(admin.ModelAdmin):
    list_display = ("window_start", "severity", "score", "cause", "acknowledged")
    list_filter = ("severity", "acknowledged")
