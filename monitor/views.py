import csv
from datetime import timedelta

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST

from . import detector, generator, parser
from .models import Anomaly, LogEntry

SENSITIVITIES = ("low", "medium", "high")
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
CHART_WINDOWS = 90


def _sensitivity(request):
    return request.session.get("sensitivity", "medium")


def _error_q():
    return Q(level__in=["ERROR", "CRITICAL"]) | Q(status_code__gte=500)


def _payload():
    """Everything the dashboard shows, shared by the page and the live-update API."""
    windows = detector.build_windows()
    keys = list(windows)[-CHART_WINDOWS:]
    flagged = {a.window_start: a for a in Anomaly.objects.filter(window_start__in=keys)}
    series = {
        "labels": [k.strftime("%H:%M") for k in keys],
        "total": [windows[k]["total_events"] for k in keys],
        "errors": [windows[k]["error_count"] for k in keys],
        "failed_logins": [windows[k]["failed_logins"] for k in keys],
        "anomaly_idx": [i for i, k in enumerate(keys) if k in flagged],
    }
    total_logs = LogEntry.objects.count()
    error_logs = LogEntry.objects.filter(_error_q()).count()
    open_qs = Anomaly.objects.filter(acknowledged=False)
    open_count = open_qs.count()
    last = Anomaly.objects.first()

    if not total_logs:
        headline, subline = "No logs yet", "Load the demo traffic or upload a log file to start."
    elif open_count == 0:
        headline = "Everything looks normal"
        subline = f"Checked {total_logs:,} log lines across {len(windows)} one-minute windows."
    else:
        word = "anomaly needs" if open_count == 1 else "anomalies need"
        headline = f"{open_count} {word} review"
        subline = f"Checked {total_logs:,} log lines across {len(windows)} one-minute windows."

    return {
        "headline": headline,
        "subline": subline,
        "stats": {
            "total_logs": total_logs,
            "error_rate": round(error_logs / total_logs * 100, 1) if total_logs else 0,
            "open_anomalies": open_count,
            "high_open": open_qs.filter(severity="High").count(),
            "last_anomaly": last.window_start.strftime("%d %b, %H:%M") if last else "None yet",
        },
        "series": series,
        "open": [
            {
                "id": a.pk,
                "time": a.window_start.strftime("%H:%M"),
                "severity": a.severity,
                "cause": a.cause,
                "url": reverse("anomaly_detail", args=[a.pk]),
            }
            for a in open_qs[:6]
        ],
    }


@ensure_csrf_cookie
def dashboard(request):
    payload = _payload()
    return render(request, "monitor/dashboard.html", {
        "payload": payload,
        "sensitivity": _sensitivity(request),
        "has_logs": payload["stats"]["total_logs"] > 0,
    })


def api_series(request):
    return JsonResponse(_payload())


@require_POST
def live_tick(request):
    mode = request.POST.get("mode", "normal")
    mode = mode if mode in ("normal", "spike", "attack") else "normal"
    generator.append_minutes(mode, 1)
    detector.run_detection(_sensitivity(request))
    return JsonResponse({"ok": True})


@require_POST
def generate(request, kind):
    if kind == "demo":
        LogEntry.objects.all().delete()
        Anomaly.objects.all().delete()
        count = generator.load_demo()
        note = f"Loaded one hour of demo traffic ({count:,} log lines)."
    elif kind == "normal":
        minutes = 15 if LogEntry.objects.exists() else 60
        count = generator.append_minutes("normal", minutes)
        note = f"Added {minutes} minutes of normal traffic ({count:,} log lines)."
    elif kind == "spike":
        count = generator.append_minutes("spike", 3)
        note = f"Added a 3-minute error spike ({count:,} log lines)."
    elif kind == "attack":
        count = generator.append_minutes("attack", 3)
        note = f"Added a 3-minute login attack ({count:,} log lines)."
    else:
        raise Http404

    result = detector.run_detection(_sensitivity(request))
    if result["status"] == "not_enough_data":
        messages.info(request, f"{note} Add normal traffic first: detection needs at least "
                               f"{detector.MIN_WINDOWS} minutes of logs.")
    else:
        messages.success(request, f"{note} Detection found {result['anomalies']} "
                                  f"anomal{'y' if result['anomalies'] == 1 else 'ies'}.")
    return redirect("dashboard")


@require_POST
def run_detect(request):
    sensitivity = request.POST.get("sensitivity", "medium")
    if sensitivity in SENSITIVITIES:
        request.session["sensitivity"] = sensitivity
    result = detector.run_detection(_sensitivity(request))
    if result["status"] == "not_enough_data":
        messages.info(request, f"Detection needs at least {detector.MIN_WINDOWS} minutes of "
                               f"logs. You have {result['windows']}.")
    else:
        messages.success(request, f"Detection finished at {_sensitivity(request)} sensitivity: "
                                  f"{result['anomalies']} anomalies in {result['windows']} windows.")
    return redirect(request.POST.get("next") or "dashboard")


def anomalies(request):
    qs = Anomaly.objects.all()
    severity = request.GET.get("severity", "")
    state = request.GET.get("state", "")
    if severity in ("High", "Medium", "Low"):
        qs = qs.filter(severity=severity)
    if state == "open":
        qs = qs.filter(acknowledged=False)
    elif state == "reviewed":
        qs = qs.filter(acknowledged=True)
    return render(request, "monitor/anomalies.html", {
        "anomalies": qs, "severity": severity, "state": state,
    })


def anomalies_export(request):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="anomalies.csv"'
    writer = csv.writer(response)
    writer.writerow(["window_start", "severity", "score", "total_events", "error_count",
                     "failed_logins", "unique_ips", "top_ip", "cause", "reviewed"])
    for a in Anomaly.objects.all():
        writer.writerow([a.window_start, a.severity, a.score, a.total_events, a.error_count,
                         a.failed_logins, a.unique_ips, a.top_ip, a.cause, a.acknowledged])
    return response


def anomaly_detail(request, pk):
    anomaly = get_object_or_404(Anomaly, pk=pk)
    window_logs = LogEntry.objects.filter(
        timestamp__gte=anomaly.window_start,
        timestamp__lt=anomaly.window_start + timedelta(minutes=1))
    suspicious = window_logs.filter(_error_q() | Q(is_failed_login=True)).order_by("timestamp")
    typical = detector.typical_values()
    comparison = [
        ("Events", anomaly.total_events, round(typical.get("total_events", 0))),
        ("Errors", anomaly.error_count, round(typical.get("error_count", 0))),
        ("Failed logins", anomaly.failed_logins, round(typical.get("failed_logins", 0))),
        ("Unique IPs", anomaly.unique_ips, round(typical.get("unique_ips", 0))),
    ]
    return render(request, "monitor/anomaly_detail.html", {
        "anomaly": anomaly,
        "suspicious": suspicious[:60],
        "suspicious_total": suspicious.count(),
        "window_total": window_logs.count(),
        "comparison": comparison,
    })


@require_POST
def acknowledge(request, pk):
    anomaly = get_object_or_404(Anomaly, pk=pk)
    anomaly.acknowledged = not anomaly.acknowledged
    anomaly.save(update_fields=["acknowledged"])
    messages.success(request, "Marked as reviewed." if anomaly.acknowledged else "Moved back to open.")
    return redirect("anomaly_detail", pk=pk)


def logs(request):
    qs = LogEntry.objects.all()
    level = request.GET.get("level", "")
    query = request.GET.get("q", "").strip()
    only_errors = request.GET.get("errors") == "1"
    if level in ("DEBUG", "INFO", "WARN", "ERROR", "CRITICAL"):
        qs = qs.filter(level=level)
    if query:
        qs = qs.filter(Q(message__icontains=query) | Q(ip__icontains=query) | Q(service__icontains=query))
    if only_errors:
        qs = qs.filter(_error_q())
    page = Paginator(qs, 50).get_page(request.GET.get("page"))
    keep = request.GET.copy()
    keep.pop("page", None)
    return render(request, "monitor/logs.html", {
        "page": page, "level": level, "q": query, "only_errors": only_errors,
        "querystring": keep.urlencode(),
    })


def upload(request):
    if request.method == "POST":
        file = request.FILES.get("logfile")
        if not file:
            messages.error(request, "Choose a .log or .txt file first.")
            return redirect("upload")
        if file.size > MAX_UPLOAD_BYTES:
            messages.error(request, "That file is larger than 5 MB. Upload a smaller slice of the log.")
            return redirect("upload")
        text = file.read().decode("utf-8", errors="ignore")
        entries, skipped = parser.parse_text(text)
        if not entries:
            messages.error(request, "No lines matched the expected format. Check the example on this page.")
            return redirect("upload")
        LogEntry.objects.bulk_create(entries, batch_size=500)
        result = detector.run_detection(_sensitivity(request))
        messages.success(request, f"Read {len(entries):,} log lines ({skipped} skipped). "
                                  f"Detection found {result['anomalies']} anomalies.")
        return redirect("anomalies")
    return render(request, "monitor/upload.html")


@require_POST
def reset(request):
    LogEntry.objects.all().delete()
    Anomaly.objects.all().delete()
    messages.success(request, "All logs and anomalies were cleared.")
    return redirect("dashboard")
