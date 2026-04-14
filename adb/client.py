"""Internal ADB API used by services, UI and automation orchestration."""

from __future__ import annotations

from typing import Any

import adbutils

import config
from adb_utils import connect_managed_device, list_devices
from models.device import DeviceInfo


class AndroidDeviceClient:
    """Small explicit API over the managed uiautomator2 device proxy."""

    def __init__(self, serial: str):
        self.serial = serial
        self.device = connect_managed_device(serial)

    def tap(self, x: int, y: int) -> Any:
        return self.device.click(x, y)

    def send_text(self, text: str) -> Any:
        return self.device.send_keys(text)

    def open_app(self, package: str | None = None) -> Any:
        return self.device.app_start(package or config.APP_PACKAGE)

    def close_app(self, package: str | None = None) -> Any:
        return self.device.app_stop(package or config.APP_PACKAGE)

    def clear_app(self, package: str | None = None) -> Any:
        return self.device.app_clear(package or config.APP_PACKAGE)

    def screenshot(self, *args, **kwargs) -> Any:
        return self.device.screenshot(*args, **kwargs)

    def shell(self, command: str, **kwargs) -> Any:
        return self.device.shell(command, **kwargs)

    def foreground_package(self) -> str:
        return self.device.app_current().get("package", "")


class AdbService:
    """Device discovery and remote ADB connection service."""

    def list_devices(self) -> list[DeviceInfo]:
        return [DeviceInfo(**item) for item in list_devices()]

    def connect_remote(self, address: str) -> str:
        return str(adbutils.adb.connect(address))

    def client_for(self, serial: str) -> AndroidDeviceClient:
        return AndroidDeviceClient(serial)

