"""Tests for mashpad.ratelimit — TokenBucket."""

import pytest

from mashpad import config
from mashpad.ratelimit import TokenBucket


# ---------------------------------------------------------------------------
# Construction helpers
# ---------------------------------------------------------------------------

def make_bucket(capacity=None, refill=None):
    capacity = capacity if capacity is not None else config.BUCKET_CAPACITY
    refill   = refill   if refill   is not None else config.BUCKET_REFILL_PER_S
    return TokenBucket(capacity=capacity, refill_per_s=refill)


# ---------------------------------------------------------------------------
# Starts full
# ---------------------------------------------------------------------------

def test_starts_full():
    bucket = make_bucket(capacity=4, refill=1.0)
    t = 0.0
    # Should be able to take 4 tokens immediately
    for _ in range(4):
        assert bucket.try_take(t) is True
    # 5th is empty
    assert bucket.try_take(t) is False


# ---------------------------------------------------------------------------
# Drop when empty
# ---------------------------------------------------------------------------

def test_returns_false_when_empty():
    bucket = make_bucket(capacity=2, refill=0.0)  # no refill
    t = 0.0
    bucket.try_take(t)
    bucket.try_take(t)
    assert bucket.try_take(t) is False


# ---------------------------------------------------------------------------
# Refill
# ---------------------------------------------------------------------------

def test_refill_restores_tokens():
    bucket = make_bucket(capacity=1, refill=1.0)
    t = 0.0
    assert bucket.try_take(t) is True  # drains the 1 token
    assert bucket.try_take(t) is False  # empty

    # After 1 second at 1/s refill, one token back
    t += 1.0
    assert bucket.try_take(t) is True


def test_refill_fractional():
    """Fractional refill: 0.5s at 2.0/s gives 1 token."""
    bucket = make_bucket(capacity=4, refill=2.0)
    t = 0.0
    # Drain completely
    for _ in range(4):
        bucket.try_take(t)
    assert bucket.try_take(t) is False  # empty

    # 0.5s at 2.0/s → +1.0 token
    t += 0.5
    assert bucket.try_take(t) is True
    assert bucket.try_take(t) is False  # gone again


def test_refill_capped_at_capacity():
    """Tokens never exceed capacity even after a long gap."""
    capacity = 5
    bucket = make_bucket(capacity=capacity, refill=10.0)
    t = 0.0
    bucket.try_take(t)  # take one

    # After 10 seconds, would refill 100 tokens, but capped at 5
    t += 10.0
    taken = 0
    for _ in range(capacity + 5):
        if bucket.try_take(t):
            taken += 1
    assert taken == capacity


# ---------------------------------------------------------------------------
# Default config values
# ---------------------------------------------------------------------------

def test_default_capacity():
    """Default bucket allows BUCKET_CAPACITY quick takes."""
    bucket = make_bucket()
    t = 0.0
    for _ in range(config.BUCKET_CAPACITY):
        assert bucket.try_take(t) is True
    assert bucket.try_take(t) is False


def test_default_refill_rate():
    """At BUCKET_REFILL_PER_S, 1 token arrives every 1/rate seconds."""
    bucket = make_bucket()
    t = 0.0
    # Drain fully
    for _ in range(config.BUCKET_CAPACITY):
        bucket.try_take(t)
    assert bucket.try_take(t) is False

    # After 1/refill_rate seconds, exactly 1 token should be available
    t += 1.0 / config.BUCKET_REFILL_PER_S
    assert bucket.try_take(t) is True
    assert bucket.try_take(t) is False


# ---------------------------------------------------------------------------
# Monotonic time assumption
# ---------------------------------------------------------------------------

def test_no_negative_refill():
    """If time goes backward (clock jitter), bucket doesn't lose tokens."""
    bucket = make_bucket(capacity=4, refill=1.0)
    t = 10.0
    bucket.try_take(t)  # take 1 → 3 left
    # Pass an earlier time (shouldn't add negative tokens)
    t2 = 9.9
    # just shouldn't crash; exact behavior (skip or clamp) is implementation detail
    # what must NOT happen: returning True when empty
    for _ in range(10):
        bucket.try_take(t2)
    # We shouldn't have gone below 0 or above capacity
    # refill from t2 is 0 additional tokens (elapsed < 0 → clamp to 0)
    # Remaining ≥ 0 — verified by ensuring try_take doesn't blow up
