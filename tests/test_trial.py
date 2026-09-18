import datetime
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from cloud_auth import CloudAuthClient
from session_manager import SessionManager


class TrialTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        directory = Path(self.temp.name)
        self.manager = SessionManager(str(directory / "registry.json"))
        self.cloud = Mock()
        self.cloud.request_trial.side_effect = lambda cid, agent_id="": (True, {
            "license_key": "cloud-key-" + cid,
            "expires_at": (datetime.datetime.now() + datetime.timedelta(hours=48)).strftime("%Y-%m-%d %H:%M:%S"),
            "gateway": "https://trial.example.test"
        })
        self.cloud.verify_trial_license.return_value = True
        self.patcher = patch("session_manager.CloudAuthClient", return_value=self.cloud)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_first_claim_is_exactly_48_hours_and_repeat_does_not_extend(self):
        started = datetime.datetime.now()
        ok, _, session = self.manager.issue_free_trial("existing-conversation")
        self.assertTrue(ok)
        key = session["license_key"]
        claim = self.manager._load_registry()["trial_claims_20260918"]["existing-conversation"]
        expiry = datetime.datetime.strptime(claim["expires_at"], "%Y-%m-%d %H:%M:%S")
        self.assertAlmostEqual((expiry - started).total_seconds(), 48 * 3600, delta=2)
        ok, _, repeat = self.manager.issue_free_trial("existing-conversation")
        self.assertTrue(ok)
        self.assertEqual(key, repeat["license_key"])
        self.assertEqual(1, len(self.manager._load_registry()["licenses"]))
        self.cloud.request_trial.assert_called_once()
        self.assertTrue(self.manager.verify_session_authorized("existing-conversation")[0])
        self.cloud.verify_trial_license.return_value = False
        self.assertFalse(self.manager.verify_session_authorized("existing-conversation")[0])

    def test_existing_paid_entitlement_is_preserved(self):
        registry = self.manager._load_registry()
        registry["sessions"]["paid-conversation"] = {
            "status": "AUTHORIZED", "license_key": "paid-license", "bound_store": {"store_uid": "STORE-1"}
        }
        self.manager._save_registry(registry)
        ok, _, session = self.manager.issue_free_trial("paid-conversation")
        self.assertTrue(ok)
        self.assertEqual("paid-license", session["license_key"])
        self.assertEqual("STORE-1", session["bound_store"]["store_uid"])
        self.assertEqual(1, len(self.manager._load_registry()["trial_claims_20260918"]))

    def test_legacy_trial_user_gets_new_policy_and_missing_identity_is_rejected(self):
        registry = self.manager._load_registry()
        registry["licenses"]["old-trial"] = {
            "type": "RSA-FREE-TRIAL", "activated_sessions": ["old-conversation"],
            "expires_at": (datetime.datetime.now() + datetime.timedelta(hours=4)).strftime("%Y-%m-%d %H:%M:%S")
        }
        registry["sessions"]["old-conversation"] = {
            "status": "AUTHORIZED", "license_key": "old-trial", "license_name": "2天免费试用"
        }
        self.manager._save_registry(registry)
        ok, _, session = self.manager.issue_free_trial("old-conversation")
        self.assertTrue(ok)
        self.assertNotEqual("old-trial", self.manager._load_registry()["trial_claims_20260918"]["old-conversation"]["license_key"])
        self.assertNotEqual("old-trial", session["license_key"])
        ok, _, _ = self.manager.issue_free_trial("default-session")
        self.assertFalse(ok)

    def test_existing_paid_session_is_blocked_after_cloud_expiry(self):
        registry = self.manager._load_registry()
        registry["sessions"]["paid-conversation"] = {
            "status": "AUTHORIZED", "license_key": "paid-license"
        }
        self.manager._save_registry(registry)
        self.cloud.is_cloud_enabled.return_value = True
        self.cloud.verify_cloud_license.return_value = (False, "EXPIRED", {})
        ok, message, _ = self.manager.verify_session_authorized("paid-conversation")
        self.assertFalse(ok)
        self.assertIn("EXPIRED", message)


class CloudTrialClientTests(unittest.TestCase):
    def test_claim_and_online_verification_routes(self):
        client = CloudAuthClient(base_url="https://trial.example.test")
        client.session.post = Mock(return_value=Mock(
            status_code=200,
            json=lambda: {"ok": True, "free": True, "license_key": "code", "expires_at": "2026-09-20 10:00:00"}
        ))
        client.session.get = Mock(return_value=Mock(status_code=200, json=lambda: {"valid": True}))
        ok, data = client.request_trial("existing-cid")
        self.assertTrue(ok)
        self.assertEqual(data["gateway"], "https://trial.example.test")
        self.assertEqual(client.session.post.call_args.kwargs["json"]["mid"], "existing-cid")
        self.assertTrue(client.verify_trial_license("code", "existing-cid", data["gateway"]))
        self.assertEqual(client.session.get.call_args.kwargs["params"]["mid"], "existing-cid")

    def test_paid_cloud_expiry_and_network_failure_never_authorize(self):
        client = CloudAuthClient(base_url="https://trial.example.test")
        client.session.get = Mock(return_value=Mock(
            status_code=403, json=lambda: {"valid": False, "error": "License has expired"}
        ))
        valid, status, _ = client.verify_cloud_license("paid-code", "machine-1")
        self.assertFalse(valid)
        self.assertEqual(status, "EXPIRED")
        self.assertEqual(client.session.get.call_args.kwargs["params"], {"key": "paid-code", "mid": "machine-1"})
        client.session.get.side_effect = requests.Timeout()
        valid, status, _ = client.verify_cloud_license("paid-code", "machine-1")
        self.assertFalse(valid)
        self.assertEqual(status, "CLOUD_UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
