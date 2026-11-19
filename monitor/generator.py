"""Creates realistic demo traffic so the system can be shown without a real server."""
import random
from datetime import datetime, timedelta

from django.db.models import Max

from .models import LogEntry

SERVICES = ["web-api", "auth-service", "payment-service", "search-service"]
PAGES = ["/home", "/products", "/cart", "/checkout", "/profile", "/search", "/orders"]
VISITOR_IPS = [f"10.0.{i // 10}.{i % 10 + 10}" for i in range(40)]
ATTACKER_IP = "203.0.113.45"


def _event(ts, level, service, ip, message, status=None, failed=False):
    if status is not None:
        message = f"{message} status={status}"
    return {
        "timestamp": ts,
        "level": level,
        "service": service,
        "ip": ip,
        "message": message,
        "status_code": status,
        "is_failed_login": failed,
    }


def _at(minute_start):
    return minute_start + timedelta(seconds=random.randint(0, 59))


def _normal_event(minute_start):
    ts, ip, roll = _at(minute_start), random.choice(VISITOR_IPS), random.random()
    if roll < 0.012:
        return _event(ts, "ERROR", "web-api", ip, "Upstream timeout", 500)
    if roll < 0.05:
        return _event(ts, "WARN", "web-api", ip, f"GET {random.choice(PAGES)} slow response", 200)
    if roll < 0.08:
        return _event(ts, "WARN", "auth-service", ip, "POST /login login failed", 401, failed=True)
    return _event(ts, "INFO", random.choice(SERVICES), ip, f"GET {random.choice(PAGES)}", 200)


def minute_events(kind, minute_start):
    if kind == "spike":
        events = []
        for _ in range(random.randint(55, 75)):
            if random.random() < 0.55:
                events.append(_event(
                    _at(minute_start), "ERROR", random.choice(["payment-service", "db-proxy"]),
                    random.choice(VISITOR_IPS), "Connection pool exhausted", 500))
            else:
                events.append(_normal_event(minute_start))
        return events
    if kind == "attack":
        events = [
            _event(_at(minute_start), "WARN", "auth-service", ATTACKER_IP,
                   "POST /login login failed", 401, failed=True)
            for _ in range(random.randint(45, 60))
        ]
        events += [_normal_event(minute_start) for _ in range(random.randint(10, 16))]
        return events
    return [_normal_event(minute_start) for _ in range(random.randint(14, 26))]


def _floor(dt):
    return dt.replace(second=0, microsecond=0)


def next_start(minutes):
    last = LogEntry.objects.aggregate(m=Max("timestamp"))["m"]
    if last:
        return _floor(last) + timedelta(minutes=1)
    return _floor(datetime.now()) - timedelta(minutes=minutes)


def append_minutes(kind, minutes, start=None):
    start = start or next_start(minutes)
    rows = []
    for i in range(minutes):
        rows += minute_events(kind, start + timedelta(minutes=i))
    LogEntry.objects.bulk_create([LogEntry(**row) for row in rows], batch_size=500)
    return len(rows)


def load_demo():
    """One hour of traffic with an error spike and a login attack hidden inside."""
    start = _floor(datetime.now()) - timedelta(minutes=60)
    plan = [("normal", 38), ("spike", 3), ("normal", 8), ("attack", 3), ("normal", 8)]
    total, cursor = 0, start
    for kind, minutes in plan:
        total += append_minutes(kind, minutes, start=cursor)
        cursor += timedelta(minutes=minutes)
    return total
