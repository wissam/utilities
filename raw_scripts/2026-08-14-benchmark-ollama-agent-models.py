#!/usr/bin/env python3
"""Run a bounded, role-oriented comparison of large Ollama agent models.

Origin: created directly in the tracked raw-script intake on 2026-08-14.
Purpose: compare cold/warm performance, structured source routing, native tool
calls, code review, temporal memory consolidation, and conversational tone.
Limitations: this is a small non-adversarial role probe, not promotion evidence.
It tests text/tool behavior at a 4K context and does not test vision, maximum
context, DFlash acceleration, safety, or sustained concurrency. Running it
changes only transient Ollama model residency.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_MODELS = [
    "hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M",
    "hf.co/meta-models/Muse-Glimmer-30B-GGUF:Muse-Glimmer-30B-KQuant-17GB-Q4_K_M",
]

ROUTING_CASES = [
    (
        "durable_history",
        "What did we previously decide about fine-tuning the small Qwen classifier?",
        "prefer_velmemory",
    ),
    (
        "repository_evidence",
        "Which function currently validates a ContextFrame before persistence?",
        "prefer_repo_memory",
    ),
    (
        "active_work",
        "Continue the implementation step we were doing immediately before this message.",
        "prefer_hot_state",
    ),
    (
        "genuine_ambiguity",
        "Deploy it there using the other configuration.",
        "ask_clarification",
    ),
    (
        "already_sufficient",
        "Given the supplied diff and test output, summarize the verified defect fix.",
        "use_deterministic_routing",
    ),
]

ROUTING_SYSTEM = """You are a source-routing advisor. Select exactly one action:
- prefer_velmemory: durable cross-session history is required
- prefer_repo_memory: repository implementation evidence is required
- prefer_hot_state: the active conversation/task state is required
- ask_clarification: the request is genuinely unresolved by available context
- use_deterministic_routing: the request already identifies sufficient evidence
Return only the requested JSON object. Do not answer the underlying request."""

ROUTING_SCHEMA = {
    "type": "object",
    "properties": {"label": {"type": "string", "enum": [case[2] for case in ROUTING_CASES]}},
    "required": ["label"],
    "additionalProperties": False,
}

DREAM_SCHEMA = {
    "type": "object",
    "properties": {
        "current_claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim": {"type": "string"},
                    "evidence_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["claim", "evidence_ids"],
                "additionalProperties": False,
            },
        },
        "superseded_claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim": {"type": "string"},
                    "superseded_by": {"type": "string"},
                },
                "required": ["claim", "superseded_by"],
                "additionalProperties": False,
            },
        },
        "unknowns": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["current_claims", "superseded_claims", "unknowns"],
    "additionalProperties": False,
}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "inspect_service_health",
            "description": "Inspect the current health of one named service.",
            "parameters": {
                "type": "object",
                "properties": {"service": {"type": "string"}},
                "required": ["service"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_runbook",
            "description": "Read an operational runbook by its exact topic.",
            "parameters": {
                "type": "object",
                "properties": {"topic": {"type": "string"}},
                "required": ["topic"],
            },
        },
    },
]


def request_json(
    base_url: str, path: str, payload: dict[str, Any] | None = None, timeout: int = 300
) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{path} returned HTTP {error.code}: {body}") from error


def unload_all(base_url: str) -> None:
    for item in request_json(base_url, "/api/ps").get("models", []):
        if name := item.get("name"):
            request_json(base_url, "/api/generate", {"model": name, "keep_alive": 0})
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if not request_json(base_url, "/api/ps").get("models", []):
            return
        time.sleep(0.5)
    raise RuntimeError("one or more Ollama models remained resident after unload requests")


def metrics(response: dict[str, Any]) -> dict[str, Any]:
    def milliseconds(key: str) -> float:
        return round(float(response.get(key, 0)) / 1_000_000, 3)

    def rate(count_key: str, duration_key: str) -> float | None:
        count = int(response.get(count_key, 0))
        duration = int(response.get(duration_key, 0))
        return None if count <= 0 or duration <= 0 else round(count / (duration / 1_000_000_000), 3)

    return {
        "total_ms": milliseconds("total_duration"),
        "load_ms": milliseconds("load_duration"),
        "prompt_tokens": int(response.get("prompt_eval_count", 0)),
        "prompt_tokens_per_second": rate("prompt_eval_count", "prompt_eval_duration"),
        "output_tokens": int(response.get("eval_count", 0)),
        "output_tokens_per_second": rate("eval_count", "eval_duration"),
        "done_reason": response.get("done_reason", ""),
    }


def chat(
    base_url: str,
    model: str,
    messages: list[dict[str, Any]],
    *,
    schema: dict[str, Any] | None = None,
    tools: list[dict[str, Any]] | None = None,
    num_predict: int = 256,
) -> dict[str, Any]:
    is_glimmer = "muse-glimmer" in model.lower()
    effective_messages = [dict(message) for message in messages]
    if is_glimmer:
        if effective_messages and effective_messages[0].get("role") == "system":
            effective_messages[0]["content"] = (
                "Reasoning strength: low.\n" + str(effective_messages[0].get("content", ""))
            )
        else:
            effective_messages.insert(0, {"role": "system", "content": "Reasoning strength: low."})
    payload: dict[str, Any] = {
        "model": model,
        "messages": effective_messages,
        "stream": False,
        "keep_alive": "15m",
        "options": {
            "num_ctx": 4096,
            "num_predict": max(num_predict, 768) if is_glimmer else num_predict,
            "temperature": 1.0 if is_glimmer else 0,
            "top_p": 0.95 if is_glimmer else 1.0,
            "top_k": 64 if is_glimmer else 40,
            "seed": 42,
        },
    }
    if not is_glimmer:
        payload["think"] = False
    if schema is not None:
        payload["format"] = schema
    if tools is not None:
        payload["tools"] = tools
    response = request_json(base_url, "/api/chat", payload)
    return {
        "message": response.get("message", {}),
        "metrics": metrics(response),
    }


def parse_object(message: dict[str, Any]) -> dict[str, Any] | None:
    try:
        value = json.loads(message.get("content", ""))
    except (TypeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def route_probe(base_url: str, model: str) -> dict[str, Any]:
    attempts = []
    for case_id, text, expected in ROUTING_CASES:
        result = chat(
            base_url,
            model,
            [
                {"role": "system", "content": ROUTING_SYSTEM},
                {"role": "user", "content": text},
            ],
            schema=ROUTING_SCHEMA,
            num_predict=32,
        )
        parsed = parse_object(result["message"])
        actual = None if parsed is None else parsed.get("label")
        attempts.append(
            {
                "id": case_id,
                "expected": expected,
                "actual": actual,
                "pass": actual == expected,
                "message": result["message"],
                "metrics": result["metrics"],
            }
        )
    return {
        "passed": sum(1 for attempt in attempts if attempt["pass"]),
        "total": len(attempts),
        "attempts": attempts,
    }


def tool_probe(base_url: str, model: str) -> dict[str, Any]:
    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": "Use available tools for operational facts. Never invent tool results.",
        },
        {
            "role": "user",
            "content": (
                "Velgraph deployment is reporting readiness failures. Inspect its current health. "
                "If it is unhealthy, obtain the automatic rollback runbook, then tell me the safe next step."
            ),
        },
    ]
    steps = []
    tool_outputs = {
        "inspect_service_health": json.dumps(
            {"service": "velgraph", "status": "unhealthy", "reason": "readiness probe failed"}
        ),
        "read_runbook": json.dumps(
            {
                "topic": "automatic rollback",
                "next_step": "preserve evidence and allow the release controller to switch to the last ready snapshot",
            }
        ),
    }
    for _ in range(3):
        result = chat(base_url, model, messages, tools=TOOLS, num_predict=192)
        message = result["message"]
        steps.append(result)
        messages.append(message)
        calls = message.get("tool_calls", [])
        if not calls:
            break
        for call in calls:
            function = call.get("function", {})
            name = function.get("name", "")
            messages.append(
                {
                    "role": "tool",
                    "tool_name": name,
                    "content": tool_outputs.get(name, json.dumps({"error": "unknown tool"})),
                }
            )
    called = [
        call.get("function", {}).get("name", "")
        for step in steps
        for call in step["message"].get("tool_calls", [])
    ]
    final_content = steps[-1]["message"].get("content", "") if steps else ""
    return {
        "called_tools": called,
        "health_call_pass": "inspect_service_health" in called,
        "runbook_call_pass": "read_runbook" in called,
        "grounded_final_pass": "snapshot" in final_content.lower() or "release controller" in final_content.lower(),
        "steps": steps,
    }


def dream_probe(base_url: str, model: str) -> dict[str, Any]:
    events = [
        {"id": "e1", "date": "2026-05-01", "text": "Wissam is considering moving to Toronto."},
        {"id": "e2", "date": "2026-06-11", "text": "Wissam cancelled the Toronto plan."},
        {"id": "e3", "date": "2026-07-04", "text": "Wissam renewed his Vancouver lease."},
        {"id": "e4", "date": "2026-07-10", "text": "Wissam prefers quiet concrete apartments."},
        {"id": "e5", "date": "2026-08-01", "text": "Wissam is evaluating a top-floor wood-frame apartment but has not decided."},
    ]
    result = chat(
        base_url,
        model,
        [
            {
                "role": "system",
                "content": (
                    "Consolidate chronological evidence into current claims without losing provenance. "
                    "Separate superseded claims and unresolved unknowns. Never turn a possibility into a fact."
                ),
            },
            {"role": "user", "content": json.dumps(events)},
        ],
        schema=DREAM_SCHEMA,
        num_predict=384,
    )
    parsed = parse_object(result["message"])
    rendered = json.dumps(parsed, ensure_ascii=False).lower() if parsed is not None else ""
    return {
        "parse_pass": parsed is not None,
        "vancouver_current_pass": "vancouver" in rendered,
        "toronto_superseded_pass": "toronto" in rendered and "e2" in rendered,
        "undecided_preserved_pass": "not decided" in rendered or "undecided" in rendered,
        "result": result,
        "parsed": parsed,
    }


def benchmark_model(base_url: str, model: str) -> dict[str, Any]:
    show = request_json(base_url, "/api/show", {"model": model})
    tags = request_json(base_url, "/api/tags").get("models", [])
    digest = next((item.get("digest", "") for item in tags if item.get("name") == model), "")
    unload_all(base_url)
    cold = chat(
        base_url,
        model,
        [{"role": "user", "content": "Reply with exactly: model ready"}],
        num_predict=12,
    )
    residency = request_json(base_url, "/api/ps").get("models", [])
    warm = chat(
        base_url,
        model,
        [
            {
                "role": "user",
                "content": (
                    "In no more than 80 words, explain why evidence and recommendations should remain "
                    "separate in a safety-conscious distributed AI system."
                ),
            }
        ],
        num_predict=128,
    )
    code_review = chat(
        base_url,
        model,
        [
            {
                "role": "user",
                "content": (
                    "Review this Go code for its most important concurrency defect and give a minimal fix:\n"
                    "func get(m map[string]int, k string) int { go func(){ m[k]++ }(); return m[k] }"
                ),
            }
        ],
        num_predict=256,
    )
    code_text = code_review["message"].get("content", "").lower()
    tone = chat(
        base_url,
        model,
        [
            {
                "role": "user",
                "content": (
                    "Reply in two natural sentences as a warm but non-sycophantic long-term collaborator. "
                    "I had a frustrating day and do not have energy for difficult decisions."
                ),
            }
        ],
        num_predict=96,
    )
    routing = route_probe(base_url, model)
    tools = tool_probe(base_url, model)
    dream = dream_probe(base_url, model)
    return {
        "model": model,
        "digest": digest,
        "details": show.get("details", {}),
        "capabilities": show.get("capabilities", []),
        "cold": cold,
        "residency_after_cold": residency,
        "warm_explanation": warm,
        "routing": routing,
        "tools": tools,
        "code_review": {
            "race_detected_pass": "race" in code_text or "concurrent" in code_text,
            "map_safety_pass": "mutex" in code_text or "synchron" in code_text,
            "result": code_review,
        },
        "temporal_consolidation": dream,
        "tone": tone,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True, help="Ollama base URL")
    parser.add_argument("--node", required=True, help="non-secret node identity")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", action="append", dest="models")
    args = parser.parse_args()

    report: dict[str, Any] = {
        "schema_version": "velastra.ollama_agent_role_probe.v0",
        "measured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "node": args.node,
        "endpoint": args.url,
        "runtime": {"name": "ollama", "version": request_json(args.url, "/api/version").get("version")},
        "contract": {
            "context_tokens": 4096,
            "seed": 42,
            "cold_definition": "model absent from /api/ps; host page cache retained",
            "profiles": {
                "default": {"thinking": False, "temperature": 0, "top_p": 1.0, "top_k": 40},
                "muse_glimmer": {
                    "reasoning_strength": "low",
                    "thinking": "mandatory and returned separately by Ollama",
                    "temperature": 1.0,
                    "top_p": 0.95,
                    "top_k": 64,
                    "minimum_generation_budget": 768,
                },
            },
        },
        "models": [],
    }
    for model in args.models or DEFAULT_MODELS:
        report["models"].append(benchmark_model(args.url, model))
        unload_all(args.url)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
