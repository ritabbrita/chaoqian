# -*- coding: utf-8 -*-
"""干支 / 五行 / 卦名 等基础表与小工具(纯函数, 无 I/O)。"""
from .bazi import ZHI_HIDDEN  # 藏干表全库只有 bazi 模块一份, 这里只是转出

GAN = "甲乙丙丁戊己庚辛壬癸"
ZHI = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]

GUA8 = ["乾", "兑", "离", "震", "巽", "坎", "艮", "坤"]  # 先天八卦序 1-8
TRIGRAM_LINES = {  # 自下而上, 1=阳
    "乾": (1, 1, 1), "兑": (1, 1, 0), "离": (1, 0, 1), "震": (1, 0, 0),
    "巽": (0, 1, 1), "坎": (0, 1, 0), "艮": (0, 0, 1), "坤": (0, 0, 0),
}
LINES_TRIGRAM = {v: k for k, v in TRIGRAM_LINES.items()}
GUA64 = {
    "乾": {"乾": "乾为天", "兑": "天泽履", "离": "天火同人", "震": "天雷无妄", "巽": "天风姤", "坎": "天水讼", "艮": "天山遁", "坤": "天地否"},
    "兑": {"乾": "泽天夬", "兑": "兑为泽", "离": "泽火革", "震": "泽雷随", "巽": "泽风大过", "坎": "泽水困", "艮": "泽山咸", "坤": "泽地萃"},
    "离": {"乾": "火天大有", "兑": "火泽睽", "离": "离为火", "震": "火雷噬嗑", "巽": "火风鼎", "坎": "火水未济", "艮": "火山旅", "坤": "火地晋"},
    "震": {"乾": "雷天大壮", "兑": "雷泽归妹", "离": "雷火丰", "震": "震为雷", "巽": "雷风恒", "坎": "雷水解", "艮": "雷山小过", "坤": "雷地豫"},
    "巽": {"乾": "风天小畜", "兑": "风泽中孚", "离": "风火家人", "震": "风雷益", "巽": "巽为风", "坎": "风水涣", "艮": "风山渐", "坤": "风地观"},
    "坎": {"乾": "水天需", "兑": "水泽节", "离": "水火既济", "震": "水雷屯", "巽": "水风井", "坎": "坎为水", "艮": "水山蹇", "坤": "水地比"},
    "艮": {"乾": "山天大畜", "兑": "山泽损", "离": "山火贲", "震": "山雷颐", "巽": "山风蛊", "坎": "山水蒙", "艮": "艮为山", "坤": "山地剥"},
    "坤": {"乾": "地天泰", "兑": "地泽临", "离": "地火明夷", "震": "地雷复", "巽": "地风升", "坎": "地水师", "艮": "地山谦", "坤": "坤为地"},
}

GAN_WX = {"甲": "木", "乙": "木", "丙": "火", "丁": "火", "戊": "土", "己": "土", "庚": "金", "辛": "金", "壬": "水", "癸": "水"}
ZHI_WX = {"子": "水", "丑": "土", "寅": "木", "卯": "木", "辰": "土", "巳": "火", "午": "火", "未": "土", "申": "金", "酉": "金", "戌": "土", "亥": "水"}
SHENG = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}   # 生
KE = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}       # 克
LIUCHONG = {"子": "午", "午": "子", "丑": "未", "未": "丑", "寅": "申", "申": "寅", "卯": "酉", "酉": "卯", "辰": "戌", "戌": "辰", "巳": "亥", "亥": "巳"}
LIUHE = {"子": "丑", "丑": "子", "寅": "亥", "亥": "寅", "卯": "戌", "戌": "卯", "辰": "酉", "酉": "辰", "巳": "申", "申": "巳", "午": "未", "未": "午"}
SANHE = [set("申子辰"), set("亥卯未"), set("寅午戌"), set("巳酉丑")]
SANHE_ELEM = {frozenset("申子辰"): "水", frozenset("亥卯未"): "木", frozenset("寅午戌"): "火", frozenset("巳酉丑"): "金"}
GAN_HE = {"甲": "己", "己": "甲", "乙": "庚", "庚": "乙", "丙": "辛", "辛": "丙", "丁": "壬", "壬": "丁", "戊": "癸", "癸": "戊"}
GAN_POLARITY = {g: (1 if i % 2 == 0 else -1) for i, g in enumerate(GAN)}
GAN_CHONG = {"甲": "庚", "庚": "甲", "乙": "辛", "辛": "乙", "丙": "壬", "壬": "丙", "丁": "癸", "癸": "丁"}
ZHI_HAI = {"子": "未", "未": "子", "丑": "午", "午": "丑", "寅": "巳", "巳": "寅", "卯": "辰", "辰": "卯", "申": "亥", "亥": "申", "酉": "戌", "戌": "酉"}
ZHI_PO = {"子": "酉", "酉": "子", "丑": "辰", "辰": "丑", "寅": "亥", "亥": "寅", "卯": "午", "午": "卯", "巳": "申", "申": "巳", "未": "戌", "戌": "未"}
ZHI_XING_GROUPS = [set("寅巳申"), set("丑戌未"), set("子卯")]
ZHI_ZIXING = set("辰午酉亥")  # 自刑

__all__ = [
    "GAN", "ZHI", "GUA8", "TRIGRAM_LINES", "LINES_TRIGRAM", "GUA64", "GAN_WX", "ZHI_WX", "SHENG", "KE",
    "LIUCHONG", "LIUHE", "SANHE", "SANHE_ELEM", "GAN_HE", "GAN_POLARITY", "GAN_CHONG", "ZHI_HAI", "ZHI_PO",
    "ZHI_XING_GROUPS", "ZHI_ZIXING", "ZHI_HIDDEN", "zhi_xing_rel", "ten_god", "favor_weight", "day_xunkong",
]


def zhi_xing_rel(z, b):
    """两地支刑的关系: "刑"(三刑/相刑) / "自刑"(辰午酉亥同支) / None。"""
    if z == b:
        return "自刑" if z in ZHI_ZIXING else None
    return "刑" if any(z in grp and b in grp for grp in ZHI_XING_GROUPS) else None


def ten_god(day_master, other_gan):
    """按日主与另一干的五行生克、阴阳同异取十神。"""
    dmwx, owx = GAN_WX[day_master], GAN_WX[other_gan]
    same_polarity = GAN_POLARITY[day_master] == GAN_POLARITY[other_gan]
    if owx == dmwx:
        return "比肩" if same_polarity else "劫财"
    if SHENG[dmwx] == owx:
        return "食神" if same_polarity else "伤官"
    if KE[dmwx] == owx:
        return "偏财" if same_polarity else "正财"
    if KE[owx] == dmwx:
        return "七杀" if same_polarity else "正官"
    return "偏印" if same_polarity else "正印"


def favor_weight(wx, profile_or_fav, unfav=None):
    """五行喜忌权重。传 profile(dict) 时优先读连续权重 element_weights(-1..1), 否则按喜/忌列表取 ±1/0。"""
    if isinstance(profile_or_fav, dict):
        weights = profile_or_fav.get("element_weights") or {}
        if wx in weights:
            try:
                return max(-1.0, min(1.0, float(weights[wx])))
            except Exception:
                pass
        fav = set(profile_or_fav.get("favorable", []))
        bad = set(profile_or_fav.get("unfavorable", []))
    else:
        fav, bad = set(profile_or_fav or []), set(unfav or [])
    return 1 if wx in fav else (-1 if wx in bad else 0)


def day_xunkong(gz):
    """日柱所在旬的旬空两支, 如 甲子旬 -> 戌亥。"""
    gi = GAN.index(gz[0])
    zi = ZHI.index(gz[1])
    i = next(k for k in range(60) if k % 10 == gi and k % 12 == zi)
    head = i - (i % 10)
    return ZHI[(head + 10) % 12] + ZHI[(head + 11) % 12]
