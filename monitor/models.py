from django.db import models


class LogEntry(models.Model):
    timestamp = models.DateTimeField(db_index=True)
    level = models.CharField(max_length=10)
    service = models.CharField(max_length=50)
    ip = models.CharField(max_length=45)
    message = models.CharField(max_length=500)
    status_code = models.PositiveSmallIntegerField(null=True, blank=True)
    is_failed_login = models.BooleanField(default=False)

    class Meta:
        ordering = ["-timestamp", "-id"]

    def __str__(self):
        return f"{self.timestamp:%Y-%m-%d %H:%M:%S} {self.level} {self.service}"

    @property
    def is_error(self):
        return self.level in ("ERROR", "CRITICAL") or (self.status_code or 0) >= 500


class Anomaly(models.Model):
    SEVERITIES = [("High", "High"), ("Medium", "Medium"), ("Low", "Low")]

    window_start = models.DateTimeField(unique=True)
    severity = models.CharField(max_length=10, choices=SEVERITIES)
    score = models.PositiveSmallIntegerField(help_text="Relative anomaly score, 0 to 100")
    total_events = models.PositiveIntegerField()
    error_count = models.PositiveIntegerField()
    failed_logins = models.PositiveIntegerField()
    unique_ips = models.PositiveIntegerField()
    top_ip = models.CharField(max_length=45, blank=True)
    cause = models.TextField()
    acknowledged = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-window_start"]

    def __str__(self):
        return f"{self.severity} anomaly at {self.window_start:%H:%M}"
