"""Device models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DeviceInfo:
    serial: str
    model: str = "Desconhecido"

