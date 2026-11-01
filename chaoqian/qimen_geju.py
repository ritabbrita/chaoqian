# -*- coding: utf-8 -*-
"""
时家奇门 · 格局判定。

纯函数模块: 只读 qimen.pan() 的返回 dict, 不改盘、不排盘、不依赖任何第三方库。

规则表 _RULES 每条带 verified 标记(confirmed / partial / conflict):
  - confirmed / partial 条目按其「实现口径」接入, 参与打分;
  - conflict 条目只接入已给出定案口径的那几组(青龙返首=戊加丙 / 飞鸟跌穴=丙加戊、
    白虎猖狂=辛加乙、朱雀投江=丁加癸、六仪击刑新表用 tian 判、三奇入墓新表、三诈五假通行表);
  - unverified 条目一律不进引擎, 清单见 _NOT_IMPLEMENTED。
格局清单与判据的整理思路参考了 taibu 与 Sudo-Biao 两个开源项目(均为 MIT), 判据以古籍与通行表为准,
未照抄其源码; 见 README「致谢」。

输出格式: formations(pan_dict, hour_zhi=None) -> {"by_palace": {宫: [格局...]}, "global": [格局...]}
每条格局 dict: id / name / kind(吉|凶|中) / level / palace / basis(判据一句) / source(古籍出处) /
verified / hint(断语)。
"""

# ---------------------------------------------------------------------------
# 常量: 与 qimen.py 同源镜像(本模块保持零依赖, 不 import qimen 以免循环导入)。
# tests/test_qimen_geju.py 有一条「镜像一致性」断言防漂移。
# ---------------------------------------------------------------------------
RING = [1, 8, 3, 4, 9, 2, 7, 6]
PALACE_NAME = {1: "坎", 2: "坤", 3: "震", 4: "巽", 5: "中", 6: "乾", 7: "兑", 8: "艮", 9: "离"}
PALACE_ELEM = {1: "水", 2: "土", 3: "木", 4: "木", 5: "土", 6: "金", 7: "金", 8: "土", 9: "火"}
STAR_HOME = {1: "天蓬", 2: "天芮", 3: "天冲", 4: "天辅", 5: "天禽", 6: "天心", 7: "天柱", 8: "天任", 9: "天英"}
DOOR_HOME = {1: "休门", 2: "死门", 3: "伤门", 4: "杜门", 6: "开门", 7: "惊门", 8: "生门", 9: "景门"}
DOOR_ELEM = {"休门": "水", "生门": "土", "伤门": "木", "杜门": "木", "景门": "火", "死门": "土", "惊门": "金", "开门": "金"}
KE = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}
GOOD_DOORS = {"开门", "休门", "生门"}

# 后天八卦对宫(反吟用), 中 5 无对宫
OPPOSITE = {1: 9, 9: 1, 2: 8, 8: 2, 3: 7, 7: 3, 4: 6, 6: 4}
SANQI = ("乙", "丙", "丁")

GEJU_VERSION = "chaoqian-qimen-geju-0.1"

# 量级: 与 Sudo-Biao 格局分层的量级对齐
LEVEL_SCORE = {"auspicious_great": 3, "auspicious": 2, "mixed": 0,
               "inauspicious": -2, "inauspicious_great": -3, "大凶": -3}
# ⚠ 下面三个系数**无古籍依据, 纯工程参数**: 为不覆盖 day_hours() 里门 ±2 的主导权重而设,
#   别当成命理口径。SCALE 0.5 折后 ±3 正好触顶 ±1.5。
SCORE_SCALE = 0.5
ZHIFU_DISCOUNT = 0.5   # 值使宫全权, 值符宫再打折
SCORE_CAP = 1.5


def _R(rid, name, kind, level, verified, source, hint, alias=None):
    d = {"name": name, "kind": kind, "level": level, "verified": verified,
         "source": source, "hint": hint}
    if alias:
        d["alias"] = alias
    return (rid, d)


_RULES = dict([
    # ---- 十干克应 -------------------------------------------------------
    _R("ganying_qinglong_fanshou", "青龙返首", "吉", "auspicious_great", "conflict",
       "十干克应通行表「戊加丙: 青龙反首, 动作大吉」/《奇门遁甲预测术》",
       "贵人扶持、官运得助; 若逢门迫入墓击刑则吉事成凶"),
    _R("ganying_feiniao_diexue", "飞鸟跌穴", "吉", "auspicious_great", "conflict",
       "《奇门遁甲预测术·详解飞鸟跌穴与青龙返首格》「天盘丙火加地盘甲子戊」",
       "归巢得所、意外得利"),
    _R("ganying_baihu_changkuang", "白虎猖狂", "凶", "inauspicious_great", "conflict",
       "《烟波钓叟歌》「六辛加乙虎猖狂」/ 十干克应表",
       "人亡家败、尊长不喜、车船俱伤"),
    _R("ganying_qinglong_taozou", "青龙逃走", "凶", "inauspicious", "confirmed",
       "《烟波钓叟歌》「六乙加辛龙逃走」/ 十干克应表",
       "奴仆拐带、六畜皆伤, 财物易失"),
    _R("ganying_taibai_ruying", "太白入荧", "凶", "inauspicious_great", "confirmed",
       "《烟波钓叟歌》「六庚加丙白入荧…白入荧兮贼即来」",
       "占贼必为; 为客进利、为主破财"),
    _R("ganying_ruying_taibai", "荧入太白", "凶", "inauspicious", "confirmed",
       "《烟波钓叟歌》「六丙加庚荧入白…荧入白兮贼即去」(异名火入金乡)",
       "门户破败、盗贼耗失, 然贼去人安"),
    _R("ganying_tengshe_yaojiao", "螣蛇夭矫", "凶", "inauspicious", "confirmed",
       "《烟波钓叟歌》「六癸加丁蛇夭矫」/ 十干克应表",
       "虚惊怪异、文书官司"),
    _R("ganying_zhuque_toujiang", "朱雀投江", "凶", "inauspicious", "confirmed",
       "《烟波钓叟歌》「六丁加癸雀投江」/ 十干克应表",
       "文书口舌俱消、音信沉溺"),
    _R("ganying_dage", "大格", "凶", "inauspicious_great", "confirmed",
       "《烟波钓叟歌》「庚加癸兮为大格」/ 十干克应「大格反吟」",
       "行人不至、官司破财, 行事多阻"),
    _R("ganying_xingge", "刑格", "凶", "inauspicious", "partial",
       "《烟波钓叟歌》「加己为刑最不宜」/ 十干克应「庚加己: 官伏刑格」",
       "官司刑讼, 忌兴讼争执"),
    _R("ganying_shangge", "上格", "凶", "inauspicious", "partial",
       "《烟波钓叟歌》「加壬之时为上格」/ 十干克应「庚加壬: 太白退位」",
       "远行迷路、音信难通、诸事阻隔", alias="小格 / 太白入牢 / 太白退位"),
    _R("ganying_dabei_ruxing", "大悖入刑", "凶", "inauspicious", "partial",
       "十干克应「丙加己: 大悖入刑」(不叫悖格)",
       "谋事悖乱、动辄招刑"),
    _R("ganying_huobei_dihu", "火悖地户", "凶", "inauspicious", "partial",
       "十干克应「己加丙: 火悖地户」(不叫悖格)",
       "事多反覆、门户不宁"),
    # ---- 悖格四式(丙与值符/时干相加) ------------------------------------
    _R("beige_fu_zhifu", "伏悖(丙加值符)", "凶", "inauspicious", "partial",
       "《烟波钓叟歌》「丙为悖兮庚为格…丙加天乙为伏悖」",
       "计划悖乱、上下不通, 宜停不宜发"),
    _R("beige_fei_zhifu", "飞悖(值符加丙)", "凶", "inauspicious", "partial",
       "《烟波钓叟歌》「天乙加丙为飞悖」",
       "号令不行、事出反覆"),
    _R("beige_fu_shigan", "伏悖(丙加时干)", "凶", "inauspicious", "partial",
       "《烟波钓叟歌》悖格四式之「丙加时干为伏悖」",
       "当下之事悖逆, 强推必乱"),
    _R("beige_fei_shigan", "飞悖(时干加丙)", "凶", "inauspicious", "partial",
       "《烟波钓叟歌》悖格四式之「时干加丙为飞悖」",
       "自乱其谋, 宜缓不宜急"),
    # ---- 三奇格局 -------------------------------------------------------
    _R("sanqi_shengdian", "三奇升殿", "吉", "auspicious_great", "confirmed",
       "「乙加震(卯)日出扶桑; 丙加离宫月照端门; 丁加兑宫玉女游西, 诸事皆宜」",
       "三奇临本位, 得地得时, 诸事皆宜"),
    _R("sanqi_deshi", "三奇得使", "吉", "auspicious_great", "partial",
       "《奇门遁甲演义》「六甲之上得三奇, 三奇得使最为良」",
       "奇仪相配, 谋望有助、求人得力"),
    _R("rumu_sanqi", "三奇入墓", "凶", "inauspicious", "conflict",
       "《遁甲演义·三奇入墓》「六乙下临二宫, 六丙到六宫, 六丁下临八宫」",
       "贵人受囚、谋事受阻; 纵有奇门不可举兵"),
    # ---- 六仪击刑 -------------------------------------------------------
    _R("liuyi_jixing", "六仪击刑", "凶", "inauspicious", "conflict",
       "《奇门遁甲全集·奇门诸格》「天盘甲子, 地盘震三宫(子刑卯)」等六条",
       "力量减半、诸事受阻, 求谋徒劳"),
    # ---- 门迫 / 门制 ----------------------------------------------------
    _R("menpo", "门迫", "凶", "inauspicious", "confirmed",
       "通行口径「门克宫叫门迫」;「吉门门迫吉不就, 凶门门迫事更凶」",
       "门被宫夺力减半: 吉门吉不就, 凶门事更凶"),
    _R("menzhi", "门制", "中", "mixed", "confirmed",
       "通行口径「宫克门叫门受制」;「吉门受制事不吉, 凶门受制凶不起」",
       "吉门受制事不吉, 凶门受制凶不起", alias="门受制"),
    # ---- 三诈五假 -------------------------------------------------------
    _R("sanzha_zhenzha", "真诈", "吉", "auspicious", "conflict",
       "《三诈五假口诀》「真诈＝三吉门+太阴+三奇」",
       "利谋事密议、托人办事, 事成而人不觉"),
    _R("sanzha_zhongzha", "重诈", "吉", "auspicious", "conflict",
       "《三诈五假口诀》「重诈＝三吉门+九地+三奇」",
       "利埋伏潜藏、稳中取利"),
    _R("sanzha_xiuzha", "休诈", "吉", "auspicious", "conflict",
       "《三诈五假口诀》「休诈＝三吉门+六合+三奇」",
       "利和合、说媒、结交与调停"),
    _R("wujia_tianjia", "天假", "中", "mixed", "conflict",
       "《三诈五假口诀》「天假＝景门+九天+三奇」",
       "利上书献策、扬名请命"),
    _R("wujia_dijia", "地假", "中", "mixed", "conflict",
       "《三诈五假口诀》「地假＝杜门+九地(或太阴、六合)+丁己癸」",
       "利遁形藏拙、避祸自守"),
    _R("wujia_renjia", "人假", "中", "mixed", "conflict",
       "《三诈五假口诀》「人假＝惊门+九天(或值符、六合)+壬癸」",
       "利虚张声势、以退为进"),
    _R("wujia_shenjia", "神假", "中", "mixed", "conflict",
       "《三诈五假口诀》「神假＝伤门+九地(或值符)+丁己癸」",
       "利催讨追索、了断旧事"),
    _R("wujia_guijia", "鬼假", "中", "mixed", "conflict",
       "《三诈五假口诀》「鬼假＝死门+九地(或太阴)+丁己癸」",
       "利丧葬祭祀、了结与收尾"),
    # ---- 九遁 -----------------------------------------------------------
    _R("jiudun_tiandun", "天遁", "吉", "auspicious_great", "partial",
       "简本九遁「天遁＝丙奇+生门+太阴」(Sudo-Biao 配九天为误)",
       "利谒贵求财、上书献策"),
    _R("jiudun_didun", "地遁", "吉", "auspicious_great", "partial",
       "简本九遁「地遁＝乙奇+开门+六合(或地盘己)」",
       "利埋伏藏形、暗中行事"),
    _R("jiudun_rendun", "人遁", "吉", "auspicious_great", "partial",
       "简本九遁「人遁＝丁奇+休门+太阴」",
       "利结交婚姻、拜访请托"),
    _R("jiudun_shendun", "神遁", "吉", "auspicious_great", "partial",
       "简本九遁「神遁＝丙奇+生门+九天」(Sudo-Biao 配九地为误)",
       "利祭祀立坛、张扬声势"),
    _R("jiudun_guidun", "鬼遁", "吉", "auspicious_great", "partial",
       "简本九遁「鬼遁＝丁奇+杜门+九地」",
       "利暗访偷袭、隐秘之事"),
    _R("jiudun_fengdun", "风遁", "吉", "auspicious_great", "partial",
       "通行九遁简表「风遁＝乙奇+开休生三吉门之一+巽四宫」"
       "(《奇门遁甲统宗大全》卷之一 同; 《奇门遁甲秘笈大全》卷六 另加地盘六辛); "
       "引擎现窄化为开门",
       "利借势传播、顺风行事"),
    _R("jiudun_yundun", "云遁", "吉", "auspicious_great", "partial",
       "通行九遁简表「云遁＝天盘乙奇+开休生三吉门之一+地盘辛, 宫位不限」; "
       "《奇门遁甲秘笈大全》卷六「开休生合乙奇，下临六辛宫者，名为云遁」/ "
       "《奇门遁甲统宗大全》卷之一「休开生与乙奇合奇，地盘六辛」/ "
       "《奇门法窍》卷六「乙奇合开休生吉门，临地辛宫为云遁」三书同; "
       "全本另有「生门合天芮壬临坤」「乙开临坤」等别支, 未接入",
       "利隐匿行踪、求雨润泽"),
    _R("jiudun_longdun", "龙遁", "吉", "auspicious_great", "partial",
       "《奇门遁甲统宗大全》卷之一「休门与乙奇合坎」/《秘笈大全》卷十五「龙遁＝乙奇+休门+坎一宫」(通行简表作三吉门之一, 本引擎未接入通式); "
       "《奇门遁甲统宗大全》卷之一「休门与乙奇合坎」/ "
       "《奇门遁甲秘笈大全》卷十五「休门与乙奇临六甲于坎宫，临六癸亦是」; "
       "全本的三吉门通式与六癸别支未接入",
       "利水事渡涉、疏通阻滞"),
    _R("jiudun_hudun", "虎遁", "吉", "auspicious_great", "partial",
       "通行九遁简表「虎遁＝天盘乙奇+休门+地盘辛+艮八宫」; "
       "《奇门遁甲秘笈大全》卷六「休门、乙奇加地盘六辛于艮宫」/ "
       "《奇门遁甲统宗大全》卷之一「休门与乙奇合艮辛」/ "
       "《奇门法窍》卷六「乙奇合休门六辛临艮」三书同; "
       "全本另有「开门甲申庚临兑」「生门辛加地盘乙于艮」等别支, 未接入",
       "利守御镇宅、伏兵待机"),
    # ---- 驿马 -----------------------------------------------------------
    _R("yima", "驿马", "中", "mixed", "partial",
       "「申子辰马在寅, 寅午戌马在申, 巳酉丑马在亥, 亥卯未马在巳」(时支起时马)",
       "主动、变动、迁移、传递, 应事快"),
    # ---- 伏吟 / 反吟(全局) ----------------------------------------------
    _R("fuyin_star", "星伏吟", "凶", "inauspicious_great", "confirmed",
       "通行口径「九星落在自己的原始宫位, 称为星伏吟」",
       "伏吟主迟滞: 利主不利客、利静不利动"),
    _R("fuyin_door", "门伏吟", "凶", "inauspicious_great", "confirmed",
       "通行口径「八门落在自己的原始宫位, 称为门伏吟」",
       "门不动则事不动, 万事停滞莫强动"),
    _R("fuyin_gan", "干伏吟", "凶", "inauspicious_great", "confirmed",
       "通行口径「天盘干与地盘干重叠, 称为干伏吟」",
       "奇仪伏而不发, 宜守成不宜开新局"),
    _R("fanyin_star", "星反吟", "凶", "inauspicious_great", "confirmed",
       "通行口径: 九星落原宫之对宫(1↔9,2↔8,3↔7,4↔6)",
       "反吟主反覆迅猛: 事颠倒、去而复返"),
    _R("fanyin_door", "门反吟", "凶", "inauspicious_great", "confirmed",
       "通行口径: 八门落原宫之对宫",
       "进退两难莫轻动, 定则必改"),
    _R("fanyin_gan", "干反吟", "凶", "inauspicious_great", "confirmed",
       "通行口径: 天盘干与对宫地盘干相叠",
       "奇仪相冲, 谋事反覆、成而复败"),
    # ---- 五不遇时(时格, 全局) · 干支口径 --------------------------------
    # 歌诀《烟波钓叟歌》只给取象; 判据依《御定奇门宝鉴·释义四十四则》合论干支, 详见 _WUBUYU 上方注释。
    _R("wubuyushi", "五不遇时", "凶", "inauspicious_great", "confirmed",
       "《烟波钓叟歌》「五不遇时龙不精, 号为日月损光明, 时干来克日干上, 甲日须知时忌庚」"
       "(奇门法窍·卷一)。判据依《御定奇门宝鉴·释义四十四则》"
       "「其法以庚加午逆行, 越过戌亥, 为时之定局。次以日干甲从庚上逆数其下, 即本日五不遇时也…"
       "顺数者; 止论其干, 故名七杀。逆数者, 合论其干支, 故曰: 五不遇时」取干支口径, "
       "即《奇门法窍·卷六》十时柱表: 甲日庚午、乙日辛巳、丙日壬辰、丁日癸卯、戊日甲寅、"
       "己日乙丑、庚日丙子、辛日丁酉、壬日戊申、癸日己未时(卷七「六甲旬五不遇时」按旬另列一遍, "
       "同此十条)",
       "时干克日干、主客不合: 百事皆凶, 纵得奇门亦不宜用"),
])

# 判据表 -------------------------------------------------------------------
# 十干克应: (天盘干, 地盘干) -> rule id。全部单向, 不做 taibu 的 reverseKey 双向查表。
_GANYING = {
    ("戊", "丙"): "ganying_qinglong_fanshou",
    ("丙", "戊"): "ganying_feiniao_diexue",
    ("辛", "乙"): "ganying_baihu_changkuang",
    ("乙", "辛"): "ganying_qinglong_taozou",
    ("庚", "丙"): "ganying_taibai_ruying",
    ("丙", "庚"): "ganying_ruying_taibai",
    ("癸", "丁"): "ganying_tengshe_yaojiao",
    ("丁", "癸"): "ganying_zhuque_toujiang",
    ("庚", "癸"): "ganying_dage",
    ("庚", "己"): "ganying_xingge",
    ("庚", "壬"): "ganying_shangge",
    ("丙", "己"): "ganying_dabei_ruxing",
    ("己", "丙"): "ganying_huobei_dihu",
}

# 六仪击刑: 天盘六仪 -> (刑宫, 旬首与刑法)。, 六宫全落实宫, 中5 永不出现。
_JIXING = {
    "戊": (3, "甲子, 子刑卯"), "己": (2, "甲戌, 戌刑未"), "庚": (8, "甲申, 申刑寅"),
    "辛": (9, "甲午, 午自刑"), "壬": (4, "甲辰, 辰自刑"), "癸": (4, "甲寅, 寅刑巳"),
}
# 三奇入墓: 天盘三奇 -> (墓宫, 墓支说明)。丁在艮8(丑), 非乾6(戌)。
_RUMU = {"乙": (2, "未, 木墓"), "丙": (6, "戌, 阳火墓"), "丁": (8, "丑, 阴火墓")}
# 三奇升殿: 天盘三奇 -> (本宫, 别名)
_SHENGDIAN = {"乙": (3, "日出扶桑"), "丙": (9, "月照端门"), "丁": (7, "玉女游西")}
# 三奇得使: 天盘三奇 -> {地盘旬首之仪: 旬首}
_DESHI = {
    "乙": {"己": "甲戌", "辛": "甲午"},
    "丙": {"戊": "甲子", "庚": "甲申"},
    "丁": {"壬": "甲辰", "癸": "甲寅"},
}
# 三诈五假: rule id -> (门集合, 神集合, 干集合)
_ZHA_JIA = [
    ("sanzha_zhenzha", GOOD_DOORS, {"太阴"}, set(SANQI)),
    ("sanzha_zhongzha", GOOD_DOORS, {"九地"}, set(SANQI)),
    ("sanzha_xiuzha", GOOD_DOORS, {"六合"}, set(SANQI)),
    ("wujia_tianjia", {"景门"}, {"九天"}, set(SANQI)),
    ("wujia_dijia", {"杜门"}, {"九地", "太阴", "六合"}, {"丁", "己", "癸"}),
    ("wujia_renjia", {"惊门"}, {"九天", "值符", "六合"}, {"壬", "癸"}),
    ("wujia_shenjia", {"伤门"}, {"九地", "值符"}, {"丁", "己", "癸"}),
    ("wujia_guijia", {"死门"}, {"九地", "太阴"}, {"丁", "己", "癸"}),
]
# 九遁: rule id -> (天盘奇, 门(单门 str 或门集合), 神集合 or None, 地盘干集合 or None, 宫 or None)
#
# 云遁 / 虎遁判据:
#   云遁 —— 三部书口径一致「开休生三吉门 + 天盘乙奇 + 下临地盘六辛」, 宫位不限:
#     《奇门遁甲秘笈大全》卷六「开休生合乙奇，下临六辛宫者，名为"云遁"」
#     《奇门遁甲统宗大全》卷之一「云遁　休开生与乙奇合奇，地盘六辛」
#     《奇门法窍》卷六「乙奇合开休生吉门，临地辛宫为云遁」
#     《奇门法窍》卷七 / 卷八的实盘案例里云遁落在九宫都出现过, 故不写死某一宫。
#   虎遁 —— 通行简表与三部书主支一致「天盘乙奇 + 休门 + 地盘辛 + 艮八宫」:
#     《奇门遁甲秘笈大全》卷六「休门、乙奇加地盘六辛于艮宫」
#     《奇门遁甲统宗大全》卷之一「虎遁　休门与乙奇合艮辛」
#     《奇门法窍》卷六「乙奇合休门六辛临艮」
#   虎遁是云遁的真子集(艮8 + 休门 + 地盘辛), 两条同宫并出属古法常态, 不是 bug
#     (《奇门法窍》卷八实盘案例即有云遁虎遁同落艮宫)。
_JIUDUN = [
    ("jiudun_tiandun", "丙", "生门", {"太阴"}, None, None),
    ("jiudun_shendun", "丙", "生门", {"九天"}, None, None),
    ("jiudun_didun", "乙", "开门", {"六合"}, {"己"}, None),
    ("jiudun_rendun", "丁", "休门", {"太阴"}, None, None),
    ("jiudun_guidun", "丁", "杜门", {"九地"}, None, None),
    ("jiudun_fengdun", "乙", "开门", None, None, 4),
    ("jiudun_yundun", "乙", GOOD_DOORS, None, {"辛"}, None),
    ("jiudun_longdun", "乙", "休门", None, None, 1),
    ("jiudun_hudun", "乙", "休门", None, {"辛"}, 8),
]
# 驿马: 时支 -> (马支, 马宫)
_YIMA_TRIAD = {
    ("申", "子", "辰"): ("寅", 8),
    ("寅", "午", "戌"): ("申", 2),
    ("巳", "酉", "丑"): ("亥", 6),
    ("亥", "卯", "未"): ("巳", 4),
}
_YIMA = {}
for _triad, _pair in _YIMA_TRIAD.items():
    for _z in _triad:
        _YIMA[_z] = _pair

# 五不遇时: 日干 -> 该日唯一的忌用时柱(干见 _WUBUYU, 支见 _WUBUYU_ZHI)。**判据合论干支**。
#
# 定谳出处 —— 《御定奇门宝鉴·释义四十四则》【释五不遇时】:
#   「五不遇时者; 时干克日干也…其法以庚加午逆行, 越过戌亥, 为时之定局。次以日干甲从庚上
#     逆数其下, 即本日五不遇时也。凡十干环列, 顺数七干, 逆数五干, 皆克第一干。
#     顺数者; 止论其干, 故名七杀。逆数者, 合论其干支, 故曰: 五不遇时。」
#   —— 只论干 = 七杀, 合论干支 = 五不遇时。「时干克日干且同阴阳」只是七杀的定义。
#
# 十时柱表(《奇门法窍》卷六按日干列、卷七「六甲旬五不遇时」按旬列, 两套完全一致):
#   甲日庚午、乙日辛巳、丙日壬辰、丁日癸卯、戊日甲寅、己日乙丑、庚日丙子、辛日丁酉、壬日戊申、癸日己未。
# 一天里七杀时干会出现两次(己日乙丑 01-03 与乙亥 21-23; 庚日丙子 23-01 与丙戌 19-21),
#   第二次时支不合, 属「七杀」而非「五不遇时」, 本引擎不判凶。
GAN_WX = {"甲": "木", "乙": "木", "丙": "火", "丁": "火", "戊": "土",
          "己": "土", "庚": "金", "辛": "金", "壬": "水", "癸": "水"}
GAN_YANG = {"甲": True, "乙": False, "丙": True, "丁": False, "戊": True,
            "己": False, "庚": True, "辛": False, "壬": True, "癸": False}
# GAN_WX / GAN_YANG 仅供单测对账(复算「时干克日干且同阴阳」, 验证 _WUBUYU 的干这一半确是日干之七杀)。
#   引擎侧判定一律走 _WUBUYU / _WUBUYU_ZHI 查表。
_WUBUYU = {"甲": "庚", "乙": "辛", "丙": "壬", "丁": "癸", "戊": "甲",
           "己": "乙", "庚": "丙", "辛": "丁", "壬": "戊", "癸": "己"}
# 十时柱的时支, 与 _WUBUYU 同一张表的另一半, **参与判定**(见 is_wubuyushi)。
_WUBUYU_ZHI = {"甲": "午", "乙": "巳", "丙": "辰", "丁": "卯", "戊": "寅",
               "己": "丑", "庚": "子", "辛": "酉", "壬": "申", "癸": "未"}

# 全局凶格: 只走 factors 强提示, **不加减分**
ADVISORY_GLOBAL = {"fuyin_star", "fuyin_door", "fuyin_gan",
                   "fanyin_star", "fanyin_door", "fanyin_gan", "liuyi_jixing",
                   # 五不遇时的惩罚由 qimen.day_hours() 在基础分上直接压地板,
                   # 不走 hour_overlay 的格局加减分, 否则重复扣分。
                   "wubuyushi"}
# 已计入 day_hours() 基础评级的项(门迫 -1), 再打分即重复扣分
BASE_COUNTED = {"menpo", "menzhi"}
NO_SCORE = ADVISORY_GLOBAL | BASE_COUNTED

STRONG_FACTOR = {
    "fuyin_star": "星伏吟·宜静守", "fuyin_door": "门伏吟·宜静守", "fuyin_gan": "干伏吟·宜静守",
    "fanyin_star": "星反吟·多反覆", "fanyin_door": "门反吟·多反覆", "fanyin_gan": "干反吟·多反覆",
    "liuyi_jixing": "六仪击刑·力减事阻",
    "wubuyushi": "五不遇时·不宜用事",
}

# unverified / 已定案不接入的条目, 留档防止日后被重新抄进来
_NOT_IMPLEMENTED = {
    "ganying_shejiao_ruhuo": "蛇矫入火(癸+丙, taibu 独有) — unverified, 两源查无此名",
    "ganying_shanyue_xianghui": "星月相会(丙+丁, taibu 独有) — unverified",
    "ganying_qiyi_xiangzuo": "奇仪相佐(乙+丙 / 乙+丁, taibu 独有) — unverified",
    "ganying_xiongshe_ruxing": "凶蛇入刑(辛+壬, taibu 独有) — unverified",
    "ganying_yunvshoumen": "玉女守门 — unverified, 两派同名异义; 丁加癸一律按朱雀投江处理",
    "ganying_zhifu_feigong": "值符飞宫 / 戊飞宫 — unverified, 我方中五寄坤下判据恒真或恒假",
    "sanqi_ru_zhonggong": "三奇入中宫 — unverified, 我方 palaces 无 key 5, 字面条件永不命中",
    "jiudun_wudun_taibu": "五遁(taibu 两干式) — conflict, 古籍无据, 一律走九遁修正版",
    "rumu_guangyi": "广义十干入墓(taibu) — conflict, 三奇部分改用 rumu_sanqi, 余六干无外部支持",
    "ganying_riyu_fusang": "日出扶桑(taibu 乙+戊版) — conflict, 已并入三奇升殿乙条别名",
}


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------
def _pname(p):
    return "%s%s宫" % (PALACE_NAME.get(p, "?"), p)


def _star_name(raw):
    """pan() 在中五寄宫时会写成 '天禽/天芮', 取真正的星名。"""
    s = str(raw or "")
    return s.split("/")[-1] if s else ""


def _mk(rid, palace, basis, **extra):
    r = _RULES[rid]
    out = {"id": rid, "name": r["name"], "kind": r["kind"], "level": r["level"],
           "palace": palace, "basis": basis, "source": r["source"],
           "verified": r["verified"], "hint": r["hint"]}
    if r.get("alias"):
        out["alias"] = r["alias"]
    out.update(extra)
    return out


# ---------------------------------------------------------------------------
# 单条规则
# ---------------------------------------------------------------------------
def geju_ganying(tian, earth, palace=None):
    """单宫十干克应查表(只收 confirmed / partial / conflict 已定案的 13 组), 返回命中列表。"""
    rid = _GANYING.get((tian, earth))
    if not rid:
        return []
    return [_mk(rid, palace, "天盘%s加地盘%s" % (tian, earth))]


def geju_liuyi_jixing(tian, palace):
    """六仪击刑, 用 tian(天盘六仪)落宫判; 表 = {戊3,己2,庚8,辛9,壬4,癸4} 定案)。"""
    hit = _JIXING.get(tian)
    if not hit or hit[0] != palace:
        return None
    return _mk("liuyi_jixing", palace, "天盘%s(%s)落%s" % (tian, hit[1], _pname(palace)))


def geju_rumu(tian, palace):
    """三奇入墓, {乙:2, 丙:6, 丁:8} —— 丁在艮8(丑), 非乾6(戌)。"""
    hit = _RUMU.get(tian)
    if not hit or hit[0] != palace:
        return None
    return _mk("rumu_sanqi", palace, "天盘%s奇入%s(%s)" % (tian, _pname(palace), hit[1]))


def geju_sanqi_shengdian(tian, palace):
    """三奇升殿 {乙:3(日出扶桑), 丙:9(月照端门), 丁:7(玉女游西)}, 取天盘三奇临本宫。"""
    hit = _SHENGDIAN.get(tian)
    if not hit or hit[0] != palace:
        return None
    return _mk("sanqi_shengdian", palace,
               "天盘%s奇临%s" % (tian, _pname(palace)), alias=hit[1])


def geju_sanqi_deshi(tian, earth, palace=None, xunshou_yi=None):
    """三奇得使: 乙↔己(甲戌)/辛(甲午), 丙↔戊(甲子)/庚(甲申), 丁↔壬(甲辰)/癸(甲寅)。

    通行口径还要求地盘那个六仪**必须是当前时辰所在旬的旬首之仪**, 不是任意己/辛。
    传了 xunshou_yi(pan() 的 'xunshou_yi')就校旬首; 没传(手工构造的 palaces)按宽松
    口径出格, 但 basis 里注明「未校旬首」、并置 xunshou_checked=False。
    """
    xun = (_DESHI.get(tian) or {}).get(earth)
    if not xun:
        return None
    if xunshou_yi:
        if earth != xunshou_yi:
            return None
        return _mk("sanqi_deshi", palace,
                   "天盘%s奇加地盘%s(本旬旬首%s之仪)" % (tian, earth, xun), xunshou_checked=True)
    return _mk("sanqi_deshi", palace,
               "天盘%s奇加地盘%s(%s之仪, 未校旬首)" % (tian, earth, xun), xunshou_checked=False)


def geju_sanzha_wujia(tian, door, god, palace=None):
    """三诈五假八条, 按通行表(真诈太阴 / 重诈九地 / 休诈六合)。"""
    out = []
    for rid, doors, gods, gans in _ZHA_JIA:
        if door in doors and god in gods and tian in gans:
            out.append(_mk(rid, palace, "%s+%s+天盘%s" % (door, god, tian)))
    return out


def geju_jiudun(tian, door, god, earth=None, palace=None):
    """九遁: 参考 Sudo-Biao 的结构, 天遁改配太阴 / 神遁改配九天; taibu 的两干式不接入。

    云遁 = 天盘乙 + 开休生三吉门之一 + 地盘辛(宫位不限, 必查地盘干);
    虎遁 = 天盘乙 + 休门 + 地盘辛 + 艮八宫。出处见 _JIUDUN 上方注释。
    need_door 允许是单门字符串或门集合。
    """
    out = []
    for rid, need_tian, need_door, gods, earths, need_p in _JIUDUN:
        if tian != need_tian:
            continue
        if isinstance(need_door, str):
            if door != need_door:
                continue
        elif door not in need_door:
            continue
        if need_p is not None and palace != need_p:
            continue
        if gods is not None or earths is not None:
            ok = (gods is not None and god in gods) or (earths is not None and earth in earths)
            if not ok:
                continue
        bits = ["天盘" + str(need_tian) + "奇", str(door)]
        if gods is not None and god in gods:
            bits.append(str(god))
        elif earths is not None and earth in earths:
            bits.append("地盘" + str(earth))
        if need_p is not None:
            bits.append(_pname(need_p))
        out.append(_mk(rid, palace, "+".join(bits)))
    return out


def geju_fuyin_fanyin(pan_result):
    """星/门/干 三类伏吟 + 三类反吟, 分别判定不合并。
    返回 {"star_fuyin","door_fuyin","gan_fuyin","fanyin": {"star","door","gan"}}"""
    palaces = (pan_result or {}).get("palaces") or {}
    keys = [p for p in palaces if p in OPPOSITE]
    if not keys:
        return {"star_fuyin": False, "door_fuyin": False, "gan_fuyin": False,
                "fanyin": {"star": False, "door": False, "gan": False}}
    # 空字段一律不算命中(否则一张空盘会被判成全盘伏吟)
    star_fu = all(_star_name(palaces[p].get("star")) == STAR_HOME.get(p) for p in keys)
    door_fu = all(palaces[p].get("door") and palaces[p].get("door") == DOOR_HOME.get(p) for p in keys)
    gan_fu = all(palaces[p].get("tian") and palaces[p].get("tian") == palaces[p].get("earth") for p in keys)
    star_fan = all(_star_name(palaces[p].get("star")) == STAR_HOME.get(OPPOSITE[p]) for p in keys)
    door_fan = all(palaces[p].get("door") and palaces[p].get("door") == DOOR_HOME.get(OPPOSITE[p]) for p in keys)
    gan_fan = all(palaces[p].get("tian") and palaces[p].get("tian") == (palaces.get(OPPOSITE[p]) or {}).get("earth")
                  for p in keys)
    return {"star_fuyin": star_fu, "door_fuyin": door_fu, "gan_fuyin": gan_fu,
            "fanyin": {"star": star_fan, "door": door_fan, "gan": gan_fan}}


def geju_yima(hour_zhi, day_zhi=None):
    """驿马, 主用时支起时马(申子辰→寅/艮8, 寅午戌→申/坤2, 巳酉丑→亥/乾6, 亥卯未→巳/巽4)。
    day_zhi 给了就附带日马作补充, 输出注明取用支。"""
    hit = _YIMA.get(hour_zhi)
    if not hit:
        return None
    ma, palace = hit
    out = _mk("yima", palace, "时支%s三合冲位在%s, 马落%s" % (hour_zhi, ma, _pname(palace)),
              ma_zhi=ma, taken_from="时支", taken_zhi=hour_zhi)
    day_hit = _YIMA.get(day_zhi) if day_zhi else None
    if day_hit:
        out["day_ma"] = {"palace": day_hit[1], "ma_zhi": day_hit[0],
                         "taken_from": "日支", "taken_zhi": day_zhi}
    return out


def classify_menpo(door, palace):
    """"menpo"(门克宫, 凶) / "menzhi"(宫克门, mixed) / None。方向以 通行口径为准:
    门克宫叫门迫, 宫克门叫门受制。qimen.py 现有的门迫判定与此同向, 不改。"""
    de, pe = DOOR_ELEM.get(door), PALACE_ELEM.get(palace)
    if not de or not pe:
        return None
    if KE.get(de) == pe:
        return "menpo"
    if KE.get(pe) == de:
        return "menzhi"
    return None


def is_wubuyushi(day_gan, hour_gan, hour_zhi=None):
    """五不遇时布尔判据(给 qimen.day_hours() 压分用, 不构造格局 dict)。

    判据 = **干支全同**古籍十时柱表: `_WUBUYU[day_gan] == hour_gan` 且
    `_WUBUYU_ZHI[day_gan] == hour_zhi`(甲庚午/乙辛巳/丙壬辰/丁癸卯/戊甲寅/己乙丑/
    庚丙子/辛丁酉/壬戊申/癸己未)。

    口径依《御定奇门宝鉴·释义四十四则》「顺数者; 止论其干, 故名七杀。
    逆数者, 合论其干支, 故曰: 五不遇时」—— 只论干那一读法书里叫七杀, 不叫五不遇时。
    因此己日乙亥时、庚日丙戌时(七杀干的当日第二次出现, 时支不合表)**不判**五不遇时。

    hour_zhi 为可选参数只为不破坏老签名; 干支口径下它是判据的一半, 缺了就无法成立,
    故不传(或传空)一律返回 False —— 宁可漏判, 不替古籍加戏。
    """
    if not day_gan or not hour_gan or not hour_zhi:
        return False
    return (_WUBUYU.get(day_gan) == hour_gan
            and _WUBUYU_ZHI.get(day_gan) == hour_zhi)


def geju_wubuyushi(day_gan, hour_gan, hour_zhi=None):
    """五不遇时(时格, 全局级)。

    《烟波钓叟歌》「五不遇时龙不精, 号为日月损光明, 时干来克日干上, 甲日须知时忌庚」
    (奇门法窍·卷一);
    《奇门法窍·卷六》「时干克日干, 甲日庚午时、乙日辛巳时…癸日己未时,
    此时出行, 主损折不利, 百事皆凶, 用兵尤忌, 虽有门奇, 切不可用」。
    它按日干/时柱判, 与宫位无关, 所以进 global 而不是 by_palace。

    判据合论干支(见 is_wubuyushi), 故凡命中必在古籍十时柱表内, basis 不再分流。
    """
    if not is_wubuyushi(day_gan, hour_gan, hour_zhi):
        return None
    return _mk("wubuyushi", None,
               "日干%s、时柱%s%s: 合《奇门法窍·卷六》十时柱表「%s日%s%s时」"
               "(时干克日干且同阴阳, 干支俱合)"
               % (day_gan, hour_gan, hour_zhi, day_gan, hour_gan, hour_zhi))


def geju_beige(pan_result):
    """悖格四式: 丙与值符 / 时干相加。
    伏悖 = 丙加(值符/时干); 飞悖 = (值符/时干)加丙。需 pan() 暴露 zhifu_palace 与 hour_gz。"""
    out = []
    palaces = (pan_result or {}).get("palaces") or {}
    zfp = (pan_result or {}).get("zhifu_palace")
    v = palaces.get(zfp) or {}
    if v:
        if v.get("tian") == "丙":
            out.append(_mk("beige_fu_zhifu", zfp, "值符落%s, 天盘丙加其上" % _pname(zfp)))
        if v.get("earth") == "丙":
            out.append(_mk("beige_fei_zhifu", zfp, "值符加于地盘丙(%s)" % _pname(zfp)))
    hour_gz = str((pan_result or {}).get("hour_gz") or "")
    sg = hour_gz[0] if hour_gz else ""
    # 甲不上盘(遁于六仪), 丙加丙自撞无义, 两者都跳过
    if sg and sg not in ("甲", "丙"):
        for p in sorted(palaces):
            pv = palaces[p] or {}
            if pv.get("tian") == "丙" and pv.get("earth") == sg:
                out.append(_mk("beige_fu_shigan", p, "天盘丙加地盘时干%s" % sg))
            if pv.get("tian") == sg and pv.get("earth") == "丙":
                out.append(_mk("beige_fei_shigan", p, "天盘时干%s加地盘丙" % sg))
    return out


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------
def formations(pan_dict, hour_zhi=None):
    """奇门格局总判定。输入 qimen.pan() 的返回 dict, 只读。
    返回 {"by_palace": {宫序: [格局...]}, "global": [格局...]}。"""
    palaces = (pan_dict or {}).get("palaces") or {}
    xunshou_yi = (pan_dict or {}).get("xunshou_yi")
    by_palace = {}

    def _add(p, item):
        if item:
            by_palace.setdefault(p, []).append(item)

    for p in sorted(palaces):
        v = palaces[p] or {}
        tian, earth, door, god = v.get("tian"), v.get("earth"), v.get("door"), v.get("god")
        for item in geju_ganying(tian, earth, p):
            _add(p, item)
        _add(p, geju_sanqi_shengdian(tian, p))
        _add(p, geju_sanqi_deshi(tian, earth, p, xunshou_yi))
        _add(p, geju_rumu(tian, p))
        _add(p, geju_liuyi_jixing(tian, p))
        for item in geju_sanzha_wujia(tian, door, god, p):
            _add(p, item)
        for item in geju_jiudun(tian, door, god, earth, p):
            _add(p, item)
        mp = classify_menpo(door, p)
        if mp:
            _add(p, _mk(mp, p, "%s(%s)与%s(%s)相克" % (
                door, DOOR_ELEM.get(door), _pname(p), PALACE_ELEM.get(p))))

    for item in geju_beige(pan_dict):
        _add(item["palace"], item)

    hz = hour_zhi or (pan_dict or {}).get("hour_zhi")
    if not hz:
        gz = str((pan_dict or {}).get("hour_gz") or "")
        hz = gz[1] if len(gz) > 1 else None
    ym = geju_yima(hz, (str((pan_dict or {}).get("day_gz") or "") + "  ")[1].strip() or None)
    if ym:
        _add(ym["palace"], ym)

    glob = []
    fy = geju_fuyin_fanyin(pan_dict)
    for key, rid in (("star_fuyin", "fuyin_star"), ("door_fuyin", "fuyin_door"), ("gan_fuyin", "fuyin_gan")):
        if fy.get(key):
            glob.append(_mk(rid, None, "全盘%s" % _RULES[rid]["name"]))
    for key, rid in (("star", "fanyin_star"), ("door", "fanyin_door"), ("gan", "fanyin_gan")):
        if (fy.get("fanyin") or {}).get(key):
            glob.append(_mk(rid, None, "全盘%s" % _RULES[rid]["name"]))
    # 五不遇时: 按日干 + 时柱(干支)判的时格, 与宫位无关, 走 global。
    # ⚠ 时支是判据的一半(合论干支, 见 is_wubuyushi), 必须把 hour_gz 的第二个字传进去。
    _hgz = str((pan_dict or {}).get("hour_gz") or "")
    wby = geju_wubuyushi(str((pan_dict or {}).get("day_gz") or "")[:1],
                         _hgz[:1], _hgz[1:2])
    if wby:
        glob.append(wby)
    return {"by_palace": by_palace, "global": glob}


def compute_all(pan_result):
    """{"by_palace", "global", "summary"} —— summary 给叙事层的一句话概览。"""
    res = formations(pan_result)
    ji, xiong = [], []
    for items in res["by_palace"].values():
        for f in items:
            (ji if f["kind"] == "吉" else xiong if f["kind"] == "凶" else []).append(f["name"])
    for f in res["global"]:
        xiong.append(f["name"])
    bits = []
    if ji:
        bits.append("吉格: " + "、".join(sorted(set(ji))))
    if xiong:
        bits.append("凶格: " + "、".join(sorted(set(xiong))))
    return {"by_palace": res["by_palace"], "global": res["global"],
            "summary": "; ".join(bits) or "本局无显著格局"}


def hour_overlay(forms, zhishi_palace, zhifu_palace):
    """把格局叠加到 day_hours() 的时段打分上。

    量级 auspicious_great=+3 / auspicious=+2 / mixed=0 / inauspicious=-2 / inauspicious_great=-3,
    折算系数 SCORE_SCALE=0.5, 总修正封顶 ±SCORE_CAP=1.5。
    叠加范围只限值使宫 + 值符宫;「值使第一、值符第二」→ 值符宫再乘 ZHIFU_DISCOUNT。
    全局凶格(伏吟/反吟/六仪击刑)与门迫/门制不加减分, 只出 factors 文字。

    ⚠ SCORE_SCALE / ZHIFU_DISCOUNT / SCORE_CAP 三个系数**无古籍依据, 是工程参数**,
      作用是不让格局盖过 day_hours() 里门 ±2 的主导权重, 别当命理口径读。

    返回 (delta, factors, picked)。
    """
    by_palace = (forms or {}).get("by_palace") or {}
    glob = (forms or {}).get("global") or []
    delta, picked, seen_palace = 0.0, [], set()
    for pal, role, weight in ((zhishi_palace, "值使", 1.0), (zhifu_palace, "值符", ZHIFU_DISCOUNT)):
        if pal is None or pal in seen_palace:
            continue
        seen_palace.add(pal)
        for f in by_palace.get(pal, []):
            picked.append({"id": f["id"], "name": f["name"], "kind": f["kind"], "level": f["level"],
                           "palace": pal, "role": role, "hint": f["hint"]})
            if f["id"] in NO_SCORE or f.get("advisory"):
                continue
            delta += LEVEL_SCORE.get(f["level"], 0) * SCORE_SCALE * weight
    for f in glob:
        picked.append({"id": f["id"], "name": f["name"], "kind": f["kind"], "level": f["level"],
                       "palace": None, "role": "全局", "hint": f["hint"]})
    delta = max(-SCORE_CAP, min(SCORE_CAP, round(delta, 2)))
    factors = []
    for item in picked:
        text = STRONG_FACTOR.get(item["id"]) or item["name"]
        if text not in factors:
            factors.append(text)
    return delta, factors, picked
