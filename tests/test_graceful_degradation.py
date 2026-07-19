"""
Regression test for a real production bug found on 2026-07-19: the app
crashed entirely and refused to start if Snowflake was unreachable (e.g.
during the account lockout encountered while debugging deployment),
because service initialization happened inside a block that raised on
failure. This violates the assignment's explicit graceful degradation
requirement - a health check should still succeed, and user-facing
requests should get a clear error message, not a hard crash.

These tests mock out the anthropic/snowflake packages so they can run
without real credentials or network access.
"""
import sys
import unittest
from unittest.mock import MagicMock

# Stub external packages before importing app, since they may not be
# installed in every test environment and we don't want real network
# calls in a unit test.
sys.modules.setdefault('anthropic', MagicMock())
sys.modules.setdefault('snowflake', MagicMock())
sys.modules.setdefault('snowflake.connector', MagicMock())
sys.modules.setdefault('snowflake.connector.errors', MagicMock())

import services.chat_service as chat_service_module


class FailingChatService:
    """Simulates ChatService.__init__ raising, exactly like it did when
    the real Snowflake account was locked."""
    def __init__(self):
        raise Exception("Simulated: Your user account has been temporarily locked.")


class TestGracefulDegradation(unittest.TestCase):
    def setUp(self):
        # Force ChatService construction to fail, same as a real Snowflake
        # outage would, then import app fresh so it picks up the failure.
        self._real_chat_service = chat_service_module.ChatService
        chat_service_module.ChatService = FailingChatService

        if 'app' in sys.modules:
            del sys.modules['app']
        import app as app_module
        self.app_module = app_module
        self.client = app_module.app.test_client()

    def tearDown(self):
        chat_service_module.ChatService = self._real_chat_service

    def test_app_starts_despite_failed_service_init(self):
        """The core bug: this used to raise and prevent the app from
        starting at all under gunicorn."""
        self.assertIsNone(self.app_module.chat_service)
        self.assertIsNone(self.app_module.data_validator)

    def test_health_check_still_succeeds(self):
        """The health endpoint should reflect that the process is alive,
        even if a downstream dependency is down."""
        response = self.client.get('/health')
        self.assertEqual(response.status_code, 200)

    def test_chat_endpoint_returns_clear_error_not_a_crash(self):
        """User-facing requests should get a clean, specific error
        instead of an unhandled AttributeError/500."""
        response = self.client.post(
            '/api/chat',
            json={'message': 'What is the population of California?'}
        )
        self.assertEqual(response.status_code, 503)
        data = response.get_json()
        self.assertIn('trouble connecting', data['message'].lower())


if __name__ == '__main__':
    unittest.main()
