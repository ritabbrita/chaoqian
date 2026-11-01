# -*- coding: utf-8 -*-
"""潮签 chaoqian: 确定性的传统历法引擎(六爻 / 八字 / 奇门 / 黄历节气 / 梅花) + 可插拔的大模型签文层。

常用入口:
    from chaoqian.bazi import build_profile        # 出生信息 -> 命盘 profile
    from chaoqian.daily import generate_daily      # 日签
    from chaoqian.monthly import monthly_fortune   # 月运
    from chaoqian.cast import cast_question        # 六爻问事
    from chaoqian.llm import AnthropicClient, CallableClient, from_env

所有结果都是传统规则下的参考线索, 未经科学验证, 不是事件概率。
"""
__version__ = "0.1.0"
