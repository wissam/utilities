#!/usr/bin/env bash
# Origin: /tmp/vel1155-resource-sample.sh.
# Purpose: sample Ollama and classifier-adapter CPU/RSS during an eval replay.
# Limitations: depends on the historical VEL-1155 script and fixed process names.
set -euo pipefail

ollama_pid=$(pgrep -xo ollama)
adapter_pid=$(pgrep -fo '^/home/wissam/.local/bin/vellm-classifierd ')
hz=$(getconf CLK_TCK)

cpu_ticks() {
  awk '{print $14 + $15}' "/proc/$1/stat"
}

start_ns=$(date +%s%N)
ollama_start=$(cpu_ticks "$ollama_pid")
adapter_start=$(cpu_ticks "$adapter_pid")

script_dir=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
SKIP_CUSTOM=1 "${script_dir}/2026-07-15-vel-1155-classifier-eval.sh" >/tmp/vel1155-resource-replay.jsonl

end_ns=$(date +%s%N)
ollama_end=$(cpu_ticks "$ollama_pid")
adapter_end=$(cpu_ticks "$adapter_pid")

awk -v elapsed_ns="$((end_ns - start_ns))" \
    -v hz="$hz" \
    -v ollama_ticks="$((ollama_end - ollama_start))" \
    -v adapter_ticks="$((adapter_end - adapter_start))" \
    'BEGIN {
      elapsed = elapsed_ns / 1000000000;
      ollama_cpu = ollama_ticks / hz;
      adapter_cpu = adapter_ticks / hz;
      printf "elapsed_seconds=%.3f\n", elapsed;
      printf "ollama_cpu_seconds=%.3f\n", ollama_cpu;
      printf "ollama_average_cpu_percent=%.2f\n", 100 * ollama_cpu / elapsed;
      printf "adapter_cpu_seconds=%.3f\n", adapter_cpu;
      printf "adapter_average_cpu_percent=%.2f\n", 100 * adapter_cpu / elapsed;
    }'

ps -p "$ollama_pid,$adapter_pid" -o pid,rss,vsz,%cpu,%mem,etime,cmd
