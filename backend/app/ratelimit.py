"""In-memory rate limiting for the authentication endpoints (security audits F1, V3, V4, V5).

Layers:
* per client IP: a cap on *all* requests to /api/auth/login, /api/auth/register and /api/auth/change-password,
  applied in middleware before the body is parsed, so malformed requests are counted too;
* per account (normalised e-mail): after LOGIN_MAX_FAILURES failed logins in LOGIN_WINDOW seconds, every login
  for that account is refused with 429 until the oldest failure leaves the window (a cooldown, not a permanent lock);
* teacher invite codes: wrong codes are counted per IP and globally (all IPs);
* password changes: wrong current passwords are counted per user.

Atomicity (V3). An attempt first RESERVES a slot - under the lock, in one step: prune, check, append. The slow part
(bcrypt) runs outside the lock. A failed attempt keeps its reservation (it IS the recorded failure); a successful one
releases it or clears the key. Parallel requests therefore cannot exceed the limit: at most `limit` attempts are ever
in flight or recorded per window.

Bounded memory (V4). Every key remembers its window. A sweep drops keys whose newest event has expired (at most every
SWEEP_INTERVAL seconds, and whenever the table is full). The table never holds more than MAX_KEYS keys: when it is full
of live keys, a NEW key is refused (429) rather than evicting an existing one - eviction would let an attacker reset
someone's lockout by flooding the table.

Limitations (docs/PILOT_READINESS.md): counters live in this process's memory - they reset on restart and are not
shared between worker processes or servers (the pilot launcher runs exactly one process). The client address is
whatever the ASGI server provides; the pilot launcher (scripts/run_server.py) disables proxy-header rewriting unless
explicitly trusted proxies are configured (V1).
"""

from __future__ import annotations

import itertools
import threading
import time
from collections import deque

# Classroom-sized defaults: a whole class may share one IP address behind the school's NAT.
LOGIN_IP_LIMIT, LOGIN_IP_WINDOW = 60, 60  # login requests per IP per minute
REGISTER_IP_LIMIT, REGISTER_IP_WINDOW = 30, 600  # registration requests per IP per 10 minutes
PWCHANGE_IP_LIMIT, PWCHANGE_IP_WINDOW = 30, 600  # password-change requests per IP per 10 minutes
LOGIN_MAX_FAILURES, LOGIN_WINDOW = 5, 900  # failed logins per account per 15 minutes
PWCHANGE_MAX_FAILURES, PWCHANGE_WINDOW = 5, 900  # wrong current passwords per user per 15 minutes
INVITE_IP_LIMIT, INVITE_IP_WINDOW = 5, 3600  # wrong teacher invite codes per IP per hour
INVITE_GLOBAL_LIMIT, INVITE_GLOBAL_WINDOW = 20, 3600  # wrong teacher invite codes from all IPs per hour
MAX_KEYS = 50_000
SWEEP_INTERVAL = 60.0

IP_LIMITS = {
    "/api/auth/login": (LOGIN_IP_LIMIT, LOGIN_IP_WINDOW),
    "/api/auth/register": (REGISTER_IP_LIMIT, REGISTER_IP_WINDOW),
    "/api/auth/change-password": (PWCHANGE_IP_LIMIT, PWCHANGE_IP_WINDOW),
}


class RateLimiter:
    def __init__(self, clock=time.monotonic, max_keys: int = MAX_KEYS, sweep_interval: float = SWEEP_INTERVAL):
        self._clock = clock
        self._max_keys = max_keys
        self._sweep_interval = sweep_interval
        self._events: dict[str, tuple[float, deque[tuple[float, int]]]] = {}  # key -> (window, (time, token)...)
        self._lock = threading.Lock()
        self._tokens = itertools.count(1)
        self._last_sweep = clock()

    # -- internal, lock held -------------------------------------------------------------------
    def _sweep(self, now: float) -> None:
        for key in [k for k, (w, q) in self._events.items() if not q or q[-1][0] <= now - w]:
            del self._events[key]
        self._last_sweep = now

    def _live(self, key: str, window: float, now: float) -> deque[tuple[float, int]] | None:
        entry = self._events.get(key)
        if entry is None:
            return None
        q = entry[1]
        while q and q[0][0] <= now - window:
            q.popleft()
        if not q:
            del self._events[key]
            return None
        return q

    def _wait(self, q: deque, window: float, now: float) -> int:
        return max(1, int(q[0][0] + window - now + 0.999))

    def _reserve_locked(self, key: str, limit: int, window: float, now: float) -> tuple[int | None, int | None]:
        q = self._live(key, window, now)
        if q is not None and len(q) >= limit:
            return None, self._wait(q, window, now)
        if q is None:
            if len(self._events) >= self._max_keys:
                self._sweep(now)
                if len(self._events) >= self._max_keys:  # full of live keys: refuse the newcomer, never evict
                    return None, int(window)
            q = deque()
            self._events[key] = (window, q)
        token = next(self._tokens)
        q.append((now, token))
        return token, None

    def _maybe_sweep(self, now: float) -> None:
        if now - self._last_sweep >= self._sweep_interval:
            self._sweep(now)

    # -- public API ------------------------------------------------------------------------------
    def reserve(self, key: str, limit: int, window: float) -> tuple[int | None, int | None]:
        """Atomically check and take a slot. Returns (token, None) or (None, retry_after_seconds)."""
        with self._lock:
            now = self._clock()
            self._maybe_sweep(now)
            return self._reserve_locked(key, limit, window, now)

    def reserve_all(self, rules: list[tuple[str, int, float]]) -> tuple[list[tuple[str, int]] | None, int | None]:
        """Reserve a slot on every key, or on none (all-or-nothing, atomic)."""
        with self._lock:
            now = self._clock()
            self._maybe_sweep(now)
            taken: list[tuple[str, int]] = []
            for key, limit, window in rules:
                token, wait = self._reserve_locked(key, limit, window, now)
                if token is None:
                    for k, t in taken:
                        self._release_locked(k, t)
                    return None, wait
                taken.append((key, token))
            return taken, None

    def _release_locked(self, key: str, token: int) -> None:
        entry = self._events.get(key)
        if entry is None:
            return
        q = entry[1]
        for item in q:
            if item[1] == token:
                q.remove(item)
                break
        if not q:
            del self._events[key]

    def release(self, key: str, token: int) -> None:
        """Give a reservation back (the attempt succeeded and must not count)."""
        with self._lock:
            self._release_locked(key, token)

    def hit(self, key: str, limit: int, window: float) -> int | None:
        """Reserve and keep (pure request counting). Returns retry-after seconds when refused."""
        return self.reserve(key, limit, window)[1]

    def retry_after(self, key: str, limit: int, window: float) -> int | None:
        """Seconds until another event is allowed, or None if under the limit (read-only)."""
        with self._lock:
            now = self._clock()
            q = self._live(key, window, now)
            return self._wait(q, window, now) if q is not None and len(q) >= limit else None

    def record(self, key: str, window: float) -> None:
        """Record an event unconditionally (used to seed state in tests and for counting)."""
        with self._lock:
            now = self._clock()
            entry = self._events.setdefault(key, (window, deque()))
            entry[1].append((now, next(self._tokens)))

    def clear(self, key: str) -> None:
        with self._lock:
            self._events.pop(key, None)

    def reset(self) -> None:
        with self._lock:
            self._events.clear()

    def size(self) -> int:
        with self._lock:
            return len(self._events)


limiter = RateLimiter()
