"""Smoke tests: the data file is valid and every page renders without errors."""

import sqlite3
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from solar_ops import data

ROOT = Path(__file__).resolve().parents[1]
PAGES = ["views/overview.py", "views/performance.py", "views/anomalies.py",
         "views/data_quality.py", "views/diesel.py", "views/about.py"]


def test_shipped_data_file_loads():
    fd = data.load()
    assert set(fd.systems.system_id) == {1418, 1419, 1420}
    assert len(fd.hourly) == 78_840
    # Same total as the ETL project's backfill report: 497.9 MWh for 2017-2019.
    assert fd.hourly.energy_kwh.sum() / 1000 == pytest.approx(497.9, abs=0.1)


def test_missing_data_file_gives_a_clear_error(tmp_path):
    with pytest.raises(data.DataError, match="not found"):
        data.load(tmp_path / "nope.db")


def test_data_file_missing_a_table_is_rejected(tmp_path):
    path = tmp_path / "bad.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE systems (system_id INTEGER)")
    with pytest.raises(data.DataError, match="missing tables"):
        data.load(path)


@pytest.fixture(scope="module")
def app():
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    at.run()
    return at


@pytest.mark.parametrize("page", PAGES)
def test_every_page_renders(app, page):
    app.switch_page(page).run()
    assert not app.exception, app.exception
    assert app.title, "page has no title"


def test_no_systems_selected_shows_a_message(app):
    app.switch_page("views/overview.py").run()
    app.sidebar.multiselect[0].set_value([]).run()
    assert not app.exception
    assert any("Pick at least one system" in i.value for i in app.info)
    app.sidebar.multiselect[0].set_value([1418, 1419, 1420]).run()


def test_overview_kpis_for_2019(app):
    app.switch_page("views/overview.py").run()
    energy = next(m for m in app.metric if m.label == "Energy")
    assert energy.value == "166.4 MWh"
