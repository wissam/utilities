#!/usr/bin/env python3
"""Benchmark a tiny Ollama model as a Velreflex surface-realization layer.

Origin: created directly in the tracked raw-script intake on 2026-07-17.
Purpose: compare unloaded-runtime cold latency, warm latency, throughput, and
basic multilingual reactions across Velastra inference nodes.
Limitations: this is a narrow probe, not a production Velreflex contract. A
"cold" run means Ollama has unloaded the model; it does not flush host caches or
reboot the device. The script changes only transient Ollama model residency.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

MODEL = "qwen3.5:2b-q4_K_M"
SYSTEM_PROMPT = (
    "You are Velreflex, a fast speech reaction layer. "
    "Return exactly one natural spoken reaction in the requested language. "
    "Do not answer or solve the underlying task. Do not explain. "
    "Do not use labels, quotation marks, stage directions, or emoji. "
    "Respect max_words."
)
CANONICAL_INPUT = {
    "event": "request_received",
    "echo": "Newton",
    "language": "en",
    "system_state": "the primary agent is still processing",
    "intent": "acknowledge the user and ask them to wait briefly",
    "max_words": 8,
}
SCENARIOS = [
    ("en_wait", CANONICAL_INPUT),
    (
        "en_handoff",
        {
            "event": "provider_timeout",
            "echo": "Newton",
            "language": "en",
            "system_state": "the preferred model did not answer",
            "intent": "say you have a headache and will ask Eva instead",
            "max_words": 12,
        },
    ),
    (
        "en_shake",
        {
            "event": "device_shaken",
            "echo": "Newton",
            "language": "en",
            "system_state": "StackChan is being shaken",
            "intent": "ask the user to stop because you are dizzy",
            "max_words": 8,
        },
    ),
    (
        "fr_wait",
        {
            "event": "request_received",
            "echo": "Newton",
            "language": "fr",
            "system_state": "l'agent principal travaille encore",
            "intent": "confirmer la demande et demander un court instant",
            "max_words": 8,
        },
    ),
    (
        "ar_wait",
        {
            "event": "request_received",
            "echo": "Newton",
            "language": "ar",
            "system_state": "الوكيل الرئيسي لا يزال يعمل",
            "intent": "أكد أنك سمعت الطلب واطلب الانتظار قليلا",
            "max_words": 8,
        },
    ),
]


def request_json(base_url: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{path} returned HTTP {error.code}: {body}") from error


def unload_all(base_url: str) -> None:
    for item in request_json(base_url, "/api/ps").get("models", []):
        name = item.get("name")
        if name:
            request_json(base_url, "/api/generate", {"model": name, "keep_alive": 0})
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        models = request_json(base_url, "/api/ps").get("models", [])
        if not models:
            return
        time.sleep(0.25)
    raise RuntimeError("one or more Ollama models remained resident after unload requests")


def duration_ms(response: dict[str, Any], key: str) -> float:
    return round(float(response.get(key, 0)) / 1_000_000, 3)


def throughput(count: int, duration_ns: int) -> float | None:
    if count <= 0 or duration_ns <= 0:
        return None
    return round(count / (duration_ns / 1_000_000_000), 3)


def react(base_url: str, reflex_input: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(reflex_input, ensure_ascii=False)},
        ],
        "stream": False,
        "think": False,
        "keep_alive": "10m",
        "options": {
            "num_ctx": 512,
            "num_predict": 24,
            "temperature": 0.2,
            "seed": 42,
        },
    }
    started = time.perf_counter_ns()
    response = request_json(base_url, "/api/chat", payload)
    wall_ns = time.perf_counter_ns() - started
    prompt_count = int(response.get("prompt_eval_count", 0))
    prompt_duration = int(response.get("prompt_eval_duration", 0))
    eval_count = int(response.get("eval_count", 0))
    eval_duration = int(response.get("eval_duration", 0))
    return {
        "text": response.get("message", {}).get("content", "").strip(),
        "wall_ms": round(wall_ns / 1_000_000, 3),
        "total_ms": duration_ms(response, "total_duration"),
        "load_ms": duration_ms(response, "load_duration"),
        "prompt_tokens": prompt_count,
        "prompt_ms": duration_ms(response, "prompt_eval_duration"),
        "prompt_tokens_per_second": throughput(prompt_count, prompt_duration),
        "output_tokens": eval_count,
        "generation_ms": duration_ms(response, "eval_duration"),
        "generation_tokens_per_second": throughput(eval_count, eval_duration),
        "done_reason": response.get("done_reason", ""),
    }


def summarize(samples: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "runs": len(samples),
        "wall_ms_median": round(statistics.median(item["wall_ms"] for item in samples), 3),
        "wall_ms_min": min(item["wall_ms"] for item in samples),
        "wall_ms_max": max(item["wall_ms"] for item in samples),
        "generation_tokens_per_second_median": round(
            statistics.median(item["generation_tokens_per_second"] for item in samples), 3
        ),
        "prompt_tokens_per_second_median": round(
            statistics.median(item["prompt_tokens_per_second"] for item in samples), 3
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--node", required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--warm-runs", type=int, default=5)
    args = parser.parse_args()

    version = request_json(args.url, "/api/version").get("version", "unknown")
    show = request_json(args.url, "/api/show", {"model": MODEL})
    unload_all(args.url)
    cold = react(args.url, CANONICAL_INPUT)
    warm = [react(args.url, CANONICAL_INPUT) for _ in range(args.warm_runs)]
    scenarios = []
    for scenario_id, reflex_input in SCENARIOS:
        result = react(args.url, reflex_input)
        scenarios.append({"id": scenario_id, "input": reflex_input, "result": result})
    residency = request_json(args.url, "/api/ps").get("models", [])

    report = {
        "schema_version": "velastra.velreflex_benchmark.v0",
        "measured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "node": args.node,
        "endpoint": args.url,
        "runtime": {"name": "ollama", "version": version},
        "model": {
            "name": MODEL,
            "digest": show.get("digest", ""),
            "details": show.get("details", {}),
        },
        "contract": {
            "context_tokens": 512,
            "max_output_tokens": 24,
            "thinking": False,
            "temperature": 0.2,
            "cold_definition": "model absent from Ollama /api/ps before request; host caches retained",
        },
        "cold": cold,
        "warm": {"summary": summarize(warm), "samples": warm},
        "scenarios": scenarios,
        "residency": residency,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
