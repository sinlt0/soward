from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Optional

import config

log = logging.getLogger("soward.dashboard")

BASE_DIR = Path(__file__).resolve().parent.parent


class DashboardProcess:
    def __init__(self, secret: str, port: int, ipc_path: str, uses_unix: bool, ipc_port: int):
        self.secret = secret
        self.port = port
        self.ipc_path = ipc_path
        self.uses_unix = uses_unix
        self.ipc_port = ipc_port
        self._task: Optional[asyncio.Task] = None
        self._proc: Optional[asyncio.subprocess.Process] = None
        self._stopping = False

    def _env(self) -> dict:
        env = dict(os.environ)
        env["SOWARD_IPC_SECRET"] = self.secret
        env["PORT"] = str(self.port)
        env["SOWARD_IPC_PATH"] = self.ipc_path
        env["SOWARD_IPC_PORT"] = str(self.ipc_port)
        env["SOWARD_IPC_MODE"] = "unix" if self.uses_unix else "tcp"
        env["PYTHONUNBUFFERED"] = "1"
        return env

    async def start(self) -> None:
        self._stopping = False
        self._task = asyncio.create_task(self._supervise())

    async def _supervise(self) -> None:
        while not self._stopping:
            try:
                self._proc = await asyncio.create_subprocess_exec(
                    sys.executable, "-m", "dashboard", cwd=str(BASE_DIR), env=self._env(),
                )
                log.info("Dashboard started on port %d (pid %s)", self.port, self._proc.pid)
                code = await self._proc.wait()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.error("Dashboard failed to launch.", exc_info=True)
                code = -1
            if self._stopping:
                return
            log.warning("Dashboard exited with code %s. Restarting in %ds.", code, config.DASHBOARD_RESTART_DELAY_SECONDS)
            await asyncio.sleep(config.DASHBOARD_RESTART_DELAY_SECONDS)

    async def stop(self) -> None:
        self._stopping = True
        if self._proc is not None and self._proc.returncode is None:
            self._proc.terminate()
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                self._proc.kill()
        if self._task is not None:
            self._task.cancel()
