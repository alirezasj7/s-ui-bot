"""Regression test: secret_box must not reuse the raw WEB_SECRET-derived key
used for session signing, and must stay backward compatible with secrets
encrypted under the old (pre-fix) key.

Before the fix, ``encrypt_secret``/``decrypt_secret`` used
``sha256(WEB_SECRET)`` directly as the Fernet key — the exact same root
material (modulo a different hash step) that ends up protecting session
cookies too. The fix derives a domain-separated subkey via HKDF with a
fixed ``info`` label, while still accepting the legacy key on decrypt so
already-encrypted reseller PasarGuard passwords are not bricked.
"""

from __future__ import annotations

import base64
import hashlib
import unittest
from unittest.mock import patch

from cryptography.fernet import Fernet

from app.services import secret_box


class SecretBoxKeySeparationTests(unittest.TestCase):
    def setUp(self):
        self._patch = patch.object(secret_box, "_root_secret", return_value=b"a-strong-web-secret-1234567890")
        self._patch.start()
        self.addCleanup(self._patch.stop)

    def test_new_key_differs_from_legacy_raw_sha256_key(self):
        secret = secret_box._root_secret()
        primary = secret_box._hkdf_fernet_key(secret)
        legacy = base64.urlsafe_b64encode(hashlib.sha256(secret).digest())
        self.assertEqual(legacy, secret_box._legacy_fernet_key(secret))
        self.assertNotEqual(primary, legacy)

    def test_round_trip_uses_new_key(self):
        token = secret_box.encrypt_secret("super-secret-password")
        self.assertIsNotNone(token)
        # Must decrypt with the primary (HKDF) key, not just the legacy one.
        primary_key = secret_box._fernet_keys()[0]
        plain = Fernet(primary_key).decrypt(token.encode("ascii")).decode("utf-8")
        self.assertEqual(plain, "super-secret-password")
        self.assertEqual(secret_box.decrypt_secret(token), "super-secret-password")

    def test_legacy_ciphertext_still_decrypts(self):
        secret = secret_box._root_secret()
        legacy_key = secret_box._legacy_fernet_key(secret)
        legacy_token = Fernet(legacy_key).encrypt(b"old-reseller-pg-password").decode("ascii")

        # Simulates a secret encrypted before this fix shipped.
        plain = secret_box.decrypt_secret(legacy_token)
        self.assertEqual(plain, "old-reseller-pg-password")

    def test_garbage_token_returns_none(self):
        self.assertIsNone(secret_box.decrypt_secret("not-a-valid-fernet-token"))
        self.assertIsNone(secret_box.decrypt_secret(""))
        self.assertIsNone(secret_box.decrypt_secret(None))


if __name__ == "__main__":
    unittest.main()
