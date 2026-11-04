"""Optional in-process Streamlit smoke test. Runs without a browser or socket."""
from datetime import date
from importlib.util import find_spec
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


@unittest.skipUnless(find_spec("streamlit"), "Optional dashboard dependency is absent")
class DashboardSmokeTests(unittest.TestCase):
    def test_fixture_stale_archive_quote_and_restart(self):
        from streamlit.testing.v1 import AppTest

        script = Path(__file__).resolve().parents[1] / "dashboard" / "app.py"
        with TemporaryDirectory() as directory, patch.dict(
            "os.environ", {"PREMFOOTBALLBOT_NOTEBOOK_PATH": str(Path(directory) / "test.sqlite3")}
        ):
            ui = AppTest.from_file(str(script), default_timeout=20).run()
            self.assertFalse(ui.exception)
            self.assertIn("empty", ui.info[0].value)
            ui.text_input[0].set_value("arsenal")
            ui.text_input[1].set_value("liverpool")
            ui.number_input[0].set_value(2026)
            ui.date_input[0].set_value(date(2026, 11, 5))
            ui.button[0].click().run()
            self.assertFalse(ui.exception)
            self.assertTrue(ui.success)
            ui.get("segmented_control")[0].set_value("Historical statistics").run()
            self.assertFalse(ui.exception)
            self.assertIn("limited", ui.info[0].value)
            next(x for x in ui.selectbox if x.label == "Archive season").select(2025).run()
            self.assertFalse(ui.exception)
            self.assertIn("STALE_HISTORICAL_DATA", ui.warning[0].value)
            ui.get("segmented_control")[0].set_value("AH notebook").run()
            ui.text_input[0].set_value("Invented Example")
            ui.text_input[1].set_value("-0.25")
            ui.text_input[2].set_value("1.95")
            ui.checkbox[0].check()
            ui.button[0].click().run()
            self.assertFalse(ui.exception)
            self.assertTrue(ui.success)
            self.assertTrue(any("<td>39/20</td>" in item.proto.body for item in ui.get("html")))

            restarted = AppTest.from_file(str(script), default_timeout=20).run()
            self.assertFalse(restarted.exception)
            self.assertTrue(any("<td>1</td>" in item.proto.body for item in restarted.get("html")))
            restarted.get("segmented_control")[0].set_value("AH notebook").run()
            self.assertFalse(restarted.exception)
            self.assertTrue(any("<td>Invented demonstration</td>" in item.proto.body
                                for item in restarted.get("html")))
