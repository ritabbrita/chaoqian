# -*- coding: utf-8 -*-
import random
import unittest

from chaoqian import liuyao


def _yao(pos, zhi, moving=False, kong=False, dark=False, bian=None, liuqin="兄弟"):
    """构造一支最小可用的爻(供 _analyze_sanhe / _build_fushen_candidates 用)。"""
    return {"pos": pos, "zhi": zhi, "wx": liuyao.ZHI_WX[zhi], "gan": None, "liuqin": liuqin,
            "moving": moving, "kong": kong, "dark_moving": dark, "bian": bian}


def _ben_yaos(lines, palace_elem, day_xunkong=""):
    """按 cast() 的口径把本卦装好(静卦), 供伏神端到端用例。"""
    ys = liuyao._zhuang(lines)
    for y in ys:
        y["liuqin"] = liuyao._liuqin(y["wx"], palace_elem)
        y["moving"] = False
        y["kong"] = y["zhi"] in (day_xunkong or "")
        y["bian"] = None
    return ys


def _future(n=24, start=0):
    return [("2030-08-%02d" % (i + 1), liuyao.ZHI[(i + start) % 12]) for i in range(n)]


def _zhi_of(days, zhi):
    return [d for d, z in days if z == zhi]


class FuFeiRelationTests(unittest.TestCase):
    def test_u1_five_relations_exhaustive(self):
        rel = liuyao._fu_fei_relation
        self.assertEqual("比和", rel("木", "木")[0])
        self.assertEqual("飞生伏", rel("木", "水")[0])
        self.assertEqual("伏生飞", rel("水", "木")[0])
        self.assertEqual("飞克伏", rel("水", "土")[0])
        self.assertEqual("伏克飞", rel("木", "土")[0])
        # 比和权重必须是 0 —— 古籍口诀未及, 不得按吉或凶赋权
        self.assertEqual(0.0, rel("木", "木")[1])
        self.assertIn("古籍口诀未及", rel("木", "木")[2])
        # 方向与相对大小: 飞生伏(最吉) > 伏克飞(吉) > 比和(0) > 伏生飞(小凶) > 飞克伏(最凶)
        order = [rel("木", "水")[1], rel("木", "土")[1], rel("木", "木")[1],
                 rel("水", "木")[1], rel("水", "土")[1]]
        self.assertEqual(order, sorted(order, reverse=True))
        # 绝对数值与 _line_strength 同量级 (±0.5~2)
        for _fu, _fei in (("木", "水"), ("木", "土"), ("水", "木"), ("水", "土")):
            self.assertLessEqual(abs(rel(_fu, _fei)[1]), 2.0)
            self.assertGreaterEqual(abs(rel(_fu, _fei)[1]), 0.5)


class UshenSortKeyTests(unittest.TestCase):
    def test_u2_moving_beats_strength(self):
        a = {"pos": 3, "zhi": "卯", "wx": "木", "moving": False, "strength_score": 3.0}
        b = {"pos": 4, "zhi": "巳", "wx": "火", "moving": True, "strength_score": 0.5}
        picked = sorted([a, b], key=lambda y: liuyao._ushen_sort_key(y, 1, "子", "申"))[0]
        self.assertIs(b, picked)

    def test_u3_lin_riyue_beats_near_shi_and_strength(self):
        a = {"pos": 4, "zhi": "申", "wx": "金", "moving": False, "strength_score": 0.0}   # 临日辰, 离世远
        b = {"pos": 2, "zhi": "卯", "wx": "木", "moving": False, "strength_score": 2.0}   # 不临日月, 近世且强
        picked = sorted([a, b], key=lambda y: liuyao._ushen_sort_key(y, 1, "子", "申"))[0]
        self.assertIs(a, picked)


class FuShenAvailabilityTests(unittest.TestCase):
    def test_u4_xiuqiu_with_support_is_conditional(self):
        fu = {"zhi": "子", "wx": "水", "kong": False}
        fly = {"zhi": "未", "wx": "土", "kong": False}
        av = liuyao._fushen_availability(fu, fly, "午", "申")   # 午月水囚, 申日金生水
        self.assertEqual("囚", av["wangshuai"])
        self.assertTrue(av["shengfu"]["sheng"])
        self.assertFalse(av["shengfu"]["lin"])
        self.assertEqual("conditional", av["availability"])

    def test_u5_wangxiang_without_support_is_available_and_strong(self):
        fu = {"zhi": "子", "wx": "水", "kong": False}
        fly = {"zhi": "戌", "wx": "土", "kong": False}
        av = liuyao._fushen_availability(fu, fly, "子", "寅")   # 子月水旺, 寅日不生不克水
        self.assertEqual("旺", av["wangshuai"])
        self.assertEqual("available", av["availability"])
        self.assertEqual("strong", av["strength_tier"])

    def test_u6_wangxiang_but_kong_is_conditional_not_blocked(self):
        fu = {"zhi": "子", "wx": "水", "kong": True}
        fly = {"zhi": "戌", "wx": "土", "kong": False}
        av = liuyao._fushen_availability(fu, fly, "酉", "寅")   # 酉月金生水 -> 相
        self.assertEqual("相", av["wangshuai"])
        self.assertNotEqual("blocked", av["availability"])
        self.assertEqual("conditional", av["availability"])
        ushen = dict(fu, hidden=True, moving=False, fly=fly, availability="conditional", wx="水")
        days = _future(24)
        hits = liuyao._yingqi_all(ushen, days, 24, "酉", "寅")
        hows = {h["how"] for h in hits}
        # 酉月子水为「相」-> 判假空(本项目选择), 不走空亡四态, 按不空之静爻走「逢值逢冲」:
        # 子日出「值用神」、午日出「冲用神」(kind 为 favorable)。
        self.assertNotIn("填实出空", hows)
        self.assertNotIn("冲空起用", hows)
        self.assertIn("值用神", hows)        # 逢子日
        self.assertIn("冲用神", hows)        # 逢午日(相 -> 冲之则暗动)
        self.assertTrue([h for h in hits if h["how"] == "值用神"][0]["date"] in _zhi_of(days, "子"))
        self.assertTrue([h for h in hits if h["how"] == "冲用神"][0]["date"] in _zhi_of(days, "午"))

    def test_u7_tianshandun_zisun_fushen_end_to_end(self):
        lines = [0, 0, 1, 1, 1, 1]                     # 天山遁
        self.assertEqual("天山遁", liuyao._hex_name(lines)[0])
        self.assertEqual(("乾", 2), liuyao.PALACE_MAP["天山遁"])
        yaos = _ben_yaos(lines, "金")
        self.assertNotIn("子孙", {y["liuqin"] for y in yaos})   # 本卦无子孙

        # 午月巳日: 皆火不生水, 水在午月为囚 -> 无用①休囚无气 + ③被旺相之飞神克害
        c1 = liuyao._build_fushen_candidates("乾", "金", yaos, "子孙", "午", "巳")
        self.assertEqual(1, len(c1))
        fu = c1[0]
        self.assertEqual((1, "子", "水"), (fu["pos"], fu["zhi"], fu["wx"]))
        self.assertEqual("辰", fu["fly"]["zhi"])
        self.assertEqual("飞克伏", fu["fu_fei"]["relation"])
        self.assertFalse(fu["shengfu"]["lin"] or fu["shengfu"]["sheng"])
        self.assertEqual("blocked", fu["availability"])
        self.assertIn("休囚无气", fu["availability_reasons"])

        c2 = liuyao._build_fushen_candidates("乾", "金", yaos, "子孙", "午", "申")
        fu2 = c2[0]
        self.assertEqual("conditional", fu2["availability"])
        days = _future(24)
        hits = liuyao._yingqi_all(dict(fu2, hidden=True), days, 24, "午", "申")
        chong = [h for h in hits if h["how"].startswith("冲飞神")]
        self.assertTrue(chong)
        self.assertIn(chong[0]["date"], _zhi_of(days, "戌"))

    def test_u7b_blocked_fushen_produces_no_chufu_candidate(self):
        yaos = _ben_yaos([0, 0, 1, 1, 1, 1], "金")
        fu = liuyao._build_fushen_candidates("乾", "金", yaos, "子孙", "午", "巳")[0]
        days = _future(24)
        hits = liuyao._yingqi_all(dict(fu, hidden=True), days, 24, "午", "巳")
        self.assertFalse([h for h in hits if h["how"].startswith("冲飞神")])
        notes = liuyao._yingqi_notes(dict(fu, hidden=True), True, False)
        self.assertTrue([n for n in notes if "终不能出" in n])

    def test_fushen_two_appear_flag(self):
        pure = liuyao._zhuang(list(liuyao.TRIGRAM_LINES["乾"]) * 2)
        fumu = [(p["pos"], p["zhi"]) for p in pure if liuyao._liuqin(p["wx"], "金") == "父母"]
        self.assertEqual([(3, "辰"), (6, "戌")], fumu)
        yaos = _ben_yaos([0, 0, 1, 1, 1, 1], "金")
        cands = liuyao._build_fushen_candidates("乾", "金", yaos, "父母", "子", "子")
        self.assertEqual(2, len(cands))
        self.assertTrue(all(c.get("fushen_two_appear") for c in cands))
        picked = sorted(cands, key=lambda y: liuyao._ushen_sort_key(y, 2, "子", "子"))[0]
        self.assertIn(picked["zhi"], ("辰", "戌"))      # 只取一, 不并列输出

    def test_two_appear_branch_is_unreachable_from_real_casts(self):
        import itertools
        from collections import Counter
        for bits in itertools.product([0, 1], repeat=6):
            lines = list(bits)
            name = liuyao._hex_name(lines)[0]
            pal, _shi = liuyao.PALACE_MAP[name]
            pe = liuyao.PALACE_ELEM[pal]
            have = {liuyao._liuqin(y["wx"], pe) for y in liuyao._zhuang(lines)}
            pure = liuyao._zhuang(list(liuyao.TRIGRAM_LINES[pal]) * 2)
            cnt = Counter(liuyao._liuqin(p["wx"], pe) for p in pure)
            for q in ("父母", "兄弟", "子孙", "妻财", "官鬼"):
                if q not in have:
                    self.assertEqual(1, cnt[q], "%s 缺%s" % (name, q))

    def test_all_eight_palaces_cover_five_liuqin(self):
        for pal, pe in liuyao.PALACE_ELEM.items():
            pure = liuyao._zhuang(list(liuyao.TRIGRAM_LINES[pal]) * 2)
            self.assertEqual({"父母", "兄弟", "子孙", "妻财", "官鬼"},
                             {liuyao._liuqin(p["wx"], pe) for p in pure}, pal)

    def test_missing_liuqin_is_defensive_not_exception(self):
        yaos = _ben_yaos([0, 0, 1, 1, 1, 1], "金")
        self.assertEqual([], liuyao._build_fushen_candidates("乾", "金", yaos, "不存在的六亲", "午", "巳"))


class DisplayFuShenTests(unittest.TestCase):
    def test_display_fushen_separate_from_yong_and_empty_for_bagua(self):
        yaos = _ben_yaos([0, 0, 1, 1, 1, 1], "金")
        disp = liuyao._display_fushen([0, 0, 1, 1, 1, 1], "乾", "金", yaos)
        self.assertTrue(disp)
        self.assertEqual({"子孙", "妻财"}, {d["liuqin"] for d in disp})
        for d in disp:
            self.assertIn(d["relation"], ("比和", "飞生伏", "伏生飞", "飞克伏", "伏克飞"))
            self.assertNotIn("availability", d)      # 展示型不带可用性/吉凶结论
        pure = _ben_yaos([1, 1, 1, 1, 1, 1], "金")
        self.assertEqual([], liuyao._display_fushen([1, 1, 1, 1, 1, 1], "乾", "金", pure))


class SanHeTests(unittest.TestCase):
    def _shui_ju(self, month="子", day="酉", kong5=False, jing3=True):
        yaos = [_yao(1, "申"), _yao(2, "申", moving=True), _yao(3, "辰" if jing3 else "子"),
                _yao(4, "申"), _yao(5, "子", moving=True, kong=kong5), _yao(6, "辰" if jing3 else "子")]
        return liuyao._analyze_sanhe(yaos, month, day, {"pos": 2, "zhi": "申", "wx": "金"}, 2, "金")

    def test_u8_static_yao_can_join_the_ju(self):
        s = self._shui_ju()
        self.assertEqual("三合", s["kind"])
        self.assertEqual("申子辰合水局", s["name"])
        self.assertEqual("成局即发", s["status"])
        self.assertEqual([2, 5], s["active_positions"])
        self.assertIn("静爻", {x["source"] for x in s["sources"] if x["zhi"] == "辰"})

    def test_u9_ju_does_not_depend_on_huashen_deling(self):
        for month, label in (("巳", "囚"), ("卯", "休")):
            s = self._shui_ju(month=month)
            self.assertEqual("三合", s["kind"], month)
            self.assertEqual("成局即发", s["status"], month)
            self.assertEqual(label, s["power"]["month_label"], month)
            self.assertEqual([], s["status_reasons"], month)
        wang = self._shui_ju(month="子")
        self.assertGreater(wang["power"]["score"], self._shui_ju(month="巳")["power"]["score"])

    def test_u9b_yuepo_member_defers_like_kong(self):
        s = self._shui_ju(month="午")
        self.assertEqual("三合", s["kind"])
        self.assertEqual("待填实", s["status"])
        self.assertNotEqual("未成(动爻不足)", s["status"])
        po = [x for x in s["yingqi"] if x.get("cause") == "月破待填实"]
        self.assertEqual(["子"], [x["zhi"] for x in po])
        self.assertIn("填实月破", po[0]["how"])
        self.assertIn("月破待填实", s["status_reasons"])
        self.assertEqual("囚", s["power"]["month_label"])   # 化神仍不得令, 但不影响成局判定

    def test_kong_po_mu_coexist_reports_kong_first(self):
        # 午月 -> 子月破; 辰日 -> 子/辰入日墓; pos2 申值旬空
        yaos = [_yao(1, "酉"), _yao(2, "申", moving=True, kong=True), _yao(3, "辰"),
                _yao(4, "酉"), _yao(5, "子", moving=True), _yao(6, "酉")]
        s = liuyao._analyze_sanhe(yaos, "午", "辰", {"pos": 2, "zhi": "申", "wx": "金"}, 2, "金")
        self.assertEqual("待填实", s["status"])                    # 空 为主因
        self.assertEqual(["旬空待填实", "月破待填实", "入墓待冲开"], s["status_reasons"])
        causes = [x["cause"] for x in s["yingqi"]]
        self.assertEqual(["旬空待填实", "月破待填实", "入墓待冲开"], causes)
        self.assertEqual(["申", "子", "戌"], [x["zhi"] for x in s["yingqi"]])

    def test_u10_xu_yi_dai_yong(self):
        yaos = [_yao(1, "申"), _yao(2, "申", moving=True), _yao(3, "子"),
                _yao(4, "申"), _yao(5, "子", moving=True), _yao(6, "子")]
        s = liuyao._analyze_sanhe(yaos, "卯", "酉", {"pos": 2, "zhi": "申", "wx": "金"}, 2, "金")
        self.assertEqual("虚一待用", s["status"])
        self.assertEqual("辰", s["missing"])
        self.assertEqual(["辰"], [x["zhi"] for x in s["yingqi"]])
        self.assertIn("逢辰日", s["yingqi"][0]["how"])
        self.assertNotEqual("半合", s["kind"])     # 虚一待用已占该五行, 不再另报半合

    def test_u11_kong_defers_to_dai_tianshi(self):
        s = self._shui_ju(kong5=True)
        self.assertEqual("三合", s["kind"])
        self.assertEqual("待填实", s["status"])
        self.assertEqual(["子"], [x["zhi"] for x in s["yingqi"]])
        self.assertIn("填实", s["yingqi"][0]["how"])
        self.assertEqual(["旬空待填实"], s["status_reasons"])

    def test_u11b_mu_defers_to_dai_chong_mu_kai(self):
        yaos = [_yao(1, "酉"), _yao(2, "申", moving=True), _yao(3, "辰"),
                _yao(4, "酉"), _yao(5, "子", moving=True), _yao(6, "酉")]
        s = liuyao._analyze_sanhe(yaos, "子", "辰", {"pos": 2, "zhi": "申", "wx": "金"}, 2, "金")
        self.assertEqual("待冲墓开", s["status"])
        self.assertEqual(["戌"], [x["zhi"] for x in s["yingqi"]])
        self.assertEqual(["入墓待冲开"], s["status_reasons"])

    def test_u12_all_static_banhe_does_not_count(self):
        yaos = [_yao(1, "寅"), _yao(2, "申"), _yao(3, "寅"),
                _yao(4, "酉"), _yao(5, "子"), _yao(6, "酉")]
        s = liuyao._analyze_sanhe(yaos, "卯", "卯", {"pos": 2, "zhi": "申", "wx": "金"}, 2, "金")
        self.assertEqual("无", s["status"])
        self.assertNotEqual("半合", s["kind"])
        # 正对照: 同样两支, 其中一支发动即成半合
        yaos2 = [_yao(1, "寅"), _yao(2, "申", moving=True), _yao(3, "寅"),
                 _yao(4, "酉"), _yao(5, "子"), _yao(6, "酉")]
        s2 = liuyao._analyze_sanhe(yaos2, "卯", "卯", {"pos": 2, "zhi": "申", "wx": "金"}, 2, "金")
        self.assertEqual("半合", s2["kind"])
        self.assertEqual("申子半合水", s2["name"])

    def test_v715_banhe_one_moving_with_zhongshen_still_forms_a_ju(self):
        ushen = {"pos": 2, "zhi": "申", "wx": "金"}
        # (a) 明动: 申动 + 子静(中神在) -> 申子半合水·成局即发
        ming = [_yao(1, "寅"), _yao(2, "申", moving=True), _yao(3, "寅"),
                _yao(4, "酉"), _yao(5, "子"), _yao(6, "酉")]
        s = liuyao._analyze_sanhe(ming, "卯", "卯", ushen, 2, "金")
        self.assertEqual("半合", s["kind"])
        self.assertEqual("申子半合水", s["name"])
        self.assertEqual("成局即发", s["status"])
        self.assertEqual([2], s["active_positions"])
        self.assertEqual("长生+帝旺", s["ban_type"])
        self.assertNotEqual(0.0, s["bonus"])       # 半合照旧反哺打分, 不是死代码
        # (b) 暗动一样算「动」
        an = [_yao(1, "寅"), _yao(2, "申", dark=True), _yao(3, "寅"),
              _yao(4, "酉"), _yao(5, "子"), _yao(6, "酉")]
        s2 = liuyao._analyze_sanhe(an, "卯", "卯", ushen, 2, "金")
        self.assertEqual("半合", s2["kind"])
        self.assertEqual([2], s2["active_positions"])
        # (c) 须含旺神(中神): 无中神的拱合(申辰)不入 BAN_SANHE_TABLE, 一爻动也不成局
        wu = [_yao(1, "寅"), _yao(2, "申", moving=True), _yao(3, "寅"),
              _yao(4, "酉"), _yao(5, "辰"), _yao(6, "酉")]
        s3 = liuyao._analyze_sanhe(wu, "卯", "卯", ushen, 2, "金")
        self.assertEqual("无", s3["kind"])
        self.assertEqual("无", s3["status"])
        self.assertIn("须含旺神", liuyao.SANHE_SCHOOL_NOTE)

    def test_v715_banhe_no_backdoor_when_sanhe_is_weicheng(self):
        yaos = [_yao(1, "辰"), _yao(2, "申", moving=True), _yao(3, "寅"),
                _yao(4, "酉"), _yao(5, "子"), _yao(6, "酉")]
        s = liuyao._analyze_sanhe(yaos, "卯", "卯", {"pos": 2, "zhi": "申", "wx": "金"}, 2, "金")
        self.assertEqual("三合", s["kind"])
        self.assertEqual("未成(动爻不足)", s["status"])
        self.assertNotIn("半合", {f["kind"] for f in s["all"]})
        self.assertEqual(0.0, s["bonus"])          # 未成不反哺打分
        self.assertIn("其子集半合不再成局", liuyao.SANHE_SCHOOL_NOTE)
        self.assertIn("不挂古籍名下", liuyao.SANHE_SCHOOL_NOTE)

    def test_u13_ju_feeds_score_and_verdict(self):
        ushen = {"pos": 3, "zhi": "卯", "wx": "木"}
        base = [_yao(1, "亥", moving=True), _yao(2, "卯"), _yao(3, "卯", moving=True),
                _yao(4, "丑"), _yao(5, "未"), _yao(6, "亥")]
        shi_in = liuyao._analyze_sanhe(base, "卯", "子", ushen, 1, "金")   # 世=pos1 亥, 在局
        self.assertEqual("亥卯未合木局", shi_in["name"])
        self.assertEqual("成局即发", shi_in["status"])
        self.assertGreater(shi_in["bonus"], 0)
        self.assertLessEqual(shi_in["bonus"], 2.0)               # 三合加成上限 +2
        self.assertEqual("世爻在局为美", shi_in["relation_to_shi"])
        self.assertEqual("妻财", shi_in["liuqin_ju"])
        self.assertIn("财旺生官", shi_in["verdict"])
        self.assertEqual("局与用神同类", shi_in["relation_to_ushen"])
        shi_out = liuyao._analyze_sanhe(base, "卯", "子", ushen, 4, "金")  # 世=pos4 丑土, 被木局克
        self.assertEqual("局克世爻，则以凶推", shi_out["relation_to_shi"])

    def test_banhe_bonus_is_halved_against_full(self):
        ushen = {"pos": 3, "zhi": "卯", "wx": "木"}
        full = [_yao(1, "亥", moving=True), _yao(2, "酉"), _yao(3, "卯", moving=True),
                _yao(4, "丑"), _yao(5, "未"), _yao(6, "酉")]
        # 半合: 亥动、卯静 -> 亥卯未组只有 1 爻动, 不够「虚一待用」, 落半合亥卯
        half = [_yao(1, "亥", moving=True), _yao(2, "酉"), _yao(3, "卯"),
                _yao(4, "丑"), _yao(5, "酉"), _yao(6, "酉")]
        f = liuyao._analyze_sanhe(full, "卯", "子", ushen, 1, "金")
        h = liuyao._analyze_sanhe(half, "卯", "子", ushen, 1, "金")
        self.assertEqual("三合", f["kind"])
        self.assertEqual("半合", h["kind"])
        self.assertLessEqual(h["bonus"], 1.0)
        self.assertLess(h["bonus"], f["bonus"])

    def test_banhe_table_is_the_eight_with_zhongshen(self):
        self.assertEqual(8, len(liuyao.BAN_SANHE_TABLE))
        for g in liuyao.BAN_SANHE_TABLE:
            self.assertTrue({"子", "午", "卯", "酉"} & set(g["branches"]), g["name"])
        pairs = {frozenset(g["branches"]) for g in liuyao.BAN_SANHE_TABLE}
        for gong in (("申", "辰"), ("亥", "未"), ("寅", "戌"), ("巳", "丑")):
            self.assertNotIn(frozenset(gong), pairs)

    def test_school_note_is_emitted(self):
        s = self._shui_ju()
        self.assertIn("增删卜易", s["school_note"])
        self.assertIn("静爻", s["school_note"])


class YingQiTests(unittest.TestCase):
    def test_u14_static_zhi_chong_vs_moving_zhi_he(self):
        days = _future(24)
        static = {"zhi": "卯", "wx": "木", "moving": False, "kong": False}
        hs = liuyao._yingqi_all(static, days, 24, "子", "子")
        by_how = {}
        for h in hs:
            by_how.setdefault(h["how"], []).append(h["date"])
        self.assertTrue(set(by_how["值用神"]) & set(_zhi_of(days, "卯")))
        self.assertTrue(set(by_how["冲用神"]) & set(_zhi_of(days, "酉")))
        self.assertNotIn("合用神", by_how)                        # 静爻不出合

        moving = {"zhi": "卯", "wx": "木", "moving": True, "kong": False}
        hm = {h["how"] for h in liuyao._yingqi_all(moving, days, 24, "子", "子")}
        hm_dates = {(h["how"], h["date"]) for h in liuyao._yingqi_all(moving, days, 24, "子", "子")}
        self.assertIn("值用神", hm)
        self.assertIn("合用神", hm)                               # LIUHE[卯]=戌
        self.assertTrue([d for w, d in hm_dates if w == "合用神" and d in _zhi_of(days, "戌")])

    def test_u15_bian_zhi_enters_candidates(self):
        days = _future(24)
        u = {"zhi": "卯", "wx": "木", "moving": True, "kong": False, "bian": {"zhi": "午", "wx": "火"}}
        hits = liuyao._yingqi_all(u, days, 24, "子", "子")
        got = [h for h in hits if h["how"] == "逢变爻午"]
        self.assertTrue(got)
        self.assertIn(got[0]["date"], _zhi_of(days, "午"))

    def test_u16_he_ban_switches_to_chong_kai(self):
        days = _future(24)
        u = {"zhi": "卯", "wx": "木", "moving": True, "kong": False, "day_combined": True}
        hits = liuyao._yingqi_all(u, days, 24, "子", "戌")
        hows = {h["how"] for h in hits}
        self.assertNotIn("合用神", hows)
        self.assertIn("冲开日合", hows)
        ck = [h for h in hits if h["how"] == "冲开日合"][0]
        self.assertIn(ck["date"], _zhi_of(days, "酉"))

    def test_yq02_kong_four_states(self):
        days = _future(24)
        base = {"zhi": "卯", "wx": "木", "kong": True}   # 申月 -> 木死; 未日 -> 不临不生 => 真空
        static = {h["how"] for h in liuyao._yingqi_all(dict(base, moving=False), days, 24, "申", "未")}
        self.assertIn("冲空起用", static)      # 空而静者, 冲之则起
        self.assertIn("填实出空", static)
        changing = {h["how"] for h in liuyao._yingqi_all(dict(base, moving=True), days, 24, "申", "未")}
        self.assertIn("动空冲实", changing)    # 空而动者, 冲之则实
        richong = {h["how"] for h in liuyao._yingqi_all(dict(base, moving=False, day_clashed=True), days, 24, "申", "酉")}
        self.assertIn("冲空转实", richong)
        yuejian = {h["how"] for h in liuyao._yingqi_all(dict(base, moving=False), days, 24, "卯", "子")}
        self.assertNotIn("冲空起用", yuejian)  # 旬空临月建不为真空, 不走空亡分支
        self.assertNotIn("填实出空", yuejian)

    def test_v715_false_kong_not_day_clashed_keeps_the_same_days(self):
        days = _future(24)
        base = {"zhi": "卯", "wx": "木", "kong": True, "moving": False}
        for month, day, why in (("子", "未", "月令相"), ("申", "子", "日辰生")):
            hits = liuyao._yingqi_all(dict(base), days, 24, month, day)
            hows = {h["how"] for h in hits}
            self.assertNotIn("填实出空", hows, why)
            self.assertNotIn("冲空起用", hows, why)
            self.assertIn("值用神", hows, why)                       # 卯日仍在候选里
            self.assertIn("冲用神", hows, why)                       # 酉日仍在候选里
            solid = liuyao._yingqi_all(dict(base, kong=False), days, 24, month, day)
            self.assertEqual({h["date"] for h in solid}, {h["date"] for h in hits}, why)

    def test_v715_false_kong_day_clashed_drops_the_chong_day(self):
        days = _future(24)
        dark_false_kong = {"zhi": "子", "wx": "水", "kong": True, "moving": False,
                           "dark_moving": True, "day_clashed": True}
        hits = liuyao._yingqi_all(dark_false_kong, days, 24, "申", "午")
        self.assertEqual("相", liuyao._wangshuai("水", "申")[0])
        you = [h for h in hits if h["date"] in _zhi_of(days, "午")]
        self.assertEqual([], you, "假空+被日冲: 冲日(午)不再单列任何候选")
        hows = {h["how"] for h in hits}
        self.assertNotIn("冲空转实", hows)
        self.assertNotIn("冲空起用", hows)
        self.assertNotIn("填实出空", hows)
        self.assertNotIn("逢冲日破", hows)                            # 极性反转在这一类上同样不许发生
        self.assertIn("暗动被引发之期", hows)                          # 子日由暗动线承接
        # 对照: 真空 + 真被日冲(卯木用神, 申月木死、酉日冲卯, 生产路径可达的组合), 空亡四态照旧,
        # 冲日仍出 critical「冲空转实」
        true_kong = {"zhi": "卯", "wx": "木", "kong": True, "moving": False,
                     "dark_moving": False, "day_clashed": True}
        rich = liuyao._yingqi_all(true_kong, days, 24, "申", "酉")
        self.assertIn("冲空转实", {h["how"] for h in rich})

    def test_v715_false_kong_never_flips_into_ri_po(self):
        days = _future(24)
        base = {"zhi": "戌", "wx": "土", "kong": True, "moving": False}
        # 子月土囚 + 午日火生土 -> 假空; 冲支 = 辰
        hits = liuyao._yingqi_all(dict(base), days, 24, "子", "午")
        self.assertEqual("囚", liuyao._wangshuai("土", "子")[0])     # 月令并不旺相
        chong = [h for h in hits if h["date"] in _zhi_of(days, "辰")]
        hows = {h["how"] for h in chong}
        self.assertIn("冲用神", hows)
        self.assertNotIn("逢冲日破", hows)
        self.assertEqual({"favorable"}, {h["kind"] for h in chong if h["how"] == "冲用神"})
        self.assertIn("假空", [h for h in chong if h["how"] == "冲用神"][0]["basis"])
        solid = liuyao._yingqi_all(dict(base, kong=False), days, 24, "子", "午")
        self.assertIn("逢冲日破", {h["how"] for h in solid if h["date"] in _zhi_of(days, "辰")})

    def test_yq03_dark_moving_is_stated_apart_from_moving(self):
        days = _future(24)
        dark = {"zhi": "卯", "wx": "木", "moving": False, "dark_moving": True, "kong": False}
        hows = {h["how"] for h in liuyao._yingqi_all(dark, days, 24, "子", "酉")}
        self.assertIn("暗动被引发之期", hows)
        self.assertNotIn("动爻逢冲", hows)
        bright = {"zhi": "卯", "wx": "木", "moving": True, "kong": False}
        self.assertIn("动爻逢冲", {h["how"] for h in liuyao._yingqi_all(bright, days, 24, "子", "子")})

    def test_yq04_weak_and_broken_turn_into_positive_days(self):
        days = _future(24)
        weak = {"zhi": "卯", "wx": "木", "moving": False, "kong": False}
        hows = {h["how"] for h in liuyao._yingqi_all(weak, days, 24, "申", "申", weak=True)}
        self.assertIn("得生扶之日", hows)
        self.assertIn("用神长生之日", hows)     # 木长生在亥
        self.assertIn("用神帝旺之日", hows)     # 木帝旺在卯
        broken = {"zhi": "卯", "wx": "木", "moving": False, "kong": False, "month_broken": True}
        bh = {h["how"] for h in liuyao._yingqi_all(broken, days, 24, "酉", "子")}
        self.assertIn("填实月破", bh)
        self.assertIn("月破逢合", bh)

    def test_every_candidate_carries_kind_and_basis(self):
        """工程改进: 每条应期带 kind(favorable/unfavorable/critical) 与 basis(出处), 供叙事层分级。"""
        days = _future(24)
        u = {"zhi": "卯", "wx": "木", "moving": True, "kong": False}
        for h in liuyao._yingqi_all(u, days, 24, "子", "子"):
            self.assertIn(h["kind"], ("favorable", "unfavorable", "critical"))
            self.assertTrue(h["basis"])
            self.assertNotIn("_prio", h)


class YingQiV714Tests(unittest.TestCase):

    def test_v714_a_xiuqiu_chong_is_ripo_not_favorable(self):
        """(a) 休囚死之用神逢冲 -> unfavorable「逢冲日破」, 且同日不再出 favorable 的「冲用神」。"""
        days = _future(24)
        u = {"zhi": "卯", "wx": "木", "moving": False, "kong": False}
        hits = liuyao._yingqi_all(u, days, 24, "申", "子")     # 申月: 木死
        self.assertEqual("死", liuyao._wangshuai("木", "申")[0])
        po = [h for h in hits if h["how"] == "逢冲日破"]
        self.assertTrue(po)
        self.assertEqual({"unfavorable"}, {h["kind"] for h in po})
        self.assertLessEqual({h["date"] for h in po}, set(_zhi_of(days, "酉")))   # 卯之冲在酉
        self.assertIn("增删卜易", po[0]["basis"])
        hows = {h["how"] for h in hits}
        self.assertNotIn("冲用神", hows)                       # 坏日子不得再挂利好标签
        for d in {h["date"] for h in po}:                      # 该日无任何 favorable 逢冲项
            same = [h for h in hits if h["date"] == d]
            self.assertFalse([h for h in same if h["kind"] == "favorable" and "冲" in h["how"]])
        # 囚(木克月建土)同样走日破
        self.assertEqual("囚", liuyao._wangshuai("木", "未")[0])
        qiu = {h["how"] for h in liuyao._yingqi_all(u, days, 24, "未", "子")}
        self.assertIn("逢冲日破", qiu)
        self.assertNotIn("冲用神", qiu)

    def test_v714_b_wangxiang_chong_stays_favorable(self):
        """(b) 回归锁: 旺/相之用神逢冲仍是暗动(favorable), 门禁不得误伤。"""
        days = _future(24)
        u = {"zhi": "卯", "wx": "木", "moving": False, "kong": False}
        for m, expect in (("寅", "旺"), ("子", "相")):
            self.assertEqual(expect, liuyao._wangshuai("木", m)[0])
            hits = liuyao._yingqi_all(u, days, 24, m, "子")
            chong = [h for h in hits if h["how"] == "冲用神"]
            self.assertTrue(chong, m)
            self.assertEqual({"favorable"}, {h["kind"] for h in chong})
            self.assertLessEqual({h["date"] for h in chong}, set(_zhi_of(days, "酉")))
            self.assertNotIn("逢冲日破", {h["how"] for h in hits})

    def test_v714_c_ushen_ri_mu_gives_chong_mu_kai_ku(self):
        """(c) 金用神逢辛丑日(静而不空): 出 critical「冲开丑墓库」(未日, prio 0) + notes 入墓提示。"""
        days = _future(24)
        u = {"zhi": "酉", "wx": "金", "moving": False, "kong": False}
        hits = liuyao._yingqi_all(u, days, 24, "酉", "丑")      # 金墓于丑, 日辰即墓
        mu = [h for h in hits if h["how"] == "冲开丑墓库"]
        self.assertTrue(mu)
        self.assertEqual("critical", mu[0]["kind"])
        self.assertLessEqual({h["date"] for h in mu}, set(_zhi_of(days, "未")))   # 丑之冲在未
        self.assertIn("入三墓俱喜冲开", mu[0]["basis"])
        # 出墓那一支不再单列候选(触发条件与「值用神」相同), 只并进当天「值用神」的 basis
        self.assertFalse([h for h in hits if h["how"] == "值用本气出墓"])
        zhi_yong = [h for h in hits if h["how"] == "值用神"]
        self.assertTrue(zhi_yong)
        self.assertLessEqual({h["date"] for h in zhi_yong}, set(_zhi_of(days, "酉")))
        self.assertTrue(all("兼作出墓论" in h["basis"] for h in zhi_yong), zhi_yong)
        # prio 0: 未土生金, weak 时同日另有「得生扶之日」(prio 3), 冲墓须排在它前面
        wk = liuyao._yingqi_all(u, days, 24, "酉", "丑", weak=True)
        same = [h["how"] for h in wk if h["date"] == mu[0]["date"]]
        self.assertIn("得生扶之日", same)
        self.assertEqual("冲开丑墓库", same[0])
        notes = liuyao._yingqi_notes(u, False, False, "丑")
        self.assertTrue([n for n in notes if "入日辰墓" in n or ("入" in n and "丑" in n and "未" in n)], notes)

    def test_v714_c3_chumu_merges_into_zhiyongshen_not_a_separate_slot(self):
        days = _future(24)
        u = {"zhi": "酉", "wx": "金", "moving": False, "kong": False}
        you_days = set(_zhi_of(days, "酉"))

        in_mu = liuyao._yingqi_all(u, days, 24, "酉", "丑")      # 金墓于丑, 日辰即墓
        self.assertFalse([h for h in in_mu if "出墓" in h["how"]])
        zy = [h for h in in_mu if h["how"] == "值用神"]
        self.assertTrue(zy)
        self.assertEqual(you_days, {h["date"] for h in zy})
        for h in zy:
            self.assertEqual("favorable", h["kind"])
            self.assertIn("静爻逢值逢冲", h["basis"])        # 原依据不丢
            self.assertIn("入丑墓", h["basis"])
            self.assertIn("兼作出墓论", h["basis"])
            self.assertIn("增删卜易", h["basis"])
            self.assertEqual(1, h["basis"].count("兼作出墓论"))   # 不重复追加

        # 同一用神不入墓(日辰为子): 「值用神」照旧, basis 不带出墓字样
        no_mu = liuyao._yingqi_all(u, days, 24, "酉", "子")
        zy2 = [h for h in no_mu if h["how"] == "值用神"]
        self.assertEqual(you_days, {h["date"] for h in zy2})
        self.assertFalse([h for h in zy2 if "出墓" in h["basis"]])
        # 每天每条 how 仍唯一, 且入墓没凭空多出候选日期
        self.assertEqual(len({(h["date"], h["how"]) for h in in_mu}), len(in_mu))
        self.assertLessEqual({h["date"] for h in in_mu if h["how"] == "值用神"},
                             {h["date"] for h in no_mu if h["how"] == "值用神"})

    def test_v714_c2_ushen_hua_mu_uses_bian_zhi(self):
        """(c-2) 动而化墓: 变爻之支(cast() 里是 ushen['bian']['zhi'])即墓库时同样出候选。"""
        days = _future(24)
        u = {"zhi": "酉", "wx": "金", "moving": True, "kong": False,
             "bian": {"gan": "癸", "zhi": "丑", "wx": "土", "liuqin": "父母", "relation": "化耗"}}
        hits = liuyao._yingqi_all(u, days, 24, "酉", "子")      # 日辰非墓, 只有化墓
        self.assertIn("冲开丑墓库", {h["how"] for h in hits})
        notes = liuyao._yingqi_notes(u, False, False, "子")
        self.assertTrue([n for n in notes if "变爻" in n and "丑" in n], notes)
        # 变爻不是墓库支就不该出
        u2 = dict(u, bian={"zhi": "午", "wx": "火"})
        self.assertNotIn("冲开丑墓库", {h["how"] for h in liuyao._yingqi_all(u2, days, 24, "酉", "子")})

    def test_v714_d_tu_ushen_self_mu_excluded(self):
        days = _future(24)
        u = {"zhi": "丑", "wx": "土", "moving": False, "kong": False}
        hits = liuyao._yingqi_all(u, days, 24, "午", "辰")
        self.assertFalse([h for h in hits if "墓库" in h["how"] or "出墓" in h["how"]], hits)
        self.assertFalse([n for n in liuyao._yingqi_notes(u, False, False, "辰") if "墓" in n])
        u2 = {"zhi": "丑", "wx": "土", "moving": True, "kong": False, "bian": {"zhi": "辰", "wx": "土"}}
        self.assertFalse([h for h in liuyao._yingqi_all(u2, days, 24, "午", "子") if "墓库" in h["how"]])

    def test_v714_e_line_strength_dark_moving_uses_wangshuai(self):
        xiang = {"pos": 3, "zhi": "卯", "wx": "木", "moving": False}
        score, factors = liuyao._line_strength(xiang, "子", "酉")   # 子月生卯木(相) + 酉日克且冲
        self.assertEqual("相", liuyao._wangshuai("木", "子")[0])
        self.assertIn("日冲暗动", factors)
        self.assertTrue(xiang.get("dark_moving"))
        self.assertIn("月建生", factors)
        self.assertIn("日辰克", factors)                            # 旧代理: +1-1=0, 不 >0 -> 误判日破
        si = {"pos": 3, "zhi": "卯", "wx": "木", "moving": False}
        _s2, f2 = liuyao._line_strength(si, "申", "酉")             # 申月木死
        self.assertIn("日冲", f2)
        self.assertNotIn("日冲暗动", f2)
        self.assertFalse(si.get("dark_moving"))
        po = {"pos": 3, "zhi": "戌", "wx": "土", "moving": False}
        _s3, f3 = liuyao._line_strength(po, "辰", "辰")             # 土旺但月破(辰戌自冲组)
        self.assertEqual("旺", liuyao._wangshuai("土", "辰")[0])
        self.assertIn("月破", f3)
        self.assertIn("日冲", f3)
        self.assertNotIn("日冲暗动", f3)
        self.assertFalse(po.get("dark_moving"))

    def test_v714_f_unfavorable_never_displaces_favorable_in_top3(self):
        hits = [{"date": "2030-08-02", "how": "逢冲日破", "kind": "unfavorable"},
                {"date": "2030-08-05", "how": "值用神", "kind": "favorable"},
                {"date": "2030-08-07", "how": "冲空转实", "kind": "critical"}]
        self.assertEqual(["值用神", "冲空转实", "逢冲日破"],
                         [h["how"] for h in liuyao._yingqi_top(hits, 3)])
        self.assertEqual(["值用神", "冲空转实"], [h["how"] for h in liuyao._yingqi_top(hits, 2)])
        # 吉项不足时不利项补位(前端专业模式对 unfavorable 已有 ⚠ 前置)
        self.assertEqual(["逢冲日破"], [h["how"] for h in liuyao._yingqi_top(hits[:1], 3)])
        self.assertEqual([], liuyao._yingqi_top([], 3))

    def test_v714_g_cast_top3_partition_invariant(self):
        """(g) 端到端: 随机 60 卦, yingqi 里不利项一律排在吉项之后, 且必然是 yingqi_all 的子集。"""
        future = [("2030-08-%02d" % (i + 1), liuyao.ZHI[i % 12]) for i in range(28)]
        for seed in range(60):
            x = liuyao.cast("测试", "财务", 28, "壬辰", "未", "午未", future, rng=random.Random(seed))
            kinds = [h["kind"] for h in x["yingqi"]]
            bad_idx = [i for i, k in enumerate(kinds) if k == "unfavorable"]
            good_idx = [i for i, k in enumerate(kinds) if k != "unfavorable"]
            if bad_idx and good_idx:
                self.assertLess(max(good_idx), min(bad_idx), "seed=%d" % seed)
            allset = {(h["date"], h["how"]) for h in x["yingqi_all"]}
            for h in x["yingqi"]:
                self.assertIn((h["date"], h["how"]), allset, "seed=%d" % seed)


class LiuYaoV715Tests(unittest.TestCase):

    def test_v715_changsheng_tables_are_one_school_per_element(self):
        for wx in ("木", "火", "土", "金", "水"):
            cs = liuyao.ZHI.index(liuyao.CHANGSHENG[wx])
            self.assertEqual(liuyao.ZHI[(cs + 4) % 12], liuyao.DIWANG[wx], "%s 帝旺" % wx)
            self.assertEqual(liuyao.ZHI[(cs + 8) % 12], liuyao.MU[wx], "%s 墓" % wx)
            self.assertEqual(liuyao.ZHI[(cs + 9) % 12], liuyao.JUE[wx], "%s 绝" % wx)
        # 土 = 水 (水土同宫), 且不得再等于火那一环
        for tbl in (liuyao.CHANGSHENG, liuyao.DIWANG, liuyao.MU, liuyao.JUE):
            self.assertEqual(tbl["水"], tbl["土"])
        self.assertEqual(("申", "子", "辰", "巳"),
                         (liuyao.CHANGSHENG["土"], liuyao.DIWANG["土"],
                          liuyao.MU["土"], liuyao.JUE["土"]))
        self.assertNotEqual(liuyao.CHANGSHENG["火"], liuyao.CHANGSHENG["土"])

    def test_v715_tu_ushen_shengwang_days_follow_shui_tu_tonggong(self):
        days = _future(24)
        u = {"zhi": "丑", "wx": "土", "moving": False, "kong": False}
        hits = liuyao._yingqi_all(u, days, 24, "寅", "卯", weak=True)   # 寅月土死 -> weak
        cs = [h for h in hits if h["how"] == "用神长生之日"]
        dw = [h for h in hits if h["how"] == "用神帝旺之日"]
        self.assertTrue(cs and dw)
        self.assertIn(cs[0]["date"], _zhi_of(days, "申"))
        self.assertIn(dw[0]["date"], _zhi_of(days, "子"))
        self.assertNotIn(cs[0]["date"], _zhi_of(days, "寅"))
        self.assertNotIn(dw[0]["date"], _zhi_of(days, "午"))

    def _kong_delta(self, zhi, wx, month, day):
        """同一支 kong=False / kong=True 两次打分之差, 以及带 kong 那次的 factors。"""
        a, _fa = liuyao._line_strength(
            {"pos": 1, "zhi": zhi, "wx": wx, "moving": False, "kong": False}, month, day)
        b, fb = liuyao._line_strength(
            {"pos": 1, "zhi": zhi, "wx": wx, "moving": False, "kong": True}, month, day)
        return round(a - b, 2), fb

    def test_v715_false_kong_costs_half_true_kong_costs_one_and_a_half(self):
        for month, day, why in (("卯", "未", "临月建(旺·野鹤原文)"),
                                ("子", "未", "月建生(相·本项目选择)"),
                                ("申", "子", "日辰生(野鹤原文)")):
            delta, factors = self._kong_delta("卯", "木", month, day)
            self.assertEqual(0.5, delta, why)
            self.assertIn("旬空(假空)", factors, why)
            self.assertNotIn("旬空(真空)", factors, why)
        # 真空侧: 死/囚/休 三档且无日辰生扶, 一律仍扣 1.5 (死 = 野鹤原文举例, 囚/休 = 本项目从严)
        for month, day, want_ws in (("申", "未", "死"), ("未", "未", "囚"), ("午", "午", "休")):
            delta, factors = self._kong_delta("卯", "木", month, day)
            self.assertEqual(want_ws, liuyao._wangshuai("木", month)[0], month)
            self.assertEqual(1.5, delta, month)
            self.assertIn("旬空(真空)", factors, month)
        _s, f3 = liuyao._line_strength(
            {"pos": 1, "zhi": "卯", "wx": "木", "moving": False, "kong": True}, "申", "酉")
        self.assertIn("空逢冲起", f3)
        self.assertFalse([x for x in f3 if x.startswith("旬空")])


class CastContractTests(unittest.TestCase):
    """cast() 返回结构的契约: 关键字段齐全、语义稳定。"""

    FUTURE = [("2030-08-%02d" % (i + 1), liuyao.ZHI[i % 12]) for i in range(28)]

    def _cast(self, seed, cat="财务"):
        return liuyao.cast("测试", cat, 28, "壬辰", "未", "午未", self.FUTURE, rng=random.Random(seed))

    def test_rule_version(self):
        self.assertEqual("chaoqian-liuyao-0.1", liuyao.RULE_VERSION)

    def test_result_keys_all_present(self):
        x = self._cast(42)
        for k in ("throws", "lines", "moving", "ben", "bian", "palace", "palace_elem", "shi", "ying",
                  "yaos", "ushen", "wangshuai", "day_note", "strength_score", "strength_label",
                  "factors", "hex_relation", "yingqi", "rule_version"):
            self.assertIn(k, x, k)
        for k in ("pos", "liuqin", "zhi", "wx", "kong", "hidden", "month_broken",
                  "day_combined", "moving", "note"):
            self.assertIn(k, x["ushen"], k)
        self.assertLessEqual(len(x["yingqi"]), 3)
        self.assertEqual(len({(h["date"], h["how"]) for h in x["yingqi"]}), len(x["yingqi"]))
        for h in x["yingqi"]:
            self.assertIn("date", h)
            self.assertIn("how", h)

    def test_new_keys_present(self):
        x = self._cast(42)
        for k in ("sanhe", "display_fushen", "yingqi_all", "yingqi_notes"):
            self.assertIn(k, x, k)
        for k in ("source", "source_label", "source_rank", "selection_status", "availability",
                  "availability_reasons", "strength_tier", "fu_fei", "fly", "shengfu",
                  "fushen_two_appear", "candidates", "dark_moving", "wangshuai"):
            self.assertIn(k, x["ushen"], k)
        for k in ("status", "kind", "branches", "elem", "sources", "relation_to_ushen",
                  "relation_to_shi", "liuqin_ju", "yingqi", "bonus", "power", "school_note",
                  "status_reasons"):
            self.assertIn(k, x["sanhe"], k)

    def test_ushen_source_precedence_ben_before_bian(self):
        for seed in range(30):
            x = self._cast(seed)
            u = x["ushen"]
            if u["source"] == "ben":
                self.assertIn(u["liuqin"], ("妻财", "世爻"))
            if any(y["liuqin"] == "妻财" for y in x["yaos"]):
                self.assertEqual("ben", u["source"], "seed=%d" % seed)

    def test_bian_takes_precedence_over_fushen(self):
        x = self._cast(7, cat="亲子")     # 天山遁, 二爻动化天风姤, 变爻亥水为子孙
        self.assertEqual("子孙", x["ushen"]["liuqin"])
        self.assertEqual("bian", x["ushen"]["source"])
        self.assertFalse(x["ushen"]["hidden"])

    def test_strength_stays_in_scale(self):
        """硬约束4: 新增权重不得把 strength_score 量纲搞飞。"""
        for seed in range(60):
            x = self._cast(seed)
            self.assertLess(abs(x["strength_score"]), 20, "seed=%d" % seed)
            self.assertIn(x["strength_label"], ("强", "平", "弱"))
            self.assertLessEqual(abs(x["sanhe"]["bonus"]), 2.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
