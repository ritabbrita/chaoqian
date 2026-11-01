# -*- coding: utf-8 -*-
"""黄历 / 节气 / 节气食养。全部由 lunar-python 确定性计算。"""
import calendar as _calendar
import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from lunar_python import Solar

from .ganzhi import ZHI

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
# 默认时区可用环境变量 CHAOQIAN_TZ 覆盖(IANA 名称, 如 Asia/Shanghai)。
DEFAULT_TZ = ZoneInfo(os.environ.get("CHAOQIAN_TZ") or "Asia/Shanghai")

_CACHE = {}


def load_data(name):
    """读取 chaoqian/data/ 下的 JSON 数据表; 缺表返回 None(相关功能自动退化)。"""
    if name not in _CACHE:
        path = os.path.join(DATA_DIR, name)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                _CACHE[name] = json.load(fh)
        except Exception:
            _CACHE[name] = None
    return _CACHE[name]


def now(tz=None):
    return datetime.now(tz or DEFAULT_TZ)


def almanac(dt=None):
    """当日黄历: 农历、年月日干支、节气、值日、二十八宿、冲煞、彭祖百忌、宜忌、吉神方位、黄道时辰。"""
    dt = dt or now()
    solar = Solar.fromYmdHms(dt.year, dt.month, dt.day, dt.hour, dt.minute, 0)
    lunar = solar.getLunar()
    prev_jq = lunar.getPrevJieQi(True)
    next_jq = lunar.getNextJieQi(True)
    lucky_hours = []
    try:
        for t in lunar.getTimes():
            if t.getTianShenLuck() == "吉":
                z = t.getZhi()
                i = ZHI.index(z)
                start = (23 + 2 * i) % 24
                lucky_hours.append({"zhi": z, "range": "%02d:00-%02d:00" % (start, (start + 2) % 24)})
    except Exception:
        pass
    day_lucky = [h for h in lucky_hours if h["zhi"] in ("巳", "午", "未", "申", "酉")]
    pick = (day_lucky or lucky_hours or [{"zhi": "午", "range": "11:00-13:00"}])[0]
    timeline = []
    try:
        # lunar.getTimes() 一天出 13 条, 首尾都是「子」(早子 00-01 / 晚子 23-01)。条目 range 写 "23-01",
        # 语义是晚子时, 所以同支后出现的覆盖先出现的(保留晚子时); 列表位置仍按首次出现排。
        index_of = {}
        for t in lunar.getTimes():
            z = t.getZhi()
            i = ZHI.index(z)
            start = (23 + 2 * i) % 24
            luck = ""
            try:
                luck = t.getTianShenLuck()
            except Exception:
                pass
            row = {"zhi": z, "start": start, "range": "%02d-%02d" % (start, (start + 2) % 24), "luck": luck}
            if z in index_of:
                timeline[index_of[z]] = row
            else:
                index_of[z] = len(timeline)
                timeline.append(row)
    except Exception:
        pass
    return {
        "solar": "%d-%02d-%02d" % (dt.year, dt.month, dt.day),
        "week": "星期" + solar.getWeekInChinese(),
        "lunar": lunar.toString(),
        # 年柱、月柱都精确到交节时刻(立春 / 各「节」), 与命盘 getEightChar 同口径。
        "gz_year": lunar.getYearInGanZhiExact(),
        "gz_month": lunar.getMonthInGanZhiExact(),
        # 整日取整的月干支: 黄历 / 留意日 / 吉日这一家按日粒度, 与 30 天扫描同口径; 八字流月用上面精确的 gz_month。
        "gz_month_day": lunar.getMonthInGanZhi(),
        "gz_day": lunar.getDayInGanZhi(),
        "day_gan": lunar.getDayGan(),
        "day_zhi": lunar.getDayZhi(),
        "shengxiao": lunar.getYearShengXiao(),
        "jieqi_prev": prev_jq.getName(),
        "jieqi_prev_date": prev_jq.getSolar().toYmd(),
        "jieqi_next": next_jq.getName(),
        "jieqi_next_date": next_jq.getSolar().toYmd(),
        "zhixing": lunar.getZhiXing(),
        "xiu": lunar.getXiu() + lunar.getZheng() + lunar.getAnimal(),
        "xiu_luck": lunar.getXiuLuck(),
        "chong": lunar.getDayChongDesc(),
        "sha": lunar.getDaySha(),
        "pengzu": [lunar.getPengZuGan(), lunar.getPengZuZhi()],
        "nayin": lunar.getDayNaYin(),
        "yi": lunar.getDayYi()[:6],
        "ji": lunar.getDayJi()[:5],
        "xishen": lunar.getPositionXiDesc(),
        "caishen": lunar.getPositionCaiDesc(),
        "lucky_hour": pick,
        "timeline": timeline,
        "lunar_month_num": abs(lunar.getMonth()),
        "lunar_day_num": lunar.getDay(),
        "year_zhi": lunar.getYearZhi(),
        "time_zhi": lunar.getTimeZhi(),
    }


def solar_month_key(dt=None):
    """八字流月按节令切换, 而不是按公历 1 号切换。"""
    dt = dt or now()
    alm = almanac(dt)
    return "%04d_%s" % (dt.year, alm["gz_month"])


def calendar_month_key(dt=None):
    """月运按公历月切换; 节令切换在 calendar_month_segments 里如实交代。"""
    dt = dt or now()
    return "%04d-%02d" % (dt.year, dt.month)


def calendar_month_segments(dt=None):
    """一个公历月总会跨两个流月(每月恰有一个「节」交节): 按日扫描, 返回
    [{gz, start, end, days, jie}] 时间顺序; jie 只在切换日那段填(如 白露)。"""
    dt = dt or now()
    ndays = _calendar.monthrange(dt.year, dt.month)[1]
    segs = []
    for d in range(1, ndays + 1):
        lunar = Solar.fromYmdHms(dt.year, dt.month, d, 12, 0, 0).getLunar()
        gz = lunar.getMonthInGanZhi()
        ymd = "%04d-%02d-%02d" % (dt.year, dt.month, d)
        if segs and segs[-1]["gz"] == gz:
            segs[-1]["end"] = ymd
            segs[-1]["days"] += 1
            continue
        jie = None
        if segs:
            try:
                jie = lunar.getJieQi() or None
            except Exception:
                jie = None
        segs.append({"gz": gz, "start": ymd, "end": ymd, "days": 1, "jie": jie})
    return segs


def jieqi_regimen(alm):
    """当前节气的食养提示; 数据 data/jieqi_regimen.json, 缺表返回 None。"""
    data = load_data("jieqi_regimen.json")
    entry = (data or {}).get(alm.get("jieqi_prev"))
    if not entry:
        return None
    out = {"name": alm["jieqi_prev"], "next_name": alm.get("jieqi_next"), "next_date": alm.get("jieqi_next_date")}
    out.update(entry)
    return out


def jieqi_tip(dt=None):
    """一句话节气提醒(交节前 3 天带预告)。"""
    alm = almanac(dt or now())
    reg = jieqi_regimen(alm)
    if not reg:
        return ""
    bits = "眼下%s——%s。" % (reg["name"], reg.get("note") or "")
    if reg.get("food_yes"):
        bits += "食宜%s;" % "、".join(reg["food_yes"][:2])
    if reg.get("food_no"):
        bits += "%s少碰。" % reg["food_no"][0]
    try:
        days = (datetime.strptime(reg["next_date"], "%Y-%m-%d").date()
                - datetime.strptime(alm["solar"], "%Y-%m-%d").date()).days
        if 0 < days <= 3:
            bits += "再过%d天就是%s了。" % (days, reg["next_name"])
    except Exception:
        pass
    return bits
