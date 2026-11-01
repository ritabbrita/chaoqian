# 潮签 chaoqian

一个**确定性的中国传统历法 / 术数引擎**, 外加一个可插拔的大模型「签文」层:

- **六爻**: 起卦、京房纳甲、八宫世应、六亲六神、用神取用、旺衰、动爻作用条件、伏神飞伏、三合半合、应期、分阶段时间线
- **八字**: 真太阳时排盘、藏干、十神、五行强弱与调候、喜忌权重、起运与大运、神煞(贵人 / 禄神 / 文昌 / 桃花)、留意日与吉日
- **奇门遁甲**: 时家奇门转盘拆补法定局、九宫布盘、时段评分、三十余条格局、五不遇时、择时
- **黄历 / 节气**: 农历、干支(精确交节)、宜忌、值日、二十八宿、黄道时辰、节气食养
- **梅花易数**: 时间起卦, 卦辞爻辞取《周易》原文
- **日签 / 月运 / 问卦**: 把以上结果组装成可审计的叙事材料, 规则文案兜底; 接入大模型时, 模型写的每一句都要过确定性护栏

> 所有结果都是**传统规则下的文化参考**, 未经科学验证, **不是事件发生概率**, 不应作为医疗、财务、法律等决策依据。

## English summary

*chaoqian* ("tide oracle") is a deterministic Python engine for traditional Chinese calendrical divination —
Liu Yao (six-line I Ching with Jing Fang Najia), Ba Zi (Four Pillars with true solar time), Qi Men Dun Jia
(hourly rotating-plate method), the Chinese almanac and solar terms, and Mei Hua time casting. It assembles an
auditable "daily slip" (five life domains, timing windows, color guide) and an event-contract-based Liu Yao reading
with a staged timeline. An optional LLM layer can rephrase the copy, but every sentence is checked by deterministic
guards against the engine's own state. Without an LLM it runs fully offline. Outputs are cultural references,
not probabilities or advice.

## 安装

需要 Python 3.10+。

```bash
pip install -r requirements.txt          # lunar-python, tzdata
pip install anthropic                    # 可选: 用 Claude 改写签文
pip install pytest                       # 可选: 跑测试
```

或作为包安装: `pip install -e .[llm,test]`。

## 快速开始

```bash
# 用虚构命主 examples/birth_example.json 生成一张日签(纯规则, 不联网)
python examples/make_daily.py --no-llm

# 同时输出月运和一支六爻, 写入文件(仓库里的 examples/daily_example.json 就是这样生成的)
python examples/make_daily.py --no-llm --with-monthly --cast "示例项目三十天内能完成吗" --seed 7 \
    --out examples/daily_example.json

# 用 Claude 改写签文(读环境变量 ANTHROPIC_API_KEY)
ANTHROPIC_API_KEY=... python examples/make_daily.py --date 2030-05-20
```

前端示例: 在仓库根目录运行 `python -m http.server 8000`, 打开 <http://localhost:8000/web/>,
页面会读取 `examples/daily_example.json` 渲染一张静态签卡(纯展示, 无登录、无网络请求)。

## 在代码里用

```python
from datetime import datetime
from zoneinfo import ZoneInfo

from chaoqian.bazi import build_profile
from chaoqian.daily import generate_daily
from chaoqian.monthly import monthly_fortune
from chaoqian.cast import cast_question

profile = build_profile({                          # 虚构命主, 与 examples/birth_example.json 相同
    "calendar": "solar", "gender": "male",
    "birth_date": "1990-06-14", "birth_time": "16:30",
    "timezone": "Asia/Shanghai", "longitude": 116.4074, "latitude": 39.9042,
})
now = datetime(2030, 5, 20, 8, 0, tzinfo=ZoneInfo("Asia/Shanghai"))

slip = generate_daily(profile, now)                 # 日签 dict
month = monthly_fortune(profile, now)               # 月运 dict
reading = cast_question("示例项目三十天内能完成吗", now, category="事业", horizon=30)
print(slip["text"]["smile"], reading["text"]["result"])
```

- `generate_daily(profile=None, ...)`: 不给命盘时只出黄历、卦象、奇门, 不出命理相性。
- `generate_daily(..., location={"lat": .., "lon": ..})`: 给了经纬度才会联网查 Open-Meteo 天气; 也可用 `weather_data=` 直接传入。
- `cast_question(..., context={"coins": [...], "anchor_ts": ...})`: 复用原卦重新看更长期限。
- `cast_question(..., category="感情", gender="female" | "male")`: 「感情」类用神随问卦人性别而定, 必须给出; 其它类别可以不给。
- 默认时区由环境变量 `CHAOQIAN_TZ` 决定(默认 `Asia/Shanghai`)。

### 接入大模型

```python
from chaoqian.llm import AnthropicClient, CallableClient

llm = AnthropicClient()            # 读 ANTHROPIC_API_KEY; 模型 / 推理档位见 CHAOQIAN_ANTHROPIC_MODEL / _EFFORT
slip = generate_daily(profile, now, llm=llm)

# 任意提供商: 包一个函数 fn(system, messages, max_tokens) -> str
llm = CallableClient(lambda system, messages, max_tokens: my_provider_call(system, messages))
```

模型失败、拒答、输出不是合法 JSON 时自动回落到规则文案(`text.fallback = True`)。
被护栏剔掉的句子记在 `text.guard_stripped`, 方便审计。提示词只描述写作规矩, 不含人设。

## 模块

| 模块 | 内容 |
|---|---|
| `chaoqian.almanac` | 黄历、节气、月份分段、节气食养 |
| `chaoqian.bazi` | 真太阳时排盘、五行强弱、喜忌、起运大运; 命令行 `python -m chaoqian.bazi --input birth.json --output profile.json [--redact]` |
| `chaoqian.ganzhi` | 干支五行、生克冲合刑害破、十神、旬空等基础表 |
| `chaoqian.natal` | 八字日运评分、留意日、吉日、流月线索 |
| `chaoqian.meihua` | 梅花易数时间起卦、周易卦爻辞查表 |
| `chaoqian.qimen` / `qimen_geju` | 奇门排盘、时段评分、格局判定 |
| `chaoqian.liuyao` | 六爻引擎 |
| `chaoqian.timing` | 六爻分阶段时间线 |
| `chaoqian.contract` | 问事合同、事前倾向冻结、解卦文案护栏 |
| `chaoqian.daily` / `monthly` / `cast` | 日签、月运、问卦的材料组装与文案 |
| `chaoqian.guards` | 叙事护栏公共部件 |
| `chaoqian.llm` / `prompts` | 可插拔大模型接口与中性提示词 |
| `chaoqian.weather` | 可选的 Open-Meteo 天气 |

规则细节见 [docs/ALGORITHM.md](docs/ALGORITHM.md)。

## 隐私设计

- 引擎默认**完全离线**; 只有显式给出经纬度(天气)或传入 `llm` 时才会联网。
- **出生信息和命盘 profile 同等敏感, 绝不要公开分享。** `build_profile()` 的输出里, 下列字段都能反推出生年月日时或出生地:

  | 字段 | 为什么敏感 |
  |---|---|
  | `calculation`(经纬度、真太阳时、均时差、时区修正) | 直接给出出生地坐标和出生时刻 |
  | `dayun_start_at`、`dayun_reference_jie`、`da_yun[].start_at / end_at` | 精确到秒的起运时刻, 配合节气可倒推出生时间 |
  | `dayun_start_age`、`da_yun[].start_age / end_age` | 年龄与起运年份可推出生年 |
  | `source_fingerprint`、`verified_at`、`source_audit` | 指纹可用来比对猜测的出生信息 |
  | `pillars`(四柱) | **四柱本身就能把出生日期(连时辰)缩到极少几个候选**, 在常见年份范围内往往能唯一反推 |
  | `da_yun[].gz`、`dayun_direction` | 与四柱一起进一步缩小候选 |

- `chaoqian.bazi.redact_profile(profile)`(或命令行 `--redact`)**只去掉坐标和精确时刻**(上表前四行, 以及每步大运的起止年份),
  **不能防止反推**: 输出里仍有四柱, 与出生信息同等敏感, 绝不要公开分享。它不含大运起止, 所以用它算日签时不计「大运喜忌」一项。
- 交给模型的材料里没有出生日期、地点、钟表时间, 也不带大运的起运日期(只写「某某大运」)。
- 不接任何数据库、记忆库或推送; 历史记录由调用方自己决定是否保存。
- 仓库自带的出生信息、测试夹具全部是**虚构**数据。请不要把真实出生信息提交进仓库(`.gitignore` 已忽略 `*.private.json`)。

## 测试

```bash
python -m pytest -q
```

测试只用合成数据(虚构命盘、合成硬币序列、合成问题), 不联网, 不调模型。

## 算法依据(书目)

《增删卜易》《卜筮正宗》《断易天机》《易隐》(六爻);
《渊海子平》《三命通会》《滴天髓》《子平真诠》(八字);
《烟波钓叟歌》《奇门遁甲统宗大全》《奇门遁甲秘笈大全》《奇门法窍》《御定奇门宝鉴》《遁甲演义》(奇门);
《周易》(卦辞爻辞)。
本项目只引用书名与短句口诀作为规则出处, 具体权重与阈值多为工程选择, 详见算法说明。

## 致谢与第三方

- [lunar-python](https://github.com/6tail/lunar-python)(MIT, 作者 6tail): 农历、干支、节气与黄历计算。
- [hhszzzz/taibu](https://github.com/hhszzzz/taibu): 伏神、三合、奇门格局的**规则整理思路**参考了其 core 部分(core 包为 MIT;
  该仓库其余部分为 AGPL-3.0-only, 本项目未使用)。本项目未复制其源码, 判据以古籍与通行表为准。
- [Sudo-Biao/Chinese-Metaphysics-Platform](https://github.com/Sudo-Biao/Chinese-Metaphysics-Platform)(MIT):
  九遁结构、格局量级分层、应期入墓等**规则思路**参考。本项目未复制其源码。
- [Open-Meteo](https://open-meteo.com/)(可选天气): 数据以 CC BY 4.0 提供; 免费接口仅限非商业用途, 商用需付费方案。
- [anthropic](https://github.com/anthropics/anthropic-sdk-python)(可选, 官方 Python SDK)。
- `chaoqian/data/yijing64.json`: 经文为《周易》卦辞爻辞(公有领域古籍, 繁体); **这份 JSON 的整理来源待考**(本项目未重新整理,
  也未逐字校勘), 欢迎提供可确认出处的版本替换。`jieqi_regimen.json` 是通用的节气饮食起居提示, 来源同样未单独记录,
  只作生活参考, 不构成医疗建议。

第三方许可以各项目仓库的最新声明为准。

## 许可

[MIT](LICENSE)
