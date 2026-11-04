"""Fail closed when a missed Realt collection cannot notify the owner."""
import importlib.util
import os
from datetime import datetime, timezone
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / ".github" / "scripts" / "telegram_watchdog.py"
spec = importlib.util.spec_from_file_location("realt_telegram_watchdog", SCRIPT)
watchdog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watchdog)


class WatchdogDeliveryTests(TestCase):
    def test_missing_telegram_configuration_fails_stale_check(self):
        with patch.object(watchdog, "last_due_slot", return_value=datetime(2026, 11, 4, 12, tzinfo=timezone.utc)), \
             patch.object(watchdog, "latest_snapshot", return_value="2026-11-03T13:37:41Z"), \
             patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "", "TELEGRAM_CHAT_ID": ""}), \
             patch.object(watchdog, "STATE") as state:
            state.exists.return_value = False
            with self.assertRaisesRegex(RuntimeError, "not delivered"):
                watchdog.main()

    def test_fresh_snapshot_does_not_require_telegram(self):
        with patch.object(watchdog, "last_due_slot", return_value=datetime(2026, 11, 4, 12, tzinfo=timezone.utc)), \
             patch.object(watchdog, "latest_snapshot", return_value="2026-11-04T12:30:00Z"), \
             patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "", "TELEGRAM_CHAT_ID": ""}), \
             patch.object(watchdog, "STATE") as state:
            watchdog.main()
            state.exists.assert_not_called()
