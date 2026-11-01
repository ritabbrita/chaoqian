# -*- coding: utf-8 -*-
"""黄历 / 八字排盘 / 日签 / 月运 / 叙事护栏。命主一律是虚构的合成命盘, 不联网。"""
import json
import random
import re
import unittest
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from lunar_python import Solar
from lunar_python.util import LunarUtil

from chaoqian import almanac as A
from chaoqian import bazi, daily, ganzhi, liuyao, meihua, monthly, natal, prompts, qimen
from chaoqian import cast as castmod
from chaoqian import guards as G
from chaoqian.llm import CallableClient, LLMClient, loads_json_loose

TZ = ZoneInfo("Asia/Shanghai")

# 虚构命主(与 examples/birth_example.json 同一个虚构生日)
SYNTHETIC_SOURCE = {
    "calendar": "solar", "gender": "female", "birth_date": "1990-06-14", "birth_time": "16:30",
    "time_precision": "minute", "timezone": "Asia/Shanghai",
    "longitude": 116.4074, "latitude": 39.9042, "coordinate_precision": "city",
    "day_boundary": "midnight",
}


def synthetic_profile(**over):
    return bazi.build_profile(dict(SYNTHETIC_SOURCE, **over), verified_at="test-fixed")


class FakeLLM(LLMClient):
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def complete(self, system, messages, max_tokens=1024):
        self.calls.append({"system": system, "messages": messages})
        return json.dumps(self.payload, ensure_ascii=False)


class CalendarTests(unittest.TestCase):
    def test_lunar_date_and_jieqi(self):
        a = A.almanac(datetime(2030, 7, 25, 8, tzinfo=TZ))
        self.assertTrue(a["lunar"].endswith("六月廿五"))
        self.assertEqual("大暑", a["jieqi_prev"])
        self.assertEqual("立秋", a["jieqi_next"])
        self.assertEqual("2030-08-07", a["jieqi_next_date"])

    def test_solar_month_key_changes_at_jie(self):
        self.assertEqual("2030_癸未", A.solar_month_key(datetime(2030, 8, 1, 8, tzinfo=TZ)))
        self.assertEqual("2030_甲申", A.solar_month_key(datetime(2030, 8, 10, 8, tzinfo=TZ)))

    def test_calendar_month_segments(self):
        segs = A.calendar_month_segments(datetime(2030, 9, 2, 8, tzinfo=TZ))
        self.assertEqual(["甲申", "乙酉"], [s["gz"] for s in segs])
        self.assertEqual((6, 24), (segs[0]["days"], segs[1]["days"]))
        self.assertEqual("2030-09-07", segs[1]["start"])
        self.assertEqual("白露", segs[1]["jie"])
        self.assertIsNone(segs[0]["jie"])
        feb = A.calendar_month_segments(datetime(2030, 2, 10, 8, tzinfo=TZ))
        self.assertEqual("立春", feb[1]["jie"])
        self.assertEqual(28, sum(s["days"] for s in feb))

    def test_year_pillar_switches_at_lichun_not_lunar_new_year(self):
        new_year_day = A.almanac(datetime(2030, 2, 3, 8, tzinfo=TZ))
        self.assertTrue(new_year_day["lunar"].endswith("正月初一"))
        self.assertEqual("己酉", new_year_day["gz_year"])          # 农历已过年, 立春未到
        self.assertEqual("庚戌", A.almanac(datetime(2030, 2, 4, 8, tzinfo=TZ))["gz_year"])
        self.assertEqual("庚戌", A.almanac(datetime(2030, 2, 10, 8, tzinfo=TZ))["gz_year"])

    def test_year_pillar_uses_exact_lichun_moment(self):
        lichun = Solar.fromYmdHms(2031, 2, 6, 12, 0, 0).getLunar().getJieQiTable()["立春"]
        self.assertEqual("2031-02-04 08:58:19", lichun.toYmdHms())
        before = A.almanac(datetime(2031, 2, 4, 8, 30, tzinfo=TZ))
        after = A.almanac(datetime(2031, 2, 4, 10, 0, tzinfo=TZ))
        self.assertEqual(("庚戌", "己丑"), (before["gz_year"], before["gz_month"]))  # 庚年五虎遁: 十二月己丑
        self.assertEqual(("辛亥", "庚寅"), (after["gz_year"], after["gz_month"]))

    def test_month_pillar_exact_on_jie_day(self):
        self.assertEqual("甲申", A.almanac(datetime(2030, 9, 7, 8, 30, tzinfo=TZ))["gz_month"])
        self.assertEqual("乙酉", A.almanac(datetime(2030, 9, 7, 23, 30, tzinfo=TZ))["gz_month"])

    def test_timeline_keeps_late_zi_hour(self):
        for ymd, early_late in (("2030-07-25", ("吉", "凶")), ("2030-07-27", ("凶", "吉"))):
            y, m, d = (int(x) for x in ymd.split("-"))
            zi = [t.getTianShenLuck() for t in Solar.fromYmdHms(y, m, d, 12, 0, 0).getLunar().getTimes()
                  if t.getZhi() == "子"]
            self.assertEqual(list(early_late), zi, ymd)
            tl = A.almanac(datetime(y, m, d, 8, 30, tzinfo=TZ))["timeline"]
            self.assertEqual(12, len(tl))
            self.assertEqual("子", tl[0]["zhi"])
            self.assertEqual("23-01", tl[0]["range"])
            self.assertEqual(early_late[1], tl[0]["luck"], ymd)

    def test_regimen_table_has_24_terms(self):
        self.assertEqual(24, len(A.load_data("jieqi_regimen.json")))
        self.assertTrue(A.jieqi_tip(datetime(2030, 7, 25, 8, tzinfo=TZ)).startswith("眼下大暑"))


class GanzhiTests(unittest.TestCase):
    def test_ten_gods(self):
        expected = ["比肩", "劫财", "食神", "伤官", "偏财", "正财", "七杀", "正官", "偏印", "正印"]
        self.assertEqual(expected, [ganzhi.ten_god("甲", g) for g in "甲乙丙丁戊己庚辛壬癸"])

    def test_xunkong_six_xun(self):
        self.assertEqual(["戌亥", "申酉", "午未", "辰巳", "寅卯", "子丑"],
                         [ganzhi.day_xunkong(g) for g in ("甲子", "甲戌", "甲申", "甲午", "甲辰", "甲寅")])

    def test_zhi_xing_rel_includes_self_punishment(self):
        self.assertEqual("自刑", ganzhi.zhi_xing_rel("午", "午"))
        self.assertEqual("刑", ganzhi.zhi_xing_rel("寅", "巳"))
        self.assertIsNone(ganzhi.zhi_xing_rel("子", "子"))
        self.assertIsNone(ganzhi.zhi_xing_rel("申", "午"))

    def test_zhi_hidden_single_source_matches_lunar_order(self):
        self.assertIs(ganzhi.ZHI_HIDDEN, bazi.ZHI_HIDDEN)
        for zhi in ganzhi.ZHI:
            self.assertEqual(LunarUtil.ZHI_HIDE_GAN[zhi], [gan for gan, _r in ganzhi.ZHI_HIDDEN[zhi]], zhi)
            self.assertAlmostEqual(1.0, sum(r for _g, r in ganzhi.ZHI_HIDDEN[zhi]), places=6, msg=zhi)
        self.assertEqual([("丙", .6), ("庚", .25), ("戊", .15)], ganzhi.ZHI_HIDDEN["巳"])
        self.assertEqual([("己", .6), ("丁", .25), ("乙", .15)], ganzhi.ZHI_HIDDEN["未"])


class BaziProfileTests(unittest.TestCase):
    def test_synthetic_birth_profile_true_solar_and_yun(self):
        p = synthetic_profile()
        self.assertEqual(["庚午", "壬午", "庚戌", "甲申"], ["".join(x) for x in p["pillars"]])
        # 1990 年夏天中国实行夏令时(UTC+9), 真太阳时校正里包含这 60 分钟
        self.assertAlmostEqual(-74.226, p["calculation"]["true_solar_offset_minutes"], places=2)
        self.assertEqual("15:15:46", p["calculation"]["true_solar_clock"])
        self.assertEqual("逆排", p["dayun_direction"])
        self.assertEqual({"years": 2, "months": 9, "days": 18, "hours": 12}, p["dayun_start_age"])
        self.assertEqual("芒种", p["dayun_reference_jie"]["name"])
        self.assertEqual("辛巳", p["da_yun"][0]["gz"])
        self.assertEqual({"金", "土"}, set(p["favorable"]))
        self.assertEqual({"木", "火"}, set(p["unfavorable"]))
        self.assertEqual(["水"], p["neutral"])

    def test_male_reverses_dayun_direction(self):
        self.assertEqual("顺排", synthetic_profile(gender="male")["dayun_direction"])

    def test_coordinate_uncertainty_away_from_boundary_keeps_hour_pillar(self):
        for longitude in (115.9, 116.9):
            p = synthetic_profile(longitude=longitude)
            self.assertEqual("甲申", "".join(p["pillars"][3]))
            self.assertEqual(0, p["calculation"]["true_solar_day_shift"])

    def test_profile_never_echoes_raw_birth_fields(self):
        blob = json.dumps(synthetic_profile(), ensure_ascii=False)
        for raw in ("1990-06-14", "birth_date", "birth_time", "16:30"):
            self.assertNotIn(raw, blob)

    def test_redacted_profile_drops_reversible_fields_but_still_works(self):
        full = synthetic_profile()
        red = bazi.redact_profile(full)
        for key in ("calculation", "dayun_start_at", "dayun_start_age", "dayun_reference_jie",
                    "source_fingerprint", "verified_at", "element_balance"):
            self.assertNotIn(key, red)
        self.assertEqual({"gender": "female"}, red["source_audit"])
        self.assertEqual([{"step": i + 1, "gz": d["gz"]} for i, d in enumerate(full["da_yun"])], red["da_yun"])
        self.assertNotIn("start", json.dumps(red["da_yun"]))
        alm = A.almanac(datetime(2030, 7, 25, 8, tzinfo=TZ))
        bz_full, bz_red = natal.bazi_today(alm, full), natal.bazi_today(alm, red)
        self.assertIsNone(bz_red["dayun"])                       # 不含大运起止, 不计大运
        dayun_delta = sum(c["delta"] for c in bz_full["components"] if c["rule"] == "大运喜忌")
        self.assertAlmostEqual(bz_full["score"] - dayun_delta, bz_red["score"], places=1)
        self.assertTrue(daily.generate_daily(red, datetime(2030, 7, 25, 8, tzinfo=TZ))["bazi"])

    def test_dayun_label_has_no_exact_dates(self):
        bz = natal.bazi_today(A.almanac(datetime(2030, 7, 25, 8, tzinfo=TZ)), synthetic_profile())
        self.assertRegex(bz["dayun"], r"^[一-鿿]{2}大运$")


class NatalTests(unittest.TestCase):
    def test_watch_days_deterministic_defensive_calendar(self):
        out = natal.watch_days(synthetic_profile(), datetime(2030, 7, 25, 8, tzinfo=TZ), days=60)
        self.assertTrue(out)
        dates = [x["date"] for x in out]
        self.assertEqual(dates, sorted(dates))
        all_tags = {tag for x in out for tag in x["tags"]}
        self.assertIn("冲夫妻宫", all_tags)
        self.assertIn("劫财透干", all_tags)
        for x in out:
            strong = [t for t in x["tags"] if t in ("劫财透干", "冲夫妻宫", "冲本命", "月破")]
            self.assertTrue(strong or len(x["tags"]) >= 2)
            self.assertIn(x["level"], ("重", "常"))

    def test_lucky_days_tables_and_exclusion(self):
        self.assertEqual(("丑", "未"), natal.TIANYI["庚"])
        self.assertEqual("申", natal.LUSHEN["庚"])
        self.assertEqual("亥", natal.WENCHANG["庚"])
        self.assertEqual("酉", natal.TAOHUA["子"])
        p = synthetic_profile()
        lucky = natal.lucky_days(p, datetime(2030, 7, 25, 8, tzinfo=TZ), days=60)
        watch = {x["date"] for x in natal.watch_days(p, datetime(2030, 7, 25, 8, tzinfo=TZ), days=60)}
        self.assertTrue(lucky)
        for x in lucky:
            self.assertNotIn(x["date"], watch)
            self.assertIn(x["level"], ("吉", "大吉"))

    def test_watch_and_lucky_today_match_calendar_scan_on_jie_days(self):
        p = synthetic_profile()
        for ds in ("2030-03-05", "2030-05-05", "2030-07-07", "2030-08-07", "2030-10-08", "2030-12-07"):
            y, m, d = (int(x) for x in ds.split("-"))
            alm = A.almanac(datetime(y, m, d, 8, 30, tzinfo=TZ))
            self.assertNotEqual(alm["gz_month"], alm["gz_month_day"], ds)
            scan_dt = datetime(y, m, d, 8, 30, tzinfo=TZ) - timedelta(days=1)
            for today_fn, list_fn in ((natal.watch_today, natal.watch_days), (natal.lucky_today, natal.lucky_days)):
                today = today_fn(alm, p)
                rows = [r for r in (list_fn(p, scan_dt, days=1) or []) if r["date"] == ds]
                self.assertEqual(bool(today), bool(rows), "%s %s" % (ds, today_fn.__name__))
                if today:
                    self.assertEqual(rows[0]["tags"], today["tags"], ds)

    def test_month_hits_carry_ten_gods_and_sanhe(self):
        hits = natal.month_hits("乙酉", synthetic_profile())
        self.assertIn("月干乙透正财", hits)
        self.assertIn("月支酉本气辛为劫财", hits)
        self.assertEqual({"正财", "劫财"}, monthly.ten_gods_in(hits))
        hits2 = natal.month_hits("丙子", synthetic_profile())
        self.assertIn("月支子与命中午相冲", hits2)
        self.assertIn("月支子与命中申半合水", hits2)
        self.assertEqual({"七杀", "伤官"}, monthly.ten_gods_in(hits2))

    def test_no_profile_degrades_to_none(self):
        alm = A.almanac(datetime(2030, 7, 25, 8, tzinfo=TZ))
        self.assertIsNone(natal.bazi_today(alm, None))
        self.assertIsNone(natal.watch_days(None))
        self.assertIsNone(natal.lucky_today(alm, {}))


class MeihuaTests(unittest.TestCase):
    def test_yijing_lookup_resolves_all_64_pairs(self):
        seen = set()
        for shang in ganzhi.GUA8:
            for xia in ganzhi.GUA8:
                entry = meihua.yijing_entry(shang, xia)
                self.assertIsNotNone(entry, shang + xia)
                self.assertTrue(entry.get("guaci"))
                self.assertGreaterEqual(len(entry.get("yao") or []), 6)
                seen.add(entry["n"])
        self.assertEqual(64, len(seen))
        cast = meihua.meihua_cast(A.almanac(datetime(2030, 9, 10, 8, 30, tzinfo=TZ)))
        self.assertTrue(cast["guaci"])
        self.assertTrue(cast["yaoci"])

    def test_palace_map_has_64_unique_hexagrams(self):
        self.assertEqual(64, len(liuyao.PALACE_MAP))


class DailyTests(unittest.TestCase):
    def test_local_daily_without_llm(self):
        p = daily.generate_daily(synthetic_profile(), datetime(2030, 7, 25, 8, tzinfo=TZ),
                                 weather_data={"desc": "晴", "tmax": 30, "tmin": 24, "rain_prob": 0})
        self.assertEqual(daily.ENGINE_VERSION, p["rule_version"])
        self.assertTrue(p["text"]["local_mode"])
        self.assertFalse(p["text"]["fallback"])
        self.assertEqual(set(daily.DOMAIN_ORDER), set(p["text"]["domains"]))
        self.assertEqual(set(daily.DOMAIN_ORDER), set(p["domain_signals"]))
        self.assertIn("伴侣", p["text"]["domains"]["love"])
        self.assertIn("亲子", p["text"]["domains"]["parent"])
        self.assertIn("primary", p["color_guide"])
        self.assertTrue(p["evidence"]["reality"])

    def test_daily_without_profile_still_has_calendar_layers(self):
        p = daily.generate_daily(None, datetime(2030, 7, 25, 8, tzinfo=TZ))
        self.assertIsNone(p["bazi"])
        self.assertIsNone(p["color_guide"])
        self.assertTrue(p["almanac"]["gz_day"])
        self.assertTrue(p["qimen"]["hours"])

    def test_color_guide_is_deterministic_and_profile_based(self):
        prof = synthetic_profile()
        alm = A.almanac(datetime(2030, 7, 26, 8, tzinfo=TZ))
        first, second = daily.daily_color_guide(alm, prof), daily.daily_color_guide(alm, prof)
        self.assertEqual(first, second)
        self.assertEqual(set(prof["favorable"]), {first["primary"]["element"], first["accent"]["element"]})
        self.assertIn("不代表能改变事件结果", first["disclaimer"])
        self.assertIsNone(daily.daily_color_guide(alm, {"element_weights": {k: -0.5 for k in "木火土金水"}}))

    def test_domain_scores_blend_tide_qimen_weather(self):
        alm = A.almanac(datetime(2030, 7, 27, 8, tzinfo=TZ))
        quiet = daily.domain_scores(alm, {"tide": 1, "components": []}, None, {"rain_prob": 0, "tmax": 28})
        storm = daily.domain_scores(alm, {"tide": 10, "components": []}, None, {"rain_prob": 0, "tmax": 28})
        for key in daily.DOMAIN_ORDER:
            self.assertGreater(storm[key], quiet[key])
        qm = {"best_ranges": ["07-09"], "slow_ranges": [], "dirs": {"生门": "东南"}, "style": "宜攻"}
        boosted = daily.domain_scores(alm, {"tide": 5, "components": []}, qm, None)
        flat = daily.domain_scores(alm, {"tide": 5, "components": []}, None, None)
        self.assertGreater(boosted["work"], flat["work"])
        self.assertGreater(boosted["money"], flat["money"])
        wet = daily.domain_scores(alm, {"tide": 5, "components": []}, None, {"rain_prob": 90, "tmax": 35})
        self.assertLess(wet["body"], flat["body"])

    def test_spouse_star_follows_gender_and_unknown_is_neutral(self):
        fem, male, unknown = daily.domain_vectors("female"), daily.domain_vectors("male"), daily.domain_vectors()
        self.assertGreater(fem["正官"]["love"], fem["正财"]["love"])
        self.assertGreater(male["正财"]["love"], male["正官"]["love"])
        self.assertEqual(unknown["正官"]["love"], unknown["正财"]["love"])
        self.assertEqual(unknown["七杀"]["love"], unknown["偏财"]["love"])
        self.assertEqual(fem["正财"]["money"], male["正财"]["money"])

    def test_signal_summary_and_custom_bands(self):
        scores = {"work": 50, "money": 55, "love": 65, "parent": 70, "body": 49}
        qm = {"best_ranges": ["11-13", "15-17"], "slow_ranges": ["19-21"]}
        display = daily.domain_signal_summary(scores, qm)
        self.assertEqual("high", display["parent"]["level"])
        self.assertEqual("aligned", display["parent"]["agreement"])
        self.assertEqual("neutral", display["work"]["level"])
        self.assertIn("未经科学验证", display["parent"]["disclaimer"])
        tight = daily.domain_signal_summary(scores, qm, {"work": {"low": 40, "high": 50}})
        self.assertEqual("high", tight["work"]["level"])

    def test_calibrated_bands_are_ordered(self):
        bands = daily.calibrate_signal_bands(synthetic_profile(), datetime(2030, 3, 1, tzinfo=TZ), days=40, with_qimen=False)
        for key in daily.DOMAIN_ORDER:
            self.assertLessEqual(bands[key]["low"], bands[key]["high"])

    def test_signal_conflict_is_explicit(self):
        strategy = daily.reconcile_signals({"tide": 2}, {"best_ranges": ["07-09", "09-11", "11-13"], "slow_ranges": []},
                                           {"work": 32, "money": 36, "love": 28, "parent": 35, "body": 34})
        self.assertEqual("弱底盘·有窗口", strategy["state"])
        self.assertIn("低风险", strategy["note"])

    def test_reconcile_signals_knows_yingqi_today(self):
        scores = {"work": 53, "money": 69, "love": 56, "parent": 56, "body": 54}
        qm = {"best_ranges": [], "slow_ranges": ["07-09", "09-11", "11-13"]}
        base = daily.reconcile_signals(None, qm, scores, date_key="2030-03-03")
        self.assertEqual([], base["yingqi_today"])
        due = [{"问": "合成示例问题", "应期": "2030-03-03", "怎么看": "冲空起用", "类别": "事业", "性质": "关键"}]
        st = daily.reconcile_signals(None, qm, scores, due, "2030-03-03")
        self.assertEqual(base["state"], st["state"])
        self.assertEqual("work", st["yingqi_today"][0]["domain"])
        self.assertIn("六爻应期落在今天(事业·冲空起用·关键)", st["note"])
        self.assertTrue(st["note"].startswith(base["note"]))

    def test_structured_time_copy_never_merges_gaps(self):
        copy = G.exact_ranges_copy("传统顺时段", ["07-09", "11-13", "15-17"], "无")
        self.assertEqual("传统顺时段：07:00–09:00、11:00–13:00、15:00–17:00。", copy)

    def test_llm_copy_is_guarded_and_push_derived_after_guard(self):
        # 华盖 / 红鸾是本引擎根本不算的神煞, 材料里不可能出现 -> 必被剔除
        llm = FakeLLM({"smile": "华盖当头,别硬刚。傍晚五点到七点可以用。", "think": "晚上别翻旧账。",
                       "domains": {"work": "按部就班。", "money": "红鸾星动,今天谈钱最顺。", "love": "先把分工说清。",
                                   "parent": "陪孩子读一页书。", "body": "身体整体稳,放心冲。"},
                       "lucky_item": "白色的杯子", "push": "红鸾星动,记得谈钱。", "yingqi_note": None})
        p = daily.generate_daily(synthetic_profile(), datetime(2030, 7, 25, 8, tzinfo=TZ), llm=llm)
        text = p["text"]
        self.assertFalse(text["fallback"])
        self.assertNotIn("红鸾", text["domains"]["money"] + text["push"])
        self.assertNotIn("华盖", text["smile"] + text["push"])
        self.assertTrue(text["domains"]["body"].startswith("传统身心线索"))
        self.assertEqual(text["smile"][:60], text["push"])
        self.assertTrue(text["guard_stripped"])
        self.assertEqual(prompts.DAILY_SYSTEM, llm.calls[0]["system"])

    def test_broken_llm_output_falls_back_to_rules(self):
        llm = CallableClient(lambda system, messages, max_tokens: "不是 JSON")
        p = daily.generate_daily(synthetic_profile(), datetime(2030, 7, 25, 8, tzinfo=TZ), llm=llm)
        self.assertTrue(p["text"]["fallback"])
        self.assertEqual("structured-fallback", p["text"]["copy_policy"])


def _facts(detail="今日乙为正财，卯藏乙正财", month_gist="无"):
    return {
        "今天日期（当地）": "2030-03-03",
        "今日时段(奇门)": {"顺": ["15-17"], "宜缓": ["13-15"]},
        "命理相性": {"日主": "庚金", "潮位": "6/10 平潮", "细节": [detail]},
        "五领域分数(仅传统信号强弱)": {"work": 55, "money": 52, "love": 50, "parent": 50, "body": 48},
        "本月基调(保持口径一致)": month_gist,
    }


def _text(**over):
    text = {"smile": "傍晚五点到七点可以用,适合整理桌面。", "think": "晚上别翻旧账。",
            "domains": {"work": "按部就班就行。", "money": "钱上稳一稳。", "love": "先把分工说清。",
                        "parent": "听孩子讲完一件小事。", "body": "多喝温水。"},
            "lucky_item": "白色的杯子", "push": None, "yingqi_note": None}
    domains = over.pop("domains", None)
    if domains:
        text["domains"].update(domains)
    text.update(over)
    return text


def _fake_ly(strength="平", hidden=False, availability=None, sanhe=None, yingqi=None):
    return {
        "strength_label": strength,
        "ushen": {"liuqin": "官鬼", "zhi": "酉", "wx": "金", "kong": False, "note": "",
                  "hidden": hidden, "availability": availability,
                  "availability_reasons": ["伏神旺相有气(旺)"],
                  "fly": {"liuqin": "兄弟", "zhi": "申"},
                  "fu_fei": {"relation": "飞生伏", "note": "飞生伏，伏神得力"}},
        "yingqi": yingqi if yingqi is not None else [],
        "sanhe": sanhe if sanhe is not None else {"status": "无"},
    }


class NarrativeGuardTests(unittest.TestCase):
    def test_daily_guard_strips_star_absent_from_material(self):
        facts = _facts()
        text, stripped = daily.guard_daily_text(_text(domains={"money": "偏财有气,适合把账对一对。"}), facts)
        self.assertNotIn("偏财", text["domains"]["money"])
        self.assertEqual(daily.domain_rule_texts(G.facts_get(facts, "五领域分数"))["money"], text["domains"]["money"])
        self.assertTrue(any(x["field"] == "domains.money" and "偏财" in x["reason"] for x in stripped), stripped)

    def test_daily_guard_allows_star_and_family_generic_in_material(self):
        text, stripped = daily.guard_daily_text(_text(domains={"money": "正财稳当,财星在位,谈钱顺。"}), _facts())
        self.assertEqual("正财稳当,财星在位,谈钱顺。", text["domains"]["money"])
        self.assertEqual([], stripped)

    def test_material_sentences_are_exempt_on_both_sides(self):
        gist = "本月财星旺,谈钱的事顺。"
        text, stripped = daily.guard_daily_text(
            _text(think=gist, domains={"money": "财星今天特别旺。"}), _facts(detail="今日丙为七杀，午藏丁正官", month_gist=gist))
        self.assertEqual(gist, text["think"])
        self.assertNotIn("财星", text["domains"]["money"])
        self.assertEqual(["domains.money"], [x["field"] for x in stripped])
        note = "用神旺相有气之日可望有信"
        kept, cast_stripped = castmod.guard_cast_text(
            {"result": "先缓", "main_factor": note + "。", "timing": "时机不显。", "advice": "先做一小步。"},
            _fake_ly(strength="弱"), {"应期说明": [note]})
        self.assertEqual(note + "。", kept["main_factor"])
        self.assertEqual([], cast_stripped)

    def test_state_and_hit_claims_are_removed(self):
        text, stripped = daily.guard_daily_text(
            _text(smile="精神好。傍晚五点到七点可以用。", yingqi_note="那卦正中应期。"), _facts())
        self.assertEqual("傍晚五点到七点可以用。", text["smile"])
        self.assertIsNone(text["yingqi_note"])
        self.assertEqual({"smile", "yingqi_note"}, {x["field"] for x in stripped})

    def test_cast_guard_keeps_love_case_ushen_synonyms(self):
        text, stripped = castmod.guard_cast_text(
            {"result": "有戏,但要挑时候", "main_factor": "夫星临日建,对方多半会先开口。",
             "timing": "官星不动,别催。", "advice": "今天先发一句问候。"},
            _fake_ly(strength="平"), {"类别": "感情"})
        self.assertEqual("夫星临日建,对方多半会先开口。", text["main_factor"])
        self.assertEqual([], stripped)

    def test_cast_guard_strips_strength_contradiction(self):
        ly = _fake_ly(strength="弱")
        text, stripped = castmod.guard_cast_text(
            {"result": "可以推进", "main_factor": "用神得力,顺利可推进。", "timing": "近日就有动静。", "advice": "今天就去谈。"},
            ly, {"用神势能": "弱(-1.2)"})
        self.assertEqual(castmod.cast_rule_text(ly)["main_factor"], text["main_factor"])
        self.assertEqual(["main_factor"], [x["field"] for x in stripped])
        keep, none_stripped = castmod.guard_cast_text(
            {"result": "先缓", "main_factor": "伏神旺相有气,只是暂时还出不来。", "timing": "时机不显。", "advice": "先做一小步。"}, ly, {})
        self.assertEqual("伏神旺相有气,只是暂时还出不来。", keep["main_factor"])
        self.assertEqual([], none_stripped)

    def test_no_english_availability_enum_reaches_copy_or_material(self):
        for enum, cn in (("available", "可用"), ("conditional", "有条件可用"), ("blocked", "暂不可用")):
            ly = _fake_ly(strength="弱", hidden=True, availability=enum)
            main = castmod.cast_rule_text(ly)["main_factor"]
            fact = castmod.fushen_fact(ly["ushen"])
            self.assertIn(cn, main)
            self.assertEqual(cn, fact["可用性"])
            for bad in ("available", "conditional", "blocked"):
                self.assertNotIn(bad, main + json.dumps(fact, ensure_ascii=False))

    def test_cast_guard_unfavorable_date_needs_multichar_word_in_date_clause(self):
        ly = _fake_ly(strength="平", yingqi=[{"date": "2030-04-20", "how": "逢冲日破", "kind": "unfavorable", "basis": "增删卜易·日辰章"}])
        for good in ("4月20号那天逢冲日破,别硬办,顺其自然。", "4月20号那天不太顺利,别硬办。",
                     "4月20号别硬推,等下周再说,那时顺利些。", "4月20号那天不利,换个吉日再说。"):
            kept, none_stripped = castmod.guard_cast_text(
                {"result": "看时候", "main_factor": "卦里没给硬话。", "timing": good, "advice": "先做一小步。"}, ly, {})
            self.assertEqual(good, kept["timing"], good)
            self.assertEqual([], none_stripped, good)
        for bad, word in (("4月20号那天挺顺利的。", "顺利"), ("4月20号大吉,放手去做。", "大吉"), ("4月20号是个吉日,宜办。", "吉日")):
            text, stripped = castmod.guard_cast_text(
                {"result": "看时候", "main_factor": "卦里没给硬话。", "timing": bad, "advice": "先做一小步。"}, ly, {})
            self.assertEqual(["timing"], [x["field"] for x in stripped], bad)
            self.assertIn(word, stripped[0]["reason"], bad)

    def test_cite_date_re_does_not_collide_with_hour_ranges(self):
        for ymd, span in (("2030-07-09", "07-09"), ("2030-03-05", "03-05"), ("2030-09-11", "09-11")):
            rx = G.cite_date_re(ymd)
            self.assertIsNone(rx.search("上午%s最顺。" % span), span)
            month, day = int(ymd[5:7]), int(ymd[8:10])
            self.assertTrue(rx.search("%d月%d号那天。" % (month, day)), ymd)
        rx = G.cite_date_re("2030-08-01")
        self.assertTrue(rx.search("8月1号那天"))
        self.assertIsNone(rx.search("8月15号那天"))

    def test_cast_rule_text_mentions_hex_relation_and_sanhe(self):
        ly = _fake_ly(strength="平", sanhe={"status": "成局即发", "name": "申子辰水局", "relation_to_ushen": "生用神"})
        ly["hex_relation"] = "六冲卦"
        out = castmod.cast_rule_text(ly)
        self.assertIn("六冲", out["result"])
        self.assertIn("申子辰水局", out["main_factor"])
        plain = castmod.cast_rule_text(_fake_ly(strength="平"))
        self.assertNotIn("三合", plain["main_factor"])


class BodyLineTests(unittest.TestCase):
    def facts(self, day, score):
        return {"今天日期（当地）": day,
                "五领域分数(仅传统信号强弱)": {k: score for k in daily.DOMAIN_ORDER},
                "本节气食养": A.load_data("jieqi_regimen.json")["立春"]}

    def test_thirty_days_rotate_and_never_assert_state(self):
        lines = [daily._domain_fallback(self.facts((date(2030, 2, 5) + timedelta(days=i)).isoformat(), 50), "body") for i in range(30)]
        self.assertGreaterEqual(len(set(lines)), 8)
        for line in lines:
            self.assertTrue(line.startswith("传统身心线索"), line)
            self.assertLessEqual(len(line), 44, line)
            self.assertFalse(G.unverified_state(line), line)
        self.assertTrue(any("本节气" in x for x in lines))

    def test_every_regimen_entry_yields_safe_lines(self):
        bad = []
        for name, reg in A.load_data("jieqi_regimen.json").items():
            for score in (95, 50, 5):
                for i in range(0, 366, 9):
                    facts = {"今天日期（当地）": (date(2030, 3, 1) + timedelta(days=i)).isoformat(),
                             "五领域分数": {k: score for k in daily.DOMAIN_ORDER}, "本节气食养": reg}
                    line = daily._domain_fallback(facts, "body")
                    if line.endswith("按平常作息即可。") or G.unverified_state(line) or len(line) > 44:
                        bad.append((name, score, line))
        self.assertEqual([], bad[:5])


class MonthlyTests(unittest.TestCase):
    def test_monthly_rule_mode_is_calendar_keyed(self):
        p = monthly.monthly_fortune(synthetic_profile(), datetime(2030, 9, 2, 8, tzinfo=TZ))
        self.assertEqual("2030-09", p["month"])
        self.assertEqual("甲申→乙酉", p["ganzhi_month"])
        self.assertEqual("乙酉", p["main_ganzhi"])
        self.assertEqual("2030-09-07", p["switch_date"])
        self.assertTrue(p["local_mode"])
        self.assertIn("白露", p["text"])
        self.assertIn("不强制生成", p["text"])
        self.assertNotIn("hits", p["segments"][0])
        self.assertRegex(str(p["basis"]["大运"]), r"^[一-鿿]{2}大运$")  # 交给模型的材料不带起运日期

    def test_star_guard_strips_unbacked_star_sentences(self):
        text, stripped = monthly.star_guard("月初节奏慢一点。下旬七杀压身先别逞强。周末去河边走走。", set())
        self.assertEqual("月初节奏慢一点。周末去河边走走。", text)
        self.assertEqual(1, len(stripped))

    def test_llm_retries_once_when_star_is_unbacked(self):
        prof = synthetic_profile()
        self.assertNotIn("七杀", monthly.ten_gods_in(natal.month_hits("乙酉", prof)))
        answers = iter([{"title": "稳", "text": "本月七杀压身。其余平稳。"}, {"title": "稳", "text": "本月平稳推进。"}])
        llm = CallableClient(lambda s, m, n: json.dumps(next(answers), ensure_ascii=False))
        p = monthly.monthly_fortune(prof, datetime(2030, 9, 2, 8, tzinfo=TZ), llm=llm)
        self.assertEqual("本月平稳推进。", p["text"])


class PromptNeutralityTests(unittest.TestCase):
    SYSTEMS = (prompts.DAILY_SYSTEM, prompts.MONTH_SYSTEM, prompts.LIUYAO_SYSTEM)

    def test_prompts_use_generic_role_and_second_person_only(self):
        for system in self.SYSTEMS:
            self.assertTrue(system.startswith("你是「潮签」的"), system[:20])
        blob = "".join(self.SYSTEMS) + daily._DAILY_INSTRUCTION + castmod._CAST_INSTRUCTION
        # 不出现第三人称性别代词: 读者一律是「用户 / 你」
        self.assertEqual([], re.findall(r"(?<!其)[他她]", blob))

    def test_loads_json_loose(self):
        self.assertEqual({"a": 1}, loads_json_loose("```json\n{\"a\": 1}\n```"))
        self.assertEqual([1], loads_json_loose("回复: [1] 完"))
        self.assertIsNone(loads_json_loose("nothing"))


class LiuyaoGenderTests(unittest.TestCase):
    FUTURE = [("2030-08-%02d" % (i + 1), liuyao.ZHI[i % 12]) for i in range(28)]

    def test_love_category_ushen_follows_gender(self):
        for gender, target in (("female", "官鬼"), ("male", "妻财")):
            for seed in range(20):
                r = liuyao.cast("合成", "感情", 28, "壬辰", "未", "午未", self.FUTURE, rng=random.Random(seed), gender=gender)
                if r["ushen"]["selection_status"] == "ok":
                    self.assertEqual(target, r["ushen"]["liuqin"], (gender, seed))

    def test_love_category_requires_gender_and_others_do_not(self):
        with self.assertRaises(ValueError):
            liuyao.cast("合成", "感情", 28, "壬辰", "未", "午未", self.FUTURE, rng=random.Random(1))
        with self.assertRaises(ValueError):
            liuyao.cast("合成", "感情", 28, "壬辰", "未", "午未", self.FUTURE, rng=random.Random(1), gender="x")
        r = liuyao.cast("合成", "事业", 28, "壬辰", "未", "午未", self.FUTURE, rng=random.Random(1))
        self.assertEqual("官鬼", r["ushen"]["liuqin"] if r["ushen"]["selection_status"] == "ok" else "官鬼")

    def test_qimen_grid(self):
        for day in range(1, 29):
            p = qimen.pan(datetime(2030, 7, day, 11, 30, tzinfo=TZ))
            self.assertEqual(8, len(p["palaces"]))
            self.assertEqual(8, len({v["door"] for v in p["palaces"].values()}))


if __name__ == "__main__":
    unittest.main()
