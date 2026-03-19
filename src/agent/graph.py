"""RPG game graph built on LangGraph.

Main entry point for LangGraph Studio / Server.

Normal turn flow:
  init_state → dispatcher → char_respond_* (parallel)
    → [event_judge ‖ memory_recorder] (parallel)
    → variable_updater
    → enemy_action
    → [auto_interact loop if unconscious]  ← see below
    → response_composer → END

Auto-interact loop (user unconscious, max MAX_AUTO_INTERACT_TURNS):
  enemy_action ──(continue)──→ auto_interact_setup
                                  → dispatcher
                                  → char_respond_* (parallel)
                                  → [event_judge ‖ memory_recorder] (parallel)
                                  → variable_updater
                                  └──(auto_loop)──→ auto_interact_setup  (repeat)
                                  └──(proceed)───→ response_composer
"""

from __future__ import annotations

from langgraph.graph import StateGraph, END

from .config import CHARACTER_CARDS
from .nodes import (
    init_state,
    handle_command,
    is_command,
    dispatcher,
    make_character_node,
    event_judge,
    memory_recorder,
    variable_updater,
    enemy_action,
    auto_interact_setup,
    should_auto_interact,
    after_auto_variable_updater,
    response_composer,
)
from .state import GameState

# ── Build graph ────────────────────────────────────────────────────

builder = StateGraph(GameState)

# 1. Init
builder.add_node("init_state", init_state)

# 2. Command handler
builder.add_node("handle_command", handle_command)

# 3. Dispatcher (shared by normal turns AND auto-interact turns)
builder.add_node("dispatcher", dispatcher)

# 4. Character nodes (one per character defined in config)
char_node_names: list[str] = []
for char_id in CHARACTER_CARDS:
    node_name = f"char_respond_{char_id}"
    builder.add_node(node_name, make_character_node(char_id))
    char_node_names.append(node_name)

# 5. Parallel judges (shared)
builder.add_node("event_judge", event_judge)
builder.add_node("memory_recorder", memory_recorder)

# 6. Variable updater (shared)
builder.add_node("variable_updater", variable_updater)

# 7. Enemy action
builder.add_node("enemy_action", enemy_action)

# 8. Auto-interact setup (injects synthetic input, increments counter)
builder.add_node("auto_interact_setup", auto_interact_setup)

# 9. Response composer
builder.add_node("response_composer", response_composer)

# ── Edges ──────────────────────────────────────────────────────────

# START → init_state
builder.set_entry_point("init_state")

# init_state → command router
builder.add_conditional_edges(
    "init_state",
    is_command,
    {"command": "handle_command", "game": "dispatcher"},
)

# handle_command → END
builder.add_edge("handle_command", END)

# dispatcher → all character nodes (fan-out, parallel)
for node_name in char_node_names:
    builder.add_edge("dispatcher", node_name)

# All character nodes → event_judge AND memory_recorder (fan-in, both run in parallel)
for node_name in char_node_names:
    builder.add_edge(node_name, "event_judge")
    builder.add_edge(node_name, "memory_recorder")

# event_judge + memory_recorder → variable_updater (fan-in)
builder.add_edge("event_judge", "variable_updater")
builder.add_edge("memory_recorder", "variable_updater")

# variable_updater → conditional:
#   - if still in auto-interact loop → back to auto_interact_setup
#   - otherwise → enemy_action
builder.add_conditional_edges(
    "variable_updater",
    after_auto_variable_updater,
    {
        "auto_loop": "auto_interact_setup",
        "proceed": "enemy_action",
    },
)

# enemy_action → conditional:
#   - user unconscious → enter auto-interact loop
#   - otherwise → response_composer
builder.add_conditional_edges(
    "enemy_action",
    should_auto_interact,
    {"continue": "auto_interact_setup", "done": "response_composer"},
)

# auto_interact_setup → dispatcher (kicks off full char cycle)
builder.add_edge("auto_interact_setup", "dispatcher")

# response_composer → END
builder.add_edge("response_composer", END)

# ── Compile ────────────────────────────────────────────────────────

graph = builder.compile(name="RPG Game")
