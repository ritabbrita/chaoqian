# -*- coding: utf-8 -*-
"""可插拔的大模型接口。引擎只负责算; 签文措辞才交给大模型, 而且大模型写的每一句都要过确定性护栏。

不传 llm(或传 None)时, 全部走规则兜底文案, 不发任何网络请求。

接入方式:
  1. AnthropicClient —— 读环境变量 ANTHROPIC_API_KEY, 需要 `pip install anthropic`;
  2. CallableClient  —— 包一个你自己的函数 fn(system, messages, max_tokens) -> str, 可接任意提供商;
  3. 自己实现 LLMClient.complete()。
"""
import json
import os
import re

STYLE_NOTE = ("中文文字里标点一律用全角(，。；：！？); "
              "如果要求输出 JSON, JSON 本身的语法符号照常用半角, 只把字段里的中文文字按全角标点写。")


class LLMClient:
    """最小接口: 给 system 与多轮 messages([{role: user|assistant, content: str}]), 返回回复文本或 None。"""

    def complete(self, system, messages, max_tokens=1024):  # pragma: no cover - interface
        raise NotImplementedError


class CallableClient(LLMClient):
    """把任意函数包成 LLMClient: fn(system, messages, max_tokens) -> str | None。"""

    def __init__(self, fn):
        self.fn = fn

    def complete(self, system, messages, max_tokens=1024):
        return self.fn(system, messages, max_tokens)


class AnthropicClient(LLMClient):
    """Anthropic Messages API 示例实现(官方 Python SDK)。

    环境变量:
      ANTHROPIC_API_KEY          必填(或 SDK 支持的其它凭据来源)
      CHAOQIAN_ANTHROPIC_MODEL   可选, 默认 claude-opus-5-5
      CHAOQIAN_ANTHROPIC_EFFORT  可选, low / medium / high, 默认 low(签文是短 JSON, 不需要长推理)
    任何失败(未安装 SDK、网络、拒答、被 max_tokens 截断、空文本)都返回 None, 上层自动走规则兜底。
    """

    DEFAULT_MODEL = "claude-opus-5-5"

    def __init__(self, model=None, api_key=None, effort=None, max_tokens=16000, timeout=120):
        self.model = model or os.environ.get("CHAOQIAN_ANTHROPIC_MODEL") or self.DEFAULT_MODEL
        self.effort = effort or os.environ.get("CHAOQIAN_ANTHROPIC_EFFORT") or "low"
        self.max_tokens = max_tokens
        self.timeout = timeout
        self._api_key = api_key
        self._client = None
        self.last_error = None

    def _get(self):
        if self._client is None:
            import anthropic  # 可选依赖, 只有用到时才导入
            kwargs = {"timeout": self.timeout}
            if self._api_key:
                kwargs["api_key"] = self._api_key
            self._client = anthropic.Anthropic(**kwargs)
        return self._client

    def complete(self, system, messages, max_tokens=1024):
        self.last_error = None
        try:
            client = self._get()
            resp = client.messages.create(
                model=self.model,
                # max_tokens 含思考 token, 给足余量; 签文本身很短。
                max_tokens=max(int(max_tokens), self.max_tokens),
                system="\n\n".join(x for x in (system, STYLE_NOTE) if x),
                messages=_normalize_messages(messages),
                output_config={"effort": self.effort},
            )
        except Exception as exc:  # 未安装 SDK / 网络 / 4xx / 5xx
            self.last_error = type(exc).__name__
            return None
        if resp.stop_reason in ("refusal", "max_tokens"):
            self.last_error = resp.stop_reason
            return None
        text = "".join(getattr(b, "text", "") for b in (resp.content or []) if getattr(b, "type", "") == "text").strip()
        if not text:
            self.last_error = "empty"
            return None
        return text


def _normalize_messages(messages):
    """合并连续同角色; 首条是 assistant 时前面垫一句 user; 丢掉空内容。"""
    out = []
    for m in messages or []:
        role, text = m.get("role"), str(m.get("content") or "")
        if role not in ("user", "assistant") or not text.strip():
            continue
        if out and out[-1]["role"] == role:
            out[-1]["content"] += "\n" + text
        else:
            out.append({"role": role, "content": text})
    if out and out[0]["role"] == "assistant":
        out.insert(0, {"role": "user", "content": "(earlier conversation)"})
    return out


def from_env():
    """有 ANTHROPIC_API_KEY 且装了 anthropic 时返回 AnthropicClient, 否则 None(纯规则模式)。"""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    try:
        import anthropic  # noqa: F401
    except Exception:
        return None
    return AnthropicClient()


def loads_json_loose(txt):
    """宽松解析模型回复里的 JSON(去 markdown 围栏, 取最外层 {} 或 [])。"""
    txt = re.sub(r"^```(json)?|```$", "", (txt or "").strip(), flags=re.M).strip()
    try:
        return json.loads(txt)
    except Exception:
        pass
    for a, b in (("{", "}"), ("[", "]")):
        i, j = txt.find(a), txt.rfind(b)
        if 0 <= i < j:
            try:
                return json.loads(txt[i:j + 1])
            except Exception:
                continue
    return None


def ask_json(llm, system, messages, max_tokens=1024):
    """调 llm 并解析 JSON; llm 为 None 或任何失败都返回 None。"""
    if llm is None:
        return None
    try:
        txt = llm.complete(system, messages, max_tokens)
    except Exception:
        return None
    return loads_json_loose(txt) if txt else None
