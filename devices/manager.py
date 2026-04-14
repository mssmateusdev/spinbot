"""High-level device manager used by UI controllers."""

from __future__ import annotations

from adb.client import AdbService
from models.device import DeviceInfo


class DeviceManager:
    def __init__(self, adb_service: AdbService | None = None):
        self.adb_service = adb_service or AdbService()

    def refresh(self) -> list[DeviceInfo]:
        return self.adb_service.list_devices()

    def connect_remote(self, address: str) -> str:
        return self.adb_service.connect_remote(address)

