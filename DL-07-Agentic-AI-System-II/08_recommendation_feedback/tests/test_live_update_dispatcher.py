import pytest
from app.live_update import dispatch_notification

def test_dispatch_notification_without_keys_logs_noop():
    success = dispatch_notification(
        user_id="user-123",
        message="Risk level updated to HIGH",
        channel="sms",
    )
    assert success is True
