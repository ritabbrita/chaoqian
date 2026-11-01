# -*- coding: utf-8 -*-
import unittest
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from chaoqian import qimen
from chaoqian import qimen_geju as gj


TZ = ZoneInfo("Asia/Shanghai")
NEUTRAL = {"dir": None, "star": None, "door": None, "god": None,
           "earth": None, "tian": None, "tianqin": None}


def mkpan(overrides=None, **kw):
    """手工构造一张最小 pan dict: 默认八宫全空(不触发任何格局), 再按 overrides 打补丁。"""
    palaces = {p: dict(NEUTRAL) for p in gj.RING}
    for p, patch in (overrides or {}).items():
        palaces[p].update(patch)
    d = {"palaces": palaces, "hour_gz": "丙子", "day_gz": "甲子",
         "hour_zhi": "子", "zhifu_palace": None, "zhishi_palace": None}
    d.update(kw)
    return d


def gnames(tian, earth):
    return [f["name"] for f in gj.geju_ganying(tian, earth)]


# day_summary 是纯函数(同一 dt 结果恒定), 缓存一份共用, 省掉重复计算。
_DAY_SUMMARY_CACHE = {}


def day_summary_cached(d):
    """d: datetime.date -> qimen.day_summary(当天 08:00 基准)。"""
    s = _DAY_SUMMARY_CACHE.get(d)
    if s is None:
        s = qimen.day_summary(datetime(d.year, d.month, d.day, 8, 0, tzinfo=TZ))
        _DAY_SUMMARY_CACHE[d] = s
    return s


class MirrorAndContractTests(unittest.TestCase):
    def test_constant_mirror_matches_qimen(self):
        """qimen_geju 是零依赖模块, 常量为 qimen.py 的镜像; 这条防漂移。"""
        for name in ("RING", "PALACE_NAME", "PALACE_ELEM", "STAR_HOME",
                     "DOOR_HOME", "DOOR_ELEM", "KE", "GOOD_DOORS"):
            self.assertEqual(getattr(qimen, name), getattr(gj, name), name)

    def test_every_rule_is_confirmed_partial_or_settled_conflict(self):
        """unverified 条目一律不进引擎(留档在 _NOT_IMPLEMENTED)。"""
        for rid, r in gj._RULES.items():
            self.assertIn(r["verified"], ("confirmed", "partial", "conflict"), rid)
            self.assertIn(r["kind"], ("吉", "凶", "中"), rid)
            self.assertIn(r["level"], gj.LEVEL_SCORE, rid)
        self.assertTrue(gj._NOT_IMPLEMENTED)
        for rid in gj._NOT_IMPLEMENTED:
            self.assertNotIn(rid, gj._RULES)

    def test_formation_dict_contract(self):
        p = mkpan({1: {"tian": "庚", "earth": "癸"}})
        f = gj.formations(p)["by_palace"][1][0]
        for key in ("name", "kind", "level", "palace", "basis", "source", "verified"):
            self.assertIn(key, f)
        self.assertEqual(1, f["palace"])


class MenpoTests(unittest.TestCase):
    def test_menpo_direction_regression(self):
        self.assertEqual("menpo", gj.classify_menpo("开门", 3))    # 金克木
        self.assertEqual("menpo", gj.classify_menpo("开门", 4))
        self.assertEqual("menzhi", gj.classify_menpo("死门", 3))   # 木克土
        self.assertIsNone(gj.classify_menpo("休门", 1))            # 水居坎, 不克不制
        self.assertIsNone(gj.classify_menpo(None, 1))

    def test_menpo_matches_engine_condition_everywhere(self):
        for door in qimen.DOOR_ELEM:
            for p in qimen.RING:
                engine = qimen.KE.get(qimen.DOOR_ELEM[door]) == qimen.PALACE_ELEM[p]
                self.assertEqual(engine, gj.classify_menpo(door, p) == "menpo", (door, p))

    def test_menzhi_level_is_mixed(self):
        self.assertEqual("mixed", gj._RULES["menzhi"]["level"])
        self.assertEqual("inauspicious", gj._RULES["menpo"]["level"])


class GanYingTests(unittest.TestCase):
    def test_qinglong_fanshou_vs_feiniao_diexue(self):
        self.assertIn("青龙返首", gnames("戊", "丙"))
        self.assertIn("飞鸟跌穴", gnames("丙", "戊"))
        self.assertNotIn("青龙返首", gnames("丙", "戊"))   # taibu 双向查表会丢格
        self.assertEqual([], gnames("丁", "戊"))           # taibu 的丁戊版已废弃

    def test_baihu_changkuang_and_qinglong_taozou(self):
        self.assertIn("白虎猖狂", gnames("辛", "乙"))
        self.assertIn("青龙逃走", gnames("乙", "辛"))
        self.assertNotIn("青龙逃走", gnames("辛", "乙"))
        self.assertEqual([], gnames("庚", "乙"))           # sudo 的庚+乙版无据

    def test_taibai_ruying_pair(self):
        self.assertIn("太白入荧", gnames("庚", "丙"))
        self.assertIn("荧入太白", gnames("丙", "庚"))
        self.assertNotIn("太白入荧", gnames("丙", "庚"))
        self.assertEqual([], gnames("庚", "丁"))           # taibu 把庚丁并入太白入荧是错的

    def test_tengshe_and_zhuque(self):
        self.assertIn("螣蛇夭矫", gnames("癸", "丁"))
        self.assertIn("朱雀投江", gnames("丁", "癸"))
        self.assertEqual([], gnames("辛", "癸"))           # sudo 的辛癸版不接入
        self.assertNotIn("玉女守门", gnames("丁", "癸"))   # 丁加癸一律按朱雀投江

    def test_dage_xingge_shangge(self):
        self.assertIn("大格", gnames("庚", "癸"))
        self.assertIn("刑格", gnames("庚", "己"))
        self.assertEqual([], gnames("戊", "癸"))           # taibu 的戊癸=刑格 已废
        self.assertEqual([], gnames("己", "庚"))           # taibu 的刑格入狱 已废
        self.assertIn("上格", gnames("庚", "壬"))
        self.assertEqual([], gnames("戊", "壬"))           # taibu 的戊壬=小格 已废

    def test_bei_pair_is_not_named_beige(self):
        self.assertIn("大悖入刑", gnames("丙", "己"))
        self.assertIn("火悖地户", gnames("己", "丙"))
        for pair in (("丙", "己"), ("己", "丙")):
            self.assertNotIn("悖格", gnames(*pair))

    def test_unverified_ganying_never_enters_engine(self):
        for pair in (("癸", "丙"), ("丙", "丁"), ("乙", "丙"), ("乙", "丁"), ("辛", "壬")):
            self.assertEqual([], gnames(*pair), pair)

    def test_severity_levels(self):
        self.assertEqual("auspicious_great", gj._RULES["ganying_qinglong_fanshou"]["level"])
        self.assertEqual("inauspicious_great", gj._RULES["ganying_baihu_changkuang"]["level"])
        self.assertEqual("inauspicious_great", gj._RULES["ganying_dage"]["level"])
        self.assertEqual("inauspicious_great", gj._RULES["ganying_taibai_ruying"]["level"])
        self.assertEqual("inauspicious", gj._RULES["ganying_ruying_taibai"]["level"])


class SanQiTests(unittest.TestCase):
    def test_shengdian(self):
        self.assertIsNotNone(gj.geju_sanqi_shengdian("乙", 3))
        self.assertIsNone(gj.geju_sanqi_shengdian("乙", 2))
        self.assertIsNotNone(gj.geju_sanqi_shengdian("丙", 9))
        self.assertIsNotNone(gj.geju_sanqi_shengdian("丁", 7))
        self.assertIsNone(gj.geju_sanqi_shengdian("丁", 6))
        self.assertEqual("日出扶桑", gj.geju_sanqi_shengdian("乙", 3)["alias"])

    def test_deshi_loose_without_xunshou(self):
        """没传 xunshou_yi(手工盘)时按旧宽松口径, 但标注未校旬首。"""
        self.assertIsNotNone(gj.geju_sanqi_deshi("乙", "己"))
        self.assertIsNotNone(gj.geju_sanqi_deshi("乙", "辛"))
        self.assertIsNone(gj.geju_sanqi_deshi("乙", "戊"))
        self.assertIsNotNone(gj.geju_sanqi_deshi("丙", "戊"))
        self.assertIsNotNone(gj.geju_sanqi_deshi("丁", "癸"))
        self.assertIsNone(gj.geju_sanqi_deshi("丁", "庚"))
        self.assertIsNone(gj.geju_sanqi_deshi("戊", "丙"))
        r = gj.geju_sanqi_deshi("乙", "己")
        self.assertFalse(r["xunshou_checked"])
        self.assertIn("未校旬首", r["basis"])

    def test_deshi_requires_current_xun_yi(self):
        """通行口径: 地盘六仪必须是当前时辰所在旬的旬首之仪。"""
        # 甲戌旬(旬首仪=己): 乙加己 成格, 乙加辛(甲午之仪)不成格
        self.assertIsNotNone(gj.geju_sanqi_deshi("乙", "己", None, "己"))
        self.assertIsNone(gj.geju_sanqi_deshi("乙", "辛", None, "己"))
        # 甲申旬(旬首仪=庚): 丙加庚 成格, 丙加戊(甲子之仪)不成格
        self.assertIsNotNone(gj.geju_sanqi_deshi("丙", "庚", None, "庚"))
        self.assertIsNone(gj.geju_sanqi_deshi("丙", "戊", None, "庚"))
        # 旬首仪对上了但三奇配错也不成格(丁的使是壬/癸)
        self.assertIsNone(gj.geju_sanqi_deshi("丁", "庚", None, "庚"))
        r = gj.geju_sanqi_deshi("丙", "庚", 6, "庚")
        self.assertTrue(r["xunshou_checked"])
        self.assertIn("本旬旬首", r["basis"])

    def test_deshi_through_formations_uses_pan_xunshou_yi(self):
        base = {6: {"tian": "丙", "earth": "庚"}}
        hit = gj.formations(mkpan(base, xunshou_yi="庚"))["by_palace"][6]
        self.assertIn("三奇得使", [f["name"] for f in hit])
        miss = gj.formations(mkpan(base, xunshou_yi="戊"))["by_palace"][6]
        self.assertNotIn("三奇得使", [f["name"] for f in miss])

    def test_rumu_ding_is_gen8_not_qian6(self):
        self.assertIsNotNone(gj.geju_rumu("乙", 2))
        self.assertIsNotNone(gj.geju_rumu("丙", 6))
        self.assertIsNotNone(gj.geju_rumu("丁", 8))
        self.assertIsNone(gj.geju_rumu("丁", 6))    # 两源同错处
        self.assertIsNone(gj.geju_rumu("乙", 8))
        self.assertIsNone(gj.geju_rumu("己", 2))    # 己无独立墓库, 不做


class JiXingTests(unittest.TestCase):
    def test_correct_table_hits(self):
        for gan, palace in (("戊", 3), ("己", 2), ("庚", 8), ("辛", 9), ("壬", 4), ("癸", 4)):
            self.assertIsNotNone(gj.geju_liuyi_jixing(gan, palace), (gan, palace))

    def test_sudo_wrong_values_miss(self):
        for gan, palace in (("庚", 4), ("辛", 7), ("壬", 8), ("癸", 5)):
            self.assertIsNone(gj.geju_liuyi_jixing(gan, palace), (gan, palace))

    def test_never_lands_on_center_five(self):
        self.assertNotIn(5, [v[0] for v in gj._JIXING.values()])

    def test_uses_tian_not_earth(self):
        p = mkpan({3: {"tian": "戊", "earth": "壬"}, 4: {"tian": "丁", "earth": "壬"}})
        names = [f["name"] for f in gj.formations(p)["by_palace"].get(3, [])]
        self.assertIn("六仪击刑", names)
        # 地盘壬落巽4 不算(那是另一流派的地盘击刑)
        self.assertNotIn("六仪击刑", [f["name"] for f in gj.formations(p)["by_palace"].get(4, [])])


class SanZhaWuJiaTests(unittest.TestCase):
    def names(self, tian, door, god):
        return [f["name"] for f in gj.geju_sanzha_wujia(tian, door, god)]

    def test_three_zha_split_by_god(self):
        self.assertIn("真诈", self.names("乙", "开门", "太阴"))
        self.assertIn("重诈", self.names("丙", "休门", "九地"))
        self.assertIn("休诈", self.names("丁", "生门", "六合"))
        self.assertEqual([], self.names("乙", "开门", "九天"))   # sudo 多塞的九天
        self.assertEqual([], self.names("戊", "开门", "太阴"))   # 非三奇

    def test_five_jia(self):
        self.assertIn("天假", self.names("丙", "景门", "九天"))
        self.assertIn("天假", self.names("乙", "景门", "九天"))  # 三奇皆可, sudo 窄化为丁是错的
        self.assertEqual([], self.names("丁", "景门", "太阴"))
        self.assertIn("地假", self.names("己", "杜门", "九地"))
        self.assertIn("地假", self.names("癸", "杜门", "六合"))
        self.assertEqual([], self.names("乙", "杜门", "九地"))
        self.assertIn("人假", self.names("壬", "惊门", "九天"))
        self.assertEqual([], self.names("丁", "惊门", "九天"))
        self.assertIn("神假", self.names("癸", "伤门", "值符"))
        self.assertEqual([], self.names("癸", "伤门", "太阴"))
        self.assertIn("鬼假", self.names("己", "死门", "太阴"))
        self.assertEqual([], self.names("己", "死门", "九天"))


class JiuDunTests(unittest.TestCase):
    def names(self, tian, door, god, earth=None, palace=None):
        return [f["name"] for f in gj.geju_jiudun(tian, door, god, earth, palace)]

    def test_tiandun_taiyin_shendun_jiutian(self):
        self.assertEqual(["天遁"], self.names("丙", "生门", "太阴"))
        self.assertEqual(["神遁"], self.names("丙", "生门", "九天"))
        self.assertEqual([], self.names("丙", "生门", "九地"))   # sudo 的配神已改正

    def test_other_dun(self):
        self.assertIn("地遁", self.names("乙", "开门", "六合"))
        self.assertIn("地遁", self.names("乙", "开门", "白虎", "己"))
        self.assertIn("人遁", self.names("丁", "休门", "太阴"))
        self.assertIn("鬼遁", self.names("丁", "杜门", "九地"))
        self.assertIn("风遁", self.names("乙", "开门", "白虎", None, 4))
        self.assertIn("龙遁", self.names("乙", "休门", "白虎", None, 1))

    # 云遁 / 虎遁判据按《奇门遁甲秘笈大全》卷六 /《奇门遁甲统宗大全》卷之一 /《奇门法窍》卷六:
    # 云遁不写死宫位但必查地盘辛; 虎遁用休门 + 地盘辛 + 艮八宫。
    def test_yundun_needs_earth_xin_any_palace(self):
        # 正例: 天盘乙 + 三吉门任一 + 地盘辛, 宫位不限
        for door in ("开门", "休门", "生门"):
            for p in (1, 2, 3, 4, 6, 7, 8, 9):
                self.assertIn("云遁", self.names("乙", door, "白虎", "辛", p),
                              "%s/%s 应判云遁" % (door, p))
        # 反例1: 乙 + 开门 + 坎一宫, 但地盘不是辛
        self.assertNotIn("云遁", self.names("乙", "开门", "白虎", "戊", 1))
        self.assertNotIn("云遁", self.names("乙", "开门", "白虎", None, 1))
        # 反例2: 地盘辛但门不是三吉门
        self.assertNotIn("云遁", self.names("乙", "杜门", "白虎", "辛", 1))
        # 反例3: 地盘辛 + 三吉门但天盘不是乙奇
        self.assertNotIn("云遁", self.names("丙", "开门", "白虎", "辛", 1))

    def test_hudun_xiumen_earth_xin_gen8(self):
        # 正例: 天盘乙 + 休门 + 地盘辛 + 艮八宫
        self.assertIn("虎遁", self.names("乙", "休门", "白虎", "辛", 8))
        # 反例1: 乙 + 生门 + 艮八宫(地盘非辛)
        self.assertNotIn("虎遁", self.names("乙", "生门", "白虎", None, 8))
        self.assertNotIn("虎遁", self.names("乙", "生门", "白虎", "辛", 8))
        # 反例2: 门与地盘都对但不在艮八宫
        self.assertNotIn("虎遁", self.names("乙", "休门", "白虎", "辛", 1))
        # 反例3: 艮八宫 + 休门但地盘非辛
        self.assertNotIn("虎遁", self.names("乙", "休门", "白虎", "戊", 8))

    def test_hudun_is_subset_of_yundun(self):
        got = self.names("乙", "休门", "白虎", "辛", 8)
        self.assertIn("虎遁", got)
        self.assertIn("云遁", got)

    def test_taibu_two_gan_form_never_hits(self):
        self.assertEqual([], self.names("丙", None, None, "己"))
        self.assertEqual([], self.names("丁", None, None, "壬"))
        # need_door 是门集合时, door=None 也必须不命中(云遁)
        self.assertEqual([], self.names("乙", None, None, "辛", 8))


class YiMaTests(unittest.TestCase):
    def test_hour_zhi_triads(self):
        self.assertEqual(8, gj.geju_yima("子")["palace"])   # 申子辰马在寅 -> 艮8
        self.assertEqual(2, gj.geju_yima("午")["palace"])   # 寅午戌马在申 -> 坤2
        self.assertEqual(6, gj.geju_yima("酉")["palace"])   # 巳酉丑马在亥 -> 乾6
        self.assertEqual(4, gj.geju_yima("卯")["palace"])   # 亥卯未马在巳 -> 巽4
        self.assertIsNone(gj.geju_yima("戊"))

    def test_marks_which_zhi_it_used(self):
        r = gj.geju_yima("子", "午")
        self.assertEqual("时支", r["taken_from"])
        self.assertEqual(2, r["day_ma"]["palace"])
        self.assertEqual("mixed", r["level"])


class FuYinFanYinTests(unittest.TestCase):
    def test_three_kinds_are_independent_keys(self):
        r = gj.geju_fuyin_fanyin(mkpan())
        for key in ("star_fuyin", "door_fuyin", "gan_fuyin", "fanyin"):
            self.assertIn(key, r)
        for key in ("star", "door", "gan"):
            self.assertIn(key, r["fanyin"])
        self.assertFalse(any([r["star_fuyin"], r["door_fuyin"], r["gan_fuyin"]]))

    def test_star_fuyin_alone(self):
        p = mkpan({pp: {"star": gj.STAR_HOME[pp]} for pp in gj.RING})
        r = gj.geju_fuyin_fanyin(p)
        self.assertTrue(r["star_fuyin"])
        self.assertFalse(r["door_fuyin"])    # 门伏吟不被星伏吟带出来
        self.assertFalse(r["gan_fuyin"])

    def test_door_and_gan_fuyin(self):
        p = mkpan({pp: {"door": gj.DOOR_HOME[pp], "tian": "戊", "earth": "戊"} for pp in gj.RING})
        r = gj.geju_fuyin_fanyin(p)
        self.assertTrue(r["door_fuyin"])
        self.assertTrue(r["gan_fuyin"])
        self.assertFalse(r["star_fuyin"])

    def test_fanyin_uses_houtian_opposite(self):
        p = mkpan({pp: {"star": gj.STAR_HOME[gj.OPPOSITE[pp]],
                        "door": gj.DOOR_HOME[gj.OPPOSITE[pp]]} for pp in gj.RING})
        r = gj.geju_fuyin_fanyin(p)
        self.assertTrue(r["fanyin"]["star"])
        self.assertTrue(r["fanyin"]["door"])
        self.assertFalse(r["star_fuyin"])

    def test_global_list_carries_fuyin(self):
        p = mkpan({pp: {"tian": "戊", "earth": "戊"} for pp in gj.RING})
        names = [f["name"] for f in gj.formations(p)["global"]]
        self.assertIn("干伏吟", names)


class BeiGeTests(unittest.TestCase):
    def test_zhifu_forms(self):
        p = mkpan({9: {"tian": "丙", "earth": "壬"}}, zhifu_palace=9)
        names = [f["name"] for f in gj.geju_beige(p)]
        self.assertIn("伏悖(丙加值符)", names)
        p2 = mkpan({9: {"tian": "壬", "earth": "丙"}}, zhifu_palace=9)
        self.assertIn("飞悖(值符加丙)", [f["name"] for f in gj.geju_beige(p2)])

    def test_shigan_forms_and_jia_skipped(self):
        p = mkpan({3: {"tian": "丙", "earth": "壬"}}, hour_gz="壬辰")
        self.assertIn("伏悖(丙加时干)", [f["name"] for f in gj.geju_beige(p)])
        jia = mkpan({3: {"tian": "丙", "earth": "壬"}}, hour_gz="甲辰")
        self.assertEqual([], [f for f in gj.geju_beige(jia) if "时干" in f["name"]])


class ScoreOverlayTests(unittest.TestCase):
    def overlay(self, pan_dict, zhishi, zhifu):
        return gj.hour_overlay(gj.formations(pan_dict), zhishi, zhifu)

    def test_zhishi_palace_takes_full_weight(self):
        p = mkpan({1: {"tian": "庚", "earth": "癸"}})
        delta, factors, picked = self.overlay(p, 1, 9)
        self.assertEqual(-1.5, delta)          # -3 * 0.5 * 1.0
        self.assertIn("大格", factors)
        self.assertEqual("值使", [f for f in picked if f["name"] == "大格"][0]["role"])

    def test_zhifu_palace_is_discounted(self):
        p = mkpan({1: {"tian": "庚", "earth": "癸"}})
        zhishi_delta, _, _ = self.overlay(p, 1, 9)
        zhifu_delta, _, _ = self.overlay(p, 9, 1)
        self.assertEqual(-0.75, zhifu_delta)   # -3 * 0.5 * 0.5
        self.assertLess(abs(zhifu_delta), abs(zhishi_delta))

    def test_cap_negative_at_minus_1_5(self):
        # 大悖入刑(-2) + 三奇入墓(-2) => -4 * 0.5 = -2.0, 封顶 -1.5
        p = mkpan({6: {"tian": "丙", "earth": "己"}})
        delta, factors, picked = self.overlay(p, 6, 6)
        self.assertEqual(-1.5, delta)
        self.assertIn("大悖入刑", factors)
        self.assertIn("三奇入墓", factors)
        self.assertGreaterEqual(len([f for f in picked if f["role"] == "值使"]), 2)

    def test_deshi_overlap_only_inside_its_own_xun(self):
        """丙加庚: 只有甲申旬(旬首仪=庚)才同时出荧入太白+丙奇得使, 其他旬只出荧入太白。"""
        base = {3: {"tian": "丙", "earth": "庚"}}   # 震3, 避开丙的墓宫乾6
        delta, factors, _ = self.overlay(mkpan(base, xunshou_yi="庚"), 3, 3)
        self.assertIn("荧入太白", factors)
        self.assertIn("三奇得使", factors)
        self.assertEqual(0.5, delta)           # (-2 + 3) * 0.5
        other, factors2, _ = self.overlay(mkpan(base, xunshou_yi="戊"), 3, 3)
        self.assertIn("荧入太白", factors2)
        self.assertNotIn("三奇得使", factors2)
        self.assertEqual(-1.0, other)          # 只剩 -2 * 0.5
        self.assertLess(other, delta)

    def test_cap_positive_at_plus_1_5(self):
        # 飞鸟跌穴(+3) + 三奇升殿(+3) + 三奇得使(+3) + 真诈(+2) + 天遁(+3) => 远超 +1.5, 封顶
        p = mkpan({9: {"tian": "丙", "earth": "戊", "door": "生门", "god": "太阴"}})
        delta, factors, _ = self.overlay(p, 9, 9)
        self.assertEqual(1.5, delta)
        for n in ("飞鸟跌穴", "三奇升殿", "真诈", "天遁"):
            self.assertIn(n, factors)

    def test_same_palace_not_counted_twice(self):
        p = mkpan({1: {"tian": "庚", "earth": "壬"}})   # 上格 -2
        single, _, picked = self.overlay(p, 1, 1)
        self.assertEqual(-1.0, single)
        self.assertEqual(1, len([f for f in picked if f["name"] == "上格"]))

    def test_global_xiong_ge_does_not_move_score(self):
        layout = {1: "戊", 9: "己", 8: "庚", 7: "辛", 6: "壬", 4: "丁", 3: "丙", 2: "乙"}
        p = mkpan({pp: {"tian": g, "earth": g} for pp, g in layout.items()})
        delta, factors, picked = self.overlay(p, 1, 1)
        self.assertEqual(0.0, delta)
        self.assertIn("干伏吟·宜静守", factors)
        self.assertTrue(any(f["role"] == "全局" for f in picked))

    def test_liuyi_jixing_is_advisory_only(self):
        # 庚落艮8 => 六仪击刑; earth 取戊避开「庚加壬=上格」把分带走
        p = mkpan({8: {"tian": "庚", "earth": "戊"}})
        delta, factors, _ = self.overlay(p, 8, 8)
        self.assertEqual(0.0, delta)
        self.assertIn("六仪击刑·力减事阻", factors)

    def test_wujia_is_mixed_and_does_not_lift_bad_door_hours(self):
        """五假是「特定事可用」而非泛吉: level=mixed, 不给凶门时段回补分。"""
        for rid in ("wujia_tianjia", "wujia_dijia", "wujia_renjia", "wujia_shenjia", "wujia_guijia"):
            self.assertEqual("mixed", gj._RULES[rid]["level"], rid)
            self.assertEqual("中", gj._RULES[rid]["kind"], rid)
        for rid in ("sanzha_zhenzha", "sanzha_zhongzha", "sanzha_xiuzha"):
            self.assertEqual("吉", gj._RULES[rid]["kind"], rid)
            self.assertEqual("auspicious", gj._RULES[rid]["level"], rid)
        # 死门 + 九地 + 己 => 鬼假, 落值使宫也不加分
        p = mkpan({2: {"tian": "己", "door": "死门", "god": "九地"}})
        delta, factors, _ = self.overlay(p, 2, 2)
        self.assertIn("鬼假", factors)
        self.assertEqual(0.0, delta)

    def test_menpo_not_double_counted(self):
        p = mkpan({3: {"door": "开门"}})
        delta, factors, _ = self.overlay(p, 3, 3)
        self.assertEqual(0.0, delta)           # day_hours() 里已经扣过 -1
        self.assertIn("门迫", factors)


class PanContractTests(unittest.TestCase):
    def test_pan_exposes_zhifu_zhishi_palace_and_hour_zhi(self):
        p = qimen.pan(datetime(2030, 8, 27, 19, 43, tzinfo=TZ))
        self.assertIn("zhifu_palace", p)
        self.assertIn("zhishi_palace", p)
        self.assertIn(p["zhifu_palace"], qimen.RING)
        self.assertIn(p["zhishi_palace"], qimen.RING)
        self.assertEqual(p["hour_gz"][1], p["hour_zhi"])
        self.assertIn("xunshou", p)
        self.assertIn("xunshou_yi", p)
        self.assertEqual(qimen.XUNSHOU_YI[p["xunshou"]], p["xunshou_yi"])
        self.assertEqual("甲戌", p["xunshou"])
        self.assertEqual("己", p["xunshou_yi"])
        # 值符落宫必是八神值符所在宫, 值使落宫必是值使门所在宫
        self.assertEqual("值符", p["palaces"][p["zhifu_palace"]]["god"])
        self.assertEqual(p["zhishi"], p["palaces"][p["zhishi_palace"]]["door"])

    def test_existing_fields_unchanged(self):
        p = qimen.pan(datetime(2030, 7, 25, 11, 30, tzinfo=TZ))
        for key in ("jieqi", "dun", "ju", "yuan", "day_gz", "hour_gz", "zhifu", "zhishi", "palaces"):
            self.assertIn(key, p)
        self.assertEqual(8, len(p["palaces"]))
        self.assertEqual("chaoqian-qimen-0.1", qimen.RULE_VERSION)


class EndToEndTests(unittest.TestCase):
    """2030-08-27 19:43 甲戌时 · 处暑阴遁一局 · 全盘伏吟。"""

    def setUp(self):
        self.dt = datetime(2030, 8, 27, 19, 43, tzinfo=TZ)
        self.p = qimen.pan(self.dt)

    def test_ju_and_hour(self):
        self.assertEqual("处暑", self.p["jieqi"])
        self.assertEqual("阴遁", self.p["dun"])
        self.assertEqual(1, self.p["ju"])
        self.assertEqual("甲戌", self.p["hour_gz"])

    def test_global_has_fuyin(self):
        names = [f["name"] for f in gj.formations(self.p)["global"]]
        self.assertIn("干伏吟", names)
        self.assertIn("星伏吟", names)
        self.assertIn("门伏吟", names)

    def test_hour_rating_not_moved_by_fuyin(self):
        hours = qimen.day_hours(self.dt)
        h = [x for x in hours if x["range"] == "19-21"][0]
        self.assertIn("score_base", h)
        self.assertIn("rating_base", h)
        self.assertTrue(any("伏吟" in f for f in h["factors"]))
        # 实际修正 == 只由「非全局凶格 / 非门迫」的格局贡献
        expected = 0.0
        for f in h["formations"]:
            if f["id"] in gj.NO_SCORE:
                continue
            w = 1.0 if f["role"] == "值使" else (gj.ZHIFU_DISCOUNT if f["role"] == "值符" else 0.0)
            expected += gj.LEVEL_SCORE[f["level"]] * gj.SCORE_SCALE * w
        expected = max(-gj.SCORE_CAP, min(gj.SCORE_CAP, round(expected, 2)))
        self.assertAlmostEqual(expected, round(h["score"] - h["score_base"], 2), places=2)
        # 伏吟三条确实在 formations 里, 却一分未动
        fu = [f for f in h["formations"] if f["role"] == "全局"]
        self.assertTrue(fu)
        self.assertTrue(all(f["id"] in gj.NO_SCORE for f in fu))

    def test_day_hours_keeps_old_fields_and_adds_new(self):
        hours = qimen.day_hours(self.dt)
        self.assertTrue(hours)
        for h in hours:
            for key in ("start", "zhi", "range", "rating", "score", "factors", "zhishi",
                        "kaimen_dir", "shengmen_dir", "rating_base", "score_base", "formations"):
                self.assertIn(key, h)
            self.assertIn(h["rating"], (0, 1, 2))
            self.assertEqual(h["rating"], 2 if h["score"] >= 2 else (0 if h["score"] <= -1 else 1))
            self.assertLessEqual(abs(round(h["score"] - h["score_base"], 2)), gj.SCORE_CAP + 1e-9)

    def test_day_summary_formations_today(self):
        s = qimen.day_summary(self.dt)
        self.assertIn("formations_today", s)
        ft = s["formations_today"]
        self.assertLessEqual(len(ft), 24)
        for item in ft:
            self.assertEqual({"range", "name", "kind", "hint"}, set(item))
            self.assertIn(item["kind"], ("吉", "凶", "中"))
        # 吉/凶 在前、中 在后
        kinds = [0 if i["kind"] in ("吉", "凶") else 1 for i in ft]
        self.assertEqual(sorted(kinds), kinds)
        # 中档(门制/驿马/五假)确实进得来
        self.assertTrue(any(i["kind"] == "中" for i in ft))
        # 老字段语义不变
        for key in ("ju", "yuan", "jieqi", "method", "zhifu", "zhishi", "hours", "style",
                    "best_ranges", "slow_ranges", "dirs", "dir_range", "rule_version"):
            self.assertIn(key, s)

    def test_month_of_pans_stay_sane(self):
        for day in range(1, 29):
            p = qimen.pan(datetime(2030, 9, day, 11, 30, tzinfo=TZ))
            res = gj.formations(p)
            for pp, items in res["by_palace"].items():
                self.assertIn(pp, qimen.RING)
                for f in items:
                    self.assertIn(f["level"], gj.LEVEL_SCORE)
            delta, _, _ = gj.hour_overlay(res, p["zhishi_palace"], p["zhifu_palace"])
            self.assertLessEqual(abs(delta), gj.SCORE_CAP + 1e-9)

    def test_compute_all_summary(self):
        r = gj.compute_all(self.p)
        self.assertIn("summary", r)
        self.assertIn("by_palace", r)
        self.assertIn("global", r)
        self.assertTrue(isinstance(r["summary"], str) and r["summary"])


class WuBuYuShiTests(unittest.TestCase):

    # 五鼠遁: 甲己日起甲子、乙庚日起丙子、丙辛日起戊子、丁壬日起庚子、戊癸日起壬子
    _WUSHU_START = {"甲": "甲", "己": "甲", "乙": "丙", "庚": "丙", "丙": "戊",
                    "辛": "戊", "丁": "庚", "壬": "庚", "戊": "壬", "癸": "壬"}

    def _hour_pillars(self, day_gan):
        """该日 12 个时柱(干支), 按五鼠遁展开。"""
        gans = list("甲乙丙丁戊己庚辛壬癸")
        zhis = list("子丑寅卯辰巳午未申酉戌亥")
        s = gans.index(self._WUSHU_START[day_gan])
        return [(gans[(s + i) % 10], zhis[i]) for i in range(12)]

    def test_qisha_appears_twice_but_only_table_pillar_is_wubuyushi(self):
        seen = {}
        for day_gan, qisha in gj._WUBUYU.items():
            hits = [z for g, z in self._hour_pillars(day_gan) if g == qisha]
            seen[day_gan] = hits
            self.assertIn(gj._WUBUYU_ZHI[day_gan], hits)      # 表内那条必在
            for z in hits:
                self.assertEqual(z == gj._WUBUYU_ZHI[day_gan],
                                 gj.is_wubuyushi(day_gan, qisha, z),
                                 "%s日%s%s时" % (day_gan, qisha, z))
        self.assertEqual(["丑", "亥"], seen["己"])
        self.assertEqual(["子", "戌"], seen["庚"])
        for day_gan, hits in seen.items():
            self.assertEqual(1 if day_gan not in ("己", "庚") else 2, len(hits), day_gan)

    def test_classic_table_is_exactly_ten_pillars(self):
        """十时柱表 = 干支各一半, 恰好十条, 与《奇门法窍》卷六/卷七两套枚举同集。"""
        self.assertEqual(10, len(gj._WUBUYU))
        self.assertEqual(10, len(gj._WUBUYU_ZHI))
        self.assertEqual(set(gj._WUBUYU), set(gj._WUBUYU_ZHI))
        table = {d + gj._WUBUYU[d] + gj._WUBUYU_ZHI[d] for d in gj._WUBUYU}
        self.assertEqual({"甲庚午", "乙辛巳", "丙壬辰", "丁癸卯", "戊甲寅",
                          "己乙丑", "庚丙子", "辛丁酉", "壬戊申", "癸己未"}, table)

    def test_table_gan_equals_qisha_derivation(self):
        derived = {}
        for day_gan, day_wx in gj.GAN_WX.items():
            for hour_gan, hour_wx in gj.GAN_WX.items():
                if gj.KE.get(hour_wx) == day_wx and gj.GAN_YANG[hour_gan] == gj.GAN_YANG[day_gan]:
                    derived[day_gan] = hour_gan
        self.assertEqual(derived, gj._WUBUYU)
        self.assertEqual(10, len(gj._WUBUYU))

    def test_is_wubuyushi_positive_and_negative(self):
        # 表内十时柱: 干支俱合 → 全 True
        for day_gan, hour_gan in gj._WUBUYU.items():
            self.assertTrue(gj.is_wubuyushi(day_gan, hour_gan, gj._WUBUYU_ZHI[day_gan]),
                            day_gan + hour_gan + gj._WUBUYU_ZHI[day_gan])
        # 干对支不对: 己日乙亥时 / 庚日丙戌时 = 七杀而非五不遇时 → False
        self.assertFalse(gj.is_wubuyushi("己", "乙", "亥"))
        self.assertFalse(gj.is_wubuyushi("庚", "丙", "戌"))
        # 反例: 辛克甲(金克木)但一阴一阳 = 正官不是七杀; 丙不克甲
        self.assertFalse(gj.is_wubuyushi("甲", "辛", "巳"))
        self.assertFalse(gj.is_wubuyushi("甲", "丙", "寅"))
        self.assertFalse(gj.is_wubuyushi("甲", "甲", "子"))
        self.assertFalse(gj.is_wubuyushi(None, "庚", "午"))
        self.assertFalse(gj.is_wubuyushi("甲", None, "午"))
        # 时支是判据的一半, 不传一律 False(宁可漏判, 不替古籍加戏)
        self.assertFalse(gj.is_wubuyushi("甲", "庚"))
        self.assertFalse(gj.is_wubuyushi("甲", "庚", ""))
        self.assertFalse(gj.is_wubuyushi("甲", "庚", None))

    def test_jiazi_day_gengwu_hour_is_wubuyushi(self):
        """2030-03-30 甲子日, 11:30 = 庚午时 → 古籍表首条「甲日庚午时」。"""
        dt = datetime(2030, 3, 30, 11, 30, tzinfo=TZ)
        p = qimen.pan(dt)
        self.assertEqual("甲子", p["day_gz"])
        self.assertEqual("庚午", p["hour_gz"])
        self.assertTrue(gj.is_wubuyushi(p["day_gz"][0], p["hour_gz"][0], p["hour_gz"][1]))
        names = [f["name"] for f in gj.formations(p)["global"]]
        self.assertIn("五不遇时", names)

    def test_yiyou_day_xinsi_hour_is_wubuyushi(self):
        """2030-04-20 乙酉日, 09:30 = 辛巳时 → 古籍表「乙日辛巳时」。"""
        dt = datetime(2030, 4, 20, 9, 30, tzinfo=TZ)
        p = qimen.pan(dt)
        self.assertEqual("乙酉", p["day_gz"])
        self.assertEqual("辛巳", p["hour_gz"])
        self.assertTrue(gj.is_wubuyushi(p["day_gz"][0], p["hour_gz"][0], p["hour_gz"][1]))
        self.assertIn("五不遇时", [f["name"] for f in gj.formations(p)["global"]])

    def _wubuyushi_form(self, dt):
        p = qimen.pan(dt)
        hit = [f for f in gj.formations(p)["global"] if f["id"] == "wubuyushi"]
        return p, (hit[0] if hit else None)

    def test_basis_cites_the_classic_table(self):
        """命中必在表内, basis 直接署《奇门法窍·卷六》十时柱表那一条。"""
        p, f = self._wubuyushi_form(datetime(2030, 3, 30, 11, 30, tzinfo=TZ))
        self.assertEqual("甲子", p["day_gz"])
        self.assertIsNotNone(f)
        self.assertIn("十时柱表「甲日庚午时」", f["basis"])
        self.assertIn("奇门法窍·卷六", f["basis"])

    def test_ji_day_yihai_hour_is_not_wubuyushi(self):
        p, f = self._wubuyushi_form(datetime(2030, 4, 14, 21, 30, tzinfo=TZ))
        self.assertEqual("己卯", p["day_gz"])
        self.assertEqual("乙亥", p["hour_gz"])
        self.assertFalse(gj.is_wubuyushi(p["day_gz"][0], p["hour_gz"][0], p["hour_gz"][1]))
        self.assertIsNone(f)
        self.assertNotIn("五不遇时", [x["name"] for x in gj.formations(p)["global"]])
        # 也不再压分
        hours = qimen.day_hours(datetime(2030, 4, 14, 8, 0, tzinfo=TZ))
        slot = [h for h in hours if h["range"] == "21-23"][0]
        self.assertFalse(slot["wubuyushi"])
        self.assertNotIn("五不遇时·不宜用事", slot["factors"])

    def test_geng_day_bingxu_hour_is_not_wubuyushi(self):
        """庚日丙戌时(19-21) 同理, 表里那条是庚日丙子时 → 不判。"""
        p, f = self._wubuyushi_form(datetime(2030, 4, 15, 19, 30, tzinfo=TZ))
        self.assertEqual("庚辰", p["day_gz"])
        self.assertEqual("丙戌", p["hour_gz"])
        self.assertFalse(gj.is_wubuyushi(p["day_gz"][0], p["hour_gz"][0], p["hour_gz"][1]))
        self.assertIsNone(f)
        hours = qimen.day_hours(datetime(2030, 4, 15, 8, 0, tzinfo=TZ))
        slot = [h for h in hours if h["range"] == "19-21"][0]
        self.assertFalse(slot["wubuyushi"])

    def test_every_hit_is_inside_the_classic_table(self):
        """全年扫一遍: 凡命中五不遇时, 日干+时干+时支必须与十时柱表逐字相符。"""
        bad, hits = [], 0
        for i in range(0, 366, 7):          # 每 7 天取一天, 4 个代表性时段
            d = date(2030, 3, 1) + timedelta(days=i)
            for h in (1, 11, 19, 21):
                p, f = self._wubuyushi_form(datetime(d.year, d.month, d.day, h, 30, tzinfo=TZ))
                if not f:
                    continue
                hits += 1
                dg, hg, hz = p["day_gz"][0], p["hour_gz"][0], p["hour_gz"][1]
                if not (gj._WUBUYU.get(dg) == hg and gj._WUBUYU_ZHI.get(dg) == hz):
                    bad.append((str(d), h, p["day_gz"], p["hour_gz"]))
        self.assertEqual([], bad)
        self.assertGreater(hits, 0)         # 采样必须真扫到命中, 否则这条测试是空的

    def test_counter_example_same_day_other_hour(self):
        """同一天 07:30 = 戊辰时: 戊土不克甲木 → 不是五不遇时。"""
        p = qimen.pan(datetime(2030, 3, 30, 7, 30, tzinfo=TZ))
        self.assertEqual("戊辰", p["hour_gz"])
        self.assertFalse(gj.is_wubuyushi(p["day_gz"][0], p["hour_gz"][0], p["hour_gz"][1]))
        self.assertNotIn("五不遇时", [f["name"] for f in gj.formations(p)["global"]])

    def test_wubuyushi_is_global_and_never_scores(self):
        """五不遇时按日干/时干判, 不挂宫; 惩罚在 day_hours 基础分, 不走格局加减分。"""
        p = qimen.pan(datetime(2030, 3, 30, 11, 30, tzinfo=TZ))
        res = gj.formations(p)
        hit = [f for f in res["global"] if f["id"] == "wubuyushi"]
        self.assertEqual(1, len(hit))
        self.assertIsNone(hit[0]["palace"])
        self.assertEqual("凶", hit[0]["kind"])
        self.assertEqual("inauspicious_great", hit[0]["level"])
        self.assertIn("五不遇时", hit[0]["source"])
        self.assertIn("wubuyushi", gj.NO_SCORE)
        for items in res["by_palace"].values():
            self.assertNotIn("wubuyushi", [f["id"] for f in items])

    def test_day_hours_floors_wubuyushi_and_keeps_it_out_of_best(self):
        dt = datetime(2030, 3, 30, 8, 0, tzinfo=TZ)
        hours = qimen.day_hours(dt)
        hit = [h for h in hours if h.get("wubuyushi")]
        self.assertEqual(1, len(hit))                     # 8 个时段的时干互不相同
        self.assertEqual("11-13", hit[0]["range"])
        self.assertEqual(0, hit[0]["rating"])             # 最差档
        self.assertLessEqual(hit[0]["score"], qimen.WUBUYU_FLOOR + gj.SCORE_CAP)
        self.assertIn("五不遇时·不宜用事", hit[0]["factors"])
        # 低于任何非五不遇时段: 永远做不成 best / dir_range 的最高分
        others = [h["score"] for h in hours if not h.get("wubuyushi")]
        self.assertLess(hit[0]["score"], min(others))
        s = qimen.day_summary(dt)
        self.assertNotIn("11-13", s["best_ranges"])
        self.assertNotEqual("11-13", s["dir_range"])
        self.assertIn("五不遇时", [f["name"] for f in s["formations_today"]])

    def test_wubuyushi_never_becomes_dir_range(self):
        for i in range(90):
            d = date(2030, 3, 1) + timedelta(days=i)
            s = day_summary_cached(d)
            bad = [h["range"] for h in s["hours"] if h.get("wubuyushi")]
            self.assertNotIn(s["dir_range"], bad, str(d))
            for r in bad:
                self.assertNotIn(r, s["best_ranges"], str(d))


class DirRangeFallbackTests(unittest.TestCase):

    def _first_day_without_best(self):
        for i in range(365):
            d = date(2030, 3, 1) + timedelta(days=i)
            s = day_summary_cached(d)
            if not s["best_ranges"]:
                return d, s
        self.fail("扫描的这一年都有吉时段, 样本假设失效")

    def test_no_best_day_returns_top_score_slot(self):
        d, s = self._first_day_without_best()
        self.assertFalse(s["dir_range_is_best"])
        self.assertIsNotNone(s["dir_range"])
        self.assertEqual("今日无突出顺时, 相对可用 " + s["dir_range"], s["dir_note"])
        pool = [h for h in s["hours"] if not h.get("wubuyushi")]
        top = sorted(pool, key=lambda h: (-h["score"], h["start"]))[0]
        self.assertEqual(top["range"], s["dir_range"])   # 并列取最早
        # 只有当 07-09 真是最高分才允许出现 07-09
        if s["dir_range"] == "07-09":
            self.assertEqual(max(h["score"] for h in pool), top["score"])
        # 吉方跟随同一个 ref, 不置空
        self.assertEqual({"开门": top["kaimen_dir"], "生门": top["shengmen_dir"]}, s["dirs"])

    def test_best_day_marks_is_best_true(self):
        for i in range(365):
            d = date(2030, 3, 1) + timedelta(days=i)
            s = day_summary_cached(d)
            if s["best_ranges"]:
                self.assertTrue(s["dir_range_is_best"])
                self.assertIsNone(s["dir_note"])
                self.assertIn(s["dir_range"], s["best_ranges"])
                best = [h for h in s["hours"] if h["rating"] == 2]
                self.assertEqual(sorted(best, key=lambda h: (-h["score"], h["start"]))[0]["range"],
                                 s["dir_range"])
                return
        self.fail("扫描的这一年都没有吉时段, 样本假设失效")

    def test_dir_range_no_longer_pinned_to_0709(self):
        """无吉时段的日子 dir_range 不固定为 07-09, 只在它真是全天最高分时才是。"""
        pinned = 0
        for i in range(60):
            d = date(2030, 3, 1) + timedelta(days=i)
            s = day_summary_cached(d)
            if s["best_ranges"] or s["dir_range"] != "07-09":
                continue
            pinned += 1
            pool = [h for h in s["hours"] if not h.get("wubuyushi")]
            self.assertEqual(max(h["score"] for h in pool),
                             [h for h in pool if h["range"] == "07-09"][0]["score"], str(d))
        self.assertLess(pinned, 60)


if __name__ == "__main__":
    unittest.main()
