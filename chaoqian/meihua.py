# -*- coding: utf-8 -*-
"""梅花易数 · 时间起卦(年支数 + 农历月日 + 时支数)。卦辞爻辞取自《周易》原文(data/yijing64.json)。"""
from .almanac import load_data
from .ganzhi import GUA8, GUA64, LINES_TRIGRAM, TRIGRAM_LINES, ZHI

# yijing64.json 的 key 与正文是繁体古籍引文, 八纯卦只写单字; 这里按 (上卦, 下卦) 二元组查表,
# 查表侧只加两条正字法映射, 把简体三画卦名翻成 json 的写法。
_YIJING_TRIGRAM_ALIAS = {"兑": "兌", "离": "離"}


def hex_name(shang, xia):
    return GUA64[shang][xia]


def hex_from_lines(lines):
    xia = LINES_TRIGRAM[tuple(lines[0:3])]
    shang = LINES_TRIGRAM[tuple(lines[3:6])]
    return shang, xia


def yijing_entry(shang, xia):
    """按 (上卦, 下卦) 取 yijing64.json 条目; 查不到返回 None。"""
    yj = load_data("yijing64.json") or {}
    key = (_YIJING_TRIGRAM_ALIAS.get(shang, shang), _YIJING_TRIGRAM_ALIAS.get(xia, xia))
    for entry in yj.values():
        if (entry.get("shang"), entry.get("xia")) == key:
            return entry
    return None


def meihua_cast(alm):
    """以黄历结果(chaoqian.almanac.almanac 的返回)按时间起卦: 上卦=(年+月+日)%8, 下卦=(+时)%8, 动爻=%6。"""
    n_year = ZHI.index(alm["year_zhi"]) + 1
    n_month = alm["lunar_month_num"]
    n_day = alm["lunar_day_num"]
    n_hour = ZHI.index(alm["time_zhi"]) + 1
    s1 = n_year + n_month + n_day
    s2 = s1 + n_hour
    shang = GUA8[(s1 % 8 or 8) - 1]
    xia = GUA8[(s2 % 8 or 8) - 1]
    dong = s2 % 6 or 6
    lines = list(TRIGRAM_LINES[xia]) + list(TRIGRAM_LINES[shang])
    moved = lines[:]
    moved[dong - 1] = 1 - moved[dong - 1]
    b_shang, b_xia = hex_from_lines(moved)
    hu_lines = lines[1:4] + lines[2:5]
    h_shang, h_xia = hex_from_lines(hu_lines)
    ben = hex_name(shang, xia)
    ben_t = yijing_entry(shang, xia)
    yao_text = None
    if ben_t and ben_t.get("yao") and len(ben_t["yao"]) >= dong:
        yao_text = ben_t["yao"][dong - 1]
    return {
        "ts_zhi": alm["time_zhi"],
        "formula": "年%d+月%d+日%d=%d → 上%s ; +时%d=%d → 下%s ; 动第%d爻" % (n_year, n_month, n_day, s1, shang, n_hour, s2, xia, dong),
        "ben": ben, "ben_shang": shang, "ben_xia": xia, "dong": dong,
        "lines": lines,
        "bian": hex_name(b_shang, b_xia),
        "hu": hex_name(h_shang, h_xia),
        "guaci": ben_t.get("guaci") if ben_t else None,
        "yaoci": yao_text,
    }
