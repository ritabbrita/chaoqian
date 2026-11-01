# -*- coding: utf-8 -*-
"""问事合同 / 期限 / 解卦护栏。全部合成数据, 不联网。"""
import json
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from chaoqian.cast import cast_question
from chaoqian.contract import build_event_contract, guard_contract_text
from chaoqian.daily import guard_daily_text
from chaoqian.llm import LLMClient


class FakeLLM(LLMClient):
    """记录调用并返回固定 JSON 的假模型。"""

    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def complete(self, system, messages, max_tokens=1024):
        self.calls.append({"system": system, "messages": messages})
        return json.dumps(self.payload, ensure_ascii=False)

    @property
    def last_prompt(self):
        return self.calls[-1]["messages"][-1]["content"]


class EventContractTests(unittest.TestCase):
    dt = datetime(2030, 5, 21, 9, 30, tzinfo=ZoneInfo("Asia/Shanghai"))
    coins = [0, 1, 2, 3, 1, 2]

    def cast(self, horizon=90, question="示例申请什么时候有结果？", **kwargs):
        context = {"coins": self.coins, **kwargs.pop("context", {})}
        return cast_question(question, self.dt, context, "文书", horizon, **kwargs)

    def test_long_horizons_cover_requested_deadline_and_keep_cast(self):
        base = self.cast(7)
        for horizon in (30, 90, 180, 365):
            p = self.cast(horizon)
            self.assertEqual(base["liuyao"]["throws"], p["liuyao"]["throws"])
            self.assertEqual(base["liuyao"]["strength_score"], p["liuyao"]["strength_score"])
            self.assertEqual(p["event_contract"]["deadline"], p["timeline"]["deadline"])
            self.assertEqual(p["timeline"]["deadline"], p["timeline"]["stages"][-1]["end"])
            self.assertIn(str(horizon), p["text"]["result"])
            dates = [x["date"] for x in p["liuyao"]["yingqi"]]
            self.assertEqual(len(dates), len(set(dates)))
            if horizon >= 90:
                self.assertGreater((datetime.fromisoformat(max(dates)).date() - self.dt.date()).days, 36)

    def test_anchor_timestamp_preserves_original_start_when_revising(self):
        tomorrow = self.dt.replace(day=19)
        p = cast_question("测试事项能完成吗？", tomorrow,
                          {"coins": self.coins, "anchor_ts": self.dt.timestamp()}, "文书", 180)
        self.assertEqual(self.dt.date().isoformat(), p["event_contract"]["start"])

    def test_comparison_not_relabelled_as_ordinary_receipt(self):
        p = self.cast(90, "三个示例方案里哪个评分最高？")
        self.assertEqual("comparison", p["event_contract"]["event_type"])
        self.assertFalse(p["event_contract"]["verifiable"])
        self.assertEqual("undetermined", p["prediction"]["direction"])
        self.assertIn("比较", p["text"]["result"])

    def test_input_validation_is_not_silently_downgraded(self):
        for question, horizon, context in (("x" * 241, 30, {}), ("测试", 500, {}),
                                           ("测试", 30, {"coins": [True] * 6})):
            with self.assertRaises(ValueError):
                cast_question(question, self.dt, context, "财务", horizon)

    def test_explicit_followup_preserves_original_event_semantics(self):
        original = build_event_contract("几个示例方案里哪个得分最高？", "事业", 90, self.dt,
                                        {"criterion": "方案A交付完成"})
        revised = build_event_contract("那现在呢？", "事业", 365, self.dt,
                                       {"inherited_event_contract": original})
        self.assertEqual("comparison", revised["event_type"])
        self.assertFalse(revised["verifiable"])
        self.assertEqual(original["target_event"], revised["target_event"])
        self.assertEqual(original["question"], revised["question"])
        self.assertEqual("那现在呢？", revised["asked_now"])
        self.assertEqual("inherited", revised["criterion_source"])
        changed = build_event_contract("那现在呢？", "事业", 365, self.dt,
                                       {"inherited_event_contract": original, "criterion": "方案B交付完成"})
        self.assertEqual("方案B交付完成", changed["target_event"])
        self.assertEqual("user", changed["criterion_source"])

    def test_llm_gets_supplied_event_facts_but_cannot_change_headline(self):
        llm = FakeLLM({"result": "近三日一定会成功", "main_factor": "对方已经准备好审批材料。",
                       "timing": "2040年8月9日办完。", "advice": "下周一把报名表填好交上。"})
        p = self.cast(90, context={"background": "目前只交了申请表，还没有面试。",
                                   "related_history": [{"question": "同一测试事项", "result": "partial"}]},
                      llm=llm)
        prompt = llm.last_prompt
        self.assertIn("目前只交了申请表，还没有面试", prompt)
        self.assertIn("同一测试事项", prompt)
        self.assertNotIn("一定会成功", str(p["text"]))
        self.assertNotIn("2040年", str(p["text"]))
        self.assertNotIn("准备好审批材料", str(p["text"]))
        self.assertGreaterEqual(len(p["text"]["guard_stripped"]), 3)
        self.assertLess(len(prompt), 22000)

    def test_one_year_prompt_is_bounded_and_does_not_dump_all_candidates(self):
        llm = FakeLLM({"result": "按全年看", "main_factor": "原卦强弱与阶段条件分别观察。",
                       "timing": "各月条件有变化。", "advice": "先确认当前阶段。"})
        cast_question("今年这件事能完成吗？", self.dt, {"coins": self.coins}, "事业", 365, llm=llm)
        self.assertLess(len(llm.last_prompt), 24000)

    def test_default_completion_standards_cover_several_categories(self):
        for question, category, expected in (("示例考试能通过吗？", "文书", "正式成绩"),
                                              ("示例行程能按时出发吗？", "其他", "实际成行"),
                                              ("示例复查结果怎么样？", "身心", "正式报告"),
                                              ("示例报销何时到账？", "财务", "实际到账"),
                                              ("示例项目能按期交付吗？", "事业", "实际交付")):
            c = build_event_contract(question, category, 90, self.dt)
            self.assertIn(expected, c["criterion"], question)
            self.assertIn("进展", c["criterion"] + "进展", question)
        self.assertIn("不提供任何医疗判断", build_event_contract("示例复查结果怎么样？", "身心", 90, self.dt)["criterion"])

    def test_adverse_event_and_comparison_are_not_positive_strength_yes(self):
        for question, context in (("A方案比B方案好吗？", {}), ("示例申请会被拒绝吗？", {}),
                                  ("示例航班会延误吗？", {}), ("申请会失败吗？", {"criterion": "收到正式拒绝通知"})):
            c = build_event_contract(question, "其他", 90, self.dt, context)
            self.assertFalse(c["verifiable"], question)

    def test_guard_does_not_treat_matching_subject_prefix_as_matching_fact(self):
        p = self.cast(context={"background": "学校已经拒绝了第一次申请。"})
        for advice in ("学校已经把录取通知寄出了。", "如果你愿意跟进，学校已经把录取通知寄出了。"):
            sample = {**p["text"], "advice": advice, "timing": "2040.8.9出结果。"}
            out, removed = guard_contract_text(sample, p["event_contract"], p["timeline"], p["text"])
            self.assertNotIn("寄出了", out["advice"])
            self.assertNotIn("2040", out["timing"])
            self.assertEqual({"advice", "timing"}, {x["field"] for x in removed})

    def test_unsupported_date_and_probability_guard_retains_conditional_advice(self):
        p = self.cast()
        sample = {"result": "成功率90%", "main_factor": "先核对原问题的条件。",
                  "timing": "2034-08-02出结果。", "advice": "如果已经报名，可核对通知里写的日期。"}
        out, removed = guard_contract_text(sample, p["event_contract"], p["timeline"], p["text"])
        self.assertEqual(sample["advice"], out["advice"])
        self.assertNotIn("2034", out["timing"])
        self.assertEqual({"result", "timing"}, {x["field"] for x in removed})

    def test_daily_cannot_relabel_event_as_prediction_hit(self):
        raw = {"smile": "按当前计划推进。", "think": "核对实际条件。", "domains": {},
               "lucky_item": "常用杯子", "yingqi_note": "那卦正中应期，已经算准了。"}
        text, stripped = guard_daily_text(raw, {})
        self.assertIsNone(text["yingqi_note"])
        self.assertTrue(any(x["field"] == "yingqi_note" for x in stripped))


if __name__ == "__main__":
    unittest.main()
