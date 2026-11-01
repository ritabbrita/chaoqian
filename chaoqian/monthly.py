# -*- coding: utf-8 -*-
"""本月潮向(月运): 公历月为单位, 内部按流月分段 —— 尾巴段一句带过, 主段(天数多)定基调;
换月日期(节)由引擎标注、模型照抄不自算; 十神 / 吉凶日进材料, 星名护栏防张冠李戴。"""
import calendar as _calendar
import json
import re
from datetime import datetime, timedelta

from .almanac import almanac, calendar_month_key, calendar_month_segments, now
from .daily import ENGINE_VERSION
from .guards import clean_text
from .llm import ask_json
from .natal import bazi_today, lucky_days, month_hits, watch_days
from .prompts import MONTH_SYSTEM

# 十神 -> 领域线索; 模型只能引用材料里出现过的星名
TEN_GOD_DOMAIN = {
    "正财": "钱(财星)", "偏财": "钱(财星)",
    "正官": "伴侣/事业(官星)", "七杀": "伴侣/事业(官杀)",
    "食神": "孩子/表达(食伤)", "伤官": "孩子/表达(食伤)",
    "正印": "学习/长辈/护身(印星)", "偏印": "学习/长辈/护身(印星)",
    "比肩": "同伴/竞争(比劫)", "劫财": "同伴/竞争(比劫)",
}
_STAR_WORDS = {
    "财": ("正财", "偏财", "财星", "妻财"),
    "官": ("正官", "七杀", "官星", "官杀", "夫星"),
    "食伤": ("食神", "伤官", "食伤", "子女星"),
    "印": ("正印", "偏印", "印星"),
    "比劫": ("比肩", "劫财", "比劫"),
}
_STAR_GROUP_OF = {"正财": "财", "偏财": "财", "正官": "官", "七杀": "官", "食神": "食伤", "伤官": "食伤",
                  "正印": "印", "偏印": "印", "比肩": "比劫", "劫财": "比劫"}
_FACTS_GODS_KEY = "十神线索(只有这里列出的星才能写进对应领域; 没列的领域只按五行偏助/偏耗说, 不许提星名)"


def ten_gods_in(hits):
    return {g for h in hits for g in TEN_GOD_DOMAIN if g in h}


def star_guard(text, allowed_gods):
    """句级护栏: 材料没给的星名不许出现; 含未授权星名的句子整句删掉。返回 (text, stripped_sentences)。"""
    allowed_groups = {_STAR_GROUP_OF[g] for g in allowed_gods if g in _STAR_GROUP_OF}
    banned = [w for grp, words in _STAR_WORDS.items() if grp not in allowed_groups for w in words]
    if not banned or not text:
        return text, []
    parts = re.split(r"(?<=[。！？!?；;])", text)
    keep, stripped = [], []
    for s in parts:
        if any(w in s for w in banned):
            stripped.append(s.strip())
        else:
            keep.append(s)
    return "".join(keep).strip(), stripped


def _md(ymd):
    return "%d/%d" % (int(ymd[5:7]), int(ymd[8:10]))


def monthly_fortune(profile=None, dt=None, llm=None):
    dt = dt or now()
    alm = almanac(dt)
    bz = bazi_today(alm, profile)
    segs = calendar_month_segments(dt)
    for s in segs:
        s["hits"] = month_hits(s["gz"], profile)
    main = max(segs, key=lambda s: s["days"])
    switch = next((s for s in segs[1:] if s.get("jie")), None)
    seg_desc = " → ".join(
        "%s月(%s–%s, %d天%s)" % (s["gz"], _md(s["start"]), _md(s["end"]), s["days"],
                                 ("," + s["jie"] + "交节起") if s.get("jie") else "")
        for s in segs)
    if switch:
        switch_note = "%s %s交节换成%s月; %s之前还是%s月的尾巴(%d天)" % (
            _md(switch["start"]), switch["jie"], switch["gz"], _md(switch["start"]), segs[0]["gz"], segs[0]["days"])
    else:
        switch_note = "本月不换流月"
    main_gods = ten_gods_in(main["hits"])
    god_lines = {}
    for g in sorted(main_gods):
        god_lines.setdefault(TEN_GOD_DOMAIN[g], []).append(g)
    month_prefix = "%04d-%02d" % (dt.year, dt.month)
    anchor = datetime(dt.year, dt.month, 1, 8, 0, tzinfo=dt.tzinfo) - timedelta(days=1)
    ndays = _calendar.monthrange(dt.year, dt.month)[1]
    wl = [x for x in (watch_days(profile, anchor, ndays) or []) if x["date"].startswith(month_prefix)]
    ll = [x for x in (lucky_days(profile, anchor, ndays) or []) if x["date"].startswith(month_prefix)]
    watch_brief = ["%s %s%s" % (_md(x["date"]), "·".join(x["tags"]), "(重)" if x.get("level") == "重" else "") for x in wl][:12]
    lucky_brief = ["%s %s%s" % (_md(x["date"]), "·".join(x["tags"]), "(大吉)" if x.get("level") == "大吉" else "") for x in ll][:12]
    facts = {
        "月份": "%d年%d月" % (dt.year, dt.month),
        "流月": seg_desc,
        "换月": switch_note,
        "主段": "%s月(本月天数最多, 主基调按它写)" % main["gz"],
        "与命局": {("%s月" % s["gz"]): (s["hits"] or "平") for s in segs},
        _FACTS_GODS_KEY: god_lines or "本月主段没有透出可引用的星",
        "本月留意日(防御性提示, 挑1-2个日期自然带一句)": watch_brief or "无",
        "本月吉日(可挑1-2个日期鼓励行动)": lucky_brief or "无",
        "大运": bz.get("dayun") if bz else None, "流年": bz.get("year_note") if bz else None,
        "命局校准": "%s；%s" % (((profile or {}).get("day_master_strength") or "未标强弱"),
                              ((profile or {}).get("climate_note") or "未标调候")),
        "生成时节气": "%s→%s(%s)" % (alm["jieqi_prev"], alm["jieqi_next"], alm["jieqi_next_date"]),
    }
    hits = main["hits"]
    helping = sum(1 for item in hits if item.endswith("偏助") or "相合" in item or "三合" in item or "半合" in item)
    limiting = sum(1 for item in hits if item.endswith("偏耗") or item.endswith("相冲"))
    if helping > limiting:
        title, posture = "传统线索偏助", "可以按现实计划稳步推进，但不把它当成结果保证"
    elif limiting > helping:
        title, posture = "传统线索偏耗", "重要决定多做一次现实核对，不依据潮签单独决策"
    else:
        title, posture = "传统线索中性", "按原有节奏安排，以真实进展为准"
    basis_text = "、".join(hits) if hits else "本月主段没有达到展示阈值的合冲或喜忌线索"
    rule_text = "本月流月：%s。传统流月规则记录(按%s月)：%s。建议口径：%s。本月不强制生成财务、伴侣、亲子或身体结论；没有对应现实材料就不补写。" % (
        switch_note, main["gz"], basis_text, posture)
    out = None
    guard_stripped = []
    if llm is not None:
        user = ("写本月潮向。输出 JSON: title(本月主题,<=8字大白话), "
                "text(5-7句大白话连成自然一段: 开头一句先交代换月——照抄材料里「换月」的日期和节气名, 说清几号之前还是上个流月的尾巴、几号起换新流月, 日期不许自己推算; "
                "然后整体基调1-2句按「主段」那个流月写, 尾巴那几天一句带过就行; 钱/伴侣/亲子/身体只写「十神线索」里有对应星的领域, 没有对应星的领域只按五行偏助/偏耗轻轻带过或不写, 绝不出现材料里没有的星名; "
                "留意日/吉日里挑1-2个日期自然揉进去(日期照抄); 末尾给一条本月小建议)。\n"
                + json.dumps(facts, ensure_ascii=False))
        msgs = [{"role": "user", "content": user}]
        for attempt in range(2):
            raw = ask_json(llm, MONTH_SYSTEM, msgs, max_tokens=800)
            if not isinstance(raw, dict):
                break
            t_title = clean_text(raw.get("title"), 12)
            t_text = clean_text(raw.get("text"), 520)
            if not (t_title and t_text):
                break
            guarded, stripped = star_guard(t_text, main_gods)
            if not stripped or attempt == 1:
                if stripped:
                    guard_stripped = stripped
                if guarded:
                    out = {"title": t_title, "text": guarded, "fallback": False, "local_mode": False}
                break
            msgs.append({"role": "assistant", "content": json.dumps(raw, ensure_ascii=False)})
            msgs.append({"role": "user", "content": "你写了材料里没有的星名(%s)。「喜用五行」不等于财星/官星, 重写: 没有对应星的领域只说偏助/偏耗, 不许出现任何十神星名。只输出 JSON。" % "、".join(stripped)[:200]})
    if out is None:
        out = {"title": title, "text": rule_text, "fallback": llm is not None, "local_mode": llm is None}
    public_segs = [{k: s[k] for k in ("gz", "start", "end", "days", "jie")} for s in segs]
    return {"month": calendar_month_key(dt), "ganzhi_month": "→".join(s["gz"] for s in segs), "main_ganzhi": main["gz"],
            "segments": public_segs,
            "switch_date": switch["start"] if switch else None, "switch_jie": switch["jie"] if switch else None,
            "title": out["title"], "text": out["text"], "basis": facts, "fallback": out["fallback"],
            "local_mode": out["local_mode"], "rule_version": ENGINE_VERSION, "monthly_version": "chaoqian-monthly-0.1",
            "guard_stripped": guard_stripped, "scientific_status": "traditional_reference_unvalidated"}
