# -*- coding: utf-8 -*-
"""命盘 x 当日干支: 八字日运评分、留意日(冲/劫/破/空)、吉日(贵人/财星/禄神/文昌/桃花)、流月线索。

所有函数都显式接收 profile(chaoqian.bazi.build_profile 的输出); profile 为空时返回 None,
上层功能自动退化。分数是传统规则下的相对势能, 不是事件概率。
"""
from lunar_python import Solar

from .almanac import now
from .bazi import PROFILE_VERSION
from .ganzhi import (GAN_CHONG, GAN_HE, GAN_WX, LIUCHONG, LIUHE, SANHE, SANHE_ELEM, ZHI, ZHI_HAI,
                     ZHI_HIDDEN, ZHI_PO, ZHI_WX, favor_weight, ten_god, zhi_xing_rel)

RULE_VERSION = "chaoqian-natal-0.1"


def _valid(profile):
    return bool(profile) and len(profile.get("pillars") or []) == 4 and all(len(p) == 2 for p in profile["pillars"])


# ---------- 留意日: 防御型日历 —— 冲 / 劫 / 破 / 空 逐日排, 只做提醒, 不做事件断言 ----------

WATCH_TIPS = {
    "劫财透干": "钱包看紧点——大额支出、借出、签约都缓一天",
    "冲夫妻宫": "跟伴侣容易呛, 分歧先搁一夜再谈",
    "冲本命": "日子冲你, 办事留余量, 别把日程排满",
    "月破": "不宜开新头, 收尾和整理最合适",
    "空亡": "重要承诺别落在今天, 容易落空",
    "忌神旺": "决定的事多核对一遍再点头",
}
_WATCH_PRIORITY = ("劫财透干", "冲夫妻宫", "冲本命", "月破", "空亡", "忌神旺")


def watch_tags_for(day_gan, day_zhi, month_zhi, profile):
    """单日留意标签; 弱信号(空亡 / 忌神旺)单独出现不报, 只做叠加项。"""
    dm = profile["day_master"]
    pillars = profile.get("pillars") or []
    year_branch, day_branch = pillars[0][1], pillars[2][1]
    tags = []
    if ten_god(dm, day_gan) == "劫财":
        tags.append("劫财透干")
    if LIUCHONG.get(day_zhi) == day_branch:
        tags.append("冲夫妻宫")
    if LIUCHONG.get(day_zhi) == year_branch:
        tags.append("冲本命")
    if LIUCHONG.get(day_zhi) == month_zhi:
        tags.append("月破")
    if day_zhi in set(profile.get("xunkong") or []):
        tags.append("空亡")
    if favor_weight(GAN_WX[day_gan], profile) <= -0.55:
        tags.append("忌神旺")
    strong = [t for t in tags if t in ("劫财透干", "冲夫妻宫", "冲本命", "月破")]
    if not strong and len(tags) < 2:
        return []
    return tags


def watch_days(profile, dt=None, days=30):
    """未来 N 天留意日(不含当天)。防御性提示, 不是事件预言。"""
    if not _valid(profile):
        return None
    dt = dt or now()
    solar = Solar.fromYmd(dt.year, dt.month, dt.day)
    out = []
    for i in range(1, days + 1):
        s = solar.next(i)
        lunar = s.getLunar()
        tags = watch_tags_for(lunar.getDayGan(), lunar.getDayZhi(), lunar.getMonthInGanZhi()[1], profile)
        if not tags:
            continue
        lead = next(t for t in _WATCH_PRIORITY if t in tags)
        out.append({"date": "%d-%02d-%02d" % (s.getYear(), s.getMonth(), s.getDay()),
                    "gz": lunar.getDayInGanZhi(), "tags": tags,
                    "level": ("重" if len(tags) >= 2 else "常"), "tip": WATCH_TIPS[lead]})
    return out


def watch_today(alm, profile):
    """今天是否留意日; 不是返回 None。月支吃 gz_month_day(整日取整), 与 watch_days 的扫描同口径。"""
    if not _valid(profile):
        return None
    tags = watch_tags_for(alm["day_gan"], alm["day_zhi"], alm["gz_month_day"][1], profile)
    if not tags:
        return None
    lead = next(t for t in _WATCH_PRIORITY if t in tags)
    return {"tags": tags, "tip": WATCH_TIPS[lead], "level": ("重" if len(tags) >= 2 else "常")}


# ---------- 吉日: 贵人 / 财星 / 禄神 / 文昌 / 桃花 ----------
# 表源: 《渊海子平》《三命通会》口诀, 与通行实现及临官位推导互相核对一致。
# 天乙贵人取主流「甲戊庚牛羊」派(另有「甲戊并牛羊」派, 差异在庚辛, 本引擎不采)。

LUCKY_TIPS = {
    "财星日": "谈钱谈单收款, 能挪到今天就挪",
    "贵人日": "求人办事、见重要的人, 今天开口最顺",
    "禄神日": "主业正财的事今天办, 水到渠成",
    "文昌日": "文书合同、写东西发内容, 今天脑子最清",
    "桃花日": "人缘亮的日子, 社交和曝光都加分",
}
_LUCKY_PRIORITY = ("财星日", "贵人日", "禄神日", "文昌日", "桃花日")
TIANYI = {"甲": ("丑", "未"), "戊": ("丑", "未"), "庚": ("丑", "未"), "乙": ("子", "申"), "己": ("子", "申"),
          "丙": ("亥", "酉"), "丁": ("亥", "酉"), "壬": ("卯", "巳"), "癸": ("卯", "巳"), "辛": ("午", "寅")}
WENCHANG = {"甲": "巳", "乙": "午", "丙": "申", "戊": "申", "丁": "酉", "己": "酉", "庚": "亥", "辛": "子", "壬": "寅", "癸": "卯"}
LUSHEN = {"甲": "寅", "乙": "卯", "丙": "巳", "戊": "巳", "丁": "午", "己": "午", "庚": "申", "辛": "酉", "壬": "亥", "癸": "子"}
TAOHUA = {}
for _grp, _hua in ((set("申子辰"), "酉"), (set("寅午戌"), "卯"), (set("巳酉丑"), "午"), (set("亥卯未"), "子")):
    for _b in _grp:
        TAOHUA[_b] = _hua


def lucky_tags_for(day_gan, day_zhi, profile):
    """单日吉星标签; 桃花是弱信号只做叠加项(与留意日的弱信号规则镜像)。"""
    dm = profile["day_master"]
    pillars = profile.get("pillars") or []
    year_branch, day_branch = pillars[0][1], pillars[2][1]
    tags = []
    if ten_god(dm, day_gan) in ("正财", "偏财"):
        tags.append("财星日")
    if day_zhi in TIANYI.get(dm, ()):
        tags.append("贵人日")
    if LUSHEN.get(dm) == day_zhi:
        tags.append("禄神日")
    if WENCHANG.get(dm) == day_zhi:
        tags.append("文昌日")
    if day_zhi in (TAOHUA.get(year_branch), TAOHUA.get(day_branch)):
        tags.append("桃花日")
    strong = [t for t in tags if t != "桃花日"]
    if not strong and len(tags) < 2:
        return []
    return tags


def lucky_days(profile, dt=None, days=30):
    """未来 N 天吉日。凶吉冲突时凶优先 —— 带留意标签的日子不进吉日名单。"""
    if not _valid(profile):
        return None
    dt = dt or now()
    solar = Solar.fromYmd(dt.year, dt.month, dt.day)
    out = []
    for i in range(1, days + 1):
        s = solar.next(i)
        lunar = s.getLunar()
        g, z = lunar.getDayGan(), lunar.getDayZhi()
        if watch_tags_for(g, z, lunar.getMonthInGanZhi()[1], profile):
            continue
        tags = lucky_tags_for(g, z, profile)
        if not tags:
            continue
        lead = next(t for t in _LUCKY_PRIORITY if t in tags)
        out.append({"date": "%d-%02d-%02d" % (s.getYear(), s.getMonth(), s.getDay()),
                    "gz": lunar.getDayInGanZhi(), "tags": tags,
                    "level": ("大吉" if len(tags) >= 2 else "吉"), "tip": LUCKY_TIPS[lead]})
    return out


def lucky_today(alm, profile):
    """今天是否吉日; 留意日优先, 冲突时返回 None。"""
    if not _valid(profile):
        return None
    if watch_tags_for(alm["day_gan"], alm["day_zhi"], alm["gz_month_day"][1], profile):
        return None
    tags = lucky_tags_for(alm["day_gan"], alm["day_zhi"], profile)
    if not tags:
        return None
    lead = next(t for t in _LUCKY_PRIORITY if t in tags)
    return {"tags": tags, "tip": LUCKY_TIPS[lead], "level": ("大吉" if len(tags) >= 2 else "吉")}


# ---------- 八字日运 ----------

def bazi_today(alm, profile, rule_version=RULE_VERSION):
    """传统规则评分。返回的是相对势能(潮位 1-10), 不是经验概率; components 逐条留痕。"""
    if not _valid(profile):
        return None
    dm = profile["day_master"]
    dm_wx = GAN_WX[dm]
    g, z = alm["day_gan"], alm["day_zhi"]
    pillars = list(profile["pillars"])
    stems = [p[0] for p in pillars]
    branches = [p[1] for p in pillars]
    day_branch = pillars[2][1]
    score = 0.0
    notes, components = [], []

    def add(name, delta, detail, scope=None):
        nonlocal score
        score += delta
        component = {"rule": name, "delta": round(delta, 2), "detail": detail}
        if scope:
            component["scope"] = scope
        components.append(component)

    # 日干权重较大; 日支按藏干加权, 不把一个地支粗暴压成单一五行。
    g_w = favor_weight(GAN_WX[g], profile)
    add("日干喜忌", 1.5 * g_w, "%s%s·%s" % (g, GAN_WX[g], ten_god(dm, g)))
    hidden_gods = []
    hidden_delta = 0.0
    for hg, ratio in ZHI_HIDDEN[z]:
        hidden_gods.append("%s%s" % (hg, ten_god(dm, hg)))
        hidden_delta += ratio * favor_weight(GAN_WX[hg], profile)
    add("日支藏干喜忌", hidden_delta, "%s藏%s" % (z, "、".join(hidden_gods)))
    notes.append("今日%s为%s，%s藏%s" % (g, ten_god(dm, g), z, "、".join(hidden_gods)))

    if GAN_HE.get(g) in stems:
        add("天干合", .7, "%s与命局%s相合" % (g, GAN_HE[g]))
    if GAN_CHONG.get(g) in stems:
        add("天干冲", -.7, "%s与命局%s相冲" % (g, GAN_CHONG[g]))

    bset = set(branches)
    for b in sorted(bset, key=ZHI.index):  # 固定顺序, 输出可复现
        weight = 1.4 if b == day_branch else .65
        scope = "spouse_palace" if b == day_branch else "general"
        if LIUCHONG[z] == b:
            add("地支冲", -weight, "%s冲%s%s" % (z, b, "(日支)" if b == day_branch else ""), scope)
            notes.append("%s与命中%s相冲，重要事留缓冲" % (z, b))
        if LIUHE[z] == b:
            add("地支合", .7 if b != day_branch else 1.0, "%s合%s" % (z, b), scope)
            notes.append("%s与命中%s六合，协作较顺" % (z, b))
        if ZHI_HAI.get(z) == b:
            add("地支害", -.45, "%s害%s" % (z, b), scope)
        if ZHI_PO.get(z) == b:
            add("地支破", -.3, "%s破%s" % (z, b), scope)
        xing = zhi_xing_rel(z, b)
        if xing == "刑":
            add("地支刑", -.45, "%s与%s成刑" % (z, b), scope)
        elif xing == "自刑":
            add("地支自刑", -.3, "%s自刑" % z, scope)
    for grp in SANHE:
        natal = grp & bset
        if z in grp and len(natal) >= 2 and z not in bset:
            add("三合成局", 1.2 * favor_weight(SANHE_ELEM[frozenset(grp)], profile), "%s会%s" % (z, "".join(sorted(natal))))
    if z in profile.get("xunkong", []):
        add("命局旬空触发", -.6, "%s落命局旬空" % z)

    # 流年、流月和大运只作背景修正, 并保留明细。
    for label, gz, weight in (("流年", alm["gz_year"], .35), ("流月", alm["gz_month"], .55)):
        elem_score = favor_weight(GAN_WX[gz[0]], profile) + favor_weight(ZHI_WX[gz[1]], profile)
        add(label + "喜忌", weight * elem_score, "%s%s" % (gz, label))
    dayun = None
    year_note = None
    yr = int(alm["solar"][:4])
    today_key = alm["solar"]
    # 当前大运只能由带起止时刻 / 年份的完整 profile 判断; redact_profile() 的输出不含这些, 此时不计大运。
    for dd in profile.get("da_yun", []):
        if dd.get("start_at") and dd.get("end_at"):
            active = dd["start_at"][:10] <= today_key <= dd["end_at"][:10]
        elif dd.get("start") is not None and dd.get("end") is not None:
            active = dd["start"] <= yr <= dd["end"]
        else:
            continue
        if active:
            dayun = "%s大运" % dd["gz"]  # 不带起止日期: 精确起运时刻可反推出生时间
            dy_score = favor_weight(GAN_WX[dd["gz"][0]], profile) + favor_weight(ZHI_WX[dd["gz"][1]], profile)
            add("大运喜忌", .35 * dy_score, dd["gz"] + "大运")
            break
    fav, unfav = set(profile.get("favorable", [])), set(profile.get("unfavorable", []))
    year_elems = {GAN_WX[alm["gz_year"][0]], ZHI_WX[alm["gz_year"][1]]}
    if year_elems & fav and not (year_elems & unfav):
        year_note = "流年%s含喜用%s" % (alm["gz_year"], "、".join(sorted(year_elems & fav)))
    elif year_elems & unfav and not (year_elems & fav):
        year_note = "流年%s偏耗，宜稳扎稳打" % alm["gz_year"]

    tide = max(1, min(10, round(5.5 + score)))
    label = "退潮" if tide <= 3 else ("平潮" if tide <= 6 else ("涨潮" if tide <= 8 else "大潮"))
    return {
        "score": round(score, 2), "tide": tide, "tide_label": label, "notes": notes[:4],
        "day_master": dm + dm_wx, "day_ten_god": ten_god(dm, g), "hidden_ten_gods": hidden_gods,
        "dayun": dayun, "year_note": year_note, "components": components, "rule_version": rule_version,
        "profile_version": profile.get("profile_version") or "unknown",
        "profile_verified": profile.get("profile_version") == PROFILE_VERSION,
        "day_master_strength": profile.get("day_master_strength"),
        "climate_note": profile.get("climate_note"),
    }


# ---------- 流月 x 命局 ----------

def month_hits(gz_month, profile):
    """流月干支对命局: 十神(月干透 / 月支本气) + 喜忌偏助 / 偏耗 + 月支与命中地支合 / 冲 / 三合 / 半合。"""
    hits = []
    if not profile:
        return hits
    mg, mz = gz_month[0], gz_month[1]
    dm = profile.get("day_master")
    if dm:
        hits.append("月干%s透%s" % (mg, ten_god(dm, mg)))
        main_hidden = ZHI_HIDDEN[mz][0][0]
        hits.append("月支%s本气%s为%s" % (mz, main_hidden, ten_god(dm, main_hidden)))
    for wxv, lab in ((GAN_WX[mg], "月干"), (ZHI_WX[mz], "月支")):
        weight = favor_weight(wxv, profile)
        if weight >= .4:
            hits.append("%s%s偏助" % (lab, wxv))
        elif weight <= -.4:
            hits.append("%s%s偏耗" % (lab, wxv))
    branches = [p[1] for p in profile["pillars"]]
    bset = set(branches)
    for b in sorted(bset, key=ZHI.index):
        if LIUHE[mz] == b:
            hits.append("月支%s与命中%s相合" % (mz, b))
        if LIUCHONG[mz] == b:
            hits.append("月支%s与命中%s相冲" % (mz, b))
    for grp in SANHE:
        if mz not in grp:
            continue
        natal = (grp - {mz}) & bset
        elem = SANHE_ELEM[frozenset(grp)]
        wang = next(x for x in grp if x in "子卯午酉")  # 三合局旺神(中神), 半合必须含它
        if len(natal) == 2:
            hits.append("月支%s与命中%s三合%s局" % (mz, "".join(sorted(natal, key=ZHI.index)), elem))
        elif len(natal) == 1 and wang in ({mz} | natal):
            hits.append("月支%s与命中%s半合%s" % (mz, next(iter(natal)), elem))
    return hits
