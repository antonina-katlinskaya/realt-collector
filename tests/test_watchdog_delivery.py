"""Fail closed when a missed Realt collection cannot notify the owner."""
import importlib.util
import os
import io,json
from datetime import timedelta
from datetime import datetime, timezone
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / ".github" / "scripts" / "telegram_watchdog.py"
spec = importlib.util.spec_from_file_location("realt_telegram_watchdog", SCRIPT)
watchdog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watchdog)


class WatchdogDeliveryTests(TestCase):
    def test_delegation_requires_a_recent_successful_canonical_monitor(self):
        now=datetime(2026,11,5,14,tzinfo=timezone.utc)
        base={'status':'completed','conclusion':'success','updated_at':'2026-11-05T13:50:00Z',
              'html_url':'https://github.com/antonina-katlinskaya/kufar-radar/actions/runs/123'}
        for changes,valid in [({},True),({'conclusion':'failure'},False),({'updated_at':'2026-11-04T13:50:00Z'},False),({'html_url':'https://example.com/not-owner'},False)]:
            response=io.StringIO(json.dumps({'workflow_runs':[{**base,**changes}]}))
            with patch.object(watchdog.urllib.request,'urlopen',return_value=response):
                if valid:self.assertEqual(watchdog.verify_owner_health_monitor(now),base['html_url'])
                else:
                    with self.assertRaises(RuntimeError):watchdog.verify_owner_health_monitor(now)

    def test_verified_delegation_does_not_send_or_claim_a_second_telegram(self):
        with patch.object(watchdog,'last_due_slot',return_value=datetime(2026,11,5,12,tzinfo=timezone.utc)), \
             patch.object(watchdog,'latest_snapshot',return_value='2026-11-04T13:00:00Z'), \
             patch.dict(os.environ,{'TELEGRAM_BOT_TOKEN':'','TELEGRAM_CHAT_ID':'','REALT_ALERT_ROUTE':'owner-health'}), \
             patch.object(watchdog,'STATE') as state, \
             patch.object(watchdog,'verify_owner_health_monitor',return_value='verified-owner-run') as monitor, \
             patch.object(watchdog.urllib.request,'urlopen') as send:
            state.exists.return_value=False
            watchdog.main();monitor.assert_called_once();send.assert_not_called();state.write_text.assert_not_called()

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

