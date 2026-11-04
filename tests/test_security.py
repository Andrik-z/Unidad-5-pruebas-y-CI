from datetime import UTC, datetime, timedelta

from src.security import can_cancel


def test_owner_within_24h():
    now = datetime.now(UTC)
    assert can_cancel("NEW", 1, 1, False, now - timedelta(hours=1), now)

def test_stranger_denied():
    now = datetime.now(UTC)
    assert not can_cancel("NEW", 1, 2, False, now, now)

def test_shipped_denied_even_admin():
    now = datetime.now(UTC)
    assert not can_cancel("SHIPPED", 1, 1, True, now, now)

def test_expired_denied():
    now = datetime.now(UTC)
    assert not can_cancel("NEW", 1, 1, False, now - timedelta(hours=25), now)

NOW = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)

def test_admin_cancels_new_order_of_other_user():
    assert can_cancel("NEW", 1, 99, True, NOW - timedelta(days=10), NOW)

def test_owner_denied_at_exactly_24h():
    assert not can_cancel("NEW", 1, 1, False, NOW - timedelta(hours=24), NOW)

def test_owner_allowed_just_before_24h():
    assert can_cancel("NEW", 1, 1, False, NOW - timedelta(hours=23, minutes=59), NOW)

def test_default_now_is_used_when_not_given():
    created = datetime.now(UTC)
    assert can_cancel("NEW", 1, 1, False, created)  # cubre la rama now=None