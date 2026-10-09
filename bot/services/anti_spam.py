from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from math import ceil
from time import monotonic


@dataclass(frozen=True, slots=True)
class AntiSpamPolicy:
    burst: int = 6
    refill_seconds: float = 2
    block_seconds: float = 10
    notice_seconds: float = 10
    global_burst: int = 30
    global_refill_seconds: float = 0.1
    heavy_interval: float = 5
    max_heavy: int = 2
    max_users: int = 4096
    idle_ttl: float = 600
    max_upload_bytes: int = 20 * 1024 * 1024

    def __post_init__(self) -> None:
        if any(getattr(self, name) <= 0 for name in self.__dataclass_fields__):
            raise ValueError("Anti-spam limits must be positive.")


@dataclass(slots=True)
class TokenBucket:
    tokens: float
    updated_at: float

    def take(self, now: float, capacity: int, refill_seconds: float) -> int:
        self.tokens = min(capacity, self.tokens + max(0, now - self.updated_at) / refill_seconds)
        self.updated_at = now
        if self.tokens < 1:
            return max(1, ceil((1 - self.tokens) * refill_seconds))
        self.tokens -= 1
        return 0


@dataclass(slots=True)
class UserActivity:
    bucket: TokenBucket
    last_seen: float
    active: bool = False
    blocked_until: float = 0
    heavy_after: float = 0
    notice_after: float = 0


@dataclass(frozen=True, slots=True)
class Rejection:
    reason: str
    retry_after: int
    notify: bool


class AntiSpamLimiter:
    """Single-process, bounded RAM only; no message contents, files or user database.

    All admission/release methods are synchronous, so checks and reservations are
    atomic within the bot's event loop. A full cache rejects new guests rather
    than evicting active requests or letting rotating IDs reset their limits.
    """

    def __init__(self, policy: AntiSpamPolicy | None = None, *, clock: Callable[[], float] = monotonic) -> None:
        self.policy = policy or AntiSpamPolicy()
        self.clock = clock
        now = clock()
        self._users: dict[int, UserActivity] = {}
        self._global = TokenBucket(self.policy.global_burst, now)
        self._notices = TokenBucket(3, now)
        self._next_cleanup = now
        self.active_heavy = 0

    def _prune(self, now: float) -> None:
        if now < self._next_cleanup:
            return
        self._next_cleanup = now + min(30, self.policy.idle_ttl)
        expired = [
            user_id for user_id, activity in self._users.items()
            if not activity.active and now - activity.last_seen >= self.policy.idle_ttl
            and now >= max(activity.blocked_until, activity.heavy_after, activity.notice_after)
        ]
        for user_id in expired:
            del self._users[user_id]

    def reject(self, user_id: int, reason: str, retry_after: float = 0) -> Rejection:
        now = self.clock()
        activity = self._users.get(user_id)
        notify = False
        if activity is None or now >= activity.notice_after:
            # Also bound replies across different users, not just one spammer.
            notify = self._notices.take(now, 3, 3) == 0
            if notify and activity is not None:
                activity.notice_after = now + self.policy.notice_seconds
        return Rejection(reason, max(0, ceil(retry_after)), notify)

    def begin(self, user_id: int) -> Rejection | None:
        now = self.clock()
        self._prune(now)
        activity = self._users.get(user_id)
        global_reserved = False
        if activity is None:
            if len(self._users) >= self.policy.max_users:
                return self.reject(user_id, "capacity", 10)
            retry = self._global.take(now, self.policy.global_burst, self.policy.global_refill_seconds)
            if retry:
                return self.reject(user_id, "capacity", retry)
            global_reserved = True
            activity = UserActivity(TokenBucket(self.policy.burst, now), now)
            self._users[user_id] = activity
        activity.last_seen = now
        if activity.blocked_until > now:
            return self.reject(user_id, "rate", activity.blocked_until - now)
        if activity.bucket.take(now, self.policy.burst, self.policy.refill_seconds):
            activity.blocked_until = now + self.policy.block_seconds
            return self.reject(user_id, "rate", self.policy.block_seconds)
        if activity.active:
            return self.reject(user_id, "busy", 1)
        if not global_reserved:
            retry = self._global.take(now, self.policy.global_burst, self.policy.global_refill_seconds)
            if retry:
                return self.reject(user_id, "capacity", retry)
        activity.active = True
        return None

    def finish(self, user_id: int) -> None:
        activity = self._users[user_id]
        activity.active = False
        activity.last_seen = self.clock()

    def begin_heavy(self, user_id: int, *, cooldown: bool = True) -> Rejection | None:
        activity = self._users[user_id]
        now = self.clock()
        if cooldown and activity.heavy_after > now:
            return self.reject(user_id, "heavy", activity.heavy_after - now)
        if self.active_heavy >= self.policy.max_heavy:
            return self.reject(user_id, "capacity", 1)
        if cooldown:
            activity.heavy_after = now + self.policy.heavy_interval
        self.active_heavy += 1
        return None

    def finish_heavy(self) -> None:
        self.active_heavy -= 1
