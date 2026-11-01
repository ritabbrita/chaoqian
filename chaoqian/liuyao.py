# -*- coding: utf-8 -*-
"""
六爻纳甲引擎: 摇卦 / 装卦 / 世应 / 六亲六神 / 用神取用 / 旺衰 / 动爻作用条件 / 伏神 / 三合半合 / 应期。

表均为京房纳甲通行口径。主要规则依据《增删卜易》《卜筮正宗》, 逐条说明见 docs/ALGORITHM.md。
凡注明「本项目选择」的地方是工程取舍, 不是古籍定量结论。

  · 用神统一候选池, 前置顺序 本卦 -> 变卦 -> 日辰/月建 -> 伏神
  · 飞伏关系四句口诀 + 比和中性; 伏神三态可用性(available / conditional / blocked)
  · 三合/半合: 静爻与暗动可入局; 空、破、墓三种「待」态; 局对用神的加减分
  · 应期: 静爻逢值逢冲 / 动爻逢值逢合、空亡四态、明动暗动分述、弱用神生旺之期、
    合绊待冲、入墓待冲开、出伏专属分支
  · 静爻逢冲按月令旺衰分暗动(旺相)与日破(休囚死); 静爻旬空分真空 / 假空
"""
# coins 参数可复用原始硬币结果(同一卦换期限重算); 长期分段见 chaoqian.timing。
import random
from datetime import timedelta

ZHI = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]
ZHI_WX = {"子": "水", "丑": "土", "寅": "木", "卯": "木", "辰": "土", "巳": "火", "午": "火", "未": "土", "申": "金", "酉": "金", "戌": "土", "亥": "水"}
SHENG = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
KE = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}
LIUHE = {"子": "丑", "丑": "子", "寅": "亥", "亥": "寅", "卯": "戌", "戌": "卯", "辰": "酉", "酉": "辰", "巳": "申", "申": "巳", "午": "未", "未": "午"}
LIUCHONG = {"子": "午", "午": "子", "丑": "未", "未": "丑", "寅": "申", "申": "寅", "卯": "酉", "酉": "卯", "辰": "戌", "戌": "辰", "巳": "亥", "亥": "巳"}
SANHE = [set("申子辰"), set("亥卯未"), set("寅午戌"), set("巳酉丑")]
JINSHEN = {"亥": "子", "寅": "卯", "巳": "午", "申": "酉", "丑": "辰", "辰": "未", "未": "戌", "戌": "丑"}
TUISHEN = {v: k for k, v in JINSHEN.items()}
# 动爻作用条件: 发动生克先核定是否有力。权重: 有力全额, 「作用未定」(休囚而未被伤克)按六折计入,
# 待时 / 受制归零。依据《增删卜易·元神忌神衰旺章》: 「不能生用神」六条未列「动而休囚、未被伤克」;
# 六折是本项目的工程折中, 非原典定量。旺相或得日辰生扶的明动爻逢空亡仍能生克
# (同章能生第五条「元神旺动, 临空化空」)。
RULE_VERSION = "chaoqian-liuyao-0.1"
ACTION_VERSION = "chaoqian-line-action-0.1"
ACTION_WEIGHT = {"available": 1.0, "uncertain": 0.6, "waiting": 0.0, "blocked": 0.0}

# 三合四局(带合化五行与局名)。SANHE 保留作简单集合, 判局一律走 SANHE_TABLE。
SANHE_TABLE = [
    {"branches": ("申", "子", "辰"), "elem": "水", "name": "申子辰合水局"},
    {"branches": ("亥", "卯", "未"), "elem": "木", "name": "亥卯未合木局"},
    {"branches": ("寅", "午", "戌"), "elem": "火", "name": "寅午戌合火局"},
    {"branches": ("巳", "酉", "丑"), "elem": "金", "name": "巳酉丑合金局"},
]
# 半合八组(与 taibu、Sudo-Biao 两个开源实现一致的口径): 皆含中神(子午卯酉)。
# 无中神的拱合(申辰/亥未/寅戌/巳丑)合力极弱, 本引擎不作成局论, 故不入表。
BAN_SANHE_TABLE = [
    {"branches": ("申", "子"), "elem": "水", "type": "长生+帝旺", "name": "申子半合水"},
    {"branches": ("子", "辰"), "elem": "水", "type": "帝旺+墓库", "name": "子辰半合水"},
    {"branches": ("亥", "卯"), "elem": "木", "type": "长生+帝旺", "name": "亥卯半合木"},
    {"branches": ("卯", "未"), "elem": "木", "type": "帝旺+墓库", "name": "卯未半合木"},
    {"branches": ("寅", "午"), "elem": "火", "type": "长生+帝旺", "name": "寅午半合火"},
    {"branches": ("午", "戌"), "elem": "火", "type": "帝旺+墓库", "name": "午戌半合火"},
    {"branches": ("巳", "酉"), "elem": "金", "type": "长生+帝旺", "name": "巳酉半合金"},
    {"branches": ("酉", "丑"), "elem": "金", "type": "帝旺+墓库", "name": "酉丑半合金"},
]
# 十二长生要位。「土」行按**水土同宫**: 长生申 / 帝旺子 / 墓辰 / 绝巳。
# 依据《增删卜易·生旺墓绝章》「水土长生在申，旺在子，墓在辰，绝在巳」, 同章明确否掉「火土长生寅上排」一派;
# 《断易天机》《易隐》「水土长生居申」为旁证。
CHANGSHENG = {"木": "亥", "火": "寅", "土": "申", "金": "巳", "水": "申"}
DIWANG = {"木": "卯", "火": "午", "土": "子", "金": "酉", "水": "子"}
MU = {"木": "未", "火": "戌", "土": "辰", "金": "丑", "水": "辰"}
JUE = {"木": "申", "火": "亥", "土": "巳", "金": "寅", "水": "巳"}

SANHE_SCHOOL_NOTE = ("《增删卜易·三合章》口径: 两爻动(明动或暗动)即可成局, 静爻本支、变出之爻、日辰月建皆可补足; "
                     "部分现代教材主张静爻/月建/伏爻不入局, 与原文冲突, 本项目从《增删卜易》。"
                     "半合(二支拱合)须含旺神(中神 子午卯酉)且两支之中至少一爻动(明动或暗动), 两支全静不作局论; "
                     "另: 同五行三合三支俱全在场却判「未成(动爻不足)」时, 其子集半合不再成局 —— "
                     "这一条是本项目的选择(避免大局判未成、子集反报成局的自相矛盾), 不挂古籍名下。")

TRIGRAM_LINES = {"乾": (1, 1, 1), "兑": (1, 1, 0), "离": (1, 0, 1), "震": (1, 0, 0), "巽": (0, 1, 1), "坎": (0, 1, 0), "艮": (0, 0, 1), "坤": (0, 0, 0)}
LINES_TRIGRAM = {v: k for k, v in TRIGRAM_LINES.items()}
GUA64 = {
    "乾": {"乾": "乾为天", "兑": "天泽履", "离": "天火同人", "震": "天雷无妄", "巽": "天风姤", "坎": "天水讼", "艮": "天山遁", "坤": "天地否"},
    "兑": {"乾": "泽天夬", "兑": "兑为泽", "离": "泽火革", "震": "泽雷随", "巽": "泽风大过", "坎": "泽水困", "艮": "泽山咸", "坤": "泽地萃"},
    "离": {"乾": "火天大有", "兑": "火泽睽", "离": "离为火", "震": "火雷噬嗑", "巽": "火风鼎", "坎": "火水未济", "艮": "火山旅", "坤": "火地晋"},
    "震": {"乾": "雷天大壮", "兑": "雷泽归妹", "离": "雷火丰", "震": "震为雷", "巽": "雷风恒", "坎": "雷水解", "艮": "雷山小过", "坤": "雷地豫"},
    "巽": {"乾": "风天小畜", "兑": "风泽中孚", "离": "风火家人", "震": "风雷益", "巽": "巽为风", "坎": "风水涣", "艮": "风山渐", "坤": "风地观"},
    "坎": {"乾": "水天需", "兑": "水泽节", "离": "水火既济", "震": "水雷屯", "巽": "水风井", "坎": "坎为水", "艮": "水山蹇", "坤": "水地比"},
    "艮": {"乾": "山天大畜", "兑": "山泽损", "离": "山火贲", "震": "山雷颐", "巽": "山风蛊", "坎": "山水蒙", "艮": "艮为山", "坤": "山地剥"},
    "坤": {"乾": "地天泰", "兑": "地泽临", "离": "地火明夷", "震": "地雷复", "巽": "地风升", "坎": "地水师", "艮": "地山谦", "坤": "坤为地"},
}
# 京房纳甲: 经卦 -> (内卦天干, 外卦天干, 内三爻支(自下而上), 外三爻支)
NAJIA = {
    "乾": ("甲", "壬", ["子", "寅", "辰"], ["午", "申", "戌"]),
    "坎": ("戊", "戊", ["寅", "辰", "午"], ["申", "戌", "子"]),
    "艮": ("丙", "丙", ["辰", "午", "申"], ["戌", "子", "寅"]),
    "震": ("庚", "庚", ["子", "寅", "辰"], ["午", "申", "戌"]),
    "巽": ("辛", "辛", ["丑", "亥", "酉"], ["未", "巳", "卯"]),
    "离": ("己", "己", ["卯", "丑", "亥"], ["酉", "未", "巳"]),
    "坤": ("乙", "癸", ["未", "巳", "卯"], ["丑", "亥", "酉"]),
    "兑": ("丁", "丁", ["巳", "卯", "丑"], ["亥", "酉", "未"]),
}
PALACE_ELEM = {"乾": "金", "兑": "金", "离": "火", "震": "木", "巽": "木", "坎": "水", "艮": "土", "坤": "土"}
LIUSHEN = ["青龙", "朱雀", "勾陈", "螣蛇", "白虎", "玄武"]
LIUSHEN_START = {"甲": 0, "乙": 0, "丙": 1, "丁": 1, "戊": 2, "己": 3, "庚": 4, "辛": 4, "壬": 5, "癸": 5}
# 类别 -> 用神六亲。「感情」没有固定用神: 按问卦人性别取, 女取官鬼(夫星)、男取妻财(妻星), 必须传 cast(gender=...)。
USHEN_BY_CATEGORY = {"事业": "官鬼", "财务": "妻财", "感情": None, "亲子": "子孙", "身心": "世爻", "文书": "父母", "其他": "世爻"}
USHEN_LOVE_BY_GENDER = {"female": "官鬼", "male": "妻财"}
# 用神来源等级, 数字小者优先; 只作前置顺序与同分兜底, 不作一票压制。
SOURCE_RANK = {"ben": 0, "bian": 1, "ri": 2, "yue": 3, "fushen": 4}
SOURCE_LABEL = {"ben": "本卦", "bian": "变卦", "ri": "日辰", "yue": "月建", "fushen": "伏神"}


def _hex_name(lines):
    xia = LINES_TRIGRAM[tuple(lines[0:3])]
    shang = LINES_TRIGRAM[tuple(lines[3:6])]
    return GUA64[shang][xia], shang, xia


def _build_palace_map():
    """八宫六十四卦: 卦名 -> (宫, 世爻位1-6)。本宫世6,一至五世,游魂4,归魂3。"""
    m = {}
    for pal in TRIGRAM_LINES:
        base = list(TRIGRAM_LINES[pal]) + list(TRIGRAM_LINES[pal])
        seq = [(list(base), 6)]
        cur = list(base)
        for i in range(5):  # 一世..五世: 累积变初..五爻
            cur = list(cur)
            cur[i] = 1 - cur[i]
            seq.append((list(cur), i + 1))
        youhun = list(cur)
        youhun[3] = 1 - youhun[3]  # 游魂: 五世卦再变四爻
        seq.append((list(youhun), 4))
        guihun = list(youhun)
        for i in range(3):  # 归魂: 内卦复原为本宫
            guihun[i] = base[i]
        seq.append((guihun, 3))
        for lines, shi in seq:
            name, _, _ = _hex_name(lines)
            m[name] = (pal, shi)
    return m


PALACE_MAP = _build_palace_map()


def _zhuang(lines):
    """装卦: 每爻 (支, 五行, 天干)。lines 自下而上。"""
    xia = LINES_TRIGRAM[tuple(lines[0:3])]
    shang = LINES_TRIGRAM[tuple(lines[3:6])]
    gi, _, zi, _ = NAJIA[xia]
    _, go, _, zo = NAJIA[shang]
    out = []
    for i in range(3):
        out.append({"pos": i + 1, "gan": gi, "zhi": zi[i], "wx": ZHI_WX[zi[i]]})
    for i in range(3):
        out.append({"pos": i + 4, "gan": go, "zhi": zo[i], "wx": ZHI_WX[zo[i]]})
    return out


def _liuqin(wx, palace_elem):
    if wx == palace_elem:
        return "兄弟"
    if SHENG[wx] == palace_elem:
        return "父母"
    if SHENG[palace_elem] == wx:
        return "子孙"
    if KE[wx] == palace_elem:
        return "官鬼"
    return "妻财"


def _wangshuai(wx, month_zhi):
    mwx = ZHI_WX[month_zhi]
    if wx == mwx:
        return "旺", 2
    if SHENG[mwx] == wx:
        return "相", 1
    if SHENG[wx] == mwx:
        return "休", 0
    if KE[wx] == mwx:
        return "囚", -1
    return "死", -2


def _kong_state(y, month_zhi, day_zhi):
    """旬空事实与可用时间分开; 静爻按真空 / 假空扣分, 明动不按真空扣分。

    《增删卜易》旬空章、元神忌神衰旺章: 动不为空, 仍待冲空实空。
    静爻的「相」归假空、休囚归真空及数值权重是本项目约定, 非原典定量。
    """
    if not y.get("kong"):
        return {"state": "not_void", "penalty": 0.0, "label": ""}
    if y["zhi"] == LIUCHONG[day_zhi]:
        return {"state": "released", "penalty": 0.0, "label": "空逢冲起"}
    if y.get("moving"):
        return {"state": "waiting", "penalty": 0.0, "label": "旬空(动空待实)"}
    ws, _ = _wangshuai(y["wx"], month_zhi)
    soft = ws in ("旺", "相") or SHENG[ZHI_WX[day_zhi]] == y["wx"]
    return {"state": "soft" if soft else "hard", "penalty": .5 if soft else 1.5,
            "label": "旬空(假空)" if soft else "旬空(真空)"}


def _line_action(y, month_zhi, day_zhi, day_xunkong="", other_yaos=()):
    """有力/待时/受制/未定：限定条件模型，不能据此断言现实成败。

    底本条文：增删卜易第十章、第二十六章；化合参考第九章午未合例。
    不把「回头克」无条件判死；旺或日扶与受制并存时保留未定。
    不做递归救应猜测：别的发动爻可能生扶受制爻时同样保留未定。
    状态优先级和不确定时不加分属于本项目的保守实现, 详见 docs/ALGORITHM.md。
    """
    zhi, wx = y["zhi"], y["wx"]
    ws, _ = _wangshuai(wx, month_zhi)
    moving = bool(y.get("moving"))
    active = moving or bool(y.get("dark_moving"))
    bian = (y.get("bian") or {}) if moving else {}
    day_help = zhi == day_zhi or SHENG[ZHI_WX[day_zhi]] == wx
    strong = ws in ("旺", "相")
    back_help = bian.get("relation") in ("回头生", "化进神")
    reasons, restrictions, waits = [], [], []
    if strong:
        reasons.append("月令%s" % ws)
    if day_help:
        reasons.append("得日辰生扶")
    if back_help:
        reasons.append(bian["relation"])
    if bian.get("wx") and KE[bian["wx"]] == wx:
        restrictions.append("动化回头克")
    if not strong and bian.get("relation") == "化退神":
        restrictions.append("休囚动化退神")
    if not strong and bian.get("zhi") == JUE.get(wx):
        restrictions.append("休囚动化绝")
    if not strong and (KE[ZHI_WX[month_zhi]] == wx or KE[ZHI_WX[day_zhi]] == wx):
        restrictions.append("休囚又受日月克")

    def wait(key, label, branches):
        waits.append({"id": key, "label": label, "branches": list(dict.fromkeys(branches))})

    void = _kong_state(y, month_zhi, day_zhi)
    if void["state"] == "waiting":
        wait("moving_void", "动空待冲实或填实", [LIUCHONG[zhi], zhi])
    if bian.get("zhi") and bian["zhi"] in (day_xunkong or ""):
        bz = bian["zhi"]
        if day_zhi != LIUCHONG[bz]:
            wait("changed_void", "化空待冲实或填实", [LIUCHONG[bz], bz])
    if zhi == LIUCHONG[month_zhi]:
        wait("month_broken", "月破待条件转变", [zhi, LIUHE[zhi]])
    if active and LIUHE[zhi] == day_zhi:
        wait("day_combined", "日合待冲开", [LIUCHONG[zhi], LIUCHONG[day_zhi]])
    if moving and bian.get("zhi") == LIUHE[zhi]:
        wait("changed_combined", "动化合待冲开", [LIUCHONG[zhi], LIUCHONG[bian["zhi"]]])
    # 与既有应期层一致：土自墓不并入此规则。
    tomb = MU.get(wx) if wx != "土" else None
    if tomb and (day_zhi == tomb or bian.get("zhi") == tomb):
        wait("tomb", "入墓待冲开", [LIUCHONG[tomb], zhi])

    possible_rescue = any(
        o.get("pos") != y.get("pos") and (o.get("moving") or o.get("dark_moving"))
        and SHENG[o["wx"]] == wx for o in other_yaos)
    if restrictions:
        status = "uncertain" if strong or day_help or back_help or possible_rescue else "blocked"
        if possible_rescue:
            reasons.append("另有发动爻相生，救应尚未核定")
    elif waits:
        # 只有空亡类待时(动空/化空)且本爻旺相或得日辰生扶 -> 仍能生克(《增删卜易·元神忌神衰旺章》能生第五条
        # 「元神旺动, 临空化空」; 忌神能克第三条同款)。出空/填实日仍由应期层给观察点, wait_for 原样保留。
        # 合绊 / 月破 / 入墓类待时不在此列, 仍归 waiting。
        if (strong or day_help) and all(w["id"] in ("moving_void", "changed_void") for w in waits):
            status = "available"
            reasons.append("旺动临空化空仍能生克")
        else:
            status = "waiting"
    elif strong or day_help or back_help:
        status = "available"
    else:
        status = "uncertain"
        reasons.append("暂缺已落实的有力条件")
    return {"version": ACTION_VERSION, "status": status,
            "label": {"available": "当前有力", "waiting": "待条件解除", "blocked": "当前受制",
                      "uncertain": "作用未定"}[status],
            "reasons": reasons + restrictions, "wait_for": waits, "void": void["state"],
            "basis": "增删卜易·元神忌神衰旺章／旬空章；条件取舍见 docs/ALGORITHM.md"}


def _line_strength(y, month_zhi, day_zhi):
    score, factors = 0.0, []
    mwx, dwx = ZHI_WX[month_zhi], ZHI_WX[day_zhi]
    month_broken = y["zhi"] == LIUCHONG[month_zhi]
    if y["wx"] == mwx:
        score += 2; factors.append("临月建")
    elif SHENG[mwx] == y["wx"]:
        score += 1; factors.append("月建生")
    elif KE[mwx] == y["wx"]:
        score -= 2; factors.append("月建克")
    elif KE[y["wx"]] == mwx:
        score -= 1; factors.append("月建囚")  # 爻克月建为「囚」, 与 _wangshuai 口径一致
    if month_broken:
        score -= 2; factors.append("月破")
        y["month_broken"] = True
    if y["zhi"] == day_zhi:
        score += 2; factors.append("临日辰")
    elif SHENG[dwx] == y["wx"]:
        score += 1; factors.append("日辰生")
    elif KE[dwx] == y["wx"]:
        score -= 1; factors.append("日辰克")
    if LIUHE.get(y["zhi"]) == day_zhi:
        factors.append("日合")
        y["day_combined"] = True
    if LIUCHONG.get(y["zhi"]) == day_zhi:
        y["day_clashed"] = True
        # 暗动 / 日破分界用月令旺衰判据, 与 _yingqi_all 同口径。
        # 依据《增删卜易·日辰章》「冲旺相之静爻即为暗动，冲衰弱之静爻则为日破」(暗动章同旨)。
        # 「旺 + 月破」的辰戌/丑未自冲组仍作日破论(破爻逢冲更破), 故加 not month_broken。
        ws_label, _ = _wangshuai(y["wx"], month_zhi)
        if ws_label in ("旺", "相") and not month_broken and not y.get("moving"):
            score += .5; factors.append("日冲暗动")
            y["dark_moving"] = True
        else:
            score -= .5; factors.append("日冲")
    if y.get("kong") and y.get("moving"):
        # 动空不扣真空/假空分, 其他日月、动变受制仍各自保留。
        # 取消空亡扣分不等于立即生效; _line_action 与应期层继续保留待时条件。
        void = _kong_state(y, month_zhi, day_zhi)
        score -= void["penalty"]
        factors.append(void["label"])
    elif y.get("kong"):
        if y.get("day_clashed"):
            factors.append("空逢冲起")
        else:
            # 静爻旬空分真假空。出处《增删卜易·旬空章》:
            #   「旺不为空；动不为空；有日建动爻动扶者，亦不为空；动而化空，伏而旺相皆不为空」
            #   「月破为空，有气不动亦为空，伏而被克亦为空，真空为空」
            #   「真空者，春土夏金秋是木，三冬逢火是真空」
            # 逐档:
            #   · 旺、得日辰生扶 -> 原文直引, 判假空(扣 .5)。
            #   · 相 -> 本项目的选择(原文「有气不动亦为空」恰把相而静判为空); 取相是为了与静爻逢冲门禁、
            #     暗动分界同用「旺/相」一档, 免得同一爻在三处得三种判语。
            #   · 休 / 囚 / 死 -> 归真空(扣 1.5); 休 / 囚 原文未表态, 亦是本项目的从严选择。
            # 正常起卦路径上 kong 由「爻支 ∈ 日辰旬空」得出, 日支永不在本旬旬空里, 故这里只判「日辰生」。
            ws_label, _ = _wangshuai(y["wx"], month_zhi)
            day_support = SHENG[dwx] == y["wx"]          # 只判「日辰生」, 见上注
            if ws_label in ("旺", "相") or day_support:
                score -= .5; factors.append("旬空(假空)")
            else:
                score -= 1.5; factors.append("旬空(真空)")
    return score, factors


def _back_relation(src_wx, changed_wx):
    if SHENG[changed_wx] == src_wx:
        return "回头生", 2
    if KE[changed_wx] == src_wx:
        return "回头克", -2
    if changed_wx == src_wx:
        return "同气", .5
    if SHENG[src_wx] == changed_wx:
        return "化泄", -.5
    return "化耗", -.5


def _hex_relation(yaos):
    pairs = [(yaos[i]["zhi"], yaos[i + 3]["zhi"]) for i in range(3)]
    if all(LIUHE.get(a) == b for a, b in pairs):
        return "六合卦"
    if all(LIUCHONG.get(a) == b for a, b in pairs):
        return "六冲卦"
    return "平"


# ---------------------------------------------------------------- 伏神 / 飞伏

def _fu_fei_relation(fu_wx, fei_wx):
    """飞伏关系。返回 (关系名, 权重, 口诀注)。
    《增删卜易·飞伏神章》四句口诀: 飞来生伏得长生 / 伏克飞名曰出暴 / 伏去生飞名泄气 / 飞来克伏遭克害。
    「飞伏比和」古籍口诀未及, 权重固定 0(中性), 不得按吉或凶赋权。
    """
    if fu_wx == fei_wx:
        return "比和", 0.0, "飞伏比和(古籍口诀未及，按中性处理)"
    if SHENG[fei_wx] == fu_wx:
        return "飞生伏", 1.5, "飞来生伏得长生，伏神易出"
    if KE[fu_wx] == fei_wx:
        return "伏克飞", 1.0, "伏克飞名曰出暴，以吉论"
    if SHENG[fu_wx] == fei_wx:
        return "伏生飞", -0.5, "伏去生飞名泄气，不吉"
    if KE[fei_wx] == fu_wx:
        return "飞克伏", -2.0, "飞来克伏遭克害，最凶"
    return "比和", 0.0, "飞伏比和(古籍口诀未及，按中性处理)"


def _fushen_shengfu(fu, month_zhi, day_zhi, moving_yaos=None):
    """`shengfu`: 与旺衰正交的「生扶」字段。
    临月建/临日辰(同五行)力大于生扶, 单列 lin 一档; 月/日/动爻生之落 sheng 档。
    """
    mwx, dwx = ZHI_WX[month_zhi], ZHI_WX[day_zhi]
    lin, sheng, tags = False, False, []
    if fu["wx"] == mwx:
        lin = True; tags.append("临月建")
    elif SHENG[mwx] == fu["wx"]:
        sheng = True; tags.append("月建生伏神")
    if fu["wx"] == dwx:
        lin = True; tags.append("临日辰")
    elif SHENG[dwx] == fu["wx"]:
        sheng = True; tags.append("日辰生伏神")
    for y in (moving_yaos or []):
        action = y.get("action") or _line_action(y, month_zhi, day_zhi)
        if action["status"] != "available":
            continue
        if SHENG[y["wx"]] == fu["wx"]:
            sheng = True; tags.append("动爻%d生伏神" % y["pos"])
    return {"lin": lin, "sheng": sheng, "tags": tags}


def _fei_weakness(fly, month_zhi, day_zhi):
    """有用⑤⑥: 飞神空破休囚墓绝, 或被日月冲克 —— 飞神被制则伏可出。返回 (原因表, 飞神月令旺衰)。"""
    reasons = []
    ws, _n = _wangshuai(fly["wx"], month_zhi)
    if fly.get("kong"):
        reasons.append("飞神旬空")
    if fly["zhi"] == LIUCHONG[month_zhi]:
        reasons.append("飞神月破")
    if ws in ("休", "囚", "死"):
        reasons.append("飞神休囚无气")
    if fly["zhi"] == LIUCHONG[day_zhi]:
        reasons.append("日辰冲飞神")
    if KE[ZHI_WX[day_zhi]] == fly["wx"]:
        reasons.append("日辰克飞神")
    if MU.get(fly["wx"]) == day_zhi:
        reasons.append("飞神入日墓")
    if JUE.get(fly["wx"]) == day_zhi:
        reasons.append("飞神绝于日")
    return reasons, ws


def _fushen_availability(fu, fly, month_zhi, day_zhi, moving_yaos=None):
    """伏神三态。
    blocked   = 无用五条并集(休囚无气 / 被日月冲克 / 被旺相之飞神克害 / 墓绝于日月飞爻 / 休囚兼值旬空月破)
    available = 有用六条并集(得日月生·旺相·得飞神生·得动爻生·日月动爻冲克飞神·飞神空破休囚墓绝)
    与 taibu 口径的两处不同: ①不设「飞神在动→available」 ②伏神落空不单独 blocked, 旺相而空落 conditional。
    返回 dict(availability / reasons / wangshuai / shengfu / fu_fei / fly_weak ...)。
    """
    rel, delta, rel_note = _fu_fei_relation(fu["wx"], fly["wx"])
    ws, ws_n = _wangshuai(fu["wx"], month_zhi)
    qi_ok = ws in ("旺", "相")
    sf = _fushen_shengfu(fu, month_zhi, day_zhi, moving_yaos)
    supported = sf["lin"] or sf["sheng"]
    fei_reasons, fei_ws = _fei_weakness(fly, month_zhi, day_zhi)
    fei_weak = bool(fei_reasons)

    fu_month_broken = fu["zhi"] == LIUCHONG[month_zhi]
    fu_day_chong = fu["zhi"] == LIUCHONG[day_zhi]
    fu_day_ke = KE[ZHI_WX[day_zhi]] == fu["wx"]
    around = (day_zhi, month_zhi, fly["zhi"])
    fu_mu_jue = (MU.get(fu["wx"]) in around) or (JUE.get(fu["wx"]) in around)

    bad = []
    if not qi_ok and not supported:
        bad.append("休囚无气")
    if (fu_month_broken or fu_day_chong or fu_day_ke) and not qi_ok and not supported:
        bad.append("被日月冲克")
    if rel == "飞克伏" and fei_ws in ("旺", "相") and not fei_weak and not qi_ok and not supported:
        bad.append("被旺相之飞神克害")
    if fu_mu_jue and not qi_ok and not supported:
        bad.append("墓绝于日月飞爻")
    if not qi_ok and (fu.get("kong") or fu_month_broken) and not supported:
        bad.append("休囚兼值旬空月破")

    good = []
    if qi_ok:
        good.append("伏神旺相有气(%s)" % ws)
    good.extend(sf["tags"])
    if rel == "飞生伏":
        good.append("得飞神生")
    good.extend(fei_reasons)

    if bad:
        status = "blocked"
    elif qi_ok or sf["lin"] or fei_weak or rel == "飞生伏":
        status = "available"
    else:
        status = "conditional"
    if fu.get("kong") and status == "available":
        # 纠正过严: 旺相而空非 blocked, 但「空而不空」仍须待冲空填实, 故降 conditional。
        status = "conditional"
        good.append("值旬空，待冲空填实方出")

    if status == "available":
        tier = "strong" if qi_ok else "moderate"
    elif status == "conditional":
        tier = "weak"
    else:
        tier = "unknown"
    return {
        "availability": status, "strength_tier": tier,
        "reasons": sorted(set(bad)) if bad else sorted(set(good)),
        "blocked_reasons": sorted(set(bad)), "available_reasons": sorted(set(good)),
        "wangshuai": ws, "wangshuai_n": ws_n, "shengfu": sf,
        "fu_fei": {"relation": rel, "delta": delta, "note": rel_note},
        "fly_weak": fei_reasons, "fly_wangshuai": fei_ws,
    }


def _ushen_sort_key(y, shi, month_zhi, day_zhi):
    """通行取舍序 —— 动静 → 临日月 → 飞伏关系 → 近世 → 旺衰 → pos → 来源等级。
    动静排在旺衰之前, 依《卜筮正宗》「两爻一动一静，取动者为用神」。
    """
    mwx = ZHI_WX[month_zhi]
    lin = (y.get("wx") == mwx) or (y.get("zhi") == day_zhi)
    active = bool(y.get("moving")) or bool(y.get("dark_moving"))
    return (
        0 if active else 1,
        0 if lin else 1,
        -float(y.get("fu_fei_delta") or 0.0),
        abs(int(y.get("pos") or 0) - shi),
        -float(y.get("strength_score") or 0.0),
        int(y.get("pos") or 0),
        int(y.get("source_rank", SOURCE_RANK["ben"])),
    )


def _build_fushen_candidates(palace, palace_elem, yaos, target, month_zhi, day_zhi, day_xunkong=""):
    """本宫首卦同爻位取伏, 本卦同位为飞。
    首卦中 target 六亲可占 1-2 爻位 -> 两条候选, 标 fushen_two_appear, 由排序取一, 不并列输出。
    首卦找不到 target(防御分支) -> 返回空表, 调用方落 selection_status='missing' 防御分支。
    """
    pure = list(TRIGRAM_LINES[palace]) * 2
    hidden = _zhuang(pure)
    moving_yaos = [y for y in yaos if y.get("moving") or y.get("dark_moving")]
    out = []
    for h in hidden:
        h["liuqin"] = _liuqin(h["wx"], palace_elem)
        if h["liuqin"] != target:
            continue
        h["moving"] = False
        h["hidden"] = True
        h["kong"] = h["zhi"] in (day_xunkong or "")
        h["strength_score"], h["factors"] = _line_strength(h, month_zhi, day_zhi)
        h.pop("dark_moving", None)  # 伏神不论暗动
        fly = yaos[h["pos"] - 1]
        fly_view = {"pos": fly["pos"], "liuqin": fly["liuqin"], "zhi": fly["zhi"], "wx": fly["wx"],
                    "kong": bool(fly.get("kong")), "moving": bool(fly.get("moving")),
                    "month_broken": bool(fly.get("month_broken"))}
        av = _fushen_availability(h, fly_view, month_zhi, day_zhi, moving_yaos)
        h["fly"] = fly_view
        h["fu_fei"] = av["fu_fei"]
        h["fu_fei_delta"] = av["fu_fei"]["delta"]
        h["availability"] = av["availability"]
        h["availability_reasons"] = av["reasons"]
        h["strength_tier"] = av["strength_tier"]
        h["fushen_wangshuai"] = av["wangshuai"]
        h["shengfu"] = av["shengfu"]
        h["fly_weak"] = av["fly_weak"]
        h["source"] = "fushen"
        h["source_rank"] = SOURCE_RANK["fushen"]
        out.append(h)
    if len(out) > 1:
        for h in out:
            h["fushen_two_appear"] = True
    return out


def _display_fushen(lines, palace, palace_elem, yaos, day_xunkong=""):
    """逐爻展示型伏神, 与取用型 `ushen` 分名分路。
    只给飞伏关系名(四句口诀之一或比和·中性), 不附吉凶结论, 不参与取用。八纯卦返回空表。
    """
    pure = list(TRIGRAM_LINES[palace]) * 2
    if list(lines) == pure:
        return []
    have = {y["liuqin"] for y in yaos}
    out = []
    for h in _zhuang(pure):
        lq = _liuqin(h["wx"], palace_elem)
        if lq in have:
            continue
        fly = yaos[h["pos"] - 1]
        rel, _delta, rel_note = _fu_fei_relation(h["wx"], fly["wx"])
        out.append({
            "pos": h["pos"], "liuqin": lq, "zhi": h["zhi"], "wx": h["wx"], "gan": h["gan"],
            "kong": h["zhi"] in (day_xunkong or ""),
            "fly": {"pos": fly["pos"], "liuqin": fly["liuqin"], "zhi": fly["zhi"], "wx": fly["wx"]},
            "relation": rel, "relation_note": rel_note,
        })
    return out


# ---------------------------------------------------------------- 三合 / 半合

def _sanhe_sources(yaos, month_zhi, day_zhi, day_xunkong=""):
    """来源池 = 动爻本支 + 变出之爻 + 静爻本支 + 日辰 + 月建。
    《增删卜易·三合章》「若两爻动，一爻不动亦成合局者，二也。」——静爻写死排除与原文相悖。
    """
    src = []
    for y in yaos:
        if y.get("moving"):
            kind = "动爻"
        elif y.get("dark_moving"):
            kind = "暗动"
        else:
            kind = "静爻"
        src.append({"zhi": y["zhi"], "wx": y["wx"], "pos": y["pos"], "source": kind,
                    "active": kind in ("动爻", "暗动"), "kong": bool(y.get("kong"))})
        if y.get("moving") and y.get("bian"):
            bz = y["bian"]["zhi"]
            src.append({"zhi": bz, "wx": y["bian"]["wx"], "pos": y["pos"], "source": "变爻",
                        "active": True, "kong": bz in (day_xunkong or "")})
    src.append({"zhi": month_zhi, "wx": ZHI_WX[month_zhi], "pos": 0, "source": "月建", "active": False, "kong": False})
    src.append({"zhi": day_zhi, "wx": ZHI_WX[day_zhi], "pos": 0, "source": "日辰", "active": False, "kong": False})
    return src


def _ju_power(elem, month_zhi, day_zhi, yaos):
    """化神力量 = 月令旺相休囚死基准 + 日辰生克调整 + 动爻克制调整。
    「月建乃万卜之提纲，日辰为六爻之主宰」——taibu 只按月令、把日辰排除, 与古法不符。
    """
    label, n = _wangshuai(elem, month_zhi)
    score = float(n)
    tags = ["月令%s" % label]
    dwx = ZHI_WX[day_zhi]
    if dwx == elem:
        score += 1.0; tags.append("临日辰")
    elif SHENG[dwx] == elem:
        score += .5; tags.append("日辰生化神")
    elif KE[dwx] == elem:
        score -= .5; tags.append("日辰克化神")
    for y in (yaos or []):
        if y.get("moving") and KE[y["wx"]] == elem:
            score -= .5; tags.append("动爻%d克化神" % y["pos"])
    return {"month_label": label, "score": round(score, 2), "factors": tags}


def _ju_status(members, month_zhi, day_zhi):
    """空破墓三因。
    《增删卜易·三合章》「有一值空破者，待填实之日月成之；有一爻入墓者，待冲开之日成之」——
    既非「不查空亡」也非「有空即不成局」, 而是局暂不发力、待填实/冲开之日方成, 本身就是一条应期。
    旬空与月破同待遇, 皆判「待填实」(应期=该支之日); 入日墓判「待冲墓开」(应期=冲墓之支)。
    三因并存时按 空 > 破 > 墓 报主因, 其余原因与应期一并保留在 reasons/yingqi 里不丢。
    只有占爻位的成员(pos>0)才延后 —— 月建/日辰本身不论空破。
    """
    basis = "增删卜易·三合章「有一值空破者，待填实之日月成之；有一爻入墓者，待冲开之日成之」"
    kong_y, po_y, mu_y, seen = [], [], [], set()
    cz = LIUCHONG[day_zhi]
    for m in members:
        if not m["pos"]:
            continue
        if m.get("kong") and ("kong", m["zhi"]) not in seen:
            seen.add(("kong", m["zhi"]))
            kong_y.append({"zhi": m["zhi"], "how": "逢%s日填实出空，局始成" % m["zhi"],
                           "kind": "critical", "cause": "旬空待填实", "basis": basis})
        if m["zhi"] == LIUCHONG[month_zhi] and ("po", m["zhi"]) not in seen:
            seen.add(("po", m["zhi"]))
            po_y.append({"zhi": m["zhi"], "how": "逢%s日填实月破，局始成" % m["zhi"],
                         "kind": "critical", "cause": "月破待填实", "basis": basis})
        if MU.get(m["wx"]) == day_zhi and ("mu", cz) not in seen:
            seen.add(("mu", cz))
            mu_y.append({"zhi": cz, "how": "逢%s日冲开%s墓，局始成" % (cz, day_zhi),
                         "kind": "critical", "cause": "入墓待冲开", "basis": basis})
    reasons = ([x["cause"] for x in kong_y[:1]] + [x["cause"] for x in po_y[:1]]
               + [x["cause"] for x in mu_y[:1]])
    yingqi = kong_y + po_y + mu_y
    if kong_y or po_y:
        return "待填实", yingqi, reasons
    if mu_y:
        return "待冲墓开", yingqi, reasons
    return "成局即发", [], []


def _ju_verdict(elem, palace_elem, ushen, shi_yao):
    """局对用神/世爻的定性。《增删卜易·三合章》「用神旺，则无不为吉，尤要世爻在局为美…」"""
    lq = _liuqin(elem, palace_elem)
    verdict = {"妻财": "合成财局，财旺生官", "子孙": "合成子孙局，乃伤官之神",
               "兄弟": "合成兄弟局，破败、耗财、阻隔之神", "官鬼": "合成官鬼局，事有主司亦有压力",
               "父母": "合成父母局，文书庇荫之神"}.get(lq, "")
    if not ushen:
        rel_u = "无涉"
    elif elem == ushen["wx"]:
        rel_u = "局与用神同类"
    elif SHENG[elem] == ushen["wx"]:
        rel_u = "局生用神"
    elif KE[elem] == ushen["wx"]:
        rel_u = "局克用神"
    elif SHENG[ushen["wx"]] == elem:
        rel_u = "用神泄于局"
    else:
        rel_u = "局与用神无涉"
    return lq, verdict, rel_u


def _analyze_sanhe(yaos, month_zhi, day_zhi, ushen=None, shi=0, palace_elem="金", day_xunkong=""):
    """三合/半合总入口。
    成局门槛 = 三支俱全 且 >=2 爻动(明动或暗动); 不设「化神得令」与门, 化神旺衰改为成局之后的力量系数。
    缺一支且在局两支皆动 -> 虚一待用, 出「逢某支日/月成局」应期。
    半合门槛: 两支须含旺神(中神, 见 BAN_SANHE_TABLE 只收 8 组) 且两支之中 >=1 爻动; 两支全静、仅靠日月凑者不作局论。
    另: 同五行三合三支俱全却判「未成(动爻不足)」时, 子集半合不再成局(本项目选择, 见 SANHE_SCHOOL_NOTE)。
    """
    src = _sanhe_sources(yaos, month_zhi, day_zhi, day_xunkong)
    shi_yao = next((y for y in yaos if y["pos"] == shi), None)
    found = []

    def _members(branches):
        return [s for s in src if s["zhi"] in branches]

    def _active_positions(members, branches):
        return sorted({m["pos"] for m in members if m["pos"] and m["active"] and m["zhi"] in branches})

    for g in SANHE_TABLE:
        br = g["branches"]
        mem = _members(br)
        present = sorted({m["zhi"] for m in mem}, key=br.index)
        act = _active_positions(mem, br)
        if len(present) == 3:
            if len(act) >= 2:
                status, yq, why = _ju_status(mem, month_zhi, day_zhi)
                found.append({"kind": "三合", "name": g["name"], "branches": list(br), "elem": g["elem"],
                              "status": status, "yingqi": yq, "members": mem, "active_positions": act,
                              "missing": None, "status_reasons": why})
            else:
                found.append({"kind": "三合", "name": g["name"], "branches": list(br), "elem": g["elem"],
                              "status": "未成(动爻不足)", "yingqi": [], "members": mem,
                              "active_positions": act, "missing": None, "status_reasons": []})
        elif len(present) == 2 and len(act) >= 2:
            miss = [b for b in br if b not in present][0]
            found.append({"kind": "三合", "name": g["name"], "branches": list(br), "elem": g["elem"],
                          "status": "虚一待用", "members": mem, "active_positions": act, "missing": miss,
                          "status_reasons": ["虚一待用"],
                          "yingqi": [{"zhi": miss, "how": "逢%s日/%s月补足三支，局成" % (miss, miss),
                                      "kind": "critical", "cause": "虚一待用",
                                      "basis": "增删卜易·三合章「缺一字者借日月补凑，谓之虚一待用」"}]})

    has_full = any(f["kind"] == "三合" and f["status"] in ("成局即发", "待填实", "待冲墓开") for f in found)
    if not has_full:
        # 有全三合时不再另报半合, 避免同组支重复计分。
        # 同五行三合三支俱全在场却被判「未成(动爻不足)」时, 半合不得另开后门(本项目选择, 古籍未写);
        # 「未成(动爻不足)」只在三支俱全分支产生, 写进 taken 不会误伤三支不全的组。
        # 注意 _sanhe_sources 把月建 / 日辰也算「在场」, 所以「三支俱全」比直觉常见。
        taken = {f["elem"] for f in found if f["status"] in ("虚一待用", "未成(动爻不足)")}
        for g in BAN_SANHE_TABLE:
            br = g["branches"]
            if g["elem"] in taken:
                continue
            mem = _members(br)
            present = {m["zhi"] for m in mem}
            if len(present) < 2:
                continue
            act = _active_positions(mem, br)
            # 两支全静(仅靠日月凑)不作半合论; 有一爻动即成。门槛 = 1 动, 不是 2 动:
            # 《增删卜易·三合章》「若两爻动，一爻不动亦成合局者，二也」主语是三合, 不外推到半合。
            if not act:
                continue
            status, yq, why = _ju_status(mem, month_zhi, day_zhi)
            found.append({"kind": "半合", "name": g["name"], "branches": list(br), "elem": g["elem"],
                          "status": status, "yingqi": yq, "members": mem, "active_positions": act,
                          "missing": None, "ban_type": g["type"], "status_reasons": why})

    rank = {"成局即发": 0, "待填实": 1, "待冲墓开": 1, "虚一待用": 2, "未成(动爻不足)": 9}
    out = []
    for f in found:
        power = _ju_power(f["elem"], month_zhi, day_zhi, yaos)
        lq, verdict, rel_u = _ju_verdict(f["elem"], palace_elem, ushen, shi_yao)
        base = 2.0 if f["kind"] == "三合" else 1.0
        bonus = 0.0
        if f["status"] == "未成(动爻不足)":
            bonus = 0.0
        else:
            if ushen and ushen["zhi"] in f["branches"]:
                bonus += base * .6
            if ushen:
                if f["elem"] == ushen["wx"]:
                    bonus += base * .5
                elif SHENG[f["elem"]] == ushen["wx"]:
                    bonus += base * .4
                elif KE[f["elem"]] == ushen["wx"]:
                    bonus -= base * .6
                elif SHENG[ushen["wx"]] == f["elem"]:
                    bonus -= base * .2
            if f["status"] != "成局即发":
                bonus *= .5
            bonus *= (1.0 + .15 * max(-2.0, min(2.0, power["score"])))
            bonus = max(-base, min(base, bonus))
        if shi_yao and shi_yao["zhi"] in f["branches"]:
            rel_s = "世爻在局为美"
        elif not shi_yao:
            rel_s = "世爻不明"
        elif SHENG[f["elem"]] == shi_yao["wx"]:
            rel_s = "局生世爻，始以吉断"
        elif KE[f["elem"]] == shi_yao["wx"]:
            rel_s = "局克世爻，则以凶推"
        else:
            rel_s = "世爻不在局内且局不生世，吉凶从缓"
        out.append({
            "kind": f["kind"], "name": f["name"], "status": f["status"], "branches": f["branches"],
            "elem": f["elem"], "missing": f["missing"], "ban_type": f.get("ban_type"),
            "positions": sorted({m["pos"] for m in f["members"] if m["pos"]}),
            "active_positions": f["active_positions"],
            "sources": [{"zhi": m["zhi"], "pos": m["pos"], "source": m["source"],
                         "active": m["active"], "kong": m["kong"]} for m in f["members"]],
            "power": power, "liuqin_ju": lq, "verdict": verdict,
            "status_reasons": f.get("status_reasons") or [],
            "relation_to_ushen": rel_u, "relation_to_shi": rel_s,
            "bonus": round(bonus, 2), "yingqi": f["yingqi"],
            "school_note": SANHE_SCHOOL_NOTE,
        })
    out.sort(key=lambda f: (rank.get(f["status"], 5) + (0 if f["kind"] == "三合" else 3), -abs(f["bonus"])))
    if not out:
        return {"status": "无", "kind": "无", "name": None, "branches": [], "elem": None,
                "sources": [], "positions": [], "active_positions": [], "power": None,
                "liuqin_ju": None, "verdict": None, "relation_to_ushen": "无涉",
                "relation_to_shi": "无涉", "bonus": 0.0, "yingqi": [], "missing": None,
                "ban_type": None, "status_reasons": [], "school_note": SANHE_SCHOOL_NOTE, "all": []}
    primary = dict(out[0])
    primary["all"] = out
    return primary


# ---------------------------------------------------------------- 应期

def _yq(hits, seen, ds, how, kind, basis, prio):
    key = (ds, how)
    if key in seen:
        return
    seen.add(key)
    hits.append({"date": ds, "how": how, "kind": kind, "basis": basis, "_prio": prio})


def _yq_annotate(hits, ds, how, note):
    """把补充说明并进当天同名候选的 basis, **不另起一条候选**。命中返回 True, 没有该条返回 False。

    用途: 两条规则触发条件完全相同(同一天必然同时命中)时, 再单列一条只会挤掉 top-3 的名额、
    却带不来新日期; 信息并进已有那条的依据里, 叙事层照样看得见(basis 会作为「依据」进入材料)。
    """
    for h in hits:
        if h["date"] == ds and h["how"] == how:
            if note not in h["basis"]:
                h["basis"] = h["basis"] + "；" + note
            return True
    return False


def _yingqi_all(ushen, future_day_zhi, horizon_days, month_zhi, day_zhi, weak=False, sanhe=None, limit=None):
    """应期候选全表。
    · 静爻逢值逢冲, 动爻逢值逢合
    · 空亡四态 kong_static / kong_changing / kong_ri_chong / kong_yue_jian(假空)
    · 明动 / 暗动分述 + 变爻支入候选
    · 弱 / 破转正向候选日: 生扶日、长生帝旺日、填实日、合日
    · 合绊改冲开: 用神被日辰合住则合日不应, 待冲开之日
    · 伏神专属出伏分支: 冲飞神日 / 飞神墓绝日 / 伏神得生扶旺相之时
    · 静爻逢冲加旺衰门禁: 旺相为暗动(favorable「冲用神」), 休囚死为日破(unfavorable「逢冲日破」); 假空一律不作日破
    · 用神入日墓 / 动而化墓 -> 「冲开墓库」(critical); 土用神自墓流派分歧大, 排除;
      出墓那一支(值本气之日)与「值用神」同日同触发, 并进其 basis 不另起候选
    """
    uz, uwx = ushen["zhi"], ushen["wx"]
    u_ws, _u_ws_n = _wangshuai(uwx, month_zhi)   # 用神月令旺衰, 静爻逢冲门禁与 _line_strength 同判据
    kong = bool(ushen.get("kong"))
    moving = bool(ushen.get("moving"))
    dark = bool(ushen.get("dark_moving"))
    hidden = bool(ushen.get("hidden"))
    day_combined = bool(ushen.get("day_combined"))
    day_clashed = bool(ushen.get("day_clashed"))
    month_broken = bool(ushen.get("month_broken"))
    fly = ushen.get("fly") or {}
    bian = ushen.get("bian") or {}
    avail = ushen.get("availability")
    chong = LIUCHONG[uz]
    he = LIUHE.get(uz)
    # 「不为真空」的判据与 _line_strength 的真假空分档同一口径: 旺/相, 或得日辰生(逐档说明见该函数)。
    # 明动旬空统一走待冲实/填实, 旺相明动也不能跳过待时条件。
    # 变量名 kong_yue_jian 是空亡四态之一的既有名, 语义为「假空」。
    kong_yue_jian = kong and not moving and (u_ws in ("旺", "相") or SHENG[ZHI_WX[day_zhi]] == uwx)
    kong_ri_chong = kong and day_clashed     # 空逢日冲, 冲空转实
    # —— 用神入墓。本气墓库法, 土用神(自墓于辰)流派分歧大, 排除。
    # 日墓 = 日辰即用神之墓库支; 化墓 = 用神发动且变爻之支即其墓库支。
    umu = None if uwx == "土" else MU.get(uwx)
    mu_open = LIUCHONG[umu] if umu else None                       # 冲开墓库之支
    rimu = bool(umu) and day_zhi == umu
    huamu = bool(umu) and moving and bian.get("zhi") == umu
    MU_BASIS = ("增删卜易·各门类应期总注章第又二十六「入三墓俱喜冲开」"
                "(且如主象临午火入墓于戌，后逢辰日则应之)")
    hits, seen = [], set()
    for ds, dz in (future_day_zhi or [])[:horizon_days]:
        # —— 空亡四态
        if kong and not kong_yue_jian:
            if dz == chong:
                if kong_ri_chong:
                    _yq(hits, seen, ds, "冲空转实", "critical", "卜筮正宗·又逢日冲谓实", 0)
                elif moving:
                    _yq(hits, seen, ds, "动空冲实", "critical", "卜筮正宗·空而动者，冲之则实", 0)
                else:
                    _yq(hits, seen, ds, "冲空起用", "critical", "卜筮正宗·空而静者，冲之则起", 0)
            if dz == uz:
                _yq(hits, seen, ds, "填实出空", "critical", "卜筮正宗·用爻旬空发动，以出旬之日断", 0)
        # —— 月破/日破转正向候选
        if month_broken:
            if dz == uz:
                _yq(hits, seen, ds, "填实月破", "critical", "增删卜易·月破逢填实之日", 1)
            if he and dz == he:
                _yq(hits, seen, ds, "月破逢合", "favorable", "增删卜易·破而逢合", 2)
        # —— 合绊主次
        if day_combined and dz == chong:
            _yq(hits, seen, ds, "冲开日合", "critical", "卜筮正宗·如逢合住，须冲破以成功", 1)
        # —— 静爻逢值逢冲 / 动爻逢值逢合
        if dz == uz:
            _yq(hits, seen, ds, "值用神", "favorable", "通行口诀·静爻逢值逢冲，动爻逢值逢合", 1)
        if (moving or dark) and he and dz == he and not day_combined:
            _yq(hits, seen, ds, "合用神", "favorable", "通行口诀·动爻逢值逢合", 1)
        if not moving and not dark and dz == chong and (not kong or kong_yue_jian):
            # 假空(不为空)之静爻按不空走「逢冲则起 / 暗动」; 真空只走上面的空亡四态, 两边互斥不重复。
            # 旺衰门禁: 《增删卜易·日辰章》「冲旺相之静爻即为暗动，冲衰弱之静爻则为日破」、暗动章
            # 「静爻旺相，日辰冲之暗动。静爻休囚，日辰冲之为日破」。
            # 假空之爻一律不入日破那一支: 《卜筮正宗》「空而静者，冲之则起」、《增删卜易·旬空章》
            # 「有日建动爻动扶者，亦不为空」; 「冲衰弱之静爻则为日破」讲的是不空之衰爻。
            if u_ws in ("旺", "相") or kong:
                _yq(hits, seen, ds, "冲用神", "favorable",
                    ("卜筮正宗·空而静者，冲之则起(增删卜易·旬空章判为假空，故不作日破论)" if kong
                     else "卜筮正宗·不空而静者，冲之则暗动"), 1)
            else:
                _yq(hits, seen, ds, "逢冲日破", "unfavorable",
                    "增删卜易·日辰章「冲衰弱之静爻则为日破」(用神%s于月令，冲之更加无用)" % u_ws, 4)
        # —— 明动/暗动分述 + 变爻支
        if moving and not kong and dz == chong:
            _yq(hits, seen, ds, "动爻逢冲", "critical", "卜筮正宗·不空而动者，冲之则散", 2)
        if dark and dz == uz:
            _yq(hits, seen, ds, "暗动被引发之期", "favorable", "卜筮正宗·不空而静者，冲之则暗动", 2)
        if (moving or dark) and bian.get("zhi") and dz == bian["zhi"]:
            _yq(hits, seen, ds, "逢变爻%s" % bian["zhi"], "favorable",
                "增删卜易·发动之爻有应于变爻之日月", 2)
        # —— 用神入墓: 冲墓开库 / 值用本气出墓
        # 墓中人不冲不发, 冲开墓库之日为第一关键日, 故 prio 0 压过同日其他候选。
        if (rimu or huamu) and mu_open:
            if dz == mu_open:
                _yq(hits, seen, ds, "冲开%s墓库" % umu, "critical", MU_BASIS, 0)
            if dz == uz:
                # 值本气之日作出墓论: 借《增删卜易·应期总注章》「静而逢值逢冲」之「值」, 力弱于冲墓。
                # 触发条件(dz == uz)与上面「值用神」完全相同, 不另起候选, 把出墓信息并进当天「值用神」的 basis。
                _mu_note = ("用神%s入%s墓，本日值其本气，兼作出墓论"
                            "(增删卜易·各门类应期总注章「静而逢值逢冲」之「值」，力弱于冲开墓库)"
                            % (uz, umu))
                if not _yq_annotate(hits, ds, "值用神", _mu_note):
                    # 兜底: 万一日后「值用神」加了门禁当天没出条目, 出墓信息不能丢, 退回单列一条
                    _yq(hits, seen, ds, "值用本气出墓", "favorable",
                        "增删卜易·各门类应期总注章「静而逢值逢冲」(入墓之爻逢本气值日作出墓候选)", 3)
        # —— 弱者以生旺之期应事
        if weak:
            if SHENG[ZHI_WX[dz]] == uwx:
                _yq(hits, seen, ds, "得生扶之日", "favorable", "增删卜易·休囚者以生旺之期应事", 3)
            if dz == CHANGSHENG.get(uwx):
                _yq(hits, seen, ds, "用神长生之日", "favorable", "增删卜易·休囚者以生旺之期应事", 3)
            if dz == DIWANG.get(uwx):
                _yq(hits, seen, ds, "用神帝旺之日", "favorable", "增删卜易·休囚者以生旺之期应事", 3)
        # —— 伏神出伏专属分支
        if hidden and avail != "blocked" and fly.get("zhi"):
            if dz == LIUCHONG[fly["zhi"]]:
                _yq(hits, seen, ds, "冲飞神%s%s" % (fly.get("liuqin") or "", fly["zhi"]), "critical",
                    "增删卜易·飞伏神章「子日冲克午火之飞神，生起卯木之伏神」", 0)
            if KE[ZHI_WX[dz]] == fly.get("wx"):
                _yq(hits, seen, ds, "日克飞神%s" % fly["zhi"], "favorable", "增删卜易·日月动爻冲克飞神则伏可出", 2)
            if MU.get(fly.get("wx")) == dz:
                _yq(hits, seen, ds, "飞神入墓之日", "favorable", "增删卜易·飞神墓绝则伏可出", 2)
            if JUE.get(fly.get("wx")) == dz:
                _yq(hits, seen, ds, "飞神绝地之日", "favorable", "增删卜易·飞神墓绝则伏可出", 2)
            if fly.get("kong") and dz == fly["zhi"]:
                _yq(hits, seen, ds, "飞神填实出空", "favorable", "增删卜易·飞神空破则伏可出", 3)
            if SHENG[ZHI_WX[dz]] == uwx:
                _yq(hits, seen, ds, "日生伏神", "favorable", "增删卜易·飞伏神章有用①得日月生", 2)
            if dz == DIWANG.get(uwx):
                _yq(hits, seen, ds, "伏神值帝旺", "favorable", "增删卜易·飞伏神章有用②旺相", 2)
        # —— 三合待填实/待冲墓开/虚一待用
        for item in ((sanhe or {}).get("yingqi") or []):
            if dz == item["zhi"]:
                _yq(hits, seen, ds, item["how"], item.get("kind", "critical"), "增删卜易·三合章", 1)
        # 已有出空、月破、入墓触发沿用；只补尚缺的化空和合绊观察点。
        # 它们仅表示某项条件可复查，不代表全部制约解除，更不是完成日期。
        for condition in (ushen.get("action") or {}).get("wait_for", []):
            if condition["id"] in ("changed_void", "day_combined", "changed_combined") and dz in condition["branches"]:
                how = {"changed_void": "化空条件观察", "day_combined": "合绊条件观察",
                       "changed_combined": "化合条件观察"}[condition["id"]]
                _yq(hits, seen, ds, how, "critical", "增删卜易·旬空章／用神元神忌神仇神章；仍须核对其他条件", 1)
    action = ushen.get("action") or {}
    # 「作用未定」(休囚无伤) 不把利日降级 —— 弱用神待生旺之日正是古法应期。
    if action.get("status") in ("waiting", "blocked"):
        for hit in hits:
            if hit["kind"] == "favorable":
                hit["kind"] = "critical"
            hit["basis"] += "；原用神%s，单项触发不代表已恢复作用或事件完成" % action["label"]
    hits.sort(key=lambda h: (h["date"], h["_prio"]))   # 主序按日期(应期本义), 同日内按规则优先级
    for h in hits:
        h.pop("_prio", None)
    return hits if limit is None else hits[:limit]


def _yingqi_top(hits, n=3):
    """top-n 取用顺序: unfavorable(逢冲日破这类坏日子)不占 favorable/critical 的位置, 只在吉项不足 n 条时补位;
    完整候选表连 kind 一起留在 yingqi_all。组内沿用 _yingqi_all 的排序(日期为主, 同日按规则优先级)。
    """
    good = [h for h in (hits or []) if h.get("kind") != "unfavorable"]
    bad = [h for h in (hits or []) if h.get("kind") == "unfavorable"]
    return (good + bad)[:n]


def _yingqi_candidates(ushen, future_day_zhi, horizon_days, month_zhi=None, day_zhi=None, weak=False, sanhe=None):
    """向下兼容入口: 返回 top-3(每项带 date/how/kind/basis)。"""
    month_zhi = month_zhi or ushen.get("_month_zhi") or "子"
    day_zhi = day_zhi or ushen.get("_day_zhi") or "子"
    # 截断走 _yingqi_top, 与 cast() 同口径(不利项不占吉项名额)。
    return _yingqi_top(_yingqi_all(ushen, future_day_zhi, horizon_days, month_zhi, day_zhi,
                                   weak=weak, sanhe=sanhe), 3)


def _yingqi_notes(ushen, weak, month_broken, day_zhi=None):
    """unfavorable / unverified 提示不进 top-3 应期(它们无日期), 单列 notes 供叙事层。"""
    notes = []
    if ushen.get("hidden"):
        if ushen.get("availability") == "blocked":
            notes.append("伏神犯无用之条(%s)，终不能出，时限内不宜以出伏定成。"
                         % "、".join(ushen.get("availability_reasons") or []))
        else:
            notes.append("「伏神值日即出伏」属后世通说，古籍未明言，本引擎不计入应期候选，仅备参考。")
    if weak:
        notes.append("用神休囚受制，未得生扶前不宜过早定成，宜以生旺之期应事。")
    if month_broken:
        notes.append("用神月破，须待填实或逢合之日方论成事。")
    # 入墓提示: 说清入的是哪个墓、待哪支冲开; 土用神自墓争议大, 不提示也不出候选。
    uwx = ushen.get("wx")
    umu = None if uwx == "土" else MU.get(uwx)
    if umu:
        bian_zhi = (ushen.get("bian") or {}).get("zhi")
        rimu = bool(day_zhi) and day_zhi == umu
        huamu = bool(ushen.get("moving")) and bian_zhi == umu
        if rimu or huamu:
            notes.append("用神%s入%s墓（%s），墓中人不冲不发，须待%s日冲开墓库方见动静。"
                         % (uwx, "日辰" if rimu else "变爻", umu, LIUCHONG[umu]))
    return notes


# ---------------------------------------------------------------- 主流程

def _mk_pseudo(zhi, palace_elem, source, month_zhi, day_zhi, day_xunkong):
    """月建/日辰充当用神时的伪爻(pos=0, 不占爻位)。"""
    y = {"pos": 0, "gan": None, "zhi": zhi, "wx": ZHI_WX[zhi], "moving": False,
         "kong": zhi in (day_xunkong or ""), "hidden": False, "yang": None,
         "shi": False, "ying": False, "bian": None, "liushen": None}
    y["liuqin"] = _liuqin(y["wx"], palace_elem)
    y["strength_score"], y["factors"] = _line_strength(y, month_zhi, day_zhi)
    y["source"] = source
    y["source_rank"] = SOURCE_RANK[source]
    return y


def _select_ushen(target, yaos, bian_yaos, palace, palace_elem, shi, month_zhi, day_zhi, day_xunkong):
    """统一候选池 + 前置顺序。
    《增删卜易》次序: 用神不上卦 -> 先取变卦 -> 再取日月 -> 日月亦非用神才寻伏神。
    本卦无用神时不直接取伏神, 先看变卦与日月。
    """
    groups = []
    ben = [y for y in yaos if y["liuqin"] == target]
    for y in ben:
        y["source"] = "ben"; y["source_rank"] = SOURCE_RANK["ben"]
    groups.append(("ben", ben))

    bian = []
    for y in yaos:
        if not y.get("moving") or not y.get("bian"):
            continue
        if y["bian"]["liuqin"] != target:
            continue
        by = dict(bian_yaos[y["pos"] - 1])
        by["liuqin"] = y["bian"]["liuqin"]
        by["moving"] = False
        by["kong"] = by["zhi"] in (day_xunkong or "")
        by["hidden"] = False
        by["bian"] = None
        by["from_pos"] = y["pos"]
        by["strength_score"], by["factors"] = _line_strength(by, month_zhi, day_zhi)
        by["source"] = "bian"; by["source_rank"] = SOURCE_RANK["bian"]
        bian.append(by)
    groups.append(("bian", bian))

    riyue = []
    for src, zhi in (("ri", day_zhi), ("yue", month_zhi)):
        p = _mk_pseudo(zhi, palace_elem, src, month_zhi, day_zhi, day_xunkong)
        if p["liuqin"] == target:
            riyue.append(p)
    groups.append(("riyue", riyue))

    fushen = _build_fushen_candidates(palace, palace_elem, yaos, target, month_zhi, day_zhi, day_xunkong)
    groups.append(("fushen", fushen))

    pool = [y for _g, items in groups for y in items]
    for _g, items in groups:
        if not items:
            continue
        items.sort(key=lambda y: _ushen_sort_key(y, shi, month_zhi, day_zhi))
        return items[0], items, pool, "ok"
    return None, [], pool, "missing"


def cast(question, category, horizon_days, day_gz, month_zhi, day_xunkong, future_day_zhi, rng=None, coins=None,
         gender=None):
    """摇卦并装卦; coins 为自下而上六次的正面枚数(0..3), 与返回的 throws 同义。

    传 coins 可复用原卦分析新的期限, 不能同时传 rng。gender(female / male)只影响「感情」类的用神,
    问「感情」时必须给出, 其它类别可以不给。
    作用条件门禁可能影响势能与同类取用; yingqi 是兼容摘要, 分阶段候选见 chaoqian.timing.build_timeline。
    """
    if gender not in (None, "female", "male"):
        raise ValueError("gender must be female, male or None")
    if category == "感情" and gender is None:
        raise ValueError("感情类问事需要给出 gender(female / male) 才能取用神")
    if coins is not None:
        if rng is not None:
            raise ValueError("coins and rng cannot be supplied together")
        if not isinstance(coins, (list, tuple)) or len(coins) != 6:
            raise ValueError("coins must contain six heads counts from bottom to top")
        if any(type(value) is not int or not 0 <= value <= 3 for value in coins):
            raise ValueError("each coin heads count must be an integer from 0 to 3")
        coins = list(coins)
    rng = rng or random.SystemRandom()
    throws, lines, moving = [], [], []
    for i in range(6):
        heads = coins[i] if coins is not None else sum(rng.randint(0, 1) for _ in range(3))
        throws.append(heads)
        if heads == 3:
            lines.append(1); moving.append(True)   # 老阳
        elif heads == 0:
            lines.append(0); moving.append(True)   # 老阴
        elif heads == 1:
            lines.append(1); moving.append(False)  # 少阳
        else:
            lines.append(0); moving.append(False)  # 少阴
    ben, shang, xia = _hex_name(lines)
    bian_lines = [1 - v if moving[i] else v for i, v in enumerate(lines)]
    bian = _hex_name(bian_lines)[0] if any(moving) else None
    palace, shi = PALACE_MAP[ben]
    ying = shi + 3 if shi <= 3 else shi - 3
    pe = PALACE_ELEM[palace]
    day_zhi = day_gz[1]
    yaos = _zhuang(lines)
    bian_yaos = _zhuang(bian_lines)
    for y in yaos:
        y["liuqin"] = _liuqin(y["wx"], pe)
        y["moving"] = moving[y["pos"] - 1]
        y["yang"] = lines[y["pos"] - 1] == 1
        y["shi"] = y["pos"] == shi
        y["ying"] = y["pos"] == ying
        y["kong"] = y["zhi"] in (day_xunkong or "")
        by = bian_yaos[y["pos"] - 1]
        by["liuqin"] = _liuqin(by["wx"], pe)
        if y["moving"]:
            rel, delta = _back_relation(y["wx"], by["wx"])
            if JINSHEN.get(y["zhi"]) == by["zhi"]:
                rel, delta = "化进神", 1.5
            elif TUISHEN.get(y["zhi"]) == by["zhi"]:
                rel, delta = "化退神", -1.5
            y["bian"] = {"gan": by["gan"], "zhi": by["zhi"], "wx": by["wx"], "liuqin": by["liuqin"], "relation": rel}
            y["back_delta"] = delta
        else:
            y["bian"] = None
    start = LIUSHEN_START.get(day_gz[0], 0)
    for i, y in enumerate(yaos):
        y["liushen"] = LIUSHEN[(start + i) % 6]
    # 每爻先算日月与动变，再取用神；避免“先挑第一爻、后看旺衰”。
    for y in yaos:
        base_score, factors = _line_strength(y, month_zhi, day_zhi)
        if y["moving"]:
            base_score += .5 + y.get("back_delta", 0)
            factors.append("动爻")
            if y.get("bian"):
                factors.append(y["bian"]["relation"])
        y["strength_score"] = round(base_score, 2)
        y["factors"] = factors
    for y in yaos:
        y["action"] = _line_action(y, month_zhi, day_zhi, day_xunkong, yaos)

    # 用神: 统一候选池 + 前置顺序
    target = USHEN_LOVE_BY_GENDER[gender] if category == "感情" else USHEN_BY_CATEGORY.get(category, "世爻")
    note = None
    selection_status = "ok"
    chosen_group = []
    if target == "世爻":
        ushen = next(y for y in yaos if y["shi"])
        ushen["source"] = "ben"; ushen["source_rank"] = SOURCE_RANK["ben"]
    else:
        ushen, chosen_group, _pool, sel = _select_ushen(
            target, yaos, bian_yaos, palace, pe, shi, month_zhi, day_zhi, day_xunkong)
        if ushen is None:
            selection_status = "missing"
            ushen = next(y for y in yaos if y["shi"])
            ushen["source"] = "ben"; ushen["source_rank"] = SOURCE_RANK["ben"]
            note = "用神%s不上卦、变卦日月皆非、本宫首卦亦无此六亲，以世爻参断" % target
        else:
            src = ushen.get("source", "ben")
            if src == "ben" and len(chosen_group) > 1:
                note = "用神两现，按动静、临日月、近世取用(《卜筮正宗》口径)"
            elif src == "bian":
                note = "用神%s不上主卦，取变卦%s%s为用" % (target, ushen["liuqin"], ushen["zhi"])
            elif src in ("ri", "yue"):
                note = "用神%s不上卦亦不见于变卦，取%s%s为用" % (target, SOURCE_LABEL[src], ushen["zhi"])
            elif src == "fushen":
                f = ushen.get("fly") or {}
                note = "用神%s不上卦，取本宫伏神；飞神为%s%s，%s；伏神%s" % (
                    target, f.get("liuqin", ""), f.get("zhi", ""),
                    (ushen.get("fu_fei") or {}).get("note", ""), ushen.get("availability", ""))
                if ushen.get("fushen_two_appear"):
                    note += "(伏神两现，已按动静·临日月·飞伏关系取一)"

    # 当前能施力才计单爻生克; 待时、受制及未定均保留记录而不冒充已生效。
    ushen["action"] = _line_action(ushen, month_zhi, day_zhi, day_xunkong, yaos)
    if ushen.get("hidden") and ushen.get("availability") in ("blocked", "conditional"):
        a = ushen["action"]
        if ushen["availability"] == "blocked":
            a.update(status="blocked", label="当前受制")
        elif a["status"] == "available":
            a.update(status="waiting", label="待条件解除")
        a["reasons"].extend(ushen.get("availability_reasons") or [])
    strength = float(ushen.get("strength_score", 0))
    factors = list(ushen.get("factors") or [])
    influences = []
    for y in yaos:
        if not (y["moving"] or y.get("dark_moving")) or y["pos"] == ushen["pos"]:
            continue
        relation = None
        if SHENG[y["wx"]] == ushen["wx"]:
            relation, nominal = "生", 1.2
        elif KE[y["wx"]] == ushen["wx"]:
            relation, nominal = "克", -1.2
        if relation is None:
            continue
        action = y["action"]
        # available 全额, uncertain(休囚无伤) 六折, waiting/blocked 归零 (ACTION_WEIGHT)。
        weight = ACTION_WEIGHT.get(action["status"], 0.0)
        delta = round(nominal * weight, 2)
        influences.append({"pos": y["pos"], "zhi": y["zhi"], "wx": y["wx"],
                           "relation": relation, "moving_type": "moving" if y["moving"] else "dark",
                           "action": action, "weight": weight, "score_delta": delta})
        strength += delta
        if delta:
            factors.append("%s爻%s%s用神%s" % ("动" if y["moving"] else "暗动", y["pos"], relation,
                                              "(六折)" if weight < 1 else ""))
    # 三合/半合: 反哺打分与定性
    sanhe = _analyze_sanhe(yaos, month_zhi, day_zhi, ushen, shi, pe, day_xunkong)
    if sanhe["status"] not in ("无", "未成(动爻不足)"):
        strength += sanhe["bonus"]
        factors.append("%s·%s" % (sanhe["name"], sanhe["status"]))
        if sanhe["relation_to_shi"]:
            factors.append(sanhe["relation_to_shi"])
    # 飞伏关系反哺
    if ushen.get("hidden") and ushen.get("fu_fei"):
        strength += float(ushen["fu_fei"]["delta"])
        factors.append("飞伏%s" % ushen["fu_fei"]["relation"])
    hex_rel = _hex_relation(yaos)
    if hex_rel == "六合卦":
        strength += .5; factors.append("六合卦")
    elif hex_rel == "六冲卦":
        strength -= .5; factors.append("六冲卦")
    strength = round(strength, 2)
    strength_label = "强" if strength >= 2 else ("平" if strength >= -.5 else "弱")
    ws_label, _ = _wangshuai(ushen["wx"], month_zhi)
    day_note = "、".join(x for x in factors if x.startswith("日"))
    weak = strength_label == "弱"
    all_hits = _yingqi_all(ushen, future_day_zhi, horizon_days, month_zhi, day_zhi, weak=weak, sanhe=sanhe)
    hits = _yingqi_top(all_hits, 3)   # 不利项不占吉项名额, 完整表见 yingqi_all
    uz = ushen["zhi"]
    return {
        "throws": throws, "coins": list(throws), "coin_encoding": "heads-count",
        "cast_context": {"day_gz": day_gz, "month_zhi": month_zhi, "day_xunkong": day_xunkong},
        "lines": lines, "moving": [i + 1 for i, m in enumerate(moving) if m],
        "ben": ben, "bian": bian, "palace": palace, "palace_elem": pe,
        "shi": shi, "ying": ying, "yaos": yaos,
        "ushen": {"pos": ushen["pos"], "liuqin": ushen["liuqin"], "zhi": uz, "wx": ushen["wx"], "kong": ushen["kong"],
                  "action": ushen["action"],
                  "hidden": bool(ushen.get("hidden")), "month_broken": bool(ushen.get("month_broken")),
                  "day_combined": bool(ushen.get("day_combined")), "day_clashed": bool(ushen.get("day_clashed")),
                  "moving": bool(ushen.get("moving")), "bian": ushen.get("bian"), "note": note,
                  "source": ushen.get("source", "ben"), "source_label": SOURCE_LABEL.get(ushen.get("source", "ben")),
                  "source_rank": ushen.get("source_rank", SOURCE_RANK["ben"]),
                  "selection_status": selection_status,
                  "dark_moving": bool(ushen.get("dark_moving")),
                  "wangshuai": ws_label,
                  "availability": ushen.get("availability"),
                  "availability_reasons": ushen.get("availability_reasons") or [],
                  "strength_tier": ushen.get("strength_tier"),
                  "fu_fei": ushen.get("fu_fei"), "fly": ushen.get("fly"),
                  "shengfu": ushen.get("shengfu"),
                  "fushen_two_appear": bool(ushen.get("fushen_two_appear")),
                  "candidates": [{"pos": c["pos"], "zhi": c["zhi"], "wx": c["wx"], "source": c.get("source"),
                                  "moving": bool(c.get("moving")), "kong": bool(c.get("kong")),
                                  "strength_score": c.get("strength_score"),
                                  "availability": c.get("availability")} for c in chosen_group]},
        "wangshuai": ws_label, "day_note": day_note, "strength_score": strength, "strength_label": strength_label,
        "factors": factors, "hex_relation": hex_rel, "yingqi": hits, "rule_version": RULE_VERSION,
        "action_version": ACTION_VERSION, "influences": influences,
        "sanhe": sanhe,
        "display_fushen": _display_fushen(lines, palace, pe, yaos, day_xunkong),
        "yingqi_all": all_hits,
        "yingqi_notes": _yingqi_notes(ushen, weak, bool(ushen.get("month_broken")), day_zhi),
    }
