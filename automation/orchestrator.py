"""Thread-safe orchestration for multiple automation instances."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Callable

from automation.spin_automator import SpinAutomator
from models.automation import InstanceConfig, InstanceHandle, InstanceStatus


LogCallback = Callable[[str, str, str], None]
StatsCallback = Callable[[str, dict], None]
FinishedCallback = Callable[[str], None]


@dataclass
class OrchestratorCallbacks:
    on_log: LogCallback
    on_stats: StatsCallback
    on_finished: FinishedCallback


class BatchOrchestrator:
    """Owns worker lifecycle so the GUI only starts/stops batches and reacts to events."""

    def __init__(self, callbacks: OrchestratorCallbacks):
        self.callbacks = callbacks
        self.stop_event = threading.Event()
        self._lock = threading.RLock()
        self._instances: dict[str, InstanceHandle] = {}

    def start(self, configs: list[InstanceConfig], ultra_eco: bool = False) -> None:
        with self._lock:
            if self.active_count:
                raise RuntimeError("A batch is already running")
            self.stop_event.clear()
            self._instances = {}

            for config in configs:
                handle = InstanceHandle(config=config, status=InstanceStatus.STARTING)
                thread = threading.Thread(
                    target=self._run_instance,
                    args=(config, ultra_eco),
                    name=f"SpinBot-{config.serial}",
                    daemon=True,
                )
                handle.thread = thread
                self._instances[config.serial] = handle
                thread.start()

    def stop(self) -> None:
        self.stop_event.set()

    def snapshot(self) -> dict[str, InstanceHandle]:
        with self._lock:
            return dict(self._instances)

    @property
    def active_count(self) -> int:
        with self._lock:
            return sum(1 for handle in self._instances.values() if handle.status.is_active)

    def _mark(self, serial: str, status: InstanceStatus) -> None:
        with self._lock:
            handle = self._instances.get(serial)
            if handle:
                handle.status = status

    def _run_instance(self, config: InstanceConfig, ultra_eco: bool) -> None:
        serial = config.serial
        self._mark(serial, InstanceStatus.RUNNING)

        def _log(message: str, level: str = "info") -> None:
            self.callbacks.on_log(serial, message, level)

        def _stats(stats: dict) -> None:
            self.callbacks.on_stats(serial, stats)

        try:
            if ultra_eco:
                self._apply_ultra_eco(serial)

            automator = SpinAutomator(
                serial=serial,
                account_email=config.email,
                stop_event=self.stop_event,
                on_log=_log,
                on_stats_update=_stats,
                device_label=config.model,
            )
            automator.run()
            self._mark(serial, InstanceStatus.STOPPED if self.stop_event.is_set() else InstanceStatus.FINISHED)
        except Exception as exc:
            self._mark(serial, InstanceStatus.FAILED)
            self.callbacks.on_log(serial, f"Erro critico na instancia: {exc}", "error")
        finally:
            if ultra_eco:
                self._restore_display(serial)
            self.callbacks.on_finished(serial)

    def _apply_ultra_eco(self, serial: str) -> None:
        from adb_utils import apply_headless_optimizations, connect_managed_device

        try:
            apply_headless_optimizations(connect_managed_device(serial))
        except Exception as exc:
            self.callbacks.on_log(serial, f"Falha ao aplicar ultra-eco: {exc}", "warning")

    def _restore_display(self, serial: str) -> None:
        from adb_utils import connect_managed_device, restore_display_defaults

        try:
            restore_display_defaults(connect_managed_device(serial))
        except Exception as exc:
            self.callbacks.on_log(serial, f"Falha ao restaurar display: {exc}", "warning")

