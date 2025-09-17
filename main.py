"""Async proxy bridging STDIN/STDOUT JSON-RPC to Devin SSE and HTTP endpoints."""

import argparse
import asyncio
import json
import logging
import os
import signal
import sys
import types
from contextlib import suppress
from typing import Optional
from urllib.parse import urljoin

import aiohttp

DEFAULT_SSE_URL = "https://mcp.devin.ai/sse"
DEFAULT_RPC_URL = "https://mcp.devin.ai/mcp"
API_KEY_ENV = "DEVIN_API_KEY"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="devin-mcp-remote",
        description="Proxy STDIO to Devin MCP over SSE/HTTP",
    )
    parser.add_argument(
        "--api-key", help="Devin Personal API key (falls back to DEVIN_API_KEY)"
    )
    parser.add_argument("--sse-url", default=DEFAULT_SSE_URL, help="Devin SSE endpoint")
    parser.add_argument("--rpc-url", default=DEFAULT_RPC_URL, help="Devin RPC endpoint")
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"],
        help="Logging verbosity",
    )
    return parser.parse_args()


def resolve_api_key(args: argparse.Namespace) -> str:
    api_key = args.api_key or os.getenv(API_KEY_ENV)
    if not api_key:
        raise SystemExit("API key is required. Provide --api-key or set DEVIN_API_KEY.")
    return api_key


class ProxyState:
    """Shared mutable proxy configuration."""

    def __init__(self, initial_rpc_url: str, *, initial_ready: bool = False) -> None:
        self._rpc_url = initial_rpc_url
        self._session_id: Optional[str] = None
        self._lock = asyncio.Lock()
        self._rpc_ready = asyncio.Event()
        if initial_ready:
            self._rpc_ready.set()

    async def get_rpc_url(self) -> str:
        async with self._lock:
            return self._rpc_url

    async def set_rpc_url(self, url: str) -> None:
        async with self._lock:
            if url != self._rpc_url:
                logging.info("RPC endpoint updated: %s", url)
            self._rpc_url = url
            self._rpc_ready.set()

    async def get_session_id(self) -> Optional[str]:
        async with self._lock:
            return self._session_id

    async def set_session_id(self, session_id: str) -> None:
        async with self._lock:
            if session_id and session_id != self._session_id:
                logging.info("Session established: %s", session_id)
            self._session_id = session_id

    async def clear_session(self) -> None:
        async with self._lock:
            if self._session_id is not None:
                logging.info("Clearing MCP session id")
            self._session_id = None

    async def wait_for_rpc_ready(self, stop_event: asyncio.Event) -> bool:
        if self._rpc_ready.is_set():
            return True
        while not stop_event.is_set():
            wait_rpc = asyncio.create_task(self._rpc_ready.wait())
            wait_stop = asyncio.create_task(stop_event.wait())
            done, pending = await asyncio.wait(
                [wait_rpc, wait_stop],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
            for task in done:
                if task is wait_rpc and not task.cancelled():
                    with suppress(asyncio.CancelledError):
                        await task
                if task is wait_stop and not task.cancelled():
                    with suppress(asyncio.CancelledError):
                        await task
            if wait_rpc in done and not wait_rpc.cancelled():
                return True
            if wait_stop in done:
                return False
        return False


async def apply_session_headers(base_headers: dict, state: "ProxyState") -> dict:
    headers = dict(base_headers)
    session_id = await state.get_session_id()
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    return headers


async def handle_endpoint_event(
    data: Optional[str], sse_url: str, state: "ProxyState"
) -> None:
    if data is None:
        return
    raw = data.strip()
    if not raw:
        return
    endpoint_value: Optional[str]
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        endpoint_value = raw
    else:
        if isinstance(parsed, str):
            endpoint_value = parsed
        elif isinstance(parsed, dict):
            endpoint_value = (
                parsed.get("endpoint") or parsed.get("url") or parsed.get("path")
            )
        else:
            endpoint_value = None
    if not endpoint_value:
        logging.debug("Endpoint event missing URL: %s", raw)
        return
    resolved = urljoin(sse_url, endpoint_value)
    await state.set_rpc_url(resolved)


async def read_sse_stream(
    session: aiohttp.ClientSession,
    url: str,
    base_headers: dict,
    state: "ProxyState",
    stop_event: asyncio.Event,
) -> None:
    backoff_seconds = 1
    while not stop_event.is_set():
        try:
            headers = await apply_session_headers(base_headers, state)
            async with session.get(url, headers=headers, timeout=None) as resp:
                resp.raise_for_status()
                logging.info("Connected to SSE stream: %s", url)
                backoff_seconds = 1
                buffer = ""
                async for chunk in resp.content.iter_any():
                    if stop_event.is_set():
                        break
                    buffer += chunk.decode("utf-8", errors="ignore")
                    buffer = buffer.replace("\r\n", "\n")
                    while "\n\n" in buffer:
                        block, buffer = buffer.split("\n\n", 1)
                        event = parse_sse_block(block)
                        if event is None:
                            continue
                        if event.event == "endpoint":
                            await handle_endpoint_event(event.data, url, state)
                            continue
                        if event.event == "ping":
                            continue
                        if event.data is None:
                            continue
                        message = event.data.strip()
                        if not message:
                            continue
                        try:
                            json.loads(message)
                        except json.JSONDecodeError:
                            logging.debug("Skipping non-JSON SSE event: %s", message)
                            continue
                        sys.stdout.write(message + "\n")
                        sys.stdout.flush()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            if stop_event.is_set():
                break
            logging.warning("SSE connection error: %s", exc)
            await asyncio.sleep(min(backoff_seconds, 30))
            backoff_seconds = min(backoff_seconds * 2, 30)


async def forward_stdin(
    session: aiohttp.ClientSession,
    base_headers: dict,
    state: "ProxyState",
    stop_event: asyncio.Event,
) -> None:
    while not stop_event.is_set():
        line = await asyncio.to_thread(sys.stdin.readline)
        if line == "":
            logging.info("STDIN closed; stopping proxy")
            stop_event.set()
            break
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError as exc:
            logging.warning("Discarding non-JSON STDIN line: %s", exc)
            continue
        try:
            ready = await state.wait_for_rpc_ready(stop_event)
            if not ready:
                break
            rpc_url = await state.get_rpc_url()
            headers = await apply_session_headers(base_headers, state)
            async with session.post(rpc_url, headers=headers, json=payload) as resp:
                if resp.status >= 400:
                    body = await resp.text()
                    logging.error(
                        "RPC POST %s failed: %s %s", rpc_url, resp.status, body
                    )
                    if resp.status == 404:
                        await state.clear_session()
                session_header = resp.headers.get("Mcp-Session-Id")
                if session_header:
                    await state.set_session_id(session_header)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logging.error("RPC POST error: %s", exc)


class SSEEvent:
    __slots__ = ("event", "data", "event_id")

    def __init__(
        self, event: Optional[str], data: Optional[str], event_id: Optional[str]
    ):
        self.event = event
        self.data = data
        self.event_id = event_id


def parse_sse_block(block: str) -> Optional[SSEEvent]:
    if not block:
        return None
    event_name: Optional[str] = None
    event_id: Optional[str] = None
    data_lines: list[str] = []
    for line in block.split("\n"):
        if not line:
            continue
        if line.startswith(":"):
            continue
        if line.startswith("event:"):
            event_name = line[6:].lstrip()
            continue
        if line.startswith("id:"):
            event_id = line[3:].lstrip()
            continue
        if line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
            continue
    data: Optional[str] = "\n".join(data_lines) if data_lines else None
    if data is None and event_name is None and event_id is None:
        return None
    return SSEEvent(event_name, data, event_id)


def install_signal_handlers(stop_event: asyncio.Event) -> None:
    def _signal_handler(_: int, __: Optional[types.FrameType]) -> None:
        if not stop_event.is_set():
            logging.info("Signal received; shutting down")
            stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        with suppress(NotImplementedError):
            signal.signal(sig, _signal_handler)


async def runner(args: argparse.Namespace) -> None:
    api_key = resolve_api_key(args)
    auth_header = {"Authorization": f"Bearer {api_key}"}

    base_sse_headers = {**auth_header, "Accept": "text/event-stream"}
    base_rpc_headers = {
        **auth_header,
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }

    stop_event = asyncio.Event()
    install_signal_handlers(stop_event)

    state = ProxyState(
        args.rpc_url,
        initial_ready=args.rpc_url != DEFAULT_RPC_URL,
    )

    timeout = aiohttp.ClientTimeout(total=None)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        tasks = [
            asyncio.create_task(
                read_sse_stream(
                    session, args.sse_url, base_sse_headers, state, stop_event
                )
            ),
            asyncio.create_task(
                forward_stdin(session, base_rpc_headers, state, stop_event)
            ),
        ]
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            stop_event.set()
            for task in tasks:
                task.cancel()
            for task in tasks:
                with suppress(asyncio.CancelledError):
                    await task


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="[%(asctime)s] %(levelname)s %(message)s",
    )
    try:
        asyncio.run(runner(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
