# mashpad/ratelimit.py — token-bucket rate limiter.
# Pure — no pygame imports; no calls to time.time() (time passed in).

from __future__ import annotations

from mashpad import config


class TokenBucket:
    """Continuous-refill token bucket.

    Starts full.  try_take(now) consumes one token and returns True, or
    returns False (and consumes nothing) when the bucket is empty.
    """

    def __init__(self, capacity: float, refill_per_s: float) -> None:
        self._capacity     = capacity
        self._refill_per_s = refill_per_s
        self._tokens       = float(capacity)   # starts full
        self._last_time: float | None = None   # wall time of last call

    def try_take(self, now: float) -> bool:
        """Attempt to consume one token.

        Refills proportionally to elapsed time since the last call, capped at
        capacity.  Returns True on success, False if no token available.
        """
        if self._last_time is not None:
            elapsed = now - self._last_time
            if elapsed > 0:
                self._tokens = min(
                    self._capacity,
                    self._tokens + elapsed * self._refill_per_s,
                )
        self._last_time = now

        if self._tokens >= 1.0:
            self._tokens -= 1.0
            return True
        return False
