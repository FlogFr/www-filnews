from io import StringIO
from unittest import mock

from django.core.management import call_command

from filnews.management.commands import analyze_news

from .helpers import NOW, DataDirTestCase, make_news


def fake_analyze(news):
    if news.id == "boom":
        raise ValueError("parser bug")
    news.tags = [f"Tag {news.id}"]
    news.analyzed_at = NOW
    return news


class AnalyzeCommandTests(DataDirTestCase):
    def test_parallel_analysis_saves_by_batch_and_survives_failures(self):
        self.add_news(*[make_news(f"n{i}") for i in range(30)], make_news("boom"))
        backend = mock.Mock(analyze=fake_analyze)
        backend.name = "heuristic"
        out = StringIO()
        with (
            mock.patch.object(analyze_news, "get_analyzer", return_value=backend),
            mock.patch.object(
                self.store, "transaction", wraps=self.store.transaction
            ) as transaction,
            self.assertLogs("filnews.management.commands.analyze_news", "ERROR"),
        ):
            call_command("analyze_news", "--workers", "4", stdout=out)

        self.assertEqual(transaction.call_count, 2)  # 25 + 5, not 30 writes.
        self.assertEqual(self.store.get("n7").tags, ["Tag n7"])
        self.assertIsNone(self.store.get("boom").analyzed_at)
        self.assertIn("1 failure", out.getvalue())
