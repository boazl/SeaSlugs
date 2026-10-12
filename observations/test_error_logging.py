from django.conf import settings
from django.test import TestCase


class ErrorLoggingTests(TestCase):
    def test_server_errors_are_written_to_the_console_log(self):
        # In production (DEBUG off) a 500 must leave its traceback in the host's log.
        logger = settings.LOGGING['loggers']['django.request']
        self.assertEqual(logger['level'], 'ERROR')
        self.assertIn('console', logger['handlers'])
        self.assertEqual(settings.LOGGING['handlers']['console']['class'], 'logging.StreamHandler')
