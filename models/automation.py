"""Automation instance models."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from enum import Enum


class InstanceStatus(str, Enum):
    STARTING = "starting"
    RUNNING = "running"
    STOPPED = "stopped"
    FINISHED = "finished"
    FAILED = "failed"

    @property
    def is_active(self) -> bool:
        return self in {InstanceStatus.STARTING, InstanceStatus.RUNNING}


@dataclass(frozen=True)
class InstanceConfig:
    serial: str
    model: str
    email: str


@dataclass
class InstanceHandle:
    config: InstanceConfig
    status: InstanceStatus
    thread: threading.Thread | None = None

