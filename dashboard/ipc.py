import http.client
import json
import os
import socket
from typing import Any, Optional


class BotUnavailable(Exception):
    pass


class BotError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


class _UnixConnection(http.client.HTTPConnection):
    def __init__(self, path: str, timeout: float):
        super().__init__("localhost", timeout=timeout)
        self._path = path

    def connect(self) -> None:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        sock.connect(self._path)
        self.sock = sock


class BotClient:
    def __init__(self):
        self.secret = os.getenv("SOWARD_IPC_SECRET", "")
        self.mode = os.getenv("SOWARD_IPC_MODE", "unix")
        self.path = os.getenv("SOWARD_IPC_PATH", "data/soward-ipc.sock")
        self.port = int(os.getenv("SOWARD_IPC_PORT", "8765"))

    def _connection(self, timeout: float) -> http.client.HTTPConnection:
        if self.mode == "unix":
            return _UnixConnection(self.path, timeout)
        return http.client.HTTPConnection("127.0.0.1", self.port, timeout=timeout)

    def request(self, method: str, path: str, user_id: Optional[str] = None, body: Any = None, timeout: float = 8.0) -> Any:
        headers = {"X-Soward-Secret": self.secret, "Content-Type": "application/json"}
        if user_id:
            headers["X-Soward-User"] = str(user_id)
        payload = json.dumps(body) if body is not None else None
        conn = self._connection(timeout)
        try:
            conn.request(method, path, body=payload, headers=headers)
            response = conn.getresponse()
            raw = response.read()
        except (OSError, http.client.HTTPException) as exc:
            raise BotUnavailable(str(exc))
        finally:
            conn.close()
        try:
            data = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            data = {}
        if response.status >= 400:
            raise BotError(response.status, data.get("error", "Request failed."))
        return data

    def get(self, path: str, user_id: Optional[str] = None) -> Any:
        return self.request("GET", path, user_id)

    def post(self, path: str, body: Any, user_id: Optional[str] = None) -> Any:
        return self.request("POST", path, user_id, body)
