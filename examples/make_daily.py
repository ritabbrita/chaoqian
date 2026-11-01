# -*- coding: utf-8 -*-
"""生成一张日签 JSON(以及可选的月运、问卦)。

    python examples/make_daily.py --no-llm                       # 纯规则, 不联网
    python examples/make_daily.py --date 2030-05-20 --out out.json
    ANTHROPIC_API_KEY=... python examples/make_daily.py           # 用 Claude 改写签文(需 pip install anthropic)

默认读取同目录的 birth_example.json(虚构命主)。
"""
import argparse
import json
import os
import random
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chaoqian.bazi import build_profile  # noqa: E402
from chaoqian.cast import cast_question  # noqa: E402
from chaoqian.daily import generate_daily  # noqa: E402
from chaoqian.llm import from_env  # noqa: E402
from chaoqian.monthly import monthly_fortune  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    ap = argparse.ArgumentParser(description="潮签示例: 生成日签 / 月运 / 问卦 JSON")
    ap.add_argument("--birth", default=os.path.join(HERE, "birth_example.json"), help="出生信息 JSON")
    ap.add_argument("--date", default="2030-05-20", help="日期 YYYY-MM-DD(按 08:00 起算)")
    ap.add_argument("--tz", default="Asia/Shanghai", help="IANA 时区名")
    ap.add_argument("--no-llm", action="store_true", help="不调大模型, 只用规则文案")
    ap.add_argument("--with-monthly", action="store_true", help="同时输出月运")
    ap.add_argument("--cast", metavar="问题", help="同时问一卦(六爻), 例如 --cast '这个项目三十天内能完成吗'")
    ap.add_argument("--seed", type=int, default=None, help="问卦随机种子(便于复现)")
    ap.add_argument("--out", help="输出文件; 不给则打印到标准输出")
    args = ap.parse_args()

    with open(args.birth, encoding="utf-8") as fh:
        source = json.load(fh)
    # verified_at 固定, 让示例输出可复现; 实际使用可省略(默认取当前 UTC 时间)。
    profile = build_profile(source, verified_at="example-fixed")
    tz = ZoneInfo(args.tz)
    y, m, d = (int(x) for x in args.date.split("-"))
    dt = datetime(y, m, d, 8, 0, tzinfo=tz)
    llm = None if args.no_llm else from_env()

    out = {"subject": source.get("name") or "示例用户",
           "llm": "none" if llm is None else type(llm).__name__,
           "daily": generate_daily(profile, dt, llm=llm)}
    if args.with_monthly:
        out["monthly"] = monthly_fortune(profile, dt, llm=llm)
    if args.cast:
        rng = random.Random(args.seed) if args.seed is not None else None
        out["cast"] = cast_question(args.cast, dt.replace(hour=9), category="事业", horizon=30, llm=llm,
                                    gender=source.get("gender"), rng=rng)
    text = json.dumps(out, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text + "\n")
        print("written:", args.out)
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        print(text)


if __name__ == "__main__":
    main()
