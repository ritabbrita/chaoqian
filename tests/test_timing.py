# -*- coding: utf-8 -*-
"""Synthetic tests only: no profiles, network, application import, or database."""
from copy import deepcopy
from datetime import datetime, timedelta
import random
import unittest
from unittest.mock import patch

from lunar_python import Solar

from chaoqian import liuyao
from chaoqian import timing


START = datetime(2030, 3, 15, 9, 0, tzinfo=timing.CALENDAR_TZ)


def _cast(seed=17, horizon=365, start=START, coins=None):
    lunar = timing._lunar(start)
    gz = lunar.getDayInGanZhi()
    gi = "甲乙丙丁戊己庚辛壬癸".index(gz[0])
    zi = liuyao.ZHI.index(gz[1])
    cycle = next(i for i in range(60) if i % 10 == gi and i % 12 == zi)
    head = cycle - cycle % 10
    kong = liuyao.ZHI[(head + 10) % 12] + liuyao.ZHI[(head + 11) % 12]
    future = []
    for offset in range(1, horizon + 1):
        day = start + timedelta(days=offset)
        future.append((day.date().isoformat(), Solar.fromYmd(day.year, day.month, day.day).getLunar().getDayZhi()))
    return liuyao.cast("合成目标是否在期限内完成", "财务", horizon, gz,
                       lunar.getMonthZhiExact(), kong, future,
                       rng=random.Random(seed) if coins is None else None, coins=coins)


class ReusableCoinsTests(unittest.TestCase):
    def test_reusing_coins_preserves_entire_original_chart_and_strength(self):
        original = _cast(horizon=30)
        revised = _cast(horizon=365, coins=original["coins"])
        for key in ("coins", "throws", "lines", "moving", "ben", "bian", "palace", "shi", "ying",
                    "yaos", "ushen", "strength_score", "strength_label", "sanhe", "cast_context"):
            self.assertEqual(original[key], revised[key], key)
        self.assertEqual("heads-count", revised["coin_encoding"])
        self.assertGreater(len(revised["yingqi_all"]), 12)
        self.assertGreater(revised["yingqi_all"][-1]["date"], (START + timedelta(days=330)).date().isoformat())

    def test_all_throw_states_replay_without_using_rng(self):
        for coins in ([0] * 6, [1] * 6, [2] * 6, [3] * 6, [0, 1, 2, 3, 0, 3]):
            first = _cast(horizon=7, coins=coins)
            second = _cast(horizon=7, coins=first["throws"])
            self.assertEqual(first, second)

    def test_coin_validation_rejects_ambiguous_or_invalid_input(self):
        for coins in ([], [0] * 5, [0] * 7, [0, 1, 2, 3, 0, 4], [0, 1, 2, 3, 0, -1],
                      [0, 1, 2, 3, 0, True], [0, 1, 2, 3, 0, 1.0], "012303"):
            with self.subTest(coins=coins), self.assertRaises(ValueError):
                _cast(horizon=7, coins=coins)
        with self.assertRaisesRegex(ValueError, "cannot be supplied"):
            liuyao.cast("合成", "其他", 7, "甲子", "子", "戌亥", [], rng=random.Random(1), coins=[1] * 6)


class CandidateAggregationTests(unittest.TestCase):
    def test_same_trigger_multiple_references_displays_and_ranks_once(self):
        hits = [{"date": "2030-05-12", "how": "合用神", "kind": "favorable", "basis": "古籍出处A"},
                {"date": "2030-05-12", "how": "合用神", "kind": "favorable", "basis": "古籍出处B"},
                {"date": "2030-05-12", "how": "得生扶之日", "kind": "favorable", "basis": "出处C"},
                {"date": "2030-05-12", "how": "用神长生之日", "kind": "favorable", "basis": "出处D"}]
        result = timing.aggregate_candidates(hits)[0]
        self.assertEqual("合用神；得生扶之日；用神长生之日", result["how"])
        self.assertEqual(4, len(result["reasons"]))
        self.assertEqual(3, result["evidence_count"])
        self.assertEqual({"古籍出处A", "古籍出处B"},
                         {r["basis"] for r in result["reasons"] if r["how"] == "合用神"})

    def test_joined_duplicate_labels_and_reaggregation_are_idempotent(self):
        joined = "逢巳日填实出空，局始成；逢变爻巳；逢巳日填实出空，局始成；逢变爻巳"
        hits = [{"date": "2030-05-19", "how": joined, "kind": "critical", "basis": "出处A"},
                {"date": "2030-05-19", "how": "逢变爻巳", "kind": "favorable", "basis": "出处B"}]
        once = timing.aggregate_candidates(hits)
        twice = timing.aggregate_candidates(once)
        self.assertEqual("逢巳日填实出空，局始成；逢变爻巳", once[0]["how"])
        self.assertEqual(2, once[0]["evidence_count"])
        self.assertEqual(2, len(once[0]["reasons"]))
        self.assertEqual(once, twice)

    def test_reference_multiplicity_cannot_outvote_distinct_triggers(self):
        hits = [{"date": "2030-05-12", "how": "合用神", "kind": "favorable", "basis": "A"},
                {"date": "2030-05-12", "how": "得生扶之日", "kind": "favorable", "basis": "B"}]
        hits.extend({"date": "2030-05-19", "how": "值用神", "kind": "favorable", "basis": "出处%d" % i}
                    for i in range(6))
        candidates = timing.aggregate_candidates(hits)
        selected = timing._representatives(candidates, 1)
        self.assertEqual("2030-05-12", selected[0]["date"])
        self.assertEqual(6, len(candidates[1]["reasons"]))
        self.assertEqual(1, candidates[1]["evidence_count"])

    def test_same_date_preserves_every_reason_and_adverse_evidence(self):
        hits = [{"date": "2030-04-01", "how": "值用神", "kind": "favorable", "basis": "A"},
                {"date": "2030-04-01", "how": "逢冲日破", "kind": "unfavorable", "basis": "B"},
                {"date": "2030-04-01", "how": "待冲墓", "kind": "critical", "basis": "C"}]
        result = timing.aggregate_candidates(hits + [hits[0]])
        self.assertEqual(1, len(result))
        self.assertEqual(3, len(result[0]["reasons"]))
        self.assertEqual("unfavorable", result[0]["kind"])
        self.assertTrue(result[0]["mixed"])
        self.assertEqual({"favorable", "critical", "unfavorable"}, set(result[0]["kinds"]))

    def test_stage_selection_keeps_critical_and_adverse_without_inventing_dates(self):
        candidates = timing.aggregate_candidates([
            {"date": "2030-04-01", "how": "吉", "kind": "favorable"},
            {"date": "2030-04-10", "how": "凶", "kind": "unfavorable"},
            {"date": "2030-04-20", "how": "关键", "kind": "critical"},
        ])
        result = timing._representatives(candidates, 2)
        self.assertEqual(["2030-04-10", "2030-04-20"], [x["date"] for x in result])
        self.assertEqual([], timing._representatives([], 2))


class TimelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = _cast()

    def test_all_supported_horizons_cover_entire_window_without_duplicate_dates(self):
        for horizon in timing.SUPPORTED_HORIZONS:
            with self.subTest(horizon=horizon):
                result = timing.build_timeline(self.original, START, horizon)
                self.assertEqual((START + timedelta(days=horizon)).date().isoformat(), result["deadline"])
                self.assertEqual(START.isoformat(), result["stages"][0]["start_at"])
                self.assertEqual(result["deadline"], result["stages"][-1]["end"])
                dates = [x["date"] for x in result["primary_candidates"]]
                self.assertEqual(len(dates), len(set(dates)))
                all_dates = {x["date"] for x in result["all_candidates"]}
                self.assertTrue(set(dates).issubset(all_dates))
                self.assertEqual(sum(len(s["candidates"]) for s in result["stages"]), len(all_dates))
                for previous, following in zip(result["stages"], result["stages"][1:]):
                    self.assertEqual(previous["end_at"], following["start_at"])
                    self.assertNotEqual(previous["month_zhi"], following["month_zhi"])
                if horizon >= 90:
                    self.assertTrue(any(x["date"] > (START + timedelta(days=horizon - 35)).date().isoformat() for x in result["primary_candidates"]))

    def test_exact_solar_term_boundary_uses_old_then_new_month(self):
        term = timing._lunar(START).getNextJie(False)
        boundary = timing._term_datetime(term)
        before = boundary - timedelta(seconds=1)
        chart = _cast(horizon=7, start=before)
        result = timing.build_timeline(chart, before, 7)
        self.assertEqual(boundary.isoformat(), result["stages"][0]["end_at"])
        self.assertEqual(boundary.isoformat(), result["stages"][1]["start_at"])
        self.assertEqual(timing._lunar(before).getMonthZhiExact(), result["stages"][0]["month_zhi"])
        self.assertEqual(timing._lunar(boundary).getMonthZhiExact(), result["stages"][1]["month_zhi"])
        exact = timing.build_timeline(chart, boundary, 7)
        self.assertEqual(timing._lunar(boundary).getMonthZhiExact(), exact["stages"][0]["month_zhi"])

    def test_future_month_conditions_change_while_original_result_does_not(self):
        snapshot = deepcopy(self.original)
        result = timing.build_timeline(self.original, START, 365)
        self.assertEqual(snapshot, self.original)
        self.assertEqual(self.original["strength_label"], result["original_strength"])
        self.assertGreater(len({s["month_state"] for s in result["stages"]}), 1)
        self.assertTrue(any(s["support"] for s in result["stages"]))
        self.assertTrue(any(s["pressure"] for s in result["stages"]))

    def test_empty_trigger_stage_has_no_manufactured_forecast(self):
        with patch.object(liuyao, "_yingqi_all", return_value=[]):
            result = timing.build_timeline(self.original, START, 90)
        self.assertEqual([], result["primary_candidates"])
        self.assertEqual([], result["all_candidates"])
        self.assertGreater(len(result["stages"]), 2)
        self.assertTrue(all("不强定日期" in s["summary"] for s in result["stages"]))

    def test_partial_future_days_do_not_truncate_longer_horizon(self):
        day = START + timedelta(days=1)
        supplied = [(day.date().isoformat(), timing._lunar(day).getDayZhi())]
        result = timing.build_timeline(self.original, START, 180, supplied)
        self.assertTrue(any(c["date"] > (START + timedelta(days=150)).date().isoformat() for c in result["all_candidates"]))
        with self.assertRaises(ValueError):
            timing.build_timeline(self.original, START, 7, supplied * 2)
        with self.assertRaises(ValueError):
            timing.build_timeline(self.original, START, 7, [(day.date().isoformat(), "错")])

    def test_includes_current_day_trigger_and_validates_horizon(self):
        today = START.date().isoformat()
        today_zhi = timing._lunar(START).getDayZhi()
        chart = deepcopy(self.original)
        chart["ushen"]["zhi"] = today_zhi
        chart["ushen"]["wx"] = liuyao.ZHI_WX[today_zhi]
        result = timing.build_timeline(chart, START, 7)
        self.assertTrue(result["includes_today"])
        self.assertIn(today, [x["date"] for x in result["all_candidates"]])
        for horizon in (True, "90", 0, 31, 366):
            with self.subTest(horizon=horizon), self.assertRaises(ValueError):
                timing.build_timeline(self.original, START, horizon)


if __name__ == "__main__":
    unittest.main()
