"""
MuleroChat - WebSocket Connection Manager.
Tracks who's online: drivers (one conn each) and admin tabs.
"""
import json
from typing import Any
from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        # driver_id (int) -> WebSocket
        self._drivers: dict[int, WebSocket] = {}
        # admin sockets (multiple tabs allowed)
        self._admins: list[WebSocket] = []

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def connect_driver(self, driver_id: int, ws: WebSocket):
        await ws.accept()
        # Kick old connection if driver reconnects
        old = self._drivers.get(driver_id)
        if old:
            try:
                await old.close(code=1000)
            except Exception:
                pass
        self._drivers[driver_id] = ws

    async def connect_admin(self, ws: WebSocket):
        await ws.accept()
        self._admins.append(ws)

    def disconnect_driver(self, driver_id: int):
        self._drivers.pop(driver_id, None)

    def disconnect_admin(self, ws: WebSocket):
        if ws in self._admins:
            self._admins.remove(ws)

    # ── Status ────────────────────────────────────────────────────────────────

    def online_driver_ids(self) -> set[int]:
        return set(self._drivers.keys())

    def is_driver_online(self, driver_id: int) -> bool:
        return driver_id in self._drivers

    # ── Send helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _pack(payload: dict) -> str:
        return json.dumps(payload, ensure_ascii=False)

    async def send_to_driver(self, driver_id: int, payload: dict) -> bool:
        ws = self._drivers.get(driver_id)
        if not ws:
            return False
        try:
            await ws.send_text(self._pack(payload))
            return True
        except Exception:
            self.disconnect_driver(driver_id)
            return False

    async def broadcast_to_admins(self, payload: dict):
        dead: list[WebSocket] = []
        for ws in list(self._admins):
            try:
                await ws.send_text(self._pack(payload))
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect_admin(ws)

    # ── Convenience events ────────────────────────────────────────────────────

    async def notify_driver_status(self, driver_id: int, driver_name: str, online: bool):
        """Tell all admins a driver came online/offline."""
        await self.broadcast_to_admins({
            "type": "status",
            "driver_id": driver_id,
            "driver_name": driver_name,
            "online": online,
        })

    async def relay_driver_message(self, driver_id: int, driver_name: str,
                                   msg_id: int, content: str | None,
                                   photo_url: str | None, created_at: str):
        """Forward a driver message to all admin tabs."""
        await self.broadcast_to_admins({
            "type": "message",
            "sender": "driver",
            "driver_id": driver_id,
            "driver_name": driver_name,
            "msg_id": msg_id,
            "content": content,
            "photo_url": photo_url,
            "created_at": created_at,
        })

    async def relay_admin_message(self, driver_id: int,
                                  msg_id: int, content: str | None,
                                  photo_url: str | None, created_at: str):
        """Forward an admin message to the target driver and other admin tabs."""
        payload = {
            "type": "message",
            "sender": "admin",
            "driver_id": driver_id,
            "msg_id": msg_id,
            "content": content,
            "photo_url": photo_url,
            "created_at": created_at,
        }
        await self.send_to_driver(driver_id, payload)
        await self.broadcast_to_admins(payload)


manager = ConnectionManager()
