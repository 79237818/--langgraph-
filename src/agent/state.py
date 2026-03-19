"""Game state definitions for the LangGraph RPG engine."""

from __future__ import annotations

from typing import Annotated, Any
from typing_extensions import TypedDict
import operator


def merge_dict(a: dict, b: dict) -> dict:
    """Merge two dicts, b overrides a."""
    result = dict(a)
    result.update(b)
    return result


def append_list(a: list, b: list) -> list:
    """Append b to a."""
    return a + b


class CharacterVars(TypedDict, total=False):
    """Per-character variable block."""

    affection: int          # 对 user 好感度 (0-100)
    sensitivity_base: int   # 身体基础敏感度 (0-100)
    sensitivity_extra: dict[str, int]  # 对其他角色的额外敏感度 {"char_id": int}
    weakness: str           # 反差弱点描述
    luck: int               # 气运值 (0-1000)
    inventory: list[str]    # 持有道具列表
    prompt_overrides: list[str]  # 被篡改/注入的 prompt 片段
    is_hostile: bool        # 是否为敌对角色
    last_enemy_action_turn: int  # 上次触发 enemy_action 的轮次


class GameState(TypedDict, total=False):
    """Global game state passed through the LangGraph graph."""

    # ── 时间 / 进度 ──────────────────────────────────────────────
    story_time: str         # 故事内时间，e.g. "第3天 傍晚"
    turn_count: int         # 对话总轮次
    real_datetime: str      # 现实时间戳（存档用）

    # ── 角色 ─────────────────────────────────────────────────────
    characters: Annotated[dict[str, CharacterVars], merge_dict]
    # 本轮参与对话的角色 id 列表（由 dispatcher 决定）
    active_characters: list[str]

    # ── 用户 ─────────────────────────────────────────────────────
    user_status: str        # "normal" | "unconscious" | "injured" | ...
    user_input: str         # 当前用户输入（原始文本）

    # ── 对话历史 ─────────────────────────────────────────────────
    # 全局对话历史，元素为 {"role": "user"/"assistant"/"system", "content": str, "char_id": str}
    messages: Annotated[list[dict], append_list]
    memory_summary: str     # memory_recorder 维护的压缩摘要

    # ── 本轮中间产物 ──────────────────────────────────────────────
    # dispatcher 决定给每个角色的过滤信息 {"char_id": "filtered context"}
    dispatcher_context: dict[str, str]
    # 各角色本轮简要输出 {"char_id": "行为描述"}
    char_responses: Annotated[dict[str, str], merge_dict]
    # event_judge 输出的变量 delta {"char_id": {"affection": 5, ...}}
    variable_deltas: dict[str, dict[str, Any]]
    # event_judge 触发的事件列表
    triggered_events: Annotated[list[str], append_list]
    # 外部注入（enemy_action 产生的 effect_prompt 等）
    pending_events: Annotated[list[str], append_list]

    # ── 昏迷自动交互 ──────────────────────────────────────────────
    auto_interact_count: int   # 本次昏迷已自动交互轮次（最多10）

    # ── 场景 ─────────────────────────────────────────────────────
    scene: str              # 当前场景描述

    # ── 存档 ─────────────────────────────────────────────────────
    save_slot: str          # 当前存档槽名，e.g. "slot1"

    # ── 最终输出 ─────────────────────────────────────────────────
    final_response: str     # response_composer 生成的最终回复
