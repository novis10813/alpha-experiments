import importlib
import tempfile
import unittest
from pathlib import Path


class ReportFrameworkTests(unittest.TestCase):
    def test_render_plotly_page_embeds_payload_and_stat_card_escapes_html(self):
        render_plotly_page = importlib.import_module("tasks.T01-orderbook-imbalance.framework").render_plotly_page
        stat_card = importlib.import_module("tasks.T01-orderbook-imbalance.framework").stat_card
        write_html_report = importlib.import_module("tasks.T01-orderbook-imbalance.framework").write_html_report

        html = render_plotly_page(
            "Title",
            "Subtitle",
            stat_card("<rows>", "1"),
            "<section></section>",
            "console.log(reportData.rows.length);",
            {"rows": [1]},
        )

        self.assertIn("&lt;rows&gt;", html)
        self.assertIn('"rows":[1]', html)
        self.assertIn("console.log", html)

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.html"
            write_html_report(object(), output, lambda _context: html)
            self.assertEqual(output.read_text(encoding="utf-8"), html)


if __name__ == "__main__":
    unittest.main()
