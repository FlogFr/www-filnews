from datetime import UTC, date, datetime

from django.test import SimpleTestCase
from django.utils import translation

from filnews.dates import format_date


class FormatDateTests(SimpleTestCase):
    def setUp(self):
        translation.activate("fr")
        self.addCleanup(translation.deactivate)

    def test_first_day_of_month_is_1er(self):
        self.assertEqual(format_date(date(2026, 11, 1), "j F Y"), "1er novembre 2026")
        self.assertEqual(format_date(date(2026, 11, 2), "j F Y"), "2 novembre 2026")
        self.assertEqual(
            format_date(date(2026, 11, 1), "l j F Y"), "dimanche 1er novembre 2026"
        )

    def test_aware_datetime_uses_local_time(self):
        # 31 October 23:30 UTC is 1 November 00:30 in Paris.
        moment = datetime(2026, 10, 31, 23, 30, tzinfo=UTC)
        self.assertEqual(
            format_date(moment, "j F Y à H:i"), "1er novembre 2026 à 00:30"
        )

    def test_escaped_day_letter_is_kept(self):
        self.assertEqual(format_date(date(2026, 11, 1), r"\j j"), "j 1er")
