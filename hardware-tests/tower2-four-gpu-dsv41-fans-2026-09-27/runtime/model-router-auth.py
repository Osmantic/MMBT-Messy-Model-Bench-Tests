#!/usr/bin/env python3
"""Load-aware, no-replay HTTP router for the Dream Fleet Qwen service."""

from __future__ import annotations

import argparse
import http.client
import json
import logging
import os
import re
import socket
import stat
import threading
import time
import uuid
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


LOG = logging.getLogger("dream-fleet-router")
HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "proxy-connection",
}
RESPONSE_HEADERS_ALWAYS_STRIP = HOP_HEADERS | {"content-length", "server", "date"}
HEADER_NAME = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")
MAX_REQUEST_BODY = 32 * 1024 * 1024
MAX_HEALTH_BODY = 1024 * 1024


@dataclass
class Endpoint:
    name: str
    url: str
    priority: int
    max_active: int = 1
    remove_fields: list[str] = field(default_factory=list)
    request_overrides: dict[str, Any] = field(default_factory=dict)
    expected_model_pattern: str | None = None
    api_key_file: str | None = field(default=None, repr=False)
    healthy: bool = False
    active: int = 0
    model_id: str | None = None
    last_error: str | None = None
    last_check: float = 0.0
    completed: int = 0
    failed: int = 0

    @property
    def available(self) -> bool:
        return self.healthy and self.active < self.max_active


@dataclass
class RouterState:
    endpoints: list[Endpoint]
    model_alias: str
    allowed_post_paths: tuple[str, ...] = ("/v1/chat/completions",)
    upstream_timeout_seconds: float = 900.0
    client_timeout_seconds: float = 30.0
    max_response_bytes: int = 64 * 1024 * 1024
    max_request_seconds: float = 1800.0
    lock: threading.RLock = field(default_factory=threading.RLock)

    def claim(self) -> Endpoint | None:
        """Claim the first healthy endpoint with capacity, without replay fallback."""
        with self.lock:
            for endpoint in sorted(self.endpoints, key=lambda item: item.priority):
                if endpoint.available:
                    endpoint.active += 1
                    return endpoint
        return None

    def release(self, endpoint: Endpoint, success: bool) -> None:
        with self.lock:
            if endpoint.active <= 0:
                LOG.error("release underflow endpoint=%s", endpoint.name)
                endpoint.active = 0
            else:
                endpoint.active -= 1
            if success:
                endpoint.completed += 1
            else:
                endpoint.failed += 1

    def request_settings(self, endpoint: Endpoint) -> tuple[str, str | None, tuple[str, ...], dict[str, Any]]:
        """Snapshot mutable request settings while holding the state lock."""
        with self.lock:
            return endpoint.url, endpoint.model_id, tuple(endpoint.remove_fields), dict(endpoint.request_overrides)

    def update_health(self, endpoint: Endpoint, *, healthy: bool, model_id: str | None, error: str | None) -> None:
        with self.lock:
            endpoint.healthy = healthy
            endpoint.model_id = model_id
            endpoint.last_error = error
            endpoint.last_check = time.time()

    def mark_transport_failure(self, endpoint: Endpoint, error: BaseException) -> None:
        with self.lock:
            endpoint.healthy = False
            endpoint.last_error = f"request failed: {type(error).__name__}: {error}"
            endpoint.last_check = time.time()

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {
                "status": "ok" if any(item.healthy for item in self.endpoints) else "degraded",
                "model": self.model_alias,
                "routing_policy": "tower2,tower1,tower3; no post-claim replay",
                "available": any(item.available for item in self.endpoints),
                "endpoints": [
                    {
                        "name": item.name,
                        "priority": item.priority,
                        "healthy": item.healthy,
                        "active": item.active,
                        "max_active": item.max_active,
                        "model_id": item.model_id,
                        "last_error": item.last_error,
                        "last_check_unix": item.last_check,
                        "completed": item.completed,
                        "failed": item.failed,
                    }
                    for item in sorted(self.endpoints, key=lambda value: value.priority)
                ],
            }


def make_connection(url: str, timeout: float) -> tuple[http.client.HTTPConnection, str]:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"unsupported endpoint URL: {url!r}")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment or parsed.username or parsed.password:
        raise ValueError("endpoint URL must be a credential-free origin without path/query/fragment")
    connection_type = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return connection_type(parsed.hostname, port, timeout=timeout), parsed.scheme


def endpoint_auth(endpoint: Endpoint) -> dict[str, str]:
    if endpoint.api_key_file is None:
        return {}
    try:
        if not Path(endpoint.api_key_file).is_absolute():raise ValueError()
        fd=os.open(endpoint.api_key_file,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC)
        try:
            info=os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.geteuid() or stat.S_IMODE(info.st_mode)!=0o600:
                raise ValueError()
            raw=os.read(fd,4097)
        finally:os.close(fd)
        if not 1<=len(raw)<=4096 or any(c<33 or c>126 for c in raw):raise ValueError()
        return {"Authorization":"Bearer "+raw.decode('ascii')}
    except (OSError,ValueError,TypeError):
        raise RuntimeError("Endpoint credential unavailable or invalid") from None


def request_json(endpoint: Endpoint, path: str, timeout: float = 3.0, *, allow_empty: bool = False) -> Any:
    connection, _ = make_connection(endpoint.url, timeout)
    try:
        connection.request("GET", path, headers={"Accept": "application/json", **endpoint_auth(endpoint)})
        response = connection.getresponse()
        payload = response.read(MAX_HEALTH_BODY + 1)
        if len(payload) > MAX_HEALTH_BODY:
            raise RuntimeError("health response too large")
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status}")
        if allow_empty and not payload.strip():
            return None
        return json.loads(payload)
    finally:
        connection.close()


def check_endpoint(state: RouterState, endpoint: Endpoint) -> None:
    try:
        health = request_json(endpoint, "/health", allow_empty=True)
        if health is not None and (not isinstance(health, dict) or health.get("status") != "ok"):
            raise RuntimeError(f"health={health!r}")
        models = request_json(endpoint, "/v1/models")
        data = models.get("data") or []
        model_ids = [item.get("id") for item in data if isinstance(item, dict) and isinstance(item.get("id"), str)]
        model_id = model_ids[0] if model_ids else None
        if endpoint.expected_model_pattern:
            model_id = next((item for item in model_ids if re.search(endpoint.expected_model_pattern or "", item)), None)
            if model_id is None:
                raise RuntimeError(f"no model matches expected pattern {endpoint.expected_model_pattern!r}")
        if not model_id:
            raise RuntimeError("no model reported")
        state.update_health(endpoint, healthy=True, model_id=model_id, error=None)
    except Exception as exc:  # health state is deliberately fail-closed
        state.update_health(endpoint, healthy=False, model_id=None, error=f"{type(exc).__name__}: {exc}")


def health_loop(state: RouterState, interval: float, stop: threading.Event) -> None:
    while not stop.is_set():
        for endpoint in state.endpoints:
            check_endpoint(state, endpoint)
        stop.wait(interval)


class RouterHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 128


class RouterHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "DreamFleetRouter/1.0"

    @property
    def state(self) -> RouterState:
        return self.server.router_state  # type: ignore[attr-defined]

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(self.state.client_timeout_seconds)

    def log_message(self, fmt: str, *args: Any) -> None:
        LOG.info("client=%s " + fmt, self.client_address[0], *args)

    def send_json(
        self,
        status: int,
        payload: Any,
        extra_headers: dict[str, str] | None = None,
        *,
        close: bool = False,
    ) -> None:
        encoded = json.dumps(payload, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        if extra_headers:
            for key, value in extra_headers.items():
                if HEADER_NAME.fullmatch(key) and "\r" not in value and "\n" not in value:
                    self.send_header(key, value)
        if close:
            self.send_header("Connection", "close")
            self.close_connection = True
        self.end_headers()
        self.wfile.write(encoded)

    @staticmethod
    def error_payload(message: str, error_type: str, code: str) -> dict[str, Any]:
        return {"error": {"message": message, "type": error_type, "param": None, "code": code}}

    @staticmethod
    def response_headers(upstream: http.client.HTTPResponse) -> list[tuple[str, str]]:
        raw_headers = upstream.getheaders()
        connection_tokens: set[str] = set()
        for key, value in raw_headers:
            if key.lower() == "connection":
                connection_tokens.update(token.strip().lower() for token in value.split(",") if token.strip())
        blocked = RESPONSE_HEADERS_ALWAYS_STRIP | connection_tokens | {
            "x-dream-fleet-endpoint",
            "x-dream-fleet-request-id",
        }
        selected: list[tuple[str, str]] = []
        for key, value in raw_headers:
            if key.lower() in blocked:
                continue
            if not HEADER_NAME.fullmatch(key) or "\r" in value or "\n" in value:
                raise http.client.HTTPException("upstream returned an unsafe response header")
            selected.append((key, value))
        return selected

    def do_GET(self) -> None:  # noqa: N802
        if self.path in {"/health", "/dream-fleet/status"}:
            snapshot = self.state.snapshot()
            self.send_json(200 if snapshot["status"] == "ok" else 503, snapshot)
            return
        if self.path == "/v1/models":
            snapshot = self.state.snapshot()
            self.send_json(
                200,
                {
                    "object": "list",
                    "data": [
                        {
                            "id": self.state.model_alias,
                            "object": "model",
                            "owned_by": "dream-fleet",
                            "routing": snapshot["routing_policy"],
                        }
                    ],
                },
            )
            return
        self.send_json(404, self.error_payload("not found", "invalid_request_error", "not_found"))

    def do_POST(self) -> None:  # noqa: N802
        request_id = str(uuid.uuid4())
        request_path = urlsplit(self.path).path
        trace_headers = {"X-Dream-Fleet-Request-ID": request_id}
        if request_path not in self.state.allowed_post_paths:
            self.send_json(404, self.error_payload("not found", "invalid_request_error", "not_found"), trace_headers)
            return
        if self.headers.get("Transfer-Encoding"):
            self.send_json(
                400,
                self.error_payload("transfer-encoded request bodies are not supported", "invalid_request_error", "invalid_transfer_encoding"),
                trace_headers,
                close=True,
            )
            return
        content_lengths = self.headers.get_all("Content-Length", failobj=[])
        if len(content_lengths) != 1:
            self.send_json(
                411,
                self.error_payload("exactly one Content-Length header is required", "invalid_request_error", "length_required"),
                trace_headers,
                close=True,
            )
            return
        try:
            length = int(content_lengths[0])
        except ValueError:
            self.send_json(400, self.error_payload("invalid content length", "invalid_request_error", "invalid_content_length"), trace_headers, close=True)
            return
        if length <= 0:
            self.send_json(400, self.error_payload("request body must not be empty", "invalid_request_error", "empty_body"), trace_headers, close=True)
            return
        if length > MAX_REQUEST_BODY:
            self.send_json(413, self.error_payload("request body exceeds 32 MiB", "invalid_request_error", "body_too_large"), trace_headers, close=True)
            return
        try:
            raw_body = self.rfile.read(length)
        except (TimeoutError, socket.timeout):
            self.send_json(408, self.error_payload("request body read timed out", "timeout_error", "request_timeout"), trace_headers, close=True)
            return
        if len(raw_body) != length:
            self.send_json(400, self.error_payload("request body ended before Content-Length bytes", "invalid_request_error", "incomplete_body"), trace_headers, close=True)
            return
        try:
            body = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            self.send_json(400, self.error_payload(f"invalid JSON: {exc.msg}", "invalid_request_error", "invalid_json"), trace_headers)
            return
        if not isinstance(body, dict):
            self.send_json(400, self.error_payload("JSON request body must be an object", "invalid_request_error", "invalid_body"), trace_headers)
            return
        requested_model = body.get("model")
        if requested_model not in {None, self.state.model_alias}:
            self.send_json(
                400,
                self.error_payload(f"unsupported model; use {self.state.model_alias!r}", "invalid_request_error", "unsupported_model"),
                trace_headers,
            )
            return

        endpoint = self.state.claim()
        if endpoint is None:
            self.send_json(
                503,
                self.error_payload("all Dream Fleet endpoints are busy or unhealthy", "capacity_error", "no_capacity"),
                {**trace_headers, "Retry-After": "2"},
            )
            return

        started = time.monotonic()
        success = False
        status = 502
        connection: http.client.HTTPConnection | None = None
        response_started = False
        try:
            endpoint_url, model_id, remove_fields, request_overrides = self.state.request_settings(endpoint)
            if not model_id:
                raise RuntimeError("claimed endpoint has no model ID")
            body["model"] = model_id
            for field_name in remove_fields:
                body.pop(field_name, None)
            body.update(request_overrides)
            forwarded = json.dumps(body, separators=(",", ":")).encode()
            connection, _ = make_connection(
                endpoint_url,
                min(self.state.upstream_timeout_seconds, self.state.max_request_seconds),
            )
            headers = {
                "Content-Type": "application/json",
                "Accept": self.headers.get("Accept", "application/json"),
                "Content-Length": str(len(forwarded)),
                "X-Dream-Fleet-Request-ID": request_id,
            }
            for header_name in ("Authorization", "User-Agent", "Accept-Encoding"):
                header_value = self.headers.get(header_name)
                if header_value and "\r" not in header_value and "\n" not in header_value:
                    headers[header_name] = header_value
            headers.update(endpoint_auth(endpoint))
            connection.request("POST", self.path, body=forwarded, headers=headers)
            upstream = connection.getresponse()
            status = upstream.status
            selected_headers = self.response_headers(upstream)
            try:
                self.send_response(upstream.status, upstream.reason)
                for key, value in selected_headers:
                    self.send_header(key, value)
                self.send_header("X-Dream-Fleet-Endpoint", endpoint.name)
                self.send_header("X-Dream-Fleet-Request-ID", request_id)
                self.send_header("Via", "1.1 dream-fleet-router")
                self.send_header("Connection", "close")
                self.end_headers()
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, socket.timeout, OSError):
                success = 200 <= upstream.status < 500
                self.close_connection = True
                LOG.info("request_id=%s endpoint=%s downstream disconnected during headers", request_id, endpoint.name)
                return
            response_started = True
            self.close_connection = True
            forwarded_bytes = 0
            while True:
                if time.monotonic() - started > self.state.max_request_seconds:
                    error = TimeoutError("absolute upstream request deadline exceeded")
                    self.state.mark_transport_failure(endpoint, error)
                    LOG.warning("request_id=%s endpoint=%s absolute deadline exceeded", request_id, endpoint.name)
                    break
                try:
                    chunk = upstream.read1(64 * 1024)
                except Exception as exc:
                    self.state.mark_transport_failure(endpoint, exc)
                    LOG.exception("request_id=%s endpoint=%s upstream stream failed", request_id, endpoint.name)
                    break
                if not chunk:
                    if upstream.length not in {None, 0}:
                        error = http.client.IncompleteRead(b"", upstream.length)
                        self.state.mark_transport_failure(endpoint, error)
                        LOG.warning(
                            "request_id=%s endpoint=%s upstream ended with %s bytes missing",
                            request_id,
                            endpoint.name,
                            upstream.length,
                        )
                        break
                    success = 200 <= upstream.status < 500
                    break
                if forwarded_bytes + len(chunk) > self.state.max_response_bytes:
                    error = RuntimeError("upstream response exceeded byte limit")
                    self.state.mark_transport_failure(endpoint, error)
                    LOG.warning("request_id=%s endpoint=%s response byte limit exceeded", request_id, endpoint.name)
                    break
                try:
                    self.wfile.write(chunk)
                    self.wfile.flush()
                    forwarded_bytes += len(chunk)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, socket.timeout, OSError):
                    # A downstream disconnect is not evidence that the model endpoint is unhealthy.
                    success = 200 <= upstream.status < 500
                    LOG.info("request_id=%s endpoint=%s downstream disconnected", request_id, endpoint.name)
                    break
        except Exception as exc:
            self.state.mark_transport_failure(endpoint, exc)
            if not response_started:
                try:
                    self.send_json(
                        502,
                        self.error_payload("claimed endpoint failed; request was not replayed", "upstream_error", "endpoint_failed"),
                        {**trace_headers, "X-Dream-Fleet-Endpoint": endpoint.name},
                        close=True,
                    )
                except (BrokenPipeError, ConnectionResetError, OSError):
                    pass
            self.close_connection = True
            LOG.exception("request_id=%s endpoint=%s failed before stream completion", request_id, endpoint.name)
        finally:
            if connection is not None:
                connection.close()
            self.state.release(endpoint, success)
            LOG.info(
                "request_id=%s endpoint=%s status=%s success=%s latency_ms=%d",
                request_id,
                endpoint.name,
                status,
                success,
                int((time.monotonic() - started) * 1000),
            )


def load_config(path: Path) -> tuple[RouterState, dict[str, Any]]:
    config = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError("config must be a JSON object")
    if not isinstance(config.get("model_alias"), str) or not config["model_alias"].strip():
        raise ValueError("model_alias must be a non-empty string")
    if not isinstance(config.get("endpoints"), list) or not config["endpoints"]:
        raise ValueError("endpoints must be a non-empty list")
    endpoints = [Endpoint(**item) for item in config["endpoints"]]
    if any(type(item.priority) is not int or type(item.max_active) is not int for item in endpoints):
        raise ValueError("endpoint priority/max_active must be integers")
    if sorted(item.priority for item in endpoints) != list(range(len(endpoints))):
        raise ValueError("endpoint priorities must be unique and contiguous from zero")
    if len({item.name for item in endpoints}) != len(endpoints):
        raise ValueError("endpoint names must be unique")
    for endpoint in endpoints:
        if (
            not endpoint.name
            or endpoint.max_active < 1
        ):
            raise ValueError("each endpoint needs a name and positive max_active")
        if any(not isinstance(item, str) or not item for item in endpoint.remove_fields):
            raise ValueError(f"endpoint {endpoint.name} has invalid remove_fields")
        if not isinstance(endpoint.request_overrides, dict):
            raise ValueError(f"endpoint {endpoint.name} request_overrides must be an object")
        if endpoint.expected_model_pattern:
            re.compile(endpoint.expected_model_pattern)
        connection, _ = make_connection(endpoint.url, 1.0)
        connection.close()
    required_order = config.get("required_order")
    actual_order = [item.name for item in sorted(endpoints, key=lambda item: item.priority)]
    if required_order is not None and actual_order != required_order:
        raise ValueError(f"endpoint order must be {required_order!r}, got {actual_order!r}")
    allowed_paths = config.get("allowed_post_paths", ["/v1/chat/completions"])
    if not isinstance(allowed_paths, list) or not allowed_paths or any(
        not isinstance(item, str) or not item.startswith("/v1/") or "?" in item or "#" in item
        for item in allowed_paths
    ):
        raise ValueError("allowed_post_paths must be non-empty /v1/ paths")
    upstream_timeout = float(config.get("upstream_timeout_seconds", 900))
    client_timeout = float(config.get("client_timeout_seconds", 30))
    health_interval = float(config.get("health_interval_seconds", 3))
    if not 1 <= upstream_timeout <= 3600 or not 1 <= client_timeout <= 300:
        raise ValueError("timeouts are outside safe bounds")
    if not 0.25 <= health_interval <= 300:
        raise ValueError("health_interval_seconds is outside safe bounds")
    max_response_bytes = config.get("max_response_bytes", 64 * 1024 * 1024)
    max_request_seconds = float(config.get("max_request_seconds", 1800))
    if type(max_response_bytes) is not int or not 1024 <= max_response_bytes <= 1024 * 1024 * 1024:
        raise ValueError("max_response_bytes is outside safe bounds")
    if not 1 <= max_request_seconds <= 7200:
        raise ValueError("max_request_seconds is outside safe bounds")
    listen_host = config.get("listen_host", "127.0.0.1")
    listen_port = config.get("listen_port")
    if not isinstance(listen_host, str) or type(listen_port) is not int or not 1 <= listen_port <= 65535:
        raise ValueError("listen_host/listen_port are invalid")
    state = RouterState(
        endpoints=endpoints,
        model_alias=config["model_alias"],
        allowed_post_paths=tuple(allowed_paths),
        upstream_timeout_seconds=upstream_timeout,
        client_timeout_seconds=client_timeout,
        max_response_bytes=max_response_bytes,
        max_request_seconds=max_request_seconds,
    )
    return state, config


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    state, config = load_config(args.config)
    for endpoint in state.endpoints:
        check_endpoint(state, endpoint)
    stop = threading.Event()
    health = threading.Thread(
        target=health_loop,
        args=(state, float(config.get("health_interval_seconds", 3)), stop),
        daemon=True,
    )
    health.start()
    server = RouterHTTPServer((config.get("listen_host", "127.0.0.1"), int(config["listen_port"])), RouterHandler)
    server.router_state = state  # type: ignore[attr-defined]
    LOG.warning("router listening on %s:%s", *server.server_address)
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        server.server_close()
        health.join(timeout=5)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    raise SystemExit(main())
