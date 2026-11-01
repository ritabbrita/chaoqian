"""问事合同(问题类型 / 期限 / 完成标准)与解卦文案的确定性护栏; 无 I/O, 不读命盘。"""
import copy
import re
from datetime import date, datetime, timedelta

CAST_VERSION = "chaoqian-cast-0.1"
CONTRACT_VERSION = "chaoqian-event-0.1"
HORIZONS = (7, 30, 90, 180, 365)


# 没给完成标准时按问题类别补一条默认标准(工作 / 学习 / 出行 / 健康 / 财务 / 审批 / 签约)。
_DEFAULT_CRITERIA = (
    (r"入职|录用|面试|升职|转正|交付|项目", "以正式通知或实际交付为准；口头意向、面谈印象只记进展。"),
    (r"录取|考试|通过|证书|毕业|成绩", "以正式成绩或录取结果为准；估分、传言只记进展。"),
    (r"出发|航班|行程|出行|旅行|搬家", "以按计划实际成行为准；改期、延误另记。"),
    (r"检查|复查|康复|体检|治疗|身体", "以医生或正式报告结论为准；本工具不提供任何医疗判断。"),
    (r"到账|收款|回款|付款|报销", "所问款项实际到账才算完成；承诺或口头准信只记进展。"),
    (r"获批|批准|审批|批复", "所问事项取得正式批准才算完成；受理、补件或口头反馈只记进展。"),
    (r"签约|签合同|签署", "完成约定签署才算完成；意向或商谈只记进展。"),
)


def build_event_contract(question, category, horizon, dt, context=None):
    context = context or {}
    question = str(question or "").strip()
    if not question or len(question) > 240:
        raise ValueError("请用 1–240 字写清要问的事")
    if isinstance(horizon, bool) or horizon not in HORIZONS:
        raise ValueError("请选择一周、一月、三个月、半年或一年")
    background = str(context.get("background") or "").strip()
    criterion = str(context.get("criterion") or "").strip()
    if len(background) > 1200 or len(criterion) > 240:
        raise ValueError("补充情况最多1200字，完成标准最多240字")
    displayed_question = question
    inherited = context.get("inherited_event_contract") or {}
    if not isinstance(inherited, dict):
        inherited = {}
    inherits_target = not criterion and bool(inherited.get("target_event"))
    if inherits_target:
        question = str(inherited.get("question") or inherited["target_event"])
        criterion = str(inherited.get("criterion") or "")
    elif not criterion and context.get("event_question"):
        question = str(context["event_question"])
    if re.search(r"最大|最多|最高|最低|最小|哪一?笔|比较|相比|比.{1,30}(?:多|少|高|低|好|差|强|弱|划算|赚钱|合适)", question):
        event_type = "comparison"
    elif re.search(r"选哪|选谁|哪个更|哪种更|还是|二选一|三选一", question):
        event_type = "choice"
    elif re.search(r"何时|什么时候|哪天|几时|多久|哪个月", question):
        event_type = "timing"
    elif re.search(r"走势|趋势|运势|发展如何|阶段|走向", question):
        event_type = "trend"
    else:
        event_type = "occurrence"
    adverse = r"拒绝|落榜|挂科|失业|解雇|延误|取消|复发|亏损|拖欠|违约|失败|倒闭|被骗|损失|事故"
    negative = bool(re.search(r"不会|不能|不成|没通过|无法|黄了|没法|不可能|" + adverse, question))
    adverse_target = bool(re.search(adverse, criterion or question)) or bool(re.search(r"未通过|没通过|未收到|没收到|不会|不能|不成|无法|不可能", criterion))
    if inherits_target:
        if inherited.get("event_type") in ("comparison", "choice", "timing", "trend", "occurrence"):
            event_type = inherited["event_type"]
        negative = negative or bool(inherited.get("negative_question"))
        adverse_target = adverse_target or bool(inherited.get("adverse_target"))
    missing = []
    if event_type == "comparison":
        missing.append("这是比较问题；需要明确候选和比较标准，不能把普通进展当成“最大／最好”。")
    elif event_type == "choice":
        missing.append("这是选择问题；请在补充情况中列出选项和你最在意的条件。")
    elif event_type == "trend":
        missing.append("趋势按阶段观察；若要核对是否断准，可补充一件具体事件与完成标准。")
    if (negative and not criterion) or adverse_target:
        missing.append("问题含否定或失败表述；补充“怎样算办成”后，再按同一标准记录结果。")
    if not background:
        missing.append("尚未提供这件事的现实进度；解读不会假定任何未提供的进展（如已报名、已签约、已获批）。")
    target = inherited["target_event"] if inherits_target else (criterion or question)
    # Comparative/superlative questions require a comparison model, not a
    # relabelled yes/no event. Preserve their uncertainty even with extra prose.
    # A favourable selected-line strength cannot be called 'yes' for rejection,
    # losses or other adverse events. Such targets need a separate validated
    # polarity model; nonempty free text alone cannot make that mapping valid.
    verifiable = event_type in ("occurrence", "timing") and not adverse_target and (not negative or bool(criterion))
    if inherits_target and inherited.get("verifiable") is False:
        verifiable = False
    if not criterion:
        criterion = next((text for pattern, text in _DEFAULT_CRITERIA if re.search(pattern, question)),
                         "以原问题所指事件实际完成为准；进展、消息和最终完成分别记录。")
    start = dt.date().isoformat()
    deadline = (dt.date() + timedelta(days=horizon)).isoformat()
    return {
        "version": CONTRACT_VERSION, "event_type": event_type,
        "question": question, "asked_now": displayed_question, "target_event": target, "criterion": criterion,
        "background": background, "category": category, "horizon": horizon,
        "start": start, "deadline": deadline, "verifiable": verifiable,
        "missing": missing, "criterion_source": "inherited" if inherits_target else ("user" if context.get("criterion") else "question"),
        "negative_question": negative or adverse_target, "adverse_target": adverse_target,
    }


def freeze_prediction(contract, ly, timeline):
    label = ly.get("strength_label")
    direction = {"强": "yes", "弱": "no"}.get(label, "undetermined")
    if not contract["verifiable"]:
        direction = "undetermined"
    action = (ly.get("ushen") or {}).get("action") or {}
    # 只有「待时」(waiting) 算条件未落实; 「作用未定」(休囚无伤) 与「受制」已由势能分数承担, 不把结论锁成
    # undetermined (依据见 liuyao 模块 ACTION_WEIGHT 注释: 增删卜易未把「动而休囚无伤」列为不能生)。
    unresolved = action and (action.get("status") == "waiting" or any(
        (item.get("action") or {}).get("status") == "waiting"
        for item in ly.get("influences", [])))
    if unresolved:
        direction = "undetermined"
    candidates = timeline.get("primary_candidates") or []
    # One pre-declared main observation window; later feedback cannot pick the
    # nearest candidate retrospectively to award a hit.
    primary = next((x for x in candidates if x.get("kind") != "unfavorable"), None)
    window = {"start": primary["date"], "end": primary["date"], "role": "observation"} if primary else None
    return {
        "version": CAST_VERSION, "direction": direction,
        "engine_rule_version": ly.get("rule_version"), "rule_tendency": label,
        "decision_policy": "rule-conditions" if action else "strength-only",
        "direction_reason": "target_not_verifiable" if not contract["verifiable"] else (
            "conditions_unresolved" if unresolved else "rule_tendency_only"),
        "conditions_resolved": not bool(unresolved) if action else None,
        "target_event": contract["target_event"], "criterion": contract["criterion"],
        "start": contract["start"], "deadline": contract["deadline"],
        "primary_window": window, "verifiable": contract["verifiable"],
        "basis": "传统规则势能形成的事前倾向，尚未证明现实预测效果；观察日不等于完成日。",
        "baseline": {"model_id": "unconditional_0.5", "probability": 0.5,
                     "note": "固定参照，仅用于后台对照；传统势能不转换为成功概率。"},
    }


def contract_fallback(contract, ly, timeline, original):
    out = copy.deepcopy(original)
    label = ly.get("strength_label", "平")
    horizon = contract["horizon"]
    if contract["event_type"] == "comparison":
        out["result"] = "%d天的阶段线索已展开，最大／最好仍需候选比较" % horizon
        out["advice"] = "先列出要比较的几项和衡量标准，再把每项目前的进度补进来。"
    elif contract["event_type"] == "choice":
        out["result"] = "%d天的阶段线索已展开，选择要结合具体选项" % horizon
        out["advice"] = "把候选选项与最在意的一条条件写清，再逐项看。"
    elif contract["negative_question"] and not contract["verifiable"]:
        out["result"] = "%d天内原卦势%s，先明确怎样算办成" % (horizon, label)
    else:
        out["result"] = "%d天内%s" % (horizon, {"强": "倾向有利，仍看条件能否落实", "平": "条件尚未明朗，分阶段观察", "弱": "阻力偏多，完成仍需转机"}[label])
        if ly.get("action_version") and freeze_prediction(contract, ly, timeline)["direction_reason"] == "conditions_unresolved":
            out["result"] = "%d天的规则势能为%s，作用条件尚未落实，成败仍需核对实际进度。" % (horizon, label)
    stages = timeline.get("stages") or []
    if stages:
        out["timing"] = "已覆盖%s至%s，共%d个阶段；下面日期是条件观察点，不是保证完成日。" % (
            contract["start"], contract["deadline"], len(stages))
    else:
        out["timing"] = "本次期限到%s；尚无清晰观察窗口。" % contract["deadline"]
    if not contract["background"] and contract["event_type"] not in ("comparison", "choice"):
        out["advice"] = "先核对这件事目前卡在哪一步；有新进展就记下来，按原完成标准继续跟踪。"
    return out


_PROMISE = re.compile(r"百分之百|百分百|100\s*[%％]|(?:成功率|命中率|概率)\s*(?:为|是|达|约)?\s*\d|(?:一定|必定|肯定|保证|必然|准会|绝对会).{0,8}(?:成功|通过|录取|康复|到账|完成|获批|发生|成行)|(?:稳稳|稳了|稳拿|包成)")
# 没有输入依据的「现实细节」: 第三方已经怎样了 / 指名某个具体事物。只认整段谓语, 条件句(如果…)不算。
_FACT = re.compile(r"(?:对方|老师|学校|医生|医院|公司|领导|单位|机构|主办方|审批人|他|她).{0,14}(?:已经|已|正在|准备好|答应|承诺|决定|愿意)|(?:那份通知|那份合同|那份报告|那次检查|那张票|那个名额|那笔款|合同已经|报告已经)")
_COND = re.compile(r"如果|假如|假设|若|倘若|是否|先确认|先核对|例如|比如")
_ABS_DATE = re.compile(r"(?<!\d)(\d{4})[-年/.](\d{1,2})[-月/.](\d{1,2})(?:日|号)?")
_SHORT_DATE = re.compile(r"(?<![\d年\-/])(\d{1,2})月(\d{1,2})(?:日|号)")


def guard_contract_text(text, contract, timeline, fallback):
    """Enforce dates, degree of certainty and specific unsupported fact patterns.

    This is a deterministic guard, not a claim to prove arbitrary prose true.
    The prompt also separates supplied facts from hypotheses and limits outputs.
    """
    corpus = contract["question"] + "\n" + contract["background"] + "\n" + contract["criterion"]
    allowed = {contract["start"], contract["deadline"]}
    for stage in timeline.get("stages") or []:
        allowed.update(x for x in (stage.get("start"), stage.get("end")) if x)
        allowed.update(x["date"] for x in stage.get("candidates") or [] if x.get("date"))
    allowed.update(x["date"] for x in timeline.get("primary_candidates") or [] if x.get("date"))
    allowed_short = {(date.fromisoformat(d).month, date.fromisoformat(d).day) for d in allowed}
    allowed_years = {date.fromisoformat(d).year for d in allowed}
    stripped = []
    out = dict(text)
    for field in ("result", "main_factor", "timing", "advice"):
        value = str(out.get(field) or "")
        reason = None
        if _PROMISE.search(value):
            reason = "把传统倾向写成保证或未经校准的成功率"
        if not reason and any(int(y) not in allowed_years for y in re.findall(r"(?<!\d)(\d{4})年", value)):
            reason = "年份不在本次阶段或候选中"
        if not reason:
            for m in _ABS_DATE.finditer(value):
                try:
                    d = date(*map(int, m.groups())).isoformat()
                except ValueError:
                    d = None
                if d not in allowed:
                    reason = "日期不在本次阶段或候选中"
                    break
        if not reason:
            masked = _ABS_DATE.sub("", value)
            if any(tuple(map(int, m.groups())) not in allowed_short for m in _SHORT_DATE.finditer(masked)):
                reason = "月日不在本次阶段或候选中"
        if not reason:
            for sentence in re.split(r"[。！？；;，,]", value):
                for m in _FACT.finditer(sentence):
                    claim = sentence[m.start():].strip()
                    # Match the whole predicate, not merely '对方已经'. A
                    # conditional only licenses its own clause, not the next
                    # factual assertion following a comma.
                    conditional = _COND.search(sentence[:m.start()])
                    if claim not in corpus and not conditional:
                        reason = "现实细节没有输入依据，也未标为假设"
                        break
                if reason:
                    break
        if field == "result" and not reason:
            if contract["event_type"] in ("comparison", "choice"):
                # A broad categorical strength cannot settle a comparison.
                value = fallback[field]
            elif contract["horizon"] > 30 and re.search(r"近[一二三四五六七八九十\d]+[天日]|一周内|这几天|明天|后天|本周", value):
                reason = "把全期结论缩成近期窗口"
            if not contract["verifiable"] and contract["negative_question"]:
                value = fallback[field]
        if field == "timing" and not reason and re.search(r"(?:今天|明天|后天|下周|这周|本周|[天日月号]).{0,12}(?:到账|完成|成功|办成|获批|通过|录取|成行|达成|出结果)", value):
            reason = "把观察时机直接写成事件完成承诺"
        if reason or not value:
            if reason:
                stripped.append({"field": field, "reason": reason})
            value = fallback[field]
        out[field] = value
    return out, stripped
