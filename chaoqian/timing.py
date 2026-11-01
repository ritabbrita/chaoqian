# -*- coding: utf-8 -*-
"""Time windows for a fixed liuyao cast, with a separate future-month assessment.

The original hexagram, selected line, and strength are never changed here. Daily
triggers retain the origin chart's rules. Future solar-month conditions are an
explicit observation layer, not a probability or a second casting.
"""
from copy import deepcopy
from datetime import datetime, time, timedelta
import re
from zoneinfo import ZoneInfo

from lunar_python import Solar

from . import liuyao

TIMING_VERSION = "chaoqian-timing-0.1"
SUPPORTED_HORIZONS = (7, 30, 90, 180, 365)
CALENDAR_TZ = ZoneInfo("Asia/Shanghai")  # lunar_python's civil solar-term times.


def _local_datetime(value):
    if not isinstance(value, datetime):
        raise ValueError("dt must be a datetime")
    value = value.replace(tzinfo=CALENDAR_TZ) if value.tzinfo is None else value.astimezone(CALENDAR_TZ)
    return value.replace(microsecond=0)


def _lunar(value):
    return Solar.fromYmdHms(value.year, value.month, value.day, value.hour, value.minute, value.second).getLunar()


def _term_datetime(term):
    return datetime.strptime(term.getSolar().toYmdHms(), "%Y-%m-%d %H:%M:%S").replace(tzinfo=CALENDAR_TZ)


def _trigger_labels(reasons):
    """Display each trigger once, including inputs already joined by semicolons.

    Multiple references for the same trigger remain separate evidence records,
    but must neither duplicate the label nor give that trigger extra ranking votes.
    """
    return list(dict.fromkeys(
        label.strip()
        for reason in reasons
        for label in re.split(r"[;；]", str(reason.get("how") or "规则触发"))
        if label.strip()
    ))


def _evidence_count(candidate):
    return len(_trigger_labels(candidate.get("reasons") or [{"how": candidate.get("how")}]))


def aggregate_candidates(hits):
    """One date, every reason; mixed auspicious/adverse evidence stays visible."""
    grouped = {}
    for hit in hits or []:
        if not isinstance(hit, dict) or not hit.get("date"):
            continue
        day = str(hit["date"])
        datetime.strptime(day, "%Y-%m-%d")
        item = grouped.setdefault(day, {"date": day, "reasons": [], "kinds": []})
        # Accept an already aggregated candidate without collapsing its distinct
        # references into one combined citation or duplicating its summary label.
        sources = hit.get("reasons") or [hit]
        if not isinstance(sources, (list, tuple)) or any(not isinstance(source, dict) for source in sources):
            raise ValueError("candidate reasons must be evidence records")
        for source in sources:
            kind = source.get("kind") or hit.get("kind") or "critical"
            if kind not in ("favorable", "critical", "unfavorable"):
                raise ValueError("unsupported candidate kind")
            reason = {"how": str(source.get("how") or "规则触发"), "kind": kind,
                      "basis": str(source.get("basis") or "")}
            if reason not in item["reasons"]:
                item["reasons"].append(reason)
            if kind not in item["kinds"]:
                item["kinds"].append(kind)
    result = []
    for day in sorted(grouped):
        item = grouped[day]
        kinds = item["kinds"]
        # Conservative headline: never hide an adverse reason behind a good one.
        item["kind"] = "unfavorable" if "unfavorable" in kinds else ("critical" if "critical" in kinds else "favorable")
        item["mixed"] = "unfavorable" in kinds and "favorable" in kinds
        labels = _trigger_labels(item["reasons"])
        item["how"] = "；".join(labels)
        item["evidence_count"] = len(labels)
        item["basis"] = "；".join(dict.fromkeys(r["basis"] for r in item["reasons"] if r["basis"]))
        result.append(item)
    return result


def _month_assessment(ushen, month_zhi):
    wx, zhi = ushen["wx"], ushen["zhi"]
    mwx = liuyao.ZHI_WX[month_zhi]
    state, _unused_score = liuyao._wangshuai(wx, month_zhi)
    support, pressure = [], []
    if mwx == wx:
        support.append("未来月令%s%s与原用神%s%s同类，月令态为%s" % (month_zhi, mwx, zhi, wx, state))
    elif liuyao.SHENG[mwx] == wx:
        support.append("未来月令%s%s生原用神%s%s，月令态为%s" % (month_zhi, mwx, zhi, wx, state))
    elif liuyao.KE[mwx] == wx:
        pressure.append("未来月令%s%s克原用神%s%s，月令态为%s" % (month_zhi, mwx, zhi, wx, state))
    elif liuyao.SHENG[wx] == mwx:
        pressure.append("原用神%s%s生未来月令%s%s，有泄耗，月令态为%s" % (zhi, wx, month_zhi, mwx, state))
    elif liuyao.KE[wx] == mwx:
        pressure.append("原用神%s%s克未来月令%s%s，有耗力，月令态为%s" % (zhi, wx, month_zhi, mwx, state))
    if liuyao.LIUCHONG[month_zhi] == zhi:
        pressure.append("未来月支%s与原用神支%s相冲，列为该阶段的月冲观察条件" % (month_zhi, zhi))
    if support and pressure:
        balance = "助力与制约并存"
    elif support:
        balance = "月令有助势条件"
    elif pressure:
        balance = "月令有制约或耗泄条件"
    else:
        balance = "月令未见单独倾向"
    return {"state": state, "support": support, "pressure": pressure, "balance": balance}


def _calendar_stages(ushen, start_at, stop_at):
    stages, current = [], start_at
    while current < stop_at:
        lunar = _lunar(current)
        gz = lunar.getMonthInGanZhiExact()
        term = lunar.getNextJie(False)
        boundary = _term_datetime(term)
        if boundary <= current:
            term = _lunar(current + timedelta(seconds=1)).getNextJie(False)
            boundary = _term_datetime(term)
        if boundary <= current:
            raise ValueError("solar-term calendar did not advance")
        end_at = min(boundary, stop_at)
        assessment = _month_assessment(ushen, gz[1])
        index = len(stages) + 1
        stages.append({
            "id": "stage-%d" % index, "start": current.date().isoformat(),
            "end": (end_at - timedelta(seconds=1)).date().isoformat(),
            "start_at": current.isoformat(), "end_at": end_at.isoformat(),
            "end_exclusive": True, "label": "第%d阶段·%s月" % (index, gz),
            "month_zhi": gz[1], "month_gz": gz, "month_state": assessment["state"],
            "support": assessment["support"], "pressure": assessment["pressure"],
            "balance": assessment["balance"],
            "summary": "%s；这是未来月令对原用神的条件观察，原卦强弱不变，不代表事情必成或必败。" % assessment["balance"],
            "next_term": {"name": term.getName(), "at": boundary.isoformat()} if boundary < stop_at else None,
            "candidates": [], "primary_candidates": [],
        })
        current = end_at
    return stages


def _representatives(candidates, limit):
    """Keep important triggers and adverse evidence in each actual solar stage.

    No dates are invented or evenly spaced. Distinct trigger labels on a date
    determine display ordering, never success probability. Additional references
    for one trigger do not increase its weight.
    """
    selected = []
    for kind in ("critical", "unfavorable", "favorable"):
        eligible = [c for c in candidates if kind in c["kinds"] and c not in selected]
        if eligible:
            eligible.sort(key=lambda c: (-_evidence_count(c), c["date"]))
            selected.append(eligible[0])
        if len(selected) >= limit:
            break
    return sorted(selected, key=lambda c: c["date"])


def build_timeline(ly, dt, horizon, future_days=None):
    """Build a complete window, including today, from the unchanged original cast.

    ``dt`` is the original casting instant, not the time a revision is requested.
    ``future_days`` optionally supplies (YYYY-MM-DD, day-branch) pairs; supplied
    entries must agree with the actual calendar. Missing dates are filled by the
    calendar, so a shorter supplied list cannot silently truncate a longer request.
    """
    if type(horizon) is not int or horizon not in SUPPORTED_HORIZONS:
        raise ValueError("supported horizons are 7, 30, 90, 180, and 365 days")
    if not isinstance(ly, dict) or not isinstance(ly.get("ushen"), dict):
        raise ValueError("a liuyao result with its original selected line is required")
    ushen = deepcopy(ly["ushen"])
    if ushen.get("zhi") not in liuyao.ZHI or ushen.get("wx") != liuyao.ZHI_WX[ushen["zhi"]]:
        raise ValueError("selected line has an invalid branch or element")
    start_at = _local_datetime(dt)
    deadline = start_at.date() + timedelta(days=horizon)
    stop_at = datetime.combine(deadline + timedelta(days=1), time.min, tzinfo=CALENDAR_TZ)
    stages = _calendar_stages(ushen, start_at, stop_at)
    calendar, observations = [], {}
    for offset in range(horizon + 1):
        day = start_at.date() + timedelta(days=offset)
        point = datetime.combine(day, time(12), tzinfo=CALENDAR_TZ)
        if offset == 0:
            point = max(point, start_at)
        label = day.isoformat()
        calendar.append((label, _lunar(point).getDayZhi()))
        observations[label] = point
    expected = dict(calendar)
    supplied = set()
    for item in future_days or []:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise ValueError("future_days entries must be date/branch pairs")
        day, branch = item
        if day in supplied or day not in expected or expected[day] != branch:
            raise ValueError("future_days must match unique dates in the requested calendar")
        supplied.add(day)

    origin_lunar = _lunar(start_at)
    context = ly.get("cast_context") or {}
    origin_month = context.get("month_zhi") or origin_lunar.getMonthZhiExact()
    origin_gz = context.get("day_gz") or origin_lunar.getDayInGanZhi()
    if origin_month not in liuyao.ZHI or len(origin_gz) != 2 or origin_gz[1] not in liuyao.ZHI:
        raise ValueError("invalid original cast calendar")
    # Results built without these fields get the selected line's changed branch and day clash filled in here.
    if "bian" not in ushen and ushen.get("source", "ben") == "ben":
        match = next((y for y in ly.get("yaos", []) if y.get("pos") == ushen.get("pos")), {})
        ushen["bian"] = deepcopy(match.get("bian"))
    ushen.setdefault("day_clashed", liuyao.LIUCHONG[ushen["zhi"]] == origin_gz[1])
    raw_hits = liuyao._yingqi_all(ushen, calendar, len(calendar), origin_month, origin_gz[1],
                                weak=ly.get("strength_label") == "弱", sanhe=ly.get("sanhe"))
    candidates = aggregate_candidates(raw_hits)
    for candidate in candidates:
        point = observations[candidate["date"]]
        stage = next(s for s in stages if datetime.fromisoformat(s["start_at"]) <= point < datetime.fromisoformat(s["end_at"]))
        candidate["stage_id"] = stage["id"]
        candidate["month_zhi"] = stage["month_zhi"]
        candidate["calendar_time"] = point.isoformat()
        candidate["scope"] = "原卦日触发；未来月令另作阶段条件观察"
        if any(s["next_term"] and s["next_term"]["at"][:10] == candidate["date"] for s in stages):
            candidate["boundary_note"] = "交节当日，日候选按日间观察时刻归属；月令以阶段所列准确交节时刻切换。"
        stage["candidates"].append(candidate)
    primary = []
    for stage in stages:
        stage["primary_candidates"] = _representatives(stage["candidates"], 3 if horizon <= 30 else 2)
        primary.extend(stage["primary_candidates"])
        if not stage["candidates"]:
            stage["summary"] += "本阶段没有原卦日触发候选，不强定日期。"
    return {
        "version": TIMING_VERSION, "horizon": horizon, "start": start_at.date().isoformat(),
        "deadline": deadline.isoformat(), "start_at": start_at.isoformat(), "calendar_timezone": "UTC+08:00",
        "includes_today": True, "stages": stages, "primary_candidates": sorted(primary, key=lambda c: c["date"]),
        "all_candidates": candidates, "raw_candidate_count": len(raw_hits),
        "original_strength": ly.get("strength_label"),
        "original_rule_version": ly.get("rule_version"), "action_version": ly.get("action_version"),
        "selection_rule": "逐个实际节令阶段保留关键触发与不利提醒，同类按不同触发理由数再按日期选代表；同一理由的多个出处不重复计数，完整候选全部保留。",
        "limitations": [
            "阶段是未来月令对固定用神的传统条件观察，不重摇卦，也不改写起卦时强弱。",
            "日候选保留原卦规则；有动静、条件变化与事情完成是不同判断，均不是发生概率。",
            "阶段按准确交节时刻划分；日候选按当地12:00归属，当天已过12:00则用起卦时刻。",
            "这些窗口不能单独用来比较多个选项孰优孰劣、推算累计数值或确认未提供的现实事实。",
        ],
    }
