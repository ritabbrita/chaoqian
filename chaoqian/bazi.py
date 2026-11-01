#!/usr/bin/env python3
"""八字排盘: 由出生信息确定性地编译出一份可审计的命盘 profile。

真太阳时校正(NOAA 均时差近似 + 经度差) -> lunar-python 精确交节四柱 -> 藏干 / 五行强弱与调候 ->
喜忌连续权重 -> 起运(分钟法, 3 天折 1 年) -> 八步大运。

日签引擎只读编译后的 profile; 本库不会把 profile 或出生信息写进提示词。

⚠ profile 与出生信息同等敏感, 绝不要公开分享: 除了 calculation(经纬度、真太阳时)、精确起运时刻、起运年龄
这些直接字段外, 四柱本身就能把出生日期(连时辰)缩到极少几个候选, 在常见年份范围内往往能唯一反推。
redact_profile() 只去掉坐标和精确时刻, 不能防反推。

命令行: python -m chaoqian.bazi --input birth.json --output profile.json [--redact]
"""

from __future__ import annotations

import argparse
import calendar
import hashlib
import json
import math
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from lunar_python import Solar
from lunar_python.util import LunarUtil


PROFILE_VERSION = "chaoqian-bazi-profile-0.1"
GAN_WX = dict(zip("甲乙丙丁戊己庚辛壬癸", "木木火火土土金金水水"))
# 地支藏干(全库唯一一份)。顺序 = 本气 / 中气 / 余气, 与 lunar_python LunarUtil.ZHI_HIDE_GAN 逐支一致(有单测锁)。
# 依据《渊海子平·地支藏遁歌》: 「巳中庚金丙戊丛」-> 巳藏 丙(本)/庚(中)/戊(余); 「未宫乙己丁共宗」-> 未藏 己(本)/丁(中)/乙(余)。
# 权重(本/中/余 = .6/.25/.15 等)是本项目约定。
ZHI_HIDDEN = {
    "子": [("癸", 1.0)], "丑": [("己", .6), ("癸", .25), ("辛", .15)],
    "寅": [("甲", .6), ("丙", .25), ("戊", .15)], "卯": [("乙", 1.0)],
    "辰": [("戊", .6), ("乙", .25), ("癸", .15)], "巳": [("丙", .6), ("庚", .25), ("戊", .15)],
    "午": [("丁", .7), ("己", .3)], "未": [("己", .6), ("丁", .25), ("乙", .15)],
    "申": [("庚", .6), ("壬", .25), ("戊", .15)], "酉": [("辛", 1.0)],
    "戌": [("戊", .6), ("辛", .25), ("丁", .15)], "亥": [("壬", .7), ("甲", .3)],
}
SHENG = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
KE = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}
ZODIAC = dict(zip("子丑寅卯辰巳午未申酉戌亥", "鼠牛虎兔龙蛇马羊猴鸡狗猪"))


def _equation_of_time_minutes(dt: datetime) -> float:
    """NOAA fractional-year approximation; apparent minus mean solar time."""
    days = 366 if calendar.isleap(dt.year) else 365
    hour = dt.hour + dt.minute / 60 + dt.second / 3600
    gamma = 2 * math.pi / days * (dt.timetuple().tm_yday - 1 + (hour - 12) / 24)
    return 229.18 * (
        .000075 + .001868 * math.cos(gamma) - .032077 * math.sin(gamma)
        - .014615 * math.cos(2 * gamma) - .040849 * math.sin(2 * gamma)
    )


def true_solar_time(civil: datetime, longitude: float, timezone_name: str) -> dict:
    """Convert naive local civil time to local apparent solar time."""
    zone = ZoneInfo(timezone_name)
    aware = civil.replace(tzinfo=zone)
    utc_offset = aware.utcoffset()
    if utc_offset is None:
        raise ValueError("timezone has no UTC offset for birth time")
    timezone_hours = utc_offset.total_seconds() / 3600
    eot = _equation_of_time_minutes(civil)
    longitude_correction = 4 * float(longitude) - 60 * timezone_hours
    total = eot + longitude_correction
    apparent = civil + timedelta(minutes=total)
    return {
        "civil_aware": aware,
        "apparent": apparent,
        "equation_of_time_minutes": eot,
        "longitude_correction_minutes": longitude_correction,
        "total_offset_minutes": total,
        "utc_offset_hours": timezone_hours,
    }


def _element_assessment(pillars: list[str]) -> dict:
    """Transparent season-aware structural heuristic, not an empirical claim."""
    balance = {x: 0.0 for x in "木火土金水"}
    for pillar in pillars:
        balance[GAN_WX[pillar[0]]] += 1.0
        for gan, ratio in ZHI_HIDDEN[pillar[1]]:
            balance[GAN_WX[gan]] += ratio
    # Month command gets additional weight because season is not equivalent to
    # one ordinary branch.  This is deliberately visible in the output audit.
    for gan, ratio in ZHI_HIDDEN[pillars[1][1]]:
        balance[GAN_WX[gan]] += .8 * ratio

    dm = GAN_WX[pillars[2][0]]
    resource = next(x for x, made in SHENG.items() if made == dm)
    output, wealth, officer = SHENG[dm], KE[dm], next(x for x, target in KE.items() if target == dm)
    support = balance[dm] + balance[resource]
    drain = balance[output] + balance[wealth] + balance[officer]
    strong = support >= drain * 1.15
    if strong:
        weights = {dm: -.75, resource: -.85, output: .8, wealth: .65, officer: .15}
        strength = "偏强"
    else:
        weights = {dm: .8, resource: .7, output: -.45, wealth: -.65, officer: -.75}
        strength = "偏弱"

    month = pillars[1][1]
    if month in "亥子丑":
        weights["火"] += .45
        weights["土"] += .15
        weights["水"] -= .2
        climate = "寒湿月令，调候先取火，土次之"
    elif month in "巳午未":
        weights["水"] += .45
        weights["金"] += .1
        weights["火"] -= .2
        climate = "燥热月令，调候先取水"
    else:
        climate = "温燥不过极，先按扶抑平衡"

    weights = {k: round(max(-1.0, min(1.0, v)), 2) for k, v in weights.items()}
    favorable = [k for k, v in weights.items() if v >= .4]
    unfavorable = [k for k, v in weights.items() if v <= -.4]
    neutral = [k for k in "木火土金水" if k not in favorable and k not in unfavorable]
    return {
        "balance": {k: round(v, 2) for k, v in balance.items()},
        "weights": weights,
        "favorable": favorable,
        "unfavorable": unfavorable,
        "neutral": neutral,
        "day_master_strength": strength,
        "climate_note": climate,
        "method": "显干1.0+各支藏干1.0+月令藏干追加0.8；再作扶抑与寒暖调候修正",
    }


def build_profile(source: dict, verified_at: str | None = None) -> dict:
    if source.get("calendar") != "solar":
        raise ValueError("this compiler currently requires calendar=solar")
    gender = source.get("gender")
    if gender not in ("female", "male"):
        raise ValueError("gender must be female or male")
    civil = datetime.strptime(source["birth_date"] + " " + source["birth_time"], "%Y-%m-%d %H:%M")
    solar_meta = true_solar_time(civil, float(source["longitude"]), source["timezone"])
    apparent = solar_meta["apparent"]
    solar = Solar.fromYmdHms(
        apparent.year, apparent.month, apparent.day,
        apparent.hour, apparent.minute, apparent.second,
    )
    lunar = solar.getLunar()
    eight = lunar.getEightChar()
    day_boundary = source.get("day_boundary", "midnight")
    eight.setSect(2 if day_boundary == "midnight" else 1)
    pillars = [eight.getYear(), eight.getMonth(), eight.getDay(), eight.getTime()]
    assessment = _element_assessment(pillars)
    year_yang = pillars[0][0] in "甲丙戊庚壬"
    forward = (year_yang and gender == "male") or ((not year_yang) and gender == "female")
    reference_jie = lunar.getNextJie() if forward else lunar.getPrevJie()
    reference_civil = datetime.strptime(reference_jie.getSolar().toYmdHms(), "%Y-%m-%d %H:%M:%S")
    # Birth time and the solar-term instant must be compared in the same time
    # frame. Correcting only the birth clock would overstate the interval by
    # the full longitude offset. Longitude cancels here; the small EoT change
    # between the two dates remains.
    reference_apparent = true_solar_time(reference_civil, float(source["longitude"]), source["timezone"])["apparent"]
    span = (reference_apparent - apparent) if forward else (apparent - reference_apparent)
    span_minutes = int(round(span.total_seconds() / 60))
    if span_minutes < 0:
        raise ValueError("invalid solar-term interval for Yun direction")
    rest = span_minutes
    start_years, rest = divmod(rest, 4320)  # 3 days = 1 year
    start_months, rest = divmod(rest, 360)  # 1 day = 4 months
    start_days, rest = divmod(rest, 12)     # 1 shichen (2h) = 10 days
    start_hours = rest * 2
    civil_solar = Solar.fromYmdHms(civil.year, civil.month, civil.day, civil.hour, civil.minute, 0)
    start_solar = civil_solar.nextYear(start_years).nextMonth(start_months).next(start_days).nextHour(start_hours)
    start_dt = datetime.strptime(start_solar.toYmdHms(), "%Y-%m-%d %H:%M:%S")
    month_index = LunarUtil.getJiaZiIndex(pillars[1])
    dayun = []
    for index in range(8):
        exact_start = start_dt.replace(year=start_dt.year + index * 10)
        next_start = exact_start.replace(year=exact_start.year + 10)
        gz_index = (month_index + (index + 1 if forward else -(index + 1))) % 60
        start_year = exact_start.year
        start_age = start_year - civil.year + 1
        dayun.append({
            "gz": LunarUtil.JIA_ZI[gz_index], "start": start_year, "end": start_year + 9,
            "start_age": start_age, "end_age": start_age + 9,
            "start_at": exact_start.strftime("%Y-%m-%d %H:%M:%S"),
            "end_at": (next_start - timedelta(seconds=1)).strftime("%Y-%m-%d %H:%M:%S"),
        })

    normalized = json.dumps(source, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    verified_at = verified_at or datetime.now(timezone.utc).isoformat()
    return {
        "note": "由出生信息确定性复算; 引擎输出与模型提示均不包含原始出生日期、地点或钟表时间。",
        "profile_version": PROFILE_VERSION,
        "verified_at": verified_at,
        "source_fingerprint": hashlib.sha256(normalized.encode()).hexdigest()[:20],
        "source_audit": {
            "calendar": "solar", "gender": gender, "time_precision": source.get("time_precision", "minute"),
            "timezone": source["timezone"], "coordinate_precision": source.get("coordinate_precision", "city"),
            "day_boundary": day_boundary,
        },
        "calculation": {
            "method": "NOAA apparent solar time + lunar-python exact solar-term pillars",
            "true_solar_offset_minutes": round(solar_meta["total_offset_minutes"], 3),
            "equation_of_time_minutes": round(solar_meta["equation_of_time_minutes"], 3),
            "longitude_correction_minutes": round(solar_meta["longitude_correction_minutes"], 3),
            "true_solar_clock": apparent.strftime("%H:%M:%S"),
            "true_solar_day_shift": (apparent.date() - civil.date()).days,
            "longitude": round(float(source["longitude"]), 6),
            "latitude": round(float(source["latitude"]), 6),
        },
        "day_master": pillars[2][0],
        "pillars": [list(x) for x in pillars],
        "favorable": assessment["favorable"],
        "unfavorable": assessment["unfavorable"],
        "neutral": assessment["neutral"],
        "element_weights": assessment["weights"],
        "element_balance": assessment["balance"],
        "day_master_strength": assessment["day_master_strength"],
        "climate_note": assessment["climate_note"],
        "element_method": assessment["method"],
        "xunkong": list(LunarUtil.getXunKong(pillars[2])),
        "shengxiao": ZODIAC[pillars[0][1]],
        "dayun_direction": "顺排" if forward else "逆排",
        "dayun_start_age": {
            "years": start_years, "months": start_months,
            "days": start_days, "hours": start_hours,
        },
        "dayun_start_at": start_solar.toYmdHms(),
        "dayun_reference_jie": {
            "name": reference_jie.getName(), "at": reference_jie.getSolar().toYmdHms(),
            "true_solar_at": reference_apparent.strftime("%Y-%m-%d %H:%M:%S"),
            "interval_minutes": span_minutes,
            "rule": "顺排取出生后下一节，逆排取出生前上一节；两端同作真太阳时校正，分钟法3天折1年",
        },
        "da_yun": dayun,
    }


# redact_profile() 保留的字段(四柱仍在, 所以输出仍然可以反推出生日期)。
_REDACTED_KEYS = ("profile_version", "day_master", "pillars", "favorable", "unfavorable", "neutral",
                  "element_weights", "day_master_strength", "climate_note", "xunkong", "dayun_direction")


def redact_profile(profile: dict) -> dict:
    """只去掉坐标和精确时刻, 不能防反推。

    去掉: calculation(经纬度、真太阳时、均时差)、source_fingerprint、verified_at、source_audit 里除性别外的字段、
    dayun_start_at、dayun_start_age、dayun_reference_jie、element_balance、shengxiao, 以及每步大运的起止时刻、年份与年龄。
    保留: 四柱、喜忌权重、旬空、性别、大运方向、每步大运的干支与顺序(step)。
    因为不留大运起止, 用它算日签时不计「大运喜忌」这一项; 需要大运时请在运行时用完整 profile。
    ⚠ 四柱本身就能把出生日期(连时辰)缩到极少几个候选, 输出与出生信息同等敏感, 绝不要公开分享。
    """
    out = {k: profile[k] for k in _REDACTED_KEYS if k in profile}
    gender = (profile.get("source_audit") or {}).get("gender")
    if gender:
        out["source_audit"] = {"gender": gender}
    out["da_yun"] = [{"step": i + 1, "gz": d["gz"]} for i, d in enumerate(profile.get("da_yun") or [])]
    out["redacted"] = True
    return out


def write_json_atomic(path: Path, payload: dict, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--redact", action="store_true", help="写出 redact_profile() 的结果(只去掉坐标和精确时刻, 不能防反推)")
    args = parser.parse_args()
    source_path, output_path = Path(args.input), Path(args.output)
    source = json.loads(source_path.read_text(encoding="utf-8"))
    profile = build_profile(source)
    if not args.check_only:
        write_json_atomic(output_path, redact_profile(profile) if args.redact else profile)
    print(json.dumps({
        "profile_version": profile["profile_version"], "pillars": ["".join(x) for x in profile["pillars"]],
        "true_solar_clock": profile["calculation"]["true_solar_clock"],
        "offset_minutes": profile["calculation"]["true_solar_offset_minutes"],
        "direction": profile["dayun_direction"], "start_at": profile["dayun_start_at"],
        "favorable": profile["favorable"], "unfavorable": profile["unfavorable"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
