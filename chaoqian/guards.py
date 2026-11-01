# -*- coding: utf-8 -*-
"""叙事护栏的公共部件: 大模型写的每一句都按引擎材料逐句核对, 不合规的整句剔除并留痕。

设计要点(日签与解卦两侧共用):
  ① 日签侧按**词级**放行星名: 材料里逐字出现的十神 / 神煞名才放行; 泛称(财星、官星…)只在
     其家族具体星名在场时放行。
  ② 解卦侧只做**状态互斥**, 不套十神 / 六亲词表 —— 六爻里 妻财 / 官鬼 常常就是用神本名。
  ③ 引擎材料原句豁免: 句子若是材料字符串的逐字子串, 永不剔。
  ④ 否定就近判定: 命中词前 4 字窗口(不跨小句)出现否定字即视为被否定。
"""
import json
import re

SENT_SPLIT_RE = re.compile(r"(?<=[。！？!?；;])")
SENT_TAIL = "。！？!?；;，,、 "
_PUNCT_ONLY_RE = re.compile(r"[\s。！？!?；;，,、·—\-–~～…\.\(\)（）「」\"']+")

TEN_GOD_NAMES = ("正财", "偏财", "正官", "七杀", "正印", "偏印", "食神", "伤官", "比肩", "劫财")
# 泛称 -> 家族具体星名; 泛称只在其家族任一具体星名逐字出现在材料里时放行
STAR_FAMILY = {
    "财星": ("正财", "偏财"), "妻财": ("正财", "偏财"),
    "官星": ("正官", "七杀"), "官杀": ("正官", "七杀"), "夫星": ("正官", "七杀"),
    "印星": ("正印", "偏印"),
    "食伤": ("食神", "伤官"), "子女星": ("食神", "伤官"),
    "比劫": ("比肩", "劫财"),
}
# 神煞 / 吉凶标签名。前 11 个是本引擎会产出的标签(吉日 / 留意日), 其余是常见但本引擎不算的,
# 材料里没有就一律视为模型自己编的。
SHENSHA_NAMES = (
    "财星日", "贵人日", "禄神日", "文昌日", "桃花日",
    "劫财透干", "冲夫妻宫", "冲本命", "忌神旺", "月破", "空亡",
    "天乙贵人", "太极贵人", "贵人", "禄神", "文昌", "桃花",
    "驿马", "华盖", "将星", "羊刃", "阳刃", "魁罡", "金舆",
    "红鸾", "天喜", "天德", "月德", "孤辰", "寡宿", "亡神", "劫煞", "灾煞", "福星",
)
# 长词在前: 掩码时先吃掉「财星日」这类整词, 免得剩下的「财星」被当成泛称误判
STAR_VOCAB = tuple(sorted(set(TEN_GOD_NAMES) | set(STAR_FAMILY) | set(SHENSHA_NAMES), key=len, reverse=True))

# 日签不得断言用户「今天」的身体、精力或情绪状态(引擎分数不是观察)。
STATE_RE = re.compile(
    r"头疼|头痛|没睡饱|没睡够|没睡好|睡不够|睡不好|睡眠不足|"
    r"睡(?:眠|得).{0,6}(?:差|不好|不踏实|不够沉)|"
    r"(?:身体|身子|精神|精力).{0,6}(?:整体稳|偏弱|偏耗|一般|很好|不错|不佳|不太好|好点|稳定|正常)|"
    r"精神好|劲头足|身体.{0,6}(?:没事|没大事|健康|无碍)|"
    r"(?:情绪|心情).{0,6}(?:低落|很差|很好|不佳|不高|高涨)")

# 把事件结果写成「卦应验 / 预测命中」的说法一律不许出现在日签里。
HIT_CLAIM_RE = re.compile(r"正中应期|卦.{0,8}应验|预测.{0,6}(?:准确|命中)|算准了|部分应验")

AUSPICIOUS_WORDS = ("大吉", "吉日", "吉时", "吉利", "顺利", "大顺", "有利", "利于", "宜办", "宜推进", "适合办")
NEG_MARKS = "不无非别莫勿未没难忌慎避欠"
NEG_WINDOW = 4
CLAUSE_SPLIT_RE = re.compile(r"[,，;；、]")


def split_sentences(text):
    return [s for s in SENT_SPLIT_RE.split(text or "") if s.strip()]


def facts_corpus(facts):
    """材料语料 = 交给模型的那串 JSON 原文。放行 / 豁免一律按它逐字判。"""
    try:
        return json.dumps(facts, ensure_ascii=False)
    except Exception:
        return str(facts)


def facts_get(facts, prefix):
    if not isinstance(facts, dict):
        return None
    for key, value in facts.items():
        if isinstance(key, str) and key.startswith(prefix):
            return value
    return None


def copy_is_empty(value):
    """剔完只剩标点, 按空处理。"""
    return not _PUNCT_ONLY_RE.sub("", value or "")


def is_material_sentence(sentence, corpus):
    """引擎材料原句豁免: 去掉句末标点后是材料的逐字子串 -> 永不剔。"""
    bare = (sentence or "").strip().strip(SENT_TAIL)
    return bool(bare) and bare in corpus


def cite_date_re(ymd):
    """日期引用正则。数字边界感知(「8月1」不命中「8月15」); 裸「月-日」必须跟 日/号,
    否则会与引擎自己的两小时段串(07-09 / 09-11…)撞车。"""
    try:
        month, day = int(str(ymd)[5:7]), int(str(ymd)[8:10])
    except Exception:
        return re.compile(r"(?!x)x")
    alts = [re.escape(str(ymd)[:10]),
            r"(?<!\d)%d月0?%d(?!\d)" % (month, day),
            r"(?<!\d)%d/0?%d(?!\d)" % (month, day),
            r"(?<![\d.A-Za-z])%d\.0?%d(?!\d)" % (month, day),
            r"(?<!\d)0?%d-0?%d\s*[日号](?!\d)" % (month, day)]
    return re.compile("|".join(alts))


def star_lists(corpus):
    """词级放行(不按组): 逐字在材料里出现的星名 / 神煞名放行; 泛称另需家族具体星名在场。"""
    allowed, banned = [], []
    for word in STAR_VOCAB:
        if word in STAR_FAMILY:
            ok = any(member in corpus for member in STAR_FAMILY[word])
        else:
            ok = word in corpus
        (allowed if ok else banned).append(word)
    return allowed, banned


def mask_allowed(sentence, allowed):
    masked = sentence
    for word in allowed:            # allowed 沿用 STAR_VOCAB 的长词优先顺序
        if word in masked:
            masked = masked.replace(word, "〇" * len(word))
    return masked


def unverified_state(value):
    return bool(STATE_RE.search(str(value or "")))


def negated_before(text, start):
    """就近否定判定: 命中词前 NEG_WINDOW 字窗口内(不跨小句)出现否定字 -> True。"""
    window = text[max(0, start - NEG_WINDOW):start]
    cut = max((window.rfind(ch) for ch in ",，;；、。！？"), default=-1)
    if cut >= 0:
        window = window[cut + 1:]
    return any(ch in window for ch in NEG_MARKS)


def unnegated_auspicious(clause):
    """小句里有没有**没被否定**的吉顺多字词(单字 吉/顺/利 误伤太多, 一律不用)。"""
    for word in AUSPICIOUS_WORDS:
        for m in re.finditer(re.escape(word), clause):
            if negated_before(clause, m.start()):
                continue
            return word
    return None


def date_scope_auspicious(sentence, date_rx):
    """某个日期的判定范围 = 只有命中它的那个小句(严格单小句)。
    范围内出现没被否定的吉顺多字词 -> 返回那个词, 否则 None。"""
    for clause in CLAUSE_SPLIT_RE.split(sentence):
        if not date_rx.search(clause):
            continue
        hit = unnegated_auspicious(clause)
        if hit:
            return hit
    return None


def forecast_window(raw, fallback):
    raw = str(raw or "").strip()
    if not raw:
        return fallback
    match = re.fullmatch(r"(\d{1,2})(?::00)?[-–](\d{1,2})(?::00)?", raw)
    if not match:
        return raw
    return "%02d:00–%02d:00" % (int(match.group(1)), int(match.group(2)))


def exact_ranges_copy(label, ranges, empty):
    """时段原样列出, 中间有空档的不合并。"""
    normalized = [forecast_window(raw, "") for raw in (ranges or [])]
    normalized = [value for value in normalized if value]
    return ("%s：%s。" % (label, "、".join(normalized))) if normalized else empty


def clean_text(value, limit):
    if not isinstance(value, (str, int, float)):
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text[:limit] if text else None
