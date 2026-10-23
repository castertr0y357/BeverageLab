"""Tests for static files serving under production conditions."""
from django.test import SimpleTestCase, Client, override_settings


class StaticFilesServingTest(SimpleTestCase):
    """Verify that static files are properly served in production mode with WhiteNoise."""

    @override_settings(DEBUG=False)
    def test_css_served_with_correct_mime_type_in_production(self) -> None:
        """Verify CSS assets return 200 and text/css content-type when DEBUG=False."""
        client = Client()
        response = client.get('/static/css/style.css')
        self.assertEqual(response.status_code, 200)
        content_type = response.headers.get('Content-Type', '')
        self.assertIn('text/css', content_type)

    @override_settings(DEBUG=False)
    def test_javascript_served_with_correct_mime_type_in_production(self) -> None:
        """Verify JavaScript assets return 200 and javascript content-type when DEBUG=False."""
        client = Client()
        response = client.get('/static/js/core_utils.js')
        self.assertEqual(response.status_code, 200)
        content_type = response.headers.get('Content-Type', '')
        self.assertTrue('javascript' in content_type or 'application/x-javascript' in content_type)
