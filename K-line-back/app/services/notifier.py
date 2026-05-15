from __future__ import annotations

from typing import Protocol

from app.core.models import Signal
from app.services.storage import Storage


class Notifier(Protocol):
    def publish(self, signal: Signal) -> None:
        ...


class DatabaseNotifier:
    """First-pass notifier: reserve the delivery interface and persist events locally."""

    def __init__(self, storage: Storage) -> None:
        self.storage = storage

    def publish(self, signal: Signal) -> None:
        self.storage.record_notification(signal)
