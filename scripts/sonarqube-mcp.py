#!/usr/bin/env python3
"""Launch SonarQube MCP with stdin buffering for eager stdio clients.

The official SonarQube MCP container logs "Server ready" before it reliably
answers JSON-RPC initialize messages. Codex sends initialize immediately after
process start, so this wrapper buffers stdin until the ready log appears.
"""

from __future__ import annotations

import os
import queue
import shlex
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Sequence


READY_MARKER = b"Status: Server ready"


def debug_enabled() -> bool:
    return os.environ.get("SONARQUBE_MCP_DEBUG", "").lower() in {"1", "true", "yes"}


def debug(message: str) -> None:
    if debug_enabled():
        print(f"sonarqube-mcp: {message}", file=sys.stderr, flush=True)


def env_value(*names: str, default: str = "") -> str:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return default


def fetch_token(host: str, token_file: str, ssh_config: str) -> str:
    remote_cmd = (
        "awk -F= '/^scanner_token=/ {print $2; exit}' "
        + shlex.quote(token_file)
    )
    return subprocess.check_output(
        ["ssh", "-F", ssh_config, host, remote_cmd],
        stdin=subprocess.DEVNULL,
        text=True,
        stderr=subprocess.DEVNULL,
    ).strip()


def build_docker_command() -> list[str]:
    pull_policy = env_value("SONARQUBE_MCP_PULL", default="missing")
    if pull_policy not in {"always", "missing", "never"}:
        raise RuntimeError(
            "SONARQUBE_MCP_PULL must be one of: always, missing, never"
        )

    command = ["docker", "run", "--init"]
    if pull_policy != "never":
        command.append(f"--pull={pull_policy}")
    command.extend(
        [
            "-i",
            "--rm",
            "-e",
            "SONARQUBE_TOKEN",
            "-e",
            "SONARQUBE_URL",
            "-e",
            "TELEMETRY_DISABLED",
            "-e",
            "SONARQUBE_LOG_TO_FILE_DISABLED",
            "mcp/sonarqube",
        ]
    )
    return command


def configure_environment() -> dict[str, str]:
    env = os.environ.copy()
    env["SONARQUBE_URL"] = env_value(
        "SONARQUBE_URL",
        "SONAR_HOST_URL",
        default="http://10.0.0.189:9000",
    )
    env["TELEMETRY_DISABLED"] = env_value("TELEMETRY_DISABLED", default="true")
    env["SONARQUBE_LOG_TO_FILE_DISABLED"] = env_value(
        "SONARQUBE_LOG_TO_FILE_DISABLED",
        default="true",
    )

    token = env_value("SONARQUBE_TOKEN", "SONAR_TOKEN")
    if not token:
        token = fetch_token(
            env_value("SONAR_TOKEN_HOST", default="ubuntu@10.0.0.189"),
            env_value(
                "SONAR_TOKEN_FILE",
                default="/home/ubuntu/sonarqube-credentials.txt",
            ),
            env_value("SONAR_TOKEN_SSH_CONFIG", default="/dev/null"),
        )

    if not token:
        raise RuntimeError(
            "SONARQUBE_TOKEN is required, or fetch via "
            "SONAR_TOKEN_HOST/SONAR_TOKEN_FILE must work"
        )

    env["SONARQUBE_TOKEN"] = token
    return env


def input_reader(chunks: queue.Queue[bytes | None]) -> None:
    try:
        while True:
            chunk = os.read(sys.stdin.fileno(), 8192)
            if not chunk:
                debug("stdin EOF")
                chunks.put(None)
                return
            debug(f"buffered {len(chunk)} stdin bytes")
            chunks.put(chunk)
    except Exception as exc:
        debug(f"stdin reader failed: {exc}")
        chunks.put(None)


def output_forwarder(pipe: object, target_fd: int) -> None:
    fd = pipe.fileno()  # type: ignore[attr-defined]
    while True:
        chunk = os.read(fd, 8192)
        if not chunk:
            return
        os.write(target_fd, chunk)


def stderr_forwarder(pipe: object, ready: threading.Event) -> None:
    while True:
        line = pipe.readline()  # type: ignore[attr-defined]
        if not line:
            return
        if READY_MARKER in line:
            debug("ready marker observed")
            ready.set()
        os.write(sys.stderr.fileno(), line)


def stdin_writer(
    proc: subprocess.Popen[bytes],
    chunks: queue.Queue[bytes | None],
    ready: threading.Event,
    ready_timeout: float,
) -> None:
    deadline = time.monotonic() + ready_timeout
    while not ready.is_set():
        if proc.poll() is not None:
            return
        if time.monotonic() > deadline:
            print(
                f"SonarQube MCP did not become ready within {ready_timeout:.0f}s",
                file=sys.stderr,
            )
            proc.terminate()
            return
        time.sleep(0.05)

    debug("releasing buffered stdin to container")
    while True:
        chunk = chunks.get()
        if chunk is None:
            try:
                debug("closing container stdin")
                proc.stdin.close()  # type: ignore[union-attr]
            except BrokenPipeError:
                pass
            return
        try:
            debug(f"writing {len(chunk)} bytes to container stdin")
            proc.stdin.write(chunk)  # type: ignore[union-attr]
            proc.stdin.flush()  # type: ignore[union-attr]
        except BrokenPipeError:
            debug("container stdin closed")
            return
        except Exception as exc:
            debug(f"stdin writer failed: {exc}")
            return


def install_signal_handlers(proc: subprocess.Popen[bytes]) -> None:
    def forward_signal(signum: int, _frame: object) -> None:
        if proc.poll() is None:
            proc.send_signal(signum)

    signal.signal(signal.SIGTERM, forward_signal)
    signal.signal(signal.SIGINT, forward_signal)


def start_threads(
    proc: subprocess.Popen[bytes],
    ready_timeout: float,
) -> Sequence[threading.Thread]:
    ready = threading.Event()
    chunks: queue.Queue[bytes | None] = queue.Queue()

    threads = [
        threading.Thread(target=input_reader, args=(chunks,), daemon=True),
        threading.Thread(
            target=output_forwarder,
            args=(proc.stdout, sys.stdout.fileno()),
            daemon=True,
        ),
        threading.Thread(
            target=stderr_forwarder,
            args=(proc.stderr, ready),
            daemon=True,
        ),
        threading.Thread(
            target=stdin_writer,
            args=(proc, chunks, ready, ready_timeout),
            daemon=True,
        ),
    ]
    for thread in threads:
        thread.start()
    return threads


def main() -> int:
    try:
        env = configure_environment()
        proc = subprocess.Popen(
            build_docker_command(),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
    except Exception as exc:
        print(f"Failed to start SonarQube MCP: {exc}", file=sys.stderr)
        return 2

    install_signal_handlers(proc)
    start_threads(
        proc,
        float(env_value("SONARQUBE_MCP_READY_TIMEOUT", default="75")),
    )
    return proc.wait()


if __name__ == "__main__":
    raise SystemExit(main())
