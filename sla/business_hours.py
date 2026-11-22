"""Business-hours arithmetic for Frontdesk SLA clocks.

Working time defaults to Monday–Friday, 09:30–18:30 in SLA_TIME_ZONE
(Asia/Kolkata). Saturday, Sunday, and hours outside that window add nothing
to the SLA clock. Public holidays are not excluded.
"""

from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone


def business_zone():
    return ZoneInfo(settings.SLA_TIME_ZONE)


def _parse_hhmm(value):
    hour, minute = value.split(":")
    return time(int(hour), int(minute))


def work_start():
    return _parse_hhmm(settings.SLA_WORK_START)


def work_end():
    return _parse_hhmm(settings.SLA_WORK_END)


def work_days():
    return {int(part) for part in settings.SLA_WORK_DAYS.split(",") if part != ""}


def minutes_per_business_day():
    start = datetime.combine(datetime.now().date(), work_start())
    end = datetime.combine(datetime.now().date(), work_end())
    return int((end - start).total_seconds() // 60)


def to_local(dt):
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, business_zone())
    return dt.astimezone(business_zone())


def _is_workday(day):
    if day.weekday() not in work_days():
        return False
    try:
        from sla.models import BusinessHoliday
        return not BusinessHoliday.objects.filter(date=day).exists()
    except Exception:
        return True


def _at(day, clock, tz):
    return datetime.combine(day, clock, tzinfo=tz)


def _next_morning(day, tz):
    nxt = day + timedelta(days=1)
    while not _is_workday(nxt):
        nxt += timedelta(days=1)
    return _at(nxt, work_start(), tz)


def _previous_close(day, tz):
    prev = day - timedelta(days=1)
    while not _is_workday(prev):
        prev -= timedelta(days=1)
    return _at(prev, work_end(), tz)


def align_forward(dt):
    """Move to the next instant at which the SLA clock is running."""
    local = to_local(dt)
    tz = local.tzinfo
    if not _is_workday(local.date()):
        day = local.date()
        while not _is_workday(day):
            day += timedelta(days=1)
        return _at(day, work_start(), tz)
    start = _at(local.date(), work_start(), tz)
    end = _at(local.date(), work_end(), tz)
    if local < start:
        return start
    if local >= end:
        return _next_morning(local.date(), tz)
    return local


def align_backward(dt):
    """Latest business instant at or before dt."""
    local = to_local(dt)
    tz = local.tzinfo
    if _is_workday(local.date()):
        start = _at(local.date(), work_start(), tz)
        end = _at(local.date(), work_end(), tz)
        if start < local <= end:
            return local
        if local > end:
            return end
    return _previous_close(local.date(), tz)


def add_business_minutes(start, minutes):
    minutes = int(minutes)
    if minutes < 0:
        raise ValueError("minutes must be zero or positive")
    current = align_forward(start)
    if minutes == 0:
        return current
    remaining = minutes
    while remaining > 0:
        day_end = _at(current.date(), work_end(), current.tzinfo)
        available = (day_end - current).total_seconds() / 60
        if remaining <= available:
            return current + timedelta(minutes=remaining)
        remaining -= available
        current = _next_morning(current.date(), current.tzinfo)
    return current


def business_minutes_between(start, end):
    start_l = to_local(start)
    end_l = to_local(end)
    if end_l <= start_l:
        return 0.0
    current = align_forward(start_l)
    if current >= end_l:
        return 0.0
    total = 0.0
    while current < end_l:
        day_end = _at(current.date(), work_end(), current.tzinfo)
        segment_end = day_end if day_end < end_l else end_l
        if segment_end > current:
            total += (segment_end - current).total_seconds() / 60
        if day_end >= end_l:
            break
        current = _next_morning(current.date(), current.tzinfo)
    return total


def elapsed_business_minutes(start, end):
    return int(round(business_minutes_between(start, end)))


def signed_business_minutes(start, end):
    if to_local(end) >= to_local(start):
        return elapsed_business_minutes(start, end)
    return -elapsed_business_minutes(end, start)


def format_minutes(minutes):
    remaining = int(round(abs(minutes)))
    day_length = minutes_per_business_day() or 1
    days, rem = divmod(remaining, day_length)
    hours, mins = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if mins or not parts:
        parts.append(f"{mins}m")
    return " ".join(parts)
