"""Synthetic counterexamples for the line-action trial; no profile or network."""
import copy
import json
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from chaoqian import cast as castmod
from chaoqian import liuyao
from chaoqian.contract import build_event_contract, freeze_prediction
from chaoqian.llm import LLMClient


class FakeLLM(LLMClient):
    """记录调用并返回固定 JSON 的假模型(不联网)。"""

    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def complete(self, system, messages, max_tokens=1024):
        self.calls.append({"system": system, "messages": messages})
        return json.dumps(self.payload, ensure_ascii=False)

    @property
    def last_prompt(self):
        return self.calls[-1]["messages"][-1]["content"]


def line(zhi, **kwargs):
    return dict({"pos": 1, "zhi": zhi, "wx": liuyao.ZHI_WX[zhi],
                 "moving": True, "kong": False}, **kwargs)


class LineActionTests(unittest.TestCase):
    def test_report_counterexample_no_longer_counts_disabled_support(self):
        r = liuyao.cast("合成测试事项", "财务", 30, "甲子", "酉", "戌亥", [],
                        coins=[0, 1, 1, 2, 3, 1])
        source = next(x for x in r["influences"] if x["pos"] == 5)
        self.assertEqual("blocked", source["action"]["status"])
        self.assertIn("动化回头克", source["action"]["reasons"])
        self.assertEqual(0, source["score_delta"])
        self.assertNotIn("动爻5生用神", r["factors"])
        self.assertAlmostEqual(.48, r["strength_score"])

    def test_strong_or_day_supported_back_clash_is_unresolved_not_declared_dead(self):
        y = line("巳", bian={"zhi": "子", "wx": "水", "relation": "回头克"})
        for month, day in (("巳", "酉"), ("酉", "卯")):
            with self.subTest(month=month, day=day):
                a = liuyao._line_action(y, month, day)
                self.assertEqual("uncertain", a["status"])
                self.assertIn("动化回头克", a["reasons"])

    def test_other_moving_support_retains_rescue_uncertainty(self):
        y = line("巳", bian={"zhi": "子", "wx": "水", "relation": "回头克"})
        rescue = line("卯", pos=2)
        a = liuyao._line_action(y, "酉", "子", other_yaos=[y, rescue])
        self.assertEqual("uncertain", a["status"])
        self.assertIn("另有发动爻相生，救应尚未核定", a["reasons"])

    def test_unrestricted_strong_source_is_available(self):
        a = liuyao._line_action(line("卯"), "寅", "子")
        self.assertEqual("available", a["status"])

    def test_back_generation_alone_does_not_erase_other_injury(self):
        y = line("巳", bian={"zhi": "卯", "wx": "木", "relation": "回头生"})
        a = liuyao._line_action(y, "酉", "子")
        self.assertEqual("uncertain", a["status"])

    def test_moving_void_has_no_void_penalty_but_still_waits(self):
        y = line("戌", kong=True)
        score, factors = liuyao._line_strength(y, "申", "子")
        a = liuyao._line_action(y, "申", "子", "戌亥")
        self.assertEqual(0, score)
        self.assertIn("旬空(动空待实)", factors)
        self.assertNotIn("旬空(真空)", factors)
        self.assertEqual("waiting", a["status"])
        self.assertEqual({"戌", "辰"}, set(a["wait_for"][0]["branches"]))

    def test_static_void_scoring_is_not_silently_changed(self):
        score, factors = liuyao._line_strength(line("戌", moving=False, kong=True), "申", "子")
        self.assertEqual(-1.5, score)
        self.assertIn("旬空(真空)", factors)

    def test_void_release_does_not_hide_month_break(self):
        y = line("戌", kong=True)
        _score, factors = liuyao._line_strength(y, "辰", "子")
        a = liuyao._line_action(y, "辰", "子", "戌亥")
        self.assertIn("月破", factors)
        self.assertEqual({"moving_void", "month_broken"}, {x["id"] for x in a["wait_for"]})

    def test_day_clash_releases_void_without_erasing_other_conditions(self):
        y = line("戌", kong=True)
        _score, factors = liuyao._line_strength(y, "申", "辰")
        a = liuyao._line_action(y, "申", "辰", "戌亥")
        self.assertIn("空逢冲起", factors)
        self.assertNotIn("moving_void", {x["id"] for x in a["wait_for"]})

    def test_injury_is_preserved_when_void_is_not_penalized(self):
        y = line("卯", kong=True, bian={"zhi": "酉", "wx": "金", "relation": "回头克"})
        a = liuyao._line_action(y, "申", "申", "寅卯")
        self.assertEqual("blocked", a["status"])
        self.assertTrue(a["wait_for"])

    def test_strong_moving_void_still_has_fill_and_clash_observations(self):
        y = line("卯", kong=True)
        y["action"] = liuyao._line_action(y, "寅", "未", "寅卯")
        days = [("2030-03-11", "卯"), ("2030-03-12", "酉")]
        original = copy.deepcopy(y)
        hits = liuyao._yingqi_all(y, days, 2, "寅", "未")
        self.assertEqual(original, y)
        self.assertIn("填实出空", {x["how"] for x in hits})
        self.assertIn("动空冲实", {x["how"] for x in hits})
        self.assertNotIn("动爻逢冲", {x["how"] for x in hits})
        self.assertTrue(all(x["kind"] == "critical" for x in hits))

    def test_combination_and_changed_void_are_explicit_waits(self):
        y = line("午", bian={"zhi": "未", "wx": "土", "relation": "化泄"})
        a = liuyao._line_action(y, "巳", "申", "午未")
        self.assertEqual("waiting", a["status"])
        self.assertEqual({"changed_void", "changed_combined"}, {x["id"] for x in a["wait_for"]})

    def test_disabled_moving_source_cannot_rescue_fushen_through_other_path(self):
        y = line("巳", bian={"zhi": "子", "wx": "水", "relation": "回头克"})
        sf = liuyao._fushen_shengfu(line("丑", moving=False), "酉", "子", [y])
        self.assertFalse(sf["sheng"])
        self.assertNotIn("动爻1生伏神", sf["tags"])


class TrialContractTests(unittest.TestCase):
    dt = datetime(2030, 5, 21, 9, tzinfo=ZoneInfo("Asia/Shanghai"))

    def test_high_score_with_unresolved_target_is_not_yes(self):
        contract = build_event_contract("合成事项能办成吗", "文书", 30, self.dt)
        ly = {"strength_label": "强", "ushen": {"action": {"status": "waiting"}},
              "rule_version": liuyao.RULE_VERSION}
        prediction = freeze_prediction(contract, ly, {})
        self.assertEqual("undetermined", prediction["direction"])
        self.assertEqual("conditions_unresolved", prediction["direction_reason"])
        for status in ("blocked", "uncertain"):
            ly = {"strength_label": "强", "ushen": {"action": {"status": status}},
                  "rule_version": liuyao.RULE_VERSION}
            prediction = freeze_prediction(contract, ly, {})
            self.assertEqual("yes", prediction["direction"], status)
            self.assertEqual("rule_tendency_only", prediction["direction_reason"])

    def test_unresolved_influence_is_not_ignored_in_headline(self):
        contract = build_event_contract("合成事项能办成吗", "文书", 30, self.dt)
        ly = {"strength_label": "强", "ushen": {"action": {"status": "available"}},
              "influences": [{"action": {"status": "waiting"}}]}
        self.assertEqual("undetermined", freeze_prediction(contract, ly, {})["direction"])
        ly["influences"] = [{"action": {"status": "uncertain"}, "weight": .6}]
        self.assertEqual("yes", freeze_prediction(contract, ly, {})["direction"])

    def test_strong_moving_void_source_is_available_v65(self):
        # 增删卜易·元神忌神衰旺章 能生第五条「元神旺动, 临空化空」: 卯木在寅月旺相, 逢空仍能生克, 出空日保留为观察点。
        # (日支取子: 未日卯木入日墓会另起 tomb 待时, 不是本条要测的情形)
        y = line("卯", kong=True)
        a = liuyao._line_action(y, "寅", "子", "寅卯")
        self.assertEqual("available", a["status"])
        self.assertIn("旺动临空化空仍能生克", a["reasons"])
        self.assertEqual({"moving_void"}, {x["id"] for x in a["wait_for"]})
        # 休囚动空仍待时 (同章「休囚又逢自空」不能生)
        self.assertEqual("waiting", liuyao._line_action(line("戌", kong=True), "申", "子", "戌亥")["status"])

    def test_uncertain_source_counts_at_sixty_percent_v65(self):
        r = liuyao.cast("合成测试事项", "财务", 30, "丁酉", "巳", "辰巳", [], coins=[3, 2, 0, 0, 1, 2])
        src = next(x for x in r["influences"] if x["pos"] == 1)
        self.assertEqual("uncertain", src["action"]["status"])
        self.assertEqual(.6, src["weight"])
        self.assertAlmostEqual(-.72, src["score_delta"])
        self.assertTrue(any("爻1克用神(六折)" in f for f in r["factors"]), r["factors"])
        self.assertEqual(liuyao.ACTION_VERSION, "chaoqian-line-action-0.1")

    def test_payload_without_action_uses_strength_only_policy(self):
        contract = build_event_contract("合成事项能办成吗", "文书", 30, self.dt)
        p = freeze_prediction(contract, {"strength_label": "强"}, {})
        self.assertEqual("yes", p["direction"])
        self.assertEqual("strength-only", p["decision_policy"])

    def test_generated_reading_cannot_erase_restrictions_or_change_version(self):
        sample = {"result": "已经能成", "main_factor": "所有助力都已经落实。",
                  "timing": "观察", "advice": "先核对实际进度。"}
        p = castmod.cast_question("合成事项能办成吗", self.dt, {"coins": [0, 1, 1, 2, 3, 1]},
                                  "财务", 30, llm=FakeLLM(sample))
        self.assertEqual(liuyao.RULE_VERSION, p["rule_version"])
        self.assertEqual(liuyao.RULE_VERSION, p["prediction"]["engine_rule_version"])
        self.assertEqual(castmod.cast_rule_text(p["liuyao"])["main_factor"], p["text"]["main_factor"])
        self.assertNotIn("所有助力都已经落实", p["text"]["main_factor"])
        self.assertTrue(p["text"]["condition_note"])


if __name__ == "__main__":
    unittest.main()
