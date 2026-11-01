import asyncio
from contextlib import suppress
import logging

from bot.services.sessions import ExpiringMemoryStorage
from bot.utils.temp_files import TemporaryFileManager, temporary_files


LOGGER = logging.getLogger(__name__)
CLEANUP_INTERVAL = 60


class PrivacyMaintenance:
    def __init__(self, storage: ExpiringMemoryStorage, files: TemporaryFileManager = temporary_files,
                 *, interval: float = CLEANUP_INTERVAL) -> None:
        if interval <= 0:
            raise ValueError("Cleanup interval must be positive")
        self.storage = storage
        self.files = files
        self.interval = interval
        self._task: asyncio.Task | None = None

    async def sweep(self) -> None:
        sessions = self.storage.expire()
        paths = await asyncio.to_thread(self.files.sweep)
        self.storage.forget_paths(paths)
        if sessions or paths:
            LOGGER.info("Privacy cleanup: %s expired dialogs, %s expired temporary entries", sessions, len(paths))
        if self.files.pending_count:
            LOGGER.warning("Could not delete %s temporary entries; will retry", self.files.pending_count)

    async def start(self) -> None:
        await self.sweep()
        self._task = asyncio.create_task(self._run(), name="privacy-maintenance")

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(self.interval)
            try:
                await self.sweep()
            except Exception:
                # Do not put paths, IDs, contents or exception text in the log.
                LOGGER.warning("Privacy cleanup failed; will retry on the next interval")

    async def close(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None
