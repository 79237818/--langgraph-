"""All graph node functions for the RPG engine."""

from __future__ import annotations

import json
import re
from typing import Any

from . import config as cfg
from .state import GameState
from .tools import save_game, load_game, list_saves


# ══════════════════════════════════════════════════════════════════
# LLM factory
# ══════════════════════════════════════════════════════════════════

def _make_llm(model_cfg: dict):
    """Instantiate an LLM from a model config dict.

    Supports optional base_url and api_key for third-party OpenAI-compatible
    proxies (e.g. one-api, new-api, openrouter, etc.).
    """
    provider = model_cfg.get("provider", "openai")
    model = model_cfg.get("model", "gpt-4o-mini")
    temperature = model_cfg.get("temperature", 0.7)
    base_url = model_cfg.get("base_url")      # e.g. "https://your-proxy.com/v1"
    api_key = model_cfg.get("api_key")        # overrides env var if set

    if provider == "openai":
        from langchain_openai import ChatOpenAI
        kwargs: dict = {"model": model, "temperature": temperature}
        if base_url:
            kwargs["base_url"] = base_url
        if api_key:
            kwargs["api_key"] = api_key
        return ChatOpenAI(**kwargs)
    elif provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        kwargs = {"model": model, "temperature": temperature}
        if base_url:
            kwargs["base_url"] = base_url
        if api_key:
            kwargs["api_key"] = api_key
        return ChatAnthropic(**kwargs)
    elif provider == "ollama":
        from langchain_ollama import ChatOllama
        kwargs = {"model": model, "temperature": temperature}
        if base_url:
            kwargs["base_url"] = base_url
        return ChatOllama(**kwargs)
    else:
        raise ValueError(f"Unsupported provider: {provider}")


def _parse_json(text: str) -> dict:
    """Extract and parse JSON from LLM output (handles markdown code blocks)."""
    # Strip markdown code fences if present
    text = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON object in the text
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group())
        return {}


# ══════════════════════════════════════════════════════════════════
# Node: init_state
# 初始化游戏状态（首次进入时）
# ══════════════════════════════════════════════════════════════════

def init_state(state: GameState) -> dict[str, Any]:
    """Initialize game state on first run."""
    updates: dict[str, Any] = {}

    if not state.get("characters"):
        updates["characters"] = {
            char_id: dict(vars_)
            for char_id, vars_ in cfg.CHARACTER_INIT_VARS.items()
        }

    if not state.get("story_time"):
        updates["story_time"] = cfg.INITIAL_STORY_TIME

    if not state.get("turn_count"):
        updates["turn_count"] = 0

    if not state.get("user_status"):
        updates["user_status"] = "normal"

    if not state.get("scene"):
        updates["scene"] = cfg.INITIAL_SCENE

    if not state.get("memory_summary"):
        updates["memory_summary"] = ""

    if not state.get("messages"):
        updates["messages"] = []

    if not state.get("pending_events"):
        updates["pending_events"] = []

    if not state.get("save_slot"):
        updates["save_slot"] = "slot1"

    if not state.get("auto_interact_count"):
        updates["auto_interact_count"] = 0

    return updates


# ══════════════════════════════════════════════════════════════════
# Node: handle_command
# 处理 /save /load /saves 等系统指令
# ══════════════════════════════════════════════════════════════════

def handle_command(state: GameState) -> dict[str, Any]:
    """Handle system commands like /save, /load, /saves."""
    user_input = (state.get("user_input") or "").strip()

    if user_input.startswith("/save"):
        parts = user_input.split()
        slot = parts[1] if len(parts) > 1 else state.get("save_slot", "slot1")
        path = save_game(dict(state), slot)
        return {"final_response": f"✅ 游戏已保存到 {path}（存档槽：{slot}）"}

    elif user_input.startswith("/load"):
        parts = user_input.split()
        slot = parts[1] if len(parts) > 1 else state.get("save_slot", "slot1")
        saved = load_game(slot)
        if saved is None:
            return {"final_response": f"❌ 存档槽 '{slot}' 不存在"}
        # Return all saved fields to restore state
        saved["final_response"] = f"✅ 已读取存档槽 '{slot}'（{saved.get('story_time', '')} / 第{saved.get('turn_count', 0)}轮）"
        return saved

    elif user_input.startswith("/saves"):
        saves = list_saves()
        if not saves:
            return {"final_response": "📂 暂无存档"}
        lines = ["📂 存档列表："]
        for s in saves:
            lines.append(f"  [{s['slot']}] {s['story_time']} | 第{s['turn_count']}轮 | {s['real_datetime'][:16]}")
        return {"final_response": "\n".join(lines)}

    return {}


def is_command(state: GameState) -> str:
    """Router: check if user input is a system command."""
    user_input = (state.get("user_input") or "").strip()
    if user_input.startswith("/"):
        return "command"
    return "game"


# ══════════════════════════════════════════════════════════════════
# Node: dispatcher
# LLM 决定哪些角色参与本轮，并过滤各角色可见信息
# ══════════════════════════════════════════════════════════════════

async def dispatcher(state: GameState) -> dict[str, Any]:
    """Dispatch user input to relevant characters with filtered context."""
    llm = _make_llm(cfg.COMPONENT_MODELS["dispatcher"])

    characters = state.get("characters", {})
    char_list = "\n".join(
        f"- {cid}: {'敌对' if v.get('is_hostile') else '友好'}, 好感度={v.get('affection', 0)}"
        for cid, v in characters.items()
    )

    user_msg = f"""当前场景：{state.get('scene', '')}
故事时间：{state.get('story_time', '')}
用户输入：{state.get('user_input', '')}
用户状态：{state.get('user_status', 'normal')}
记忆摘要：{state.get('memory_summary', '（无）')}

可用角色：
{char_list}

所有角色ID列表：{list(characters.keys())}"""

    from langchain_core.messages import SystemMessage, HumanMessage
    response = await llm.ainvoke([
        SystemMessage(content=cfg.DISPATCHER_SYSTEM),
        HumanMessage(content=user_msg),
    ])

    result = _parse_json(response.content)
    active = result.get("active_characters", list(characters.keys()))
    context = result.get("dispatcher_context", {char_id: user_msg for char_id in active})

    return {
        "active_characters": active,
        "dispatcher_context": context,
    }


# ══════════════════════════════════════════════════════════════════
# Node: character_respond_<char_id>
# 每个角色独立 LLM，根据角色卡 + 对话历史生成本轮行为
# ══════════════════════════════════════════════════════════════════

def make_character_node(char_id: str):
    """Factory: create a character respond node for a given char_id."""

    async def character_respond(state: GameState) -> dict[str, Any]:
        # Skip if this character is not active this turn
        if char_id not in state.get("active_characters", []):
            return {}

        model_cfg = cfg.CHARACTER_MODELS.get(char_id, cfg.COMPONENT_MODELS["dispatcher"])
        llm = _make_llm(model_cfg)

        char_vars = state.get("characters", {}).get(char_id, {})
        card = cfg.CHARACTER_CARDS.get(char_id, "")
        overrides = char_vars.get("prompt_overrides", [])
        override_text = "\n".join(overrides) if overrides else ""

        # Build system prompt: world info + character card + overrides
        system_parts = [cfg.WORLD_INFO, card]
        if override_text:
            system_parts.append(f"\n【特殊状态/注入信息】\n{override_text}")
        system_parts.append(
            f"\n【当前状态】好感度={char_vars.get('affection', 0)}, "
            f"气运值={char_vars.get('luck', 0)}, "
            f"道具={char_vars.get('inventory', [])}"
        )
        system_parts.append(
            "\n请根据以上设定，简要描述你本轮的行为和反应（100字以内，第一人称）。"
            "不需要完整对话，只需要行为摘要供后续整合使用。"
        )
        system_content = "\n".join(system_parts)

        # Build message history for this character
        from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
        history_msgs = []
        for msg in state.get("messages", []):
            if msg.get("char_id") == char_id or msg.get("role") == "user":
                if msg["role"] == "user":
                    history_msgs.append(HumanMessage(content=msg["content"]))
                elif msg["role"] == "assistant":
                    history_msgs.append(AIMessage(content=msg["content"]))

        # Add dispatcher context as the current turn's input
        ctx = state.get("dispatcher_context", {}).get(char_id, state.get("user_input", ""))
        history_msgs.append(HumanMessage(content=f"[本轮上下文]\n{ctx}"))

        invoke_msgs = [SystemMessage(content=system_content)] + history_msgs[-20:]  # keep last 20
        response = await llm.ainvoke(invoke_msgs)

        return {"char_responses": {char_id: response.content}}

    character_respond.__name__ = f"char_respond_{char_id}"
    return character_respond


# ══════════════════════════════════════════════════════════════════
# Node: event_judge
# LLM 判断变量变化和事件触发
# ══════════════════════════════════════════════════════════════════

async def event_judge(state: GameState) -> dict[str, Any]:
    """Judge variable changes and triggered events from this turn."""
    llm = _make_llm(cfg.COMPONENT_MODELS["event_judge"])

    char_responses = state.get("char_responses", {})
    characters = state.get("characters", {})

    char_status = "\n".join(
        f"- {cid}: 好感度={v.get('affection', 0)}, 敏感度={v.get('sensitivity_base', 0)}, 气运={v.get('luck', 0)}"
        for cid, v in characters.items()
    )
    responses_text = "\n".join(
        f"[{cid}]: {resp}" for cid, resp in char_responses.items()
    )

    user_msg = f"""用户输入：{state.get('user_input', '')}
用户状态：{state.get('user_status', 'normal')}
当前场景：{state.get('scene', '')}

各角色本轮行为：
{responses_text}

当前角色状态：
{char_status}

待处理事件：{state.get('pending_events', [])}"""

    from langchain_core.messages import SystemMessage, HumanMessage
    response = await llm.ainvoke([
        SystemMessage(content=cfg.EVENT_JUDGE_SYSTEM),
        HumanMessage(content=user_msg),
    ])

    result = _parse_json(response.content)
    updates: dict[str, Any] = {
        "variable_deltas": result.get("variable_deltas", {}),
        "triggered_events": result.get("triggered_events", []),
    }
    if result.get("user_status_change"):
        updates["user_status"] = result["user_status_change"]

    return updates


# ══════════════════════════════════════════════════════════════════
# Node: memory_recorder
# LLM 压缩本轮关键信息到 memory_summary
# ══════════════════════════════════════════════════════════════════

async def memory_recorder(state: GameState) -> dict[str, Any]:
    """Compress this turn's key info into memory_summary."""
    llm = _make_llm(cfg.COMPONENT_MODELS["memory_recorder"])

    responses_text = "\n".join(
        f"[{cid}]: {resp}"
        for cid, resp in state.get("char_responses", {}).items()
    )

    user_msg = f"""现有摘要：
{state.get('memory_summary', '（无）')}

本轮新内容：
用户输入：{state.get('user_input', '')}
角色行为：
{responses_text}
触发事件：{state.get('triggered_events', [])}
故事时间：{state.get('story_time', '')}"""

    from langchain_core.messages import SystemMessage, HumanMessage
    response = await llm.ainvoke([
        SystemMessage(content=cfg.MEMORY_RECORDER_SYSTEM),
        HumanMessage(content=user_msg),
    ])

    return {"memory_summary": response.content}


# ══════════════════════════════════════════════════════════════════
# Node: variable_updater
# Python 节点：应用 variable_deltas + 处理 pending_events
# ══════════════════════════════════════════════════════════════════

def variable_updater(state: GameState) -> dict[str, Any]:
    """Apply variable_deltas to characters and handle external injections."""
    characters = {k: dict(v) for k, v in state.get("characters", {}).items()}
    deltas = state.get("variable_deltas", {})

    for char_id, delta in deltas.items():
        if char_id not in characters:
            continue
        char = characters[char_id]
        for key, change in delta.items():
            if key in ("affection", "sensitivity_base", "luck"):
                current = char.get(key, 0)
                new_val = current + change
                # Clamp values
                if key in ("affection", "sensitivity_base"):
                    new_val = max(0, min(100, new_val))
                elif key == "luck":
                    new_val = max(0, min(1000, new_val))
                char[key] = new_val
            elif key == "inventory" and isinstance(change, list):
                char["inventory"] = char.get("inventory", []) + change
            elif key == "prompt_overrides" and isinstance(change, list):
                char["prompt_overrides"] = char.get("prompt_overrides", []) + change

    # Increment turn count
    turn_count = state.get("turn_count", 0) + 1

    # Append user input to messages
    new_messages = [{"role": "user", "content": state.get("user_input", ""), "char_id": "user"}]

    return {
        "characters": characters,
        "turn_count": turn_count,
        "messages": new_messages,
        "variable_deltas": {},   # clear after applying
        "triggered_events": [],  # clear after processing
    }


# ══════════════════════════════════════════════════════════════════
# Node: enemy_action
# 敌对角色消耗气运值换取特殊效果
# ══════════════════════════════════════════════════════════════════

async def enemy_action(state: GameState) -> dict[str, Any]:
    """Enemy character spends luck to gain special effects."""
    characters = {k: dict(v) for k, v in state.get("characters", {}).items()}
    turn_count = state.get("turn_count", 0)
    new_events: list[str] = []

    for char_id, char_vars in characters.items():
        if not char_vars.get("is_hostile"):
            continue
        luck = char_vars.get("luck", 0)
        last_turn = char_vars.get("last_enemy_action_turn", -99)

        # Check trigger conditions
        if luck < cfg.ENEMY_ACTION_LUCK_THRESHOLD:
            continue
        if turn_count - last_turn < cfg.ENEMY_ACTION_TURN_COOLDOWN:
            continue

        # Call enemy strategy LLM
        llm = _make_llm(cfg.COMPONENT_MODELS["enemy_strategy"])
        card = cfg.CHARACTER_CARDS.get(char_id, "")

        user_msg = f"""角色：{char_id}
{card}
当前气运值：{luck}
当前轮次：{turn_count}
当前场景：{state.get('scene', '')}
记忆摘要：{state.get('memory_summary', '')}
用户状态：{state.get('user_status', 'normal')}"""

        from langchain_core.messages import SystemMessage, HumanMessage
        response = await llm.ainvoke([
            SystemMessage(content=cfg.ENEMY_STRATEGY_SYSTEM),
            HumanMessage(content=user_msg),
        ])

        result = _parse_json(response.content)
        if result.get("use_luck") and result.get("luck_cost", 0) > 0:
            cost = min(result["luck_cost"], luck)
            characters[char_id]["luck"] = luck - cost
            characters[char_id]["last_enemy_action_turn"] = turn_count
            effect = result.get("effect_prompt", "")
            if effect:
                new_events.append(f"[敌对行动/{char_id}] {effect}")

    updates: dict[str, Any] = {"characters": characters}
    if new_events:
        updates["pending_events"] = new_events
    return updates


# ══════════════════════════════════════════════════════════════════
# Node: auto_interact_setup
# user 昏迷时：注入虚拟 user_input，递增计数，激活所有角色
# 之后复用 dispatcher → char_respond → event_judge/memory_recorder
# → variable_updater 完整链路
# ══════════════════════════════════════════════════════════════════

def auto_interact_setup(state: GameState) -> dict[str, Any]:
    """Inject a synthetic user_input for the auto-interact turn.

    This node kicks off a full dispatcher→chars→judges→updater cycle
    while the user is unconscious. Each call increments auto_interact_count.
    """
    count = state.get("auto_interact_count", 0) + 1
    synthetic_input = (
        f"[系统：用户昏迷中，第{count}轮自动交互。"
        "请各角色根据当前情境自由行动，不受用户指令约束。]"
    )
    # Activate all characters for this auto turn
    all_chars = list(state.get("characters", {}).keys())
    return {
        "auto_interact_count": count,
        "user_input": synthetic_input,
        "active_characters": all_chars,
    }


def should_auto_interact(state: GameState) -> str:
    """Router: enter/continue auto-interact loop or proceed to response_composer."""
    if (
        state.get("user_status") == "unconscious"
        and state.get("auto_interact_count", 0) < cfg.MAX_AUTO_INTERACT_TURNS
    ):
        return "continue"
    return "done"


def after_auto_variable_updater(state: GameState) -> str:
    """Router after variable_updater: loop back or go to enemy_action."""
    if (
        state.get("user_status") == "unconscious"
        and state.get("auto_interact_count", 0) < cfg.MAX_AUTO_INTERACT_TURNS
    ):
        return "auto_loop"
    return "proceed"


# ══════════════════════════════════════════════════════════════════
# Node: response_composer
# 整合所有信息，生成最终回复给 user
# ══════════════════════════════════════════════════════════════════

async def response_composer(state: GameState) -> dict[str, Any]:
    """Compose the final narrative response for the user."""
    llm = _make_llm(cfg.COMPONENT_MODELS["response_composer"])

    char_responses = state.get("char_responses", {})
    responses_text = "\n".join(
        f"[{cid}的行为]: {resp}" for cid, resp in char_responses.items()
    )

    characters = state.get("characters", {})
    char_status = "\n".join(
        f"- {cid}: 好感度={v.get('affection', 0)}, 气运={v.get('luck', 0)}, 道具={v.get('inventory', [])}"
        for cid, v in characters.items()
    )

    # Collect auto-interact logs if any
    auto_logs = [
        m["content"] for m in state.get("messages", [])
        if m.get("char_id") == "auto"
    ]
    auto_text = "\n".join(auto_logs) if auto_logs else ""

    user_msg = f"""用户输入：{state.get('user_input', '')}
用户状态：{state.get('user_status', 'normal')}
当前场景：{state.get('scene', '')}
故事时间：{state.get('story_time', '')}
第{state.get('turn_count', 0)}轮

角色行为摘要：
{responses_text}

角色当前状态：
{char_status}

记忆摘要：
{state.get('memory_summary', '（无）')}

触发事件：{state.get('triggered_events', [])}
待处理事件：{state.get('pending_events', [])}
{f"昏迷期间自动交互：{chr(10)}{auto_text}" if auto_text else ""}"""

    from langchain_core.messages import SystemMessage, HumanMessage
    response = await llm.ainvoke([
        SystemMessage(content=cfg.RESPONSE_COMPOSER_SYSTEM),
        HumanMessage(content=user_msg),
    ])

    # Append final response to messages
    new_msg = {"role": "assistant", "content": response.content, "char_id": "narrator"}

    return {
        "final_response": response.content,
        "messages": [new_msg],
        "char_responses": {},       # clear for next turn
        "auto_interact_count": 0,   # reset
        "pending_events": [],       # clear consumed events
    }
