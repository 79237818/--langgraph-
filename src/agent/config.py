"""Game configuration: character cards, world info, and model settings.

Edit this file to customize characters, world background, and which LLM
each component uses.
"""

from __future__ import annotations

# ══════════════════════════════════════════════════════════════════
# 世界观 / 背景信息
# ══════════════════════════════════════════════════════════════════

WORLD_INFO = """
【世界观设定】
（在此填写世界观、背景故事、规则等信息）

示例：这是一个架空的现代都市世界，存在着普通人不知晓的隐秘势力……
"""

# ══════════════════════════════════════════════════════════════════
# 角色卡
# key = char_id，在整个系统中唯一标识一个角色
# ══════════════════════════════════════════════════════════════════

CHARACTER_CARDS: dict[str, str] = {
    "char_001": """
【角色卡：角色A】
名字：角色A（占位符，请替换）
性别：女
性格：温柔、体贴，表面平静内心细腻
背景：（填写背景故事）
行为准则：（填写该角色的行为倾向和禁忌）
""",
    "char_002": """
【角色卡：角色B（敌对）】
名字：角色B（占位符，请替换）
性别：男
性格：冷酷、算计，目的性强
背景：（填写背景故事）
行为准则：（填写该角色的行为倾向和禁忌）
敌对标记：此角色对 user 持敌对态度，会主动谋划不利于 user 的行动。
""",
}

# 角色初始变量（与 CharacterVars 对应）
CHARACTER_INIT_VARS: dict[str, dict] = {
    "char_001": {
        "affection": 50,
        "sensitivity_base": 30,
        "sensitivity_extra": {"char_002": 0},
        "weakness": "（待填写）",
        "luck": 100,
        "inventory": [],
        "prompt_overrides": [],
        "is_hostile": False,
        "last_enemy_action_turn": -99,
    },
    "char_002": {
        "affection": 10,
        "sensitivity_base": 20,
        "sensitivity_extra": {"char_001": 0},
        "weakness": "（待填写）",
        "luck": 600,
        "inventory": [],
        "prompt_overrides": [],
        "is_hostile": True,
        "last_enemy_action_turn": -99,
    },
}

# ══════════════════════════════════════════════════════════════════
# 模型配置
#
# 每个条目支持以下字段：
#   provider    : "openai"（兼容所有 OpenAI 格式的中转服务）
#                 "anthropic" | "ollama"（其他提供商）
#   model       : 模型名称，与中转服务支持的名称一致
#   temperature : 生成温度
#   base_url    : 中转服务地址，例如 "https://your-proxy.com/v1"
#                 留空则读取环境变量 OPENAI_BASE_URL
#   api_key     : 对应的 API Key
#                 留空则读取环境变量 OPENAI_API_KEY
#
# 每个角色/组件可以指向不同的中转服务和 Key，互相独立。
# ══════════════════════════════════════════════════════════════════

# ── 公共中转配置（可在各条目里覆盖）──────────────────────────────
# 如果所有 LLM 都走同一个中转，只需在 .env 里设置
# OPENAI_BASE_URL 和 OPENAI_API_KEY，下面留空即可。
# 如果某个角色/组件需要单独的中转，在对应条目里填写即可。
_DEFAULT_BASE_URL = ""   # 留空 → 读 OPENAI_BASE_URL 环境变量
_DEFAULT_API_KEY  = ""   # 留空 → 读 OPENAI_API_KEY  环境变量


def _m(model: str, temperature: float = 0.7,
        base_url: str = _DEFAULT_BASE_URL,
        api_key: str = _DEFAULT_API_KEY) -> dict:
    """Shorthand to build a model config dict."""
    cfg: dict = {"provider": "openai", "model": model, "temperature": temperature}
    if base_url:
        cfg["base_url"] = base_url
    if api_key:
        cfg["api_key"] = api_key
    return cfg


# 每个角色使用的模型（可各自指定不同的 base_url / api_key）
CHARACTER_MODELS: dict[str, dict] = {
    # 示例：char_001 走默认中转
    "char_001": _m("gpt-4o-mini", temperature=0.8),
    # 示例：char_002 走另一个中转（取消注释并填写）
    # "char_002": _m("gpt-4o-mini", temperature=0.7,
    #                base_url="https://other-proxy.com/v1",
    #                api_key="sk-other-key"),
    "char_002": _m("gpt-4o-mini", temperature=0.7),
}

# 各功能组件使用的模型
COMPONENT_MODELS: dict[str, dict] = {
    "dispatcher":        _m("gpt-4o-mini", temperature=0.3),
    "event_judge":       _m("gpt-4o-mini", temperature=0.2),
    "memory_recorder":   _m("gpt-4o-mini", temperature=0.3),
    "enemy_strategy":    _m("gpt-4o",      temperature=0.6),
    "response_composer": _m("gpt-4o",      temperature=0.9),
    "auto_interact":     _m("gpt-4o-mini", temperature=0.8),
}

# ══════════════════════════════════════════════════════════════════
# 组件 Prompt 模板
# ══════════════════════════════════════════════════════════════════

DISPATCHER_SYSTEM = """你是一个游戏叙事调度器。
你的任务是：根据用户的输入和当前场景，决定哪些角色应该参与本轮对话，并为每个参与角色提供经过过滤的上下文信息（只包含该角色应该知道的内容）。

输出格式（严格 JSON）：
{
  "active_characters": ["char_id1", "char_id2"],
  "dispatcher_context": {
    "char_id1": "该角色本轮应知道的信息摘要",
    "char_id2": "该角色本轮应知道的信息摘要"
  },
  "reasoning": "简短说明调度理由"
}

注意：
- 敌对角色不应知道友好角色的弱点信息
- 不在场的角色不应知道当前对话内容
- 保持角色信息隔离"""

EVENT_JUDGE_SYSTEM = """你是一个游戏事件裁判。
根据本轮对话内容和当前角色状态，判断：
1. 各角色变量的变化（好感度、敏感度、气运值等）
2. 是否触发特殊事件

输出格式（严格 JSON）：
{
  "variable_deltas": {
    "char_id": {
      "affection": 0,
      "sensitivity_base": 0,
      "luck": 0
    }
  },
  "triggered_events": [],
  "user_status_change": null,
  "reasoning": "简短说明判断依据"
}

变量变化规则：
- affection 范围 0-100，根据对话亲密程度变化
- sensitivity_base 范围 0-100，根据特定互动变化
- luck 范围 0-1000，根据角色运气相关事件变化
- triggered_events 可包含: "user_unconscious", "user_injured", "scene_change", "item_found" 等
- user_status_change 可为 null 或 "normal"/"unconscious"/"injured" 等"""

MEMORY_RECORDER_SYSTEM = """你是一个游戏记忆记录器。
根据本轮对话，提取并压缩关键信息，追加到现有摘要中。

要求：
- 记录重要的情节发展、角色关系变化、关键道具/事件
- 保持简洁，总摘要不超过500字
- 用第三人称叙述
- 输出格式：直接输出更新后的完整摘要文本（不需要 JSON）"""

ENEMY_STRATEGY_SYSTEM = """你是一个敌对角色的策略决策器。
当前敌对角色的气运值充足，你需要决定是否消耗气运值来获取特殊能力、道具或触发事件。

输出格式（严格 JSON）：
{
  "use_luck": true/false,
  "luck_cost": 0,
  "effect_prompt": "简短描述获得的效果或事件（如：角色B获得了迷雾道具，可在下轮使用）",
  "reasoning": "决策理由"
}

注意：
- luck_cost 必须 > 0 且 <= 当前气运值
- effect_prompt 会被注入到游戏状态中，影响后续剧情
- 可以选择不使用（use_luck: false）"""

RESPONSE_COMPOSER_SYSTEM = """你是一个游戏叙事合成器。
根据本轮所有角色的行为、事件结果和记忆摘要，生成最终呈现给玩家的叙事文本。

要求：
- 以沉浸式第二人称（"你"）叙述
- 整合所有角色的行为和反应
- 体现场景氛围和情绪
- 如有特殊事件发生，自然地融入叙述
- 结尾可以暗示下一步的可能性，但不要替玩家做决定
- 长度适中（200-500字）"""

AUTO_INTERACT_SYSTEM = """你是一个游戏自动叙事器。
用户当前处于昏迷状态，角色们在用户不知情的情况下进行互动。
根据各角色的性格和当前情境，生成一段角色间的自动对话或行动描述。
输出简短（100字以内），用第三人称叙述。"""

# ══════════════════════════════════════════════════════════════════
# 游戏初始状态
# ══════════════════════════════════════════════════════════════════

INITIAL_SCENE = "（在此填写游戏开始时的场景描述）"
INITIAL_STORY_TIME = "第1天 清晨"
MAX_AUTO_INTERACT_TURNS = 10  # 昏迷时最多自动交互轮次
ENEMY_ACTION_LUCK_THRESHOLD = 500   # 触发 enemy_action 的最低气运值
ENEMY_ACTION_TURN_COOLDOWN = 5      # 两次 enemy_action 之间的最少轮次间隔
