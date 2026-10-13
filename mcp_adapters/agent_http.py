"""Local loopback, synchronous JSON API for a true passive frontend.

Endpoints: POST /conversations, POST /chat, GET /history/<uuid>.
No CORS headers; bound to 127.0.0.1 and authenticated with a bearer token.
"""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import urlsplit

from mcp_adapters.agent_gateway import AgentGateway

MAX_BODY_BYTES = 131_072


def serve_http(gateway: AgentGateway, token: str, port: int = 8734) -> None:
    if not token.strip():
        raise ValueError("METASTOCK_GATEWAY_TOKEN must be set for HTTP mode")

    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, payload: dict[str, Any]) -> None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _auth(self) -> bool:
            if self.headers.get("Authorization", "") != f"Bearer {token}":
                self._send(401, {"error": "Unauthorized"})
                return False
            return True

        def do_POST(self) -> None:
            if not self._auth():
                return
            length = self.headers.get("Content-Length", "")
            if not length.isdigit() or int(length) > MAX_BODY_BYTES:
                self._send(413, {"error": "Invalid body length"})
                return
            try:
                params = json.loads(self.rfile.read(int(length)))
                if not isinstance(params, dict):
                    raise ValueError("Expected JSON object")
                if urlsplit(self.path).path == "/conversations":
                    result = gateway.create_conversation(params.get("title"))
                elif urlsplit(self.path).path == "/chat":
                    result = gateway.chat(params["conversation_id"], params["message"], params.get("client_turn_id"))
                else:
                    self._send(404, {"error": "Not found"})
                    return
                self._send(200, result)
            except (ValueError, KeyError, TypeError) as exc:
                self._send(400, {"error": f"{type(exc).__name__}: {exc}"})
            except LookupError:
                self._send(404, {"error": "Conversation not found"})
            except Exception as exc:
                self.log_error("agent request failed: %s", type(exc).__name__)
                self._send(500, {"error": "Agent request failed"})

        def do_GET(self) -> None:
            if not self._auth():
                return
            path = urlsplit(self.path).path
            if not path.startswith("/history/"):
                self._send(404, {"error": "Not found"})
                return
            try:
                self._send(200, gateway.get_history(path.removeprefix("/history/")))
            except ValueError:
                self._send(400, {"error": "Invalid conversation identifier"})
            except LookupError:
                self._send(404, {"error": "Conversation not found"})
            except Exception as exc:
                self.log_error("history failed: %s", type(exc).__name__)
                self._send(500, {"error": "History failed"})

    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
