# -*- coding: utf-8 -*-
"""
时家奇门 · 转盘 · 拆补法 排局引擎。
只依赖 lunar_python。定局表、布盘、八门九星八神均为通行口径; 格局判定见 qimen_geju。
"""
from lunar_python import Solar

try:  # 格局模块缺失时引擎照常工作, 只是没有 formations 字段
    from . import qimen_geju as _geju
except Exception:  # pragma: no cover
    _geju = None

ZHI = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]
GAN = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"]
PALACE_NAME = {1: "坎", 2: "坤", 3: "震", 4: "巽", 5: "中", 6: "乾", 7: "兑", 8: "艮", 9: "离"}
PALACE_DIR = {1: "正北", 2: "西南", 3: "正东", 4: "东南", 5: "中宫", 6: "西北", 7: "正西", 8: "东北", 9: "正南"}
PALACE_ELEM = {1: "水", 2: "土", 3: "木", 4: "木", 5: "土", 6: "金", 7: "金", 8: "土", 9: "火"}
STAR_HOME = {1: "天蓬", 2: "天芮", 3: "天冲", 4: "天辅", 5: "天禽", 6: "天心", 7: "天柱", 8: "天任", 9: "天英"}
DOOR_HOME = {1: "休门", 2: "死门", 3: "伤门", 4: "杜门", 6: "开门", 7: "惊门", 8: "生门", 9: "景门"}
GODS = ["值符", "螣蛇", "太阴", "六合", "白虎", "玄武", "九地", "九天"]
LIUYI_SANQI = ["戊", "己", "庚", "辛", "壬", "癸", "丁", "丙", "乙"]
XUNSHOU_YI = {"甲子": "戊", "甲戌": "己", "甲申": "庚", "甲午": "辛", "甲辰": "壬", "甲寅": "癸"}
RING = [1, 8, 3, 4, 9, 2, 7, 6]  # 转盘顺时针宫序: 坎艮震巽离坤兑乾
GOOD_DOORS = {"开门", "休门", "生门"}
BAD_DOORS = {"死门", "惊门", "伤门"}
DOOR_ELEM = {"休门": "水", "生门": "土", "伤门": "木", "杜门": "木", "景门": "火", "死门": "土", "惊门": "金", "开门": "金"}
SHENG = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
KE = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}
GOOD_STARS = {"天心", "天任", "天辅"}
SLOW_STARS = {"天芮", "天蓬"}
GOOD_GODS = {"太阴", "六合", "九地", "九天"}
SLOW_GODS = {"白虎", "玄武", "螣蛇"}
RULE_VERSION = "chaoqian-qimen-0.1"
# 五不遇时地板分: 时段基础分理论下限 = 门-2 星-1 神-.5 门迫-1 = -4.5, 格局叠加再 ±1.5,
# 故非五不遇时段的最低可能分 = -6。压到 -9 保证五不遇时段永远低于任何别的时段, 既进不了
# rating==2 的吉时段, 也不可能成为 day_summary 里「全天最高分」的兜底候选。
# 依据《奇门法窍·卷六》「虽有门奇, 切不可用」—— 门吉奇全也不许翻身。
WUBUYU_FLOOR = -9

# 定局表: 节气 -> (遁: 1阳/-1阴, [上元局, 中元局, 下元局])
JU_TABLE = {
    "冬至": (1, [1, 7, 4]), "小寒": (1, [2, 8, 5]), "大寒": (1, [3, 9, 6]),
    "立春": (1, [8, 5, 2]), "雨水": (1, [9, 6, 3]), "惊蛰": (1, [1, 7, 4]),
    "春分": (1, [3, 9, 6]), "清明": (1, [4, 1, 7]), "谷雨": (1, [5, 2, 8]),
    "立夏": (1, [4, 1, 7]), "小满": (1, [5, 2, 8]), "芒种": (1, [6, 3, 9]),
    "夏至": (-1, [9, 3, 6]), "小暑": (-1, [8, 2, 5]), "大暑": (-1, [7, 1, 4]),
    "立秋": (-1, [2, 5, 8]), "处暑": (-1, [1, 4, 7]), "白露": (-1, [9, 3, 6]),
    "秋分": (-1, [7, 1, 4]), "寒露": (-1, [6, 9, 3]), "霜降": (-1, [5, 8, 2]),
    "立冬": (-1, [6, 9, 3]), "小雪": (-1, [5, 8, 2]), "大雪": (-1, [4, 7, 1]),
}
_YUAN_BY_ZHI = {"子": 0, "午": 0, "卯": 0, "酉": 0, "寅": 1, "申": 1, "巳": 1, "亥": 1, "辰": 2, "戌": 2, "丑": 2, "未": 2}


def _gz_index(gz):
    g, z = GAN.index(gz[0]), ZHI.index(gz[1])
    for i in range(60):
        if i % 10 == g and i % 12 == z:
            return i
    raise ValueError(gz)


def _sanyuan(day_gz):
    """拆补法: 日所在五日元的符头支定上中下元。"""
    i = _gz_index(day_gz)
    futou = i - (i % 5)
    return _YUAN_BY_ZHI[ZHI[futou % 12]]


def _ring_rotate(base_map, from_palace, to_palace):
    """转盘: 环上整体旋转, 把 from_palace 的内容转到 to_palace。base_map: palace->item (环上8宫)。"""
    fi, ti = RING.index(from_palace), RING.index(to_palace)
    off = (ti - fi) % 8
    return {RING[(RING.index(p) + off) % 8]: v for p, v in base_map.items()}


def pan(dt):
    """给定 datetime(本地时区), 起一局。返回 dict。"""
    solar = Solar.fromYmdHms(dt.year, dt.month, dt.day, dt.hour, dt.minute, 0)
    lunar = solar.getLunar()
    jq = lunar.getPrevJieQi(True).getName()
    day_gz = lunar.getDayInGanZhi()
    hour_gz = lunar.getTimeInGanZhi()
    dun, jus = JU_TABLE.get(jq, (1, [1, 7, 4]))
    yuan = _sanyuan(day_gz)
    ju = jus[yuan]
    # 地盘: 三奇六仪从局数宫起布, 阳顺阴逆
    earth = {}
    p = ju
    for gan in LIUYI_SANQI:
        earth[p] = gan
        p = p + dun
        p = 9 if p < 1 else (1 if p > 9 else p)
    gan_palace = {v: k for k, v in earth.items()}
    # 旬首 -> 值符原宫
    hi = _gz_index(hour_gz)
    xunshou_gz = None
    for i in range(60):
        if (hi - i) % 60 % 10 == 0:
            xunshou_gz = GAN[(hi - i) % 60 % 10] + ZHI[(hi - i) % 60 % 12]
            break
    yi = XUNSHOU_YI[xunshou_gz]
    fu_palace = gan_palace[yi]
    zhifu_star = STAR_HOME[fu_palace]
    zhishi_door = DOOR_HOME.get(fu_palace, "死门")  # 中五寄坤二死门
    zhishi_home = fu_palace if fu_palace != 5 else 2
    # 值符随时干: 天盘星环旋转, 值符星原宫 -> 时干地盘宫 (时干为甲用旬首六仪)
    hour_gan = hour_gz[0]
    target_gan = yi if hour_gan == "甲" else hour_gan
    fu_target = gan_palace[target_gan]
    if fu_target == 5:
        fu_target = 2  # 寄坤
    star_base = {pp: STAR_HOME[pp] for pp in RING}
    star_from = fu_palace if fu_palace != 5 else 2
    stars = _ring_rotate(star_base, star_from, fu_target)
    # 天盘干随星走: 星原宫的地盘干跟着星
    tian_gan = {}
    for pp, st in stars.items():
        home = [k for k, v in STAR_HOME.items() if v == st]
        h = home[0] if home else 5
        tian_gan[pp] = earth.get(h if h != 5 else 5, "")
    qin_at = fu_target if fu_palace == 5 else None
    # 值使随时支: 从值使原宫起旬首时, 阳顺阴逆按宫数飞, 数至当前时辰
    n = hi % 10  # 旬内第几时辰
    dp = zhishi_home
    for _ in range(n):
        dp = dp + dun
        dp = 9 if dp < 1 else (1 if dp > 9 else dp)
    if dp == 5:
        dp = 2
    door_base = {pp: DOOR_HOME[pp] for pp in RING}
    doors = _ring_rotate(door_base, zhishi_home, dp)
    # 八神: 从值符落宫起, 阳顺阴逆沿环布
    gods = {}
    fi = RING.index(fu_target)
    for k, god in enumerate(GODS):
        gods[RING[(fi + dun * k) % 8]] = god
    return {
        "jieqi": jq, "dun": "阳遁" if dun == 1 else "阴遁", "ju": ju,
        "yuan": ["上元", "中元", "下元"][yuan], "day_gz": day_gz, "hour_gz": hour_gz,
        "zhifu": zhifu_star, "zhishi": zhishi_door,
        # 值符/值使落宫、时支、本旬旬首与旬首之仪, 供 qimen_geju 反查
        "zhifu_palace": fu_target, "zhishi_palace": dp, "hour_zhi": hour_gz[1],
        "xunshou": xunshou_gz, "xunshou_yi": yi,
        "palaces": {pp: {"dir": PALACE_DIR[pp], "star": (("天禽/" + stars.get(pp)) if pp == qin_at else stars.get(pp)),
                          "door": doors.get(pp), "god": gods.get(pp), "earth": earth.get(pp), "tian": tian_gan.get(pp),
                          "tianqin": earth.get(5) if pp == qin_at else None} for pp in RING},
    }


def day_hours(dt_base, hours=(7, 9, 11, 13, 15, 17, 19, 21)):
    """当日各时辰起局 -> 时段评级 + 吉门方位。rating: 2顺/1平/0缓。
    在基础评级(值使门吉凶 + 星 + 神 + 门迫)之上叠加格局修正, 原值保留在 rating_base/score_base。
    五不遇时(日干 + 时柱干支全合古籍十时柱表)基础分直接压到 WUBUYU_FLOOR, 并出 wubuyushi 布尔字段。"""
    out = []
    for h in hours:
        d = dt_base.replace(hour=h, minute=30)
        try:
            p = pan(d)
        except Exception:
            continue
        zs = p["zhishi"]
        score, factors = (2 if zs in GOOD_DOORS else (-2 if zs in BAD_DOORS else 0)), [zs]
        zsp = next((pp for pp, v in p["palaces"].items() if v["door"] == zs), None)
        zsv = p["palaces"].get(zsp, {})
        star_name = zsv.get("star") or ""
        if any(s in star_name for s in GOOD_STARS):
            score += 1; factors.append(star_name + "助")
        elif any(s in star_name for s in SLOW_STARS):
            score -= 1; factors.append(star_name + "缓")
        if zsv.get("god") in GOOD_GODS:
            score += .5; factors.append(zsv["god"] + "助")
        elif zsv.get("god") in SLOW_GODS:
            score -= .5; factors.append(zsv["god"] + "扰")
        if zsp and KE.get(DOOR_ELEM[zs]) == PALACE_ELEM[zsp]:
            score -= 1; factors.append("门迫")
        # --- 五不遇时: 时家奇门大凶时格, 《奇门法窍·卷六》「时干克日干, 甲日庚午时…
        #     癸日己未时, 此时出行, 主损折不利, 百事皆凶, 用兵尤忌, 虽有门奇, 切不可用」。
        #     判据合论干支(日干 + 时干 + 时支全合十时柱表), 依《御定奇门宝鉴·释义四十四则》
        #     「顺数者; 止论其干, 故名七杀。逆数者, 合论其干支, 故曰: 五不遇时」;
        #     只论干的读法书里叫七杀, 故己日乙亥时、庚日丙戌时不判。
        #     压在基础分上(不走格局叠加, 免得被 SCORE_CAP ±1.5 稀释), 效果是 rating 恒 0、
        #     score 低于任何非五不遇时段, 永不进 best 与 dir_range 候选。 ---
        wubuyushi = False
        if _geju is not None:
            try:
                wubuyushi = _geju.is_wubuyushi(p["day_gz"][0], p["hour_gz"][0], p["hour_gz"][1])
            except Exception:
                wubuyushi = False
        if wubuyushi:
            score = min(score, WUBUYU_FLOOR)
            factors.append("五不遇时·不宜用事")
        rating = 2 if score >= 2 else (0 if score <= -1 else 1)
        # --- 格局叠加: 只取值使宫 + 值符宫, 0.5 折封顶 ±1.5, 全局凶格只出文字 ---
        score_base, rating_base, forms = score, rating, []
        if _geju is not None:
            try:
                fx = _geju.formations(p, p.get("hour_zhi"))
                delta, gfactors, forms = _geju.hour_overlay(fx, p.get("zhishi_palace"), p.get("zhifu_palace"))
                if delta:
                    score = round(score + delta, 2)
                for t in gfactors:
                    if t not in factors:
                        factors.append(t)
                rating = 2 if score >= 2 else (0 if score <= -1 else 1)
            except Exception:
                score, rating, forms = score_base, rating_base, []
        kai = next((pp for pp, v in p["palaces"].items() if v["door"] == "开门"), None)
        sheng = next((pp for pp, v in p["palaces"].items() if v["door"] == "生门"), None)
        out.append({"start": h, "zhi": ZHI[((h + 1) // 2) % 12], "range": "%02d-%02d" % (h, h + 2),
                    "rating": rating, "score": score, "factors": factors, "zhishi": zs,
                    "rating_base": rating_base, "score_base": score_base, "formations": forms,
                    "wubuyushi": wubuyushi,
                    "kaimen_dir": PALACE_DIR.get(kai), "shengmen_dir": PALACE_DIR.get(sheng)})
    return out


def _formations_today(hours, limit=24):
    """全天各时段值得一提的格局摘要(给叙事层用), 每项 {range, name, kind, hint}。
    吉/凶 在前、中(五假/驿马/门制) 在后, 组内保持时间顺序; kind 保留给叙事层自筛。"""
    out, seen = [], set()
    for h in hours:
        for f in h.get("formations") or []:
            kind = f.get("kind")
            if kind not in ("吉", "凶", "中"):
                continue
            key = (h["range"], f.get("name"))
            if key in seen:
                continue
            seen.add(key)
            out.append({"range": h["range"], "name": f.get("name"), "kind": kind,
                        "hint": f.get("hint") or ""})
    out.sort(key=lambda x: 0 if x["kind"] in ("吉", "凶") else 1)   # stable, 组内仍按时段
    return out[:limit]


def day_summary(dt_base):
    """全天奇门概要: 局 + 时段 + 最佳时段吉方 + 攻守风格。"""
    noon = dt_base.replace(hour=11, minute=30)
    p = pan(noon)
    hours = day_hours(dt_base)
    best = [h for h in hours if h["rating"] == 2]
    slow = [h for h in hours if h["rating"] == 0]
    good_ratio = len(best) / max(1, len(hours))
    style = "宜主动推进" if good_ratio >= 0.5 else ("先观察,后推进" if good_ratio >= 0.25 else "宜守不宜攻")
    dirs = {}
    # --- 无 rating==2 的吉时段时, 取全天 score 最高段(并列取最早)并如实标 is_best=False ---
    #   时家奇门没有任何一派以某个固定时辰为默认吉时(《奇门法窍·卷六》「选时之法尤急…只五不遇时、
    #   避五入墓, 虽有门奇, 不宜取用」, 无吉时的正解是候时 / 择次吉)。
    #   dirs(开门/生门吉方) 跟随同一个 ref, 不置空 —— 否则吉方连同顺时一起丢。
    pool = [h for h in hours if not h.get("wubuyushi")] or hours   # 五不遇时段永不进候选
    if best:
        ref, dir_range_is_best = sorted(best, key=lambda h: (-h.get("score", 0), h["start"]))[0], True
    elif pool:
        ref, dir_range_is_best = sorted(pool, key=lambda h: (-h.get("score", 0), h["start"]))[0], False
    else:
        ref, dir_range_is_best = None, False
    # dir_note 给下游 / 接口用; 叙事层与前端如需同一句话请保持措辞一致。
    dir_note = None if (ref is None or dir_range_is_best) else ("今日无突出顺时, 相对可用 " + ref["range"])
    if ref:
        dirs = {"开门": ref["kaimen_dir"], "生门": ref["shengmen_dir"]}
    return {"ju": "%s%d局" % (p["dun"], p["ju"]), "yuan": p["yuan"], "jieqi": p["jieqi"],
            "method": "拆补法·转盘", "zhifu": p["zhifu"], "zhishi": p["zhishi"],
            "hours": hours, "style": style, "best_ranges": [h["range"] for h in best],
            "slow_ranges": [h["range"] for h in slow], "dirs": dirs,
            "formations_today": _formations_today(hours),
            "dir_range": ref["range"] if ref else None,
            "dir_range_is_best": dir_range_is_best, "dir_note": dir_note,
            "rule_version": RULE_VERSION}
