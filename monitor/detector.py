"""Anomaly detection.

Step 1: group logs into one-minute windows and count simple features.
Step 2: an Isolation Forest (unsupervised ML) marks windows that are easy to isolate.
Step 3: a sanity check keeps only windows that really differ from the typical minute,
        which cuts down false alarms. Then a plain-language cause is written.
"""
from collections import Counter
from datetime import timedelta

import numpy as np
from django.conf import settings
from django.core.mail import send_mail
from sklearn.ensemble import IsolationForest

from .models import Anomaly, LogEntry

FEATURES = ["total_events", "error_count", "failed_logins", "unique_ips"]
MIN_WINDOWS = 15
CONTAMINATION = {"low": 0.06, "medium": 0.12, "high": 0.20}
STRICTNESS = {"low": 1.5, "medium": 1.0, "high": 0.7}  # multiplies the minimum change needed
BASE_DELTA = {"error_count": 5, "failed_logins": 6, "unique_ips": 8, "total_events": 20}
CAUSE_PRIORITY = ["failed_logins", "error_count", "total_events", "unique_ips"]


def build_windows():
    """Returns {minute: counts}, with empty minutes filled in so quiet periods are visible."""
    windows = {}
    rows = LogEntry.objects.order_by("timestamp").values_list(
        "timestamp", "level", "status_code", "ip", "is_failed_login")
    for ts, level, status, ip, failed in rows.iterator():
        key = ts.replace(second=0, microsecond=0)
        w = windows.setdefault(key, {
            "total_events": 0, "error_count": 0, "failed_logins": 0,
            "ips": Counter(), "failed_ips": Counter()})
        w["total_events"] += 1
        w["ips"][ip] += 1
        if level in ("ERROR", "CRITICAL") or (status or 0) >= 500:
            w["error_count"] += 1
        if failed:
            w["failed_logins"] += 1
            w["failed_ips"][ip] += 1
    if not windows:
        return {}
    cursor, last = min(windows), max(windows)
    while cursor <= last:
        windows.setdefault(cursor, {
            "total_events": 0, "error_count": 0, "failed_logins": 0,
            "ips": Counter(), "failed_ips": Counter()})
        cursor += timedelta(minutes=1)
    for w in windows.values():
        w["unique_ips"] = len(w["ips"])
    return dict(sorted(windows.items()))


def _qualifies(feature, value, typical, factor):
    if feature == "total_events":
        rose = value - typical >= BASE_DELTA[feature] * factor and value >= 2 * typical
        dropped = typical >= 10 and value <= 0.3 * typical
        return rose or dropped
    return value - typical >= BASE_DELTA[feature] * factor and value >= 2 * typical


def _describe(feature, window, typical):
    value = window[feature]
    typical = round(typical)
    if feature == "failed_logins":
        ip, count = (window["failed_ips"].most_common(1) or [("unknown", 0)])[0]
        share = round(100 * count / max(value, 1))
        return (f"Burst of failed logins: {value} attempts this minute, {share}% from {ip}. "
                f"Possible brute-force attack.", ip)
    if feature == "error_count":
        return (f"Sudden spike in server errors: {value} errors this minute against a "
                f"typical {typical}.", "")
    if feature == "total_events":
        if value < typical:
            return (f"Traffic dropped to {value} events against a typical {typical}. "
                    f"A service may be down.", "")
        return (f"Unusual traffic volume: {value} events against a typical {typical}.", "")
    return (f"Requests came from an unusual number of IP addresses: {value} against a "
            f"typical {typical}.", "")


def typical_values():
    windows = build_windows()
    if not windows:
        return {}
    return {f: float(np.median([w[f] for w in windows.values()])) for f in FEATURES}


def run_detection(sensitivity="medium"):
    sensitivity = sensitivity if sensitivity in CONTAMINATION else "medium"
    windows = build_windows()
    if len(windows) < MIN_WINDOWS:
        return {"status": "not_enough_data", "windows": len(windows), "anomalies": 0, "new": 0}

    keys = list(windows)
    X = np.array([[windows[k][f] for f in FEATURES] for k in keys], dtype=float)
    model = IsolationForest(
        n_estimators=150, contamination=CONTAMINATION[sensitivity], random_state=42).fit(X)
    flagged = model.predict(X) == -1
    raw = -model.decision_function(X)  # higher means easier to isolate
    spread = raw.max() - raw.min() or 1.0
    scores = (raw - raw.min()) / spread * 100
    medians = np.median(X, axis=0)
    factor = STRICTNESS[sensitivity]

    found = {}
    for i, key in enumerate(keys):
        if not flagged[i]:
            continue
        window = windows[key]
        feature = next((f for f in CAUSE_PRIORITY
                        if _qualifies(f, window[f], medians[FEATURES.index(f)], factor)), None)
        if feature is None:
            continue  # unusual to the model, but not different enough to alert on
        cause, top_ip = _describe(feature, window, medians[FEATURES.index(feature)])
        score = int(round(scores[i]))
        found[key] = {
            "severity": "High" if score >= 70 else "Medium" if score >= 40 else "Low",
            "score": score,
            "total_events": window["total_events"],
            "error_count": window["error_count"],
            "failed_logins": window["failed_logins"],
            "unique_ips": window["unique_ips"],
            "top_ip": top_ip or (window["ips"].most_common(1) or [("", 0)])[0][0],
            "cause": cause,
        }

    Anomaly.objects.exclude(window_start__in=list(found)).delete()
    new_count = 0
    for key, values in found.items():
        anomaly, created = Anomaly.objects.update_or_create(window_start=key, defaults=values)
        if created:
            new_count += 1
            if anomaly.severity == "High":
                _send_alert(anomaly)
    return {"status": "ok", "windows": len(keys), "anomalies": len(found), "new": new_count}


def _send_alert(anomaly):
    """Stands in for Amazon SNS: the alert text is printed in the terminal."""
    send_mail(
        subject=f"[Logwatch] High severity anomaly at {anomaly.window_start:%H:%M}",
        message=f"{anomaly.cause}\n\nOpen the dashboard to review the log lines.",
        from_email=settings.ALERT_FROM,
        recipient_list=settings.ALERT_TO,
        fail_silently=True,
    )
