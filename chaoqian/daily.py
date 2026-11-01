# -*- coding: utf-8 -*-
"""日签: 黄历 + 梅花起卦 + 八字日运 + 奇门时段 + (可选)天气 -> 五领域分数 -> 叙事材料 -> 签文。

分数是传统规则势能, 不是事件概率。签文先由规则生成兜底版本; 传入 llm 时由大模型改写,
改写结果逐句过 chaoqian.guards 的护栏, 不合规的句子整句剔除并回落到规则文案。
"""
import copy
import hashlib
import json
import re
from datetime import datetime, timedelta

from . import guards as G
from . import qimen as _qimen
from .almanac import almanac, jieqi_regimen, now
from .ganzhi import GAN_WX, ZHI_HIDDEN, favor_weight, ten_god
from .llm import ask_json
from .meihua import meihua_cast
from .natal import bazi_today, lucky_days, lucky_today, watch_days, watch_today
from .prompts import DAILY_SYSTEM
from .weather import weather as fetch_weather

ENGINE_VERSION = "chaoqian-daily-0.1"
DOMAIN_ORDER = ("work", "money", "love", "parent", "body")
DOMAIN_LABELS = {"work": "工作", "money": "财务", "love": "伴侣", "parent": "亲子", "body": "身心"}

# 信号带: 分数 >= high 为「偏助」, <= low 为「偏耗」, 中间为中性。带只决定等级标签, 不决定文案。
# 默认是对所有领域一致的经验带; 想按某张命盘的实际分布定带, 用 calibrate_signal_bands() 回放一年取 30/70 分位。
DEFAULT_SIGNAL_BANDS = {key: {"low": 46, "high": 58} for key in DOMAIN_ORDER}

COLOR_PALETTES = {
    "木": [("松柏绿", "#58745D"), ("青竹色", "#708B69"), ("鼠尾草绿", "#9CAF96")],
    "火": [("暖朱红", "#A8584F"), ("豆沙粉", "#C28782"), ("陶橘色", "#B96F50")],
    "土": [("燕麦米", "#D4C19F"), ("焦糖棕", "#987052"), ("砂岩色", "#BE9F78")],
    "金": [("云朵白", "#E9E6DE"), ("雾银灰", "#AAB1B5"), ("香槟金", "#C7AD72")],
    "水": [("深海蓝", "#35546D"), ("墨蓝色", "#2D4055"), ("雨夜青", "#486877")],
}

FALLBACK = {
    "退潮": {"smile": "今天适合收尾和休整, 把拖着的小事了结一件就算赢。", "think": "别硬刚难缠的人和事, 大决定放到明天。",
             "domains": {"work": "少开新头, 收尾旧事更顺", "money": "别冲动消费, 核对一下账目", "love": "和伴侣少讲道理, 先把分工说清",
                         "parent": "亲子安排少加码, 先照顾情绪", "body": "早点休息, 让电量自己回来"},
             "lucky_item": "白色的杯子", "push": "今天适合休整, 别硬撑。"},
    "平潮": {"smile": "不好不坏的一天, 上午把拖了几天的小事做掉最划算。", "think": "睡前别翻旧聊天记录, 别跟自己较劲。",
             "domains": {"work": "按部就班, 午前效率更好", "money": "平平, 记一笔小账就好", "love": "适合和伴侣对齐一件小事",
                         "parent": "适合听孩子讲完一件小事", "body": "多喝温水, 起来走走"},
             "lucky_item": "白色的杯子", "push": "今天很稳, 按你的节奏来。"},
    "涨潮": {"smile": "今天开口的事容易成, 想推进什么就今天说。", "think": "别把「随便」当回答, 也别答应得太满。",
             "domains": {"work": "沟通顺, 适合主动对齐", "money": "可以做个小决定", "love": "伴侣沟通较顺, 共同安排可推进",
                         "parent": "亲子互动顺, 适合把约定说具体", "body": "按时吃饭, 别熬过头"},
             "lucky_item": "有花纹的布", "push": "今天顺, 想做的事开口。"},
    "大潮": {"smile": "今天运气经得起用, 做一件平时舍不得做的事。", "think": "唯一要防的是答应太多, 挑一件最想要的。",
             "domains": {"work": "适合拍板和开新头", "money": "宜谈, 不宜赌", "love": "适合和伴侣说清真正需要",
                         "parent": "适合肯定孩子做对的一件事", "body": "记得吃正经饭"},
             "lucky_item": "亮色的小物", "push": "今天你说了算。"},
}

_CATEGORY_DOMAIN = {"财务": "money", "事业": "work", "文书": "work", "感情": "love", "亲子": "parent", "身心": "body"}


def _gender(profile):
    return ((profile or {}).get("source_audit") or {}).get("gender")


def domain_vectors(gender=None):
    """十神 -> 各领域的加减向量。伴侣领域按命主性别取配偶星: 女命官杀为夫星, 男命财星为妻星;
    性别未知时两组配偶星各取一半权重, 不预设任何一方。"""
    vectors = {
        "正官": {"work": 7, "love": 7, "parent": 2, "body": -2},
        "七杀": {"work": 6, "love": 4, "parent": -2, "body": -4},
        "正财": {"money": 8, "love": 2, "parent": 1},
        "偏财": {"money": 7, "love": 2, "parent": 1},
        "正印": {"work": 3, "love": 1, "parent": 4, "body": 6},
        "偏印": {"work": 2, "parent": 3, "body": 4},
        "食神": {"love": 2, "parent": 8, "body": 3},
        "伤官": {"work": 2, "love": 1, "parent": 6, "body": -1},
        "比肩": {"work": 3, "money": -2, "parent": 2},
        "劫财": {"work": 2, "money": -5, "parent": -1},
    }
    if gender == "male":
        vectors = copy.deepcopy(vectors)
        vectors["正财"]["love"], vectors["正官"]["love"] = 7, 2
        vectors["偏财"]["love"], vectors["七杀"]["love"] = 4, 2
    elif gender != "female":
        vectors = copy.deepcopy(vectors)
        vectors["正财"]["love"] = vectors["正官"]["love"] = 4.5
        vectors["偏财"]["love"] = vectors["七杀"]["love"] = 3
    return vectors


def domain_scores(alm, bz, qm, wx, profile=None):
    """五领域综合线索 5-95: 潮位打底 + 日干支十神(命局喜忌加权) + 日支合冲(夫妻宫加重) + 旬空 + 奇门 + 天气。"""
    base = 50.0 + ((bz["tide"] - 5) * 5 if bz else 0)
    s = {key: base for key in DOMAIN_ORDER}
    if profile and profile.get("day_master"):
        dm = profile["day_master"]
        vectors = domain_vectors(_gender(profile))

        def apply_gan(gan, weight):
            sign = favor_weight(GAN_WX[gan], profile)
            if sign == 0:
                sign = .15
            for k, v in vectors[ten_god(dm, gan)].items():
                s[k] += v * sign * weight

        apply_gan(alm["day_gan"], 1.0)
        for hg, ratio in ZHI_HIDDEN[alm["day_zhi"]]:
            apply_gan(hg, ratio * .75)
        # 伴侣看日支(夫妻宫)合冲; 亲子只描述作为家长的互动状态, 不冒充孩子本人的命盘。
        for c in (bz or {}).get("components", []):
            rule = c.get("rule")
            spouse = c.get("scope") == "spouse_palace"
            if rule == "地支合":
                s["love"] += 4 if spouse else 1
                s["parent"] += 1
            elif rule == "地支冲":
                s["love"] -= 5 if spouse else 1
                s["parent"] -= 1.5
                s["body"] -= 2
            elif rule in ("地支刑", "地支害", "地支破"):
                s["love"] -= 2 if spouse else .5
                s["parent"] -= 1
                s["body"] -= 1.5
        if alm["day_zhi"] in profile.get("xunkong", []):
            s["work"] -= 4
            s["money"] -= 4
    if qm:
        if qm.get("best_ranges"):
            s["work"] += 5
        if (qm.get("dirs") or {}).get("生门"):
            s["money"] += 3
        if qm.get("style") == "宜守不宜攻":
            s["work"] -= 5
    if wx:
        # 降雨概率 >= 75% / 最高温 >= 34℃ 时身心略扣分(阈值可按所在地气候调整)。
        if (wx.get("rain_prob") or 0) >= 75:
            s["body"] -= 3
        if (wx.get("tmax") or 0) >= 34:
            s["body"] -= 3
    return {k: max(5, min(95, round(v))) for k, v in s.items()}


def calibrate_signal_bands(profile, start, days=366, with_qimen=True, low_pct=30, high_pct=70):
    """按某张命盘回放 days 天(不含天气), 各领域取 low_pct / high_pct 分位作为信号带。
    with_qimen=False 时更快(不起奇门盘), 但与日签实际口径略有差异。"""
    series = {k: [] for k in DOMAIN_ORDER}
    for i in range(days):
        dt = (start + timedelta(days=i)).replace(hour=8, minute=0, second=0, microsecond=0)
        alm = almanac(dt)
        bz = bazi_today(alm, profile)
        qm = _qimen.day_summary(dt) if with_qimen else None
        for k, v in domain_scores(alm, bz, qm, None, profile).items():
            series[k].append(v)

    def pct(values, p):
        values = sorted(values)
        idx = min(len(values) - 1, max(0, round(p / 100 * (len(values) - 1))))
        return values[idx]

    return {k: {"low": pct(v, low_pct), "high": pct(v, high_pct)} for k, v in series.items()}


def _bands(bands):
    out = dict(DEFAULT_SIGNAL_BANDS)
    out.update(bands or {})
    return out


def _level(value, band):
    return "high" if value >= band["high"] else ("low" if value <= band["low"] else "neutral")


def domain_signal_summary(scores, qm, bands=None):
    """展示层: 各领域传统方向与奇门时段是否同向; 从不表示概率。"""
    bands = _bands(bands)
    best = len((qm or {}).get("best_ranges") or [])
    slow = len((qm or {}).get("slow_ranges") or [])
    timing = "high" if best > slow else ("low" if slow > best else "neutral")
    out = {}
    for key in DOMAIN_ORDER:
        value = int((scores or {}).get(key, 50))
        band = bands[key]
        direction = _level(value, band)
        if direction == "neutral":
            agreement, agreement_label = "neutral", "传统线索中性"
        elif timing == "neutral":
            agreement, agreement_label = "timing_neutral", "传统时段未分高低"
        elif direction == timing:
            agreement, agreement_label = "aligned", "领域线索与时段同向"
        else:
            agreement, agreement_label = "conflict", "领域线索与时段相反"
        out[key] = {
            "score": value, "level": direction,
            "level_label": {"high": "偏助", "low": "偏耗", "neutral": "中性"}[direction],
            "agreement": agreement, "agreement_label": agreement_label, "timing": timing,
            "band": dict(band), "reference": "chaoqian-domain-rule-0.1",
            "disclaimer": "传统规则线索，未经科学验证，也不是事件发生概率。",
        }
    return out


_RULE_TEMPLATES = {
    "work": {"high": "传统工作线索偏助；只作准备与复盘参考。",
             "neutral": "传统工作线索中性；按现实计划安排。",
             "low": "传统工作线索偏耗；重要交付多核对一次。"},
    "money": {"high": "传统财务线索偏助；仍以账单和合同为准。",
              "neutral": "传统财务线索中性；只做原定安排。",
              "low": "传统财务线索偏耗；金额和条款多核对。"},
    "love": {"high": "传统伴侣线索偏助；适合把共同安排说具体。",
             "neutral": "传统伴侣线索中性；按平常方式沟通。",
             "low": "传统伴侣线索偏耗；先听完再谈分工。"},
    "parent": {"high": "传统亲子线索偏助；适合肯定具体行动。",
               "neutral": "传统亲子线索中性；照平常节奏陪伴。",
               "low": "传统亲子线索偏耗；提醒少一点、先听完整。"},
    "body": {"high": "传统身心线索偏助；真实精力仍以体感为准。",
             "neutral": "传统身心线索中性；按平常作息即可。",
             "low": "传统身心线索偏耗；给休息和补水留位置。"},
}


def domain_rule_texts(scores, bands=None):
    """确定性的规则文案, 与信号带同一口径。"""
    bands = _bands(bands)
    return {key: _RULE_TEMPLATES[key][_level(int((scores or {}).get(key, 50)), bands[key])] for key in DOMAIN_ORDER}


def daily_color_guide(alm, profile):
    """可解释的五行配色提示; 只作配色建议, 不把颜色当成事件因果。"""
    raw_weights = (profile or {}).get("element_weights") or {}
    if not raw_weights:
        return None
    elements = ("木", "火", "土", "金", "水")
    weights = {}
    for wxv in elements:
        try:
            weights[wxv] = max(-1.0, min(1.0, float(raw_weights.get(wxv, 0))))
        except Exception:
            weights[wxv] = 0.0
    # 日干按 1 份、日支按藏干比例合计 1 份。已经明显出现的元素略降权, 让配色在命盘有利范围内做当天微调。
    daily_load = {wxv: 0.0 for wxv in elements}
    daily_load[GAN_WX[alm["day_gan"]]] += 1.0
    for hidden_gan, ratio in ZHI_HIDDEN[alm["day_zhi"]]:
        daily_load[GAN_WX[hidden_gan]] += ratio
    ranked = sorted(
        ((weights[wxv] - 0.28 * daily_load[wxv], weights[wxv], wxv) for wxv in elements if weights[wxv] > 0.05),
        key=lambda row: (-row[0], -row[1], elements.index(row[2])),
    )
    if not ranked:
        return None
    primary_element = ranked[0][2]
    accent_element = ranked[1][2] if len(ranked) > 1 else primary_element
    date_key = alm.get("solar") or alm.get("gz_day") or "daily"

    def pick(wxv, role):
        palette = COLOR_PALETTES[wxv]
        digest = hashlib.sha256((date_key + wxv + role).encode("utf-8")).digest()
        name, hex_color = palette[digest[0] % len(palette)]
        return {"name": name, "hex": hex_color, "element": wxv, "role": role}

    favorable = [wxv for wxv in elements if weights[wxv] >= 0.4]
    today_dom = max(elements, key=lambda wxv: daily_load[wxv])
    return {
        "primary": pick(primary_element, "主色"),
        "accent": pick(accent_element, "点缀"),
        "reason": "命盘较宜%s；今日%s偏显，主色取%s，%s作点缀。" % (
            "、".join(favorable) or primary_element, today_dom, primary_element, accent_element),
        "method": "命盘连续五行权重＋当日干支藏干；有利元素优先，当日已显元素略降权。",
        "disclaimer": "传统五行穿搭提示，只作配色与行动提醒，不代表能改变事件结果。",
    }


def reconcile_signals(bz, qm, scores, due_today=None, date_key=None):
    """明确说明命理基调与奇门时机的冲突, 不让模型自行抹平。
    due_today: 用户自己的问卦里「应期落在今天」的条目(可选), 与整体气场 / 时段分开说。"""
    baseline = round(sum((scores or {"x": 50}).values()) / max(1, len(scores or {"x": 50})))
    best = len((qm or {}).get("best_ranges") or [])
    slow = len((qm or {}).get("slow_ranges") or [])
    if baseline < 43 and best >= 3:
        note, state = "整体势能偏低，但今天有可用时段；只推进低风险、可回退的一小步。", "弱底盘·有窗口"
    elif baseline >= 62 and slow >= 3:
        note, state = "整体底盘不差，但今天时机偏慢；准备和收尾优先，拍板另择时。", "强底盘·慢时机"
    elif baseline < 43:
        note, state = "整体势能偏低且时机不帮忙；今天以休整、核对和止损为主。", "宜守"
    elif baseline >= 62 and best >= 3:
        note, state = "整体底盘和时机同向；可以主动，但仍只选一件最重要的事。", "可进"
    else:
        note, state = "整体与时机没有明显同向信号；按日常节奏，小步验证。", "平衡"
    yq_today = []
    date_key = date_key or now().date().isoformat()
    for it in (due_today or []):
        if not isinstance(it, dict):
            continue
        if it.get("应期") != date_key or it.get("怎么看") == "最终截止日回看":
            continue
        cat = str(it.get("类别") or "")
        yq_today.append({"date": date_key, "category": cat, "domain": _CATEGORY_DOMAIN.get(cat),
                         "how": str(it.get("怎么看") or ""), "kind": str(it.get("性质") or ""),
                         "question": str(it.get("问") or "")[:40]})
    if yq_today:
        parts = ["%s·%s·%s" % (y["category"] or "其他", y["how"] or "应期", y["kind"] or "候选") for y in yq_today]
        note += ("另: 六爻应期落在今天(%s)——这是传统规则的观察提醒, 不代表会有消息或办成, 与整体气场、奇门时段分开说; "
                 "对应领域那句写「留意消息/接住」别硬推, 性质为「不利」的写「别在这天推」; 其它领域照上面的口径。" % "; ".join(parts))
    return {"state": state, "note": note, "baseline": baseline, "timing_best": best, "timing_slow": slow, "yingqi_today": yq_today}


def daily_evidence(alm, bz, qm, scores, wx):
    """可审计的证据清单: 传统规则与现实信息分层记录; 分数是信号, 不是概率。"""
    supports, limits, reality = [], [], []

    def item(rule_id, label, detail, layer, delta=None):
        out = {"rule_id": rule_id, "label": label, "detail": detail, "layer": layer}
        if delta is not None:
            out["delta"] = round(float(delta), 2)
        return out

    components = sorted(((bz or {}).get("components") or []), key=lambda row: -abs(float(row.get("delta") or 0)))
    seen = set()
    for component in components:
        delta = float(component.get("delta") or 0)
        if abs(delta) < 0.05:
            continue
        label = str(component.get("rule") or "八字日运")
        detail = str(component.get("detail") or "")
        if (label, detail) in seen:
            continue
        seen.add((label, detail))
        (supports if delta > 0 else limits).append(item("bazi-day", "八字·" + label, detail, "traditional", delta))
    if qm:
        best = list(qm.get("best_ranges") or [])
        slow = list(qm.get("slow_ranges") or [])
        if best:
            supports.append(item("qimen-hour", "奇门·可用时段", "、".join(best[:3]), "traditional"))
        if slow:
            limits.append(item("qimen-hour", "奇门·宜缓时段", "、".join(slow[:3]), "traditional"))
        for f in (qm.get("formations_today") or [])[:6]:
            target = supports if f.get("kind") == "吉" else (limits if f.get("kind") == "凶" else None)
            if target is not None:
                target.append(item("qimen-geju", "奇门·格局 " + str(f.get("name") or ""),
                                   "%s %s" % (f.get("range") or "", f.get("hint") or ""), "traditional"))
    if wx:
        bits = []
        if wx.get("desc"):
            bits.append(str(wx["desc"]))
        if wx.get("tmin") is not None and wx.get("tmax") is not None:
            bits.append("%s–%s℃" % (wx["tmin"], wx["tmax"]))
        if wx.get("rain_prob") is not None:
            bits.append("降雨概率%s%%" % wx["rain_prob"])
        if bits:
            reality.append(item("weather-open-meteo", "现实层·天气", "，".join(bits), "reality"))
    if not supports:
        supports.append(item("signal-neutral", "传统规则·中性", "今天没有达到展示阈值的明显助力项", "traditional"))
    if not limits:
        limits.append(item("signal-neutral", "传统规则·中性", "今天没有达到展示阈值的明显限制项", "traditional"))
    return {
        "supports": supports[:3], "limits": limits[:2], "reality": reality[:2],
        "rulebook": [
            {"rule_id": "bazi-day", "label": "八字日运", "basis": "传统源流：《渊海子平》《三命通会》《滴天髓》《子平真诠》；当前权重为本项目自定义，未经实证验证"},
            {"rule_id": "qimen-hour", "label": "奇门时机", "basis": "传统源流：《烟波钓叟歌》《遁甲演义》；当前门星神宫评分为本项目自定义，未经实证验证"},
            {"rule_id": "qimen-geju", "label": "奇门格局", "basis": "传统源流：《烟波钓叟歌》《奇门遁甲秘笈大全》十干克应/三奇/九遁/三诈/伏吟反吟；格局对时段分的修正系数为本项目自定义"},
            {"rule_id": "weather-open-meteo", "label": "现实天气", "basis": "Open-Meteo 客观背景；是否具有预测价值须由数据检验"},
        ],
        "rule_version": ENGINE_VERSION,
        "disclaimer": "传统书籍只能说明文化源流，不能代替预测验证；现实信息与传统线索分层记录。",
    }


# ---------- 身心行: 引擎等级前半句 + 节气食养 / 作息建议按日期轮换的后半句, 从不断言身体状态 ----------

_BODY_GENERIC_TIPS = ["每小时起身走两步, 倒杯温水", "午饭后闭眼小睡一刻钟", "傍晚出门走一圈再回来收尾",
                      "十点半前上床, 手机放远一点", "晚餐清淡些, 饭后散散步", "喝够温水, 少喝甜饮",
                      "睡前温水泡脚十分钟", "早餐认真吃, 带点蛋白质", "下午三点后少喝咖啡茶", "起身伸展, 拍拍后背和大腿后侧"]
_DAY_KEY = "今天日期"
_HOURS_KEY = "今日时段(奇门)"
_SCORES_KEY = "五领域分数"
_BAZI_KEY = "命理相性"
_REGIMEN_KEY = "本节气食养"


def _body_tip_short(text, n=12):
    text = re.sub(r"[(（][^)）]*[)）]", "", str(text or "")).strip(" ,，。")
    return text[:n]


def body_line(rule_text, facts):
    """身心行; 建池时就过状态护栏, 轮换只在安全句里转。"""
    head = str(rule_text or "").split("；")[0] or "传统身心线索中性"
    pool = []
    regimen = G.facts_get(facts, _REGIMEN_KEY)
    if isinstance(regimen, dict):
        yes = [_body_tip_short(x, 6) for x in (regimen.get("food_yes") or []) if x][:3]
        no = [_body_tip_short(x, 8) for x in (regimen.get("food_no") or []) if x][:2]
        if yes:
            pool.append("本节气宜吃点%s" % "、".join(yes[:2]))
        if len(yes) > 2:
            pool.append("这个节气%s正当时" % yes[2])
        pool.extend("本节气少碰%s" % x for x in no)
        if regimen.get("living"):
            pool.append(_body_tip_short(regimen["living"], 22))
    pool.extend(_BODY_GENERIC_TIPS)
    pool = [t for t in pool if not G.unverified_state("%s；%s。" % (head, t))] or ["按平常作息即可"]
    try:
        idx = datetime.strptime(str(G.facts_get(facts, _DAY_KEY) or ""), "%Y-%m-%d").timetuple().tm_yday
    except Exception:
        idx = 0
    idx += {"偏助": 0, "中性": 1, "偏耗": 2}.get(head[-2:], 0)
    tip = pool[idx % len(pool)].rstrip("。")
    line = "%s；%s。" % (head, tip)
    return line if not G.unverified_state(line) else "%s；按平常作息即可。" % head


def _domain_fallback(facts, key, bands=None):
    scores = G.facts_get(facts, _SCORES_KEY)
    scores = scores if isinstance(scores, dict) else {}
    if key == "body":
        return body_line(domain_rule_texts(scores, bands)["body"], facts)
    if scores:
        return domain_rule_texts(scores, bands)[key]
    label = "平潮"
    bazi_fact = G.facts_get(facts, _BAZI_KEY)
    if isinstance(bazi_fact, dict):
        tide = str(bazi_fact.get("潮位") or "")
        label = next((x for x in ("退潮", "平潮", "涨潮", "大潮") if x in tide), "平潮")
    return FALLBACK[label]["domains"].get(key) or FALLBACK["平潮"]["domains"]["work"]


def _line_fallback(facts, field):
    hours = G.facts_get(facts, _HOURS_KEY)
    hours = hours if isinstance(hours, dict) else {}
    if field == "smile":
        return G.exact_ranges_copy("传统顺时段", hours.get("顺"), "今天没有明确的传统顺时段。")
    return G.exact_ranges_copy("传统宜缓时段", hours.get("宜缓"), "今天没有明确的传统宜缓时段。")


def validate_daily_text(out):
    """模型输出的结构校验; 缺字段返回 None(整份走规则兜底)。push 不在这里派生, 留到护栏之后。"""
    if not isinstance(out, dict):
        return None
    domains = out.get("domains")
    if not isinstance(domains, dict):
        return None
    clean_domains = {}
    for key in DOMAIN_ORDER:
        value = G.clean_text(domains.get(key), 44)
        if not value:
            return None
        clean_domains[key] = value
    smile = G.clean_text(out.get("smile"), 64)
    think = G.clean_text(out.get("think"), 64)
    if not smile or not think:
        return None
    return {
        "smile": smile, "think": think, "domains": clean_domains,
        "lucky_item": G.clean_text(out.get("lucky_item"), 30) or "顺手常用的小物",
        "push": G.clean_text(out.get("push"), 60),
        "yingqi_note": G.clean_text(out.get("yingqi_note"), 100),
    }


def guard_daily_text(text, facts, bands=None):
    """日签护栏(词级)。材料里没给的十神 / 神煞星名 -> 整句剔除并记 guard_stripped; 字段剔空 -> 回落规则句;
    引擎材料原句豁免; 不许把事件结果写成预测命中; 不许断言今天的身体 / 情绪状态; 身心行一律用规则建议。
    push 在这里才派生, 且派生自过滤后的 smile。返回 (text, stripped)。"""
    if not isinstance(text, dict):
        return text, []
    corpus = G.facts_corpus(facts)
    allowed, banned = G.star_lists(corpus)
    stripped = []

    def clean(field, value):
        if not value:
            return value
        keep = []
        for sentence in G.split_sentences(value):
            core = sentence.strip()
            if G.HIT_CLAIM_RE.search(core):
                stripped.append({"field": field, "sentence": core, "reason": "事件发生不能作为预测命中的证据"})
                continue
            if G.unverified_state(core):
                stripped.append({"field": field, "sentence": core, "reason": "传统分数不能确认今天的身体或情绪状态"})
                continue
            if G.is_material_sentence(core, corpus):
                keep.append(sentence)
                continue
            masked = G.mask_allowed(core, allowed)
            hit = next((w for w in banned if w in masked), None)
            if hit:
                stripped.append({"field": field, "sentence": core, "reason": "材料没给的星名: " + hit})
                continue
            keep.append(sentence)
        out = "".join(keep).strip()
        return "" if G.copy_is_empty(out) else out

    domains = text.get("domains")
    if isinstance(domains, dict):
        for key in list(domains):
            domains[key] = clean("domains." + key, domains.get(key)) or _domain_fallback(facts, key, bands)
    text.setdefault("domains", {})["body"] = _domain_fallback(facts, "body", bands)
    for field in ("smile", "think"):
        text[field] = clean(field, text.get(field)) or _line_fallback(facts, field)
    text["lucky_item"] = clean("lucky_item", text.get("lucky_item")) or "顺手常用的小物"
    text["yingqi_note"] = clean("yingqi_note", text.get("yingqi_note")) or None
    text["push"] = clean("push", text.get("push")) or text["smile"][:60]
    return text, stripped


def geju_brief(qm, limit=4):
    """今日奇门格局摘要(只给吉 / 凶, 中性不进叙事); 五不遇时优先占位。"""
    items = [x for x in ((qm or {}).get("formations_today") or []) if x.get("kind") in ("吉", "凶")]
    items.sort(key=lambda x: 0 if x.get("name") == "五不遇时" else 1)
    return [{"时段": x.get("range"), "格局": x.get("name"), "吉凶": x.get("kind"), "提示": x.get("hint")} for x in items[:limit]] or "无"


def daily_facts(alm, bz, wx, qm=None, scores=None, strategy=None, color_guide=None, regimen=None,
                watch_now=None, lucky_now=None, context=None, bands=None):
    """组装交给模型(和护栏)的叙事材料。键名前缀被护栏按前缀读取, 改名时两边一起改。"""
    context = context or {}
    if qm:
        tl_sum = {"顺": qm["best_ranges"], "宜缓": qm["slow_ranges"]}
        if qm.get("dir_range") and qm.get("dir_range_is_best") is False:
            # 今天根本没有吉时段时, dir_range 只是全天相对最高分, 不能写成「最顺」。
            tl_sum["说明"] = "今日无突出顺时, 顺段仅相对可用(%s), 不要写成最顺、也不要说成当天最好的时段" % qm.get("dir_range")
    else:
        tl = alm.get("timeline") or []
        tl_sum = {"顺": [h["range"] for h in tl if h["luck"] == "吉" and 7 <= h["start"] <= 21],
                  "宜缓": [h["range"] for h in tl if h["luck"] == "凶" and 7 <= h["start"] <= 21]}
    return {
        "今天日期（当地）": alm.get("solar"),
        "今日时段(奇门)": tl_sum,
        "奇门行动风格与吉方": ({"风格": qm["style"], "吉方": qm["dirs"]} if qm else "无"),
        "今日奇门格局(引擎已算;最多挑1条吉格或凶格在smile/think里点一句,提格局名和时段即可,别展开卦理)": geju_brief(qm),
        "黄历": {"干支": "%s年 %s月 %s日" % (alm["gz_year"], alm["gz_month"], alm["gz_day"]),
               "值日": alm["zhixing"] + "日", "宜": alm["yi"], "忌": alm["ji"]},
        "命理相性": ({"日主": bz["day_master"], "潮位": "%d/10 %s" % (bz["tide"], bz["tide_label"]), "细节": bz["notes"]} if bz else "无"),
        "五领域分数(仅传统信号强弱,不是概率,解语以各领域等级为准)": scores or "无",
        "五领域等级(不同领域阈值不同,必须按此等级表达,不能自行用50分分界)": domain_signal_summary(scores, qm, bands),
        "冲突仲裁(必须作为总口径)": strategy or "无",
        "今日配色(引擎已算好,不得改动)": color_guide or "无",
        "天气(现实层,只作参考)": wx or "未知",
        "本月基调(保持口径一致)": context.get("month_gist") or "无",
        "本节气食养(smile里可自然引用一样,别硬塞成菜谱)": regimen or "无",
        "今日留意(防御性提示,把tip揉进think或对应领域一句,轻巧提醒别吓人)": watch_now or "无",
        "今日吉星(可把tip揉进smile或对应领域一句,鼓励行动别吹过头)": lucky_now or "无",
        "今天到观察窗口的问事(只作提醒,不代表今天完成)": context.get("due_today") or "无",
    }


_DAILY_INSTRUCTION = (
    "以下是今天全部材料, 写今天的签, 全部大白话。love 只写伴侣 / 亲密关系的互动建议, 不写单身、桃花或关系结局;"
    "parent 只写亲子互动建议, 不得把命盘说成孩子本人的运势。命理基调与奇门时机若冲突, 必须按「冲突仲裁」说明,"
    "不能一边说全天顺一边又说不要推进。时段须原样引用, 不能把21-23写成到21点, 也不能把中间有空档的时段合并成一段。输出 JSON, 字段:"
    " smile(把今天顺的时段和最值得做的一件事合成一句,<=32字,时段照抄材料, 写法如'X点到Y点相对顺, 适合做某件小事'),"
    " think(把该缓的时段和最该避免的一件事合成一句,<=32字,轻巧不吓人),"
    " domains(object,五个key: work/money/love/parent/body,各一句<=28字大白话,口吻跟各领域等级走: 偏助说得顺, 偏耗如实说偏弱但给台阶;"
    "仲裁里 yingqi_today 只可提醒核对进展, 不得断言今天有动静或一定收到消息),"
    " lucky_item(结合喜用五行只挑一个日常物件,不要另编颜色), push(<=30字大白话推送文案,不要署名),"
    " yingqi_note(有今天的观察窗口时只写一句留意现实进度的提醒; 不得写正中应期、卦应验或预测准确; 观察日不代表完成日; 没有相关材料则null)。\n"
)


def compose_daily(alm, bz, wx, qm=None, scores=None, strategy=None, color_guide=None, llm=None,
                  regimen=None, watch_now=None, lucky_now=None, context=None, bands=None):
    facts = daily_facts(alm, bz, wx, qm, scores, strategy, color_guide, regimen, watch_now, lucky_now, context, bands)
    if llm is not None:
        user = _DAILY_INSTRUCTION + json.dumps(facts, ensure_ascii=False)
        out = validate_daily_text(ask_json(llm, DAILY_SYSTEM, [{"role": "user", "content": user}], max_tokens=900))
        if out:
            out, guard_stripped = guard_daily_text(out, facts, bands)
            out["guard_stripped"] = guard_stripped
            out["fallback"] = False
            out["local_mode"] = False
            out["copy_policy"] = "narrative-guarded"
            return out
    tide_label = bz["tide_label"] if bz else "平潮"
    out = copy.deepcopy(FALLBACK[tide_label])
    out["fallback"] = llm is not None
    out["local_mode"] = llm is None
    out["yingqi_note"] = None
    if scores:
        out["domains"] = domain_rule_texts(scores, bands)
    out["smile"] = _line_fallback(facts, "smile")
    out["think"] = _line_fallback(facts, "think")
    out["domains"]["body"] = _domain_fallback(facts, "body", bands)
    out["guard_stripped"] = []
    out["copy_policy"] = "structured-fallback"
    return out


def generate_daily(profile=None, dt=None, llm=None, location=None, weather_data=None, context=None, bands=None):
    """生成一张日签。

    profile       chaoqian.bazi.build_profile() 的输出; 为空时只出黄历 / 卦象 / 奇门, 不出命理相性。
    dt            带时区的 datetime, 默认当前时间(CHAOQIAN_TZ, 默认 Asia/Shanghai)。
    llm           chaoqian.llm.LLMClient; None = 纯规则文案, 不联网。
    location      {"lat": .., "lon": ..}; 给了才会联网查天气。weather_data 可直接传天气 dict 代替。
    context       可选: {"month_gist": 本月基调一句, "due_today": [用户问卦里应期落在今天的条目]}。
    bands         各领域信号带, 默认 DEFAULT_SIGNAL_BANDS; 可用 calibrate_signal_bands() 按命盘校准。
    """
    context = context or {}
    dt = dt or now()
    alm = almanac(dt)
    cast = meihua_cast(alm)
    bz = bazi_today(alm, profile)
    wx = weather_data
    if wx is None and location and location.get("lat") is not None:
        wx = fetch_weather(location["lat"], location["lon"])
    qm = None
    try:
        qm = _qimen.day_summary(dt.replace(hour=8, minute=0))
    except Exception:
        qm = None
    scores = domain_scores(alm, bz, qm, wx, profile)
    strategy = reconcile_signals(bz, qm, scores, context.get("due_today"), alm["solar"])
    color_guide = daily_color_guide(alm, profile)
    regimen = jieqi_regimen(alm)
    watch_now, lucky_now = watch_today(alm, profile), lucky_today(alm, profile)
    text = compose_daily(alm, bz, wx, qm, scores, strategy, color_guide, llm=llm, regimen=regimen,
                         watch_now=watch_now, lucky_now=lucky_now, context=context, bands=bands)
    return {"date": alm["solar"], "almanac": alm, "cast": cast, "bazi": bz, "weather": wx, "qimen": qm,
            "domain_scores": scores, "domain_signals": domain_signal_summary(scores, qm, bands),
            "strategy": strategy, "color_guide": color_guide,
            "evidence": daily_evidence(alm, bz, qm, scores, wx), "regimen": regimen,
            "watch_days": watch_days(profile, dt), "watch_today": watch_now,
            "lucky_days": lucky_days(profile, dt), "lucky_today": lucky_now,
            "text": text, "rule_version": ENGINE_VERSION,
            "scientific_status": "traditional_reference_unvalidated"}
