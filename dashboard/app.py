"""Run from the checkout root with python -m streamlit run dashboard/app.py."""
from dataclasses import asdict
from datetime import date
from html import escape

import streamlit as st

from dashboard.services import SEASONS, load_report, report_statuses
from premfootballbot.manual_notebook import FIXTURE_STATUS, ODDS_STATUS, Notebook, NotebookError


def club(value):
    return value.replace("-", " ").title()


def season_label(year):
    return f"{year}–{str(year + 1)[-2:]}"


def fixture_label(fixture):
    return f"{club(fixture.home)} vs {club(fixture.away)} · {fixture.match_date}"


def table(rows):
    """Render bounded local values as text in a scrollable semantic table."""
    columns = tuple(rows[0])
    headings = "".join(f'<th scope="col">{escape(name)}</th>' for name in columns)
    body = "".join(
        "<tr>" + "".join(f"<td>{escape(str(row[key])) if row[key] is not None else '—'}</td>"
                         for key in columns) + "</tr>"
        for row in rows
    )
    st.html('<div style="overflow-x:auto"><table style="width:100%">'
            f"<thead><tr>{headings}</tr></thead><tbody>{body}</tbody></table></div>")


def saved(message):
    st.session_state["notice"] = message
    st.rerun()


def fixture_form(notebook, fixture=None):
    editing = fixture is not None
    key = f"fixture-{fixture.id}-{fixture.revision}" if editing else "new-fixture"
    with st.form(key, clear_on_submit=False):
        home_col, away_col = st.columns(2)
        home = home_col.text_input("Home club ID", fixture.home if editing else "", max_chars=80,
                                   placeholder="arsenal")
        away = away_col.text_input("Away club ID", fixture.away if editing else "", max_chars=80,
                                   placeholder="liverpool")
        season_col, date_col = st.columns(2)
        today = date.today()
        season = season_col.number_input("Season start year", 1992, 2099,
                                         fixture.season if editing else today.year - (today.month < 7), step=1)
        match_date = date_col.date_input("Fixture date", value=fixture.match_date if editing else None,
                                        min_value=date(1992, 7, 1), max_value=date(2100, 6, 30))
        kickoff = st.text_input("Claimed kickoff UTC (optional)", fixture.kickoff if editing else "",
                                max_chars=27, placeholder="YYYY-MM-DDTHH:MM:SSZ")
        if st.form_submit_button("Save correction" if editing else "Add fixture", type="primary"):
            identity = notebook.save_fixture(home=home, away=away, season=season, match_date=match_date,
                                             kickoff=kickoff, previous=fixture)
            st.session_state["selected_fixture"] = identity
            saved("Fixture revision saved." if editing else "Fixture available on your watchlist.")


def select_fixture(fixtures):
    by_id = {item.id: item for item in fixtures}
    ids = list(by_id)
    previous = st.session_state.get("selected_fixture")
    index = ids.index(previous) if previous in by_id else 0
    chosen = st.selectbox("Fixture", ids, index=index, format_func=lambda key: fixture_label(by_id[key]))
    st.session_state["selected_fixture"] = chosen
    return by_id[chosen]


def watchlist(notebook, fixtures):
    st.header("My Watchlist")
    st.caption("MANUAL_FIXTURE_UNVERIFIED · Fixture details are supplied by you.")
    with st.expander("Add a fixture", expanded=not fixtures):
        fixture_form(notebook)
    if not fixtures:
        st.info("Your watchlist is empty. Add two club IDs and a date to get started.")
        return
    table([
        {"Fixture": fixture_label(f), "Season": season_label(f.season), "Claimed UTC": f.kickoff or "Unknown",
         "Status": FIXTURE_STATUS, "Observations": f.observation_count, "Saved UTC": f.saved,
         "Last capture UTC": f.last_capture}
        for f in fixtures
    ])
    fixture = select_fixture(fixtures)
    st.caption(f"Fixture ID {fixture.id} · Revision {fixture.revision}")
    with st.expander("Correct selected fixture"):
        st.caption("Saving creates a new revision. Earlier quotes retain their original fixture details.")
        fixture_form(notebook, fixture)


def _form(results):
    return " ".join("W" if r.goals_for > r.goals_against else
                    "L" if r.goals_for < r.goals_against else "D" for r in results) or "Unavailable"


def team_panel(team):
    with st.container(border=True):
        st.subheader(club(team.team_id))
        st.caption(f"{team.status} · {team.overall.matches} eligible matches")
        if team.overall.matches:
            goals, conceded, points = st.columns(3)
            goals.metric("GF / match", f"{team.overall.goals_for_per_match:.2f}")
            conceded.metric("GA / match", f"{team.overall.goals_against_per_match:.2f}")
            points.metric("Points", team.overall.points)
        table([
            {"Sample": label, "Played": s.matches, "W": s.wins, "D": s.draws,
             "L": s.losses, "GF": s.goals_for, "GA": s.goals_against}
            for label, s in (("Overall", team.overall), ("Home", team.home), ("Away", team.away))
        ])
        st.text(f"Last 5 ({len(team.last_5)})   {_form(team.last_5)}")
        st.text(f"Last 10 ({len(team.last_10)})  {_form(team.last_10)}")


def historical(fixtures):
    st.header("Historical statistics")
    st.caption("RETROSPECTIVE_DESCRIPTIVE_ONLY · Reconstructed calendar dates. Historical availability and kickoff UTC are unknown.")
    if not fixtures:
        st.info("Add a watchlist fixture to compare its clubs.")
        return
    fixture = select_fixture(fixtures)
    source_col, date_col = st.columns(2)
    source_year = source_col.selectbox("Archive season", SEASONS, format_func=season_label,
                                       index=SEASONS.index(fixture.season) if fixture.season in SEASONS else None,
                                       key=f"archive-{fixture.id}-{fixture.revision}")
    analysis_date = date_col.date_input("Analysis date", fixture.match_date,
                                        key=f"analysis-{fixture.id}-{fixture.revision}")
    if source_year is None:
        st.info("Select an archive season. Coverage is limited to 2024–25 and 2025–26.")
        return
    if source_year != fixture.season:
        st.caption(f"Showing {season_label(source_year)} archive results for a {season_label(fixture.season)} watchlist fixture.")
    report = load_report(fixture.home, fixture.away, source_year, analysis_date)
    statuses = report_statuses(report)
    if "SOURCE_INVALID" in statuses:
        st.error(f"SOURCE_INVALID · The pinned archive could not be verified ({report.source_detail}).")
        return
    if "STALE_HISTORICAL_DATA" in statuses:
        st.warning("STALE_HISTORICAL_DATA · Results are too old for current-form analysis.")
    st.caption(" · ".join(statuses))
    home, away = st.columns(2)
    with home:
        team_panel(report.home)
    with away:
        team_panel(report.away)
    with st.expander("Source evidence and eligible results"):
        st.text(f"Repository  {report.source_repository}\nCommit      {report.source_commit}\n"
                f"Archive     {report.source_path} ({report.licence})\n"
                f"Cutoff      {report.eligible_through} ({report.embargo_days}-day embargo)\n"
                f"Last result {report.last_eligible_date or 'Unavailable'}\n"
                f"Included    {report.included_matches}\n"
                f"Excluded    {', '.join(f'{k} {n}' for k, n in report.exclusions)}")
        st.caption(f"{report.evidence_status} · Historical availability {report.historical_availability}")
        for team in (report.home, report.away):
            st.markdown(f"**{club(team.team_id)} · last eligible results**")
            if team.last_10:
                table([asdict(r) for r in team.last_10])
            else:
                st.caption("No eligible results for this club.")
    if report.computed_historical_standings:
        with st.expander("Computed historical standings"):
            st.caption("Results-only points and goal totals through the cutoff. Official deductions and tie-breaks are outside this table.")
            table([{"Club": club(team), "Played": s.matches, "Pts": s.points, "GD": s.goal_difference}
                   for team, s in report.computed_historical_standings])


def market(notebook, fixtures):
    st.header("AH notebook")
    st.caption("MANUAL_ODDS_UNVERIFIED · Claimed observation and local capture are separate timestamps.")
    if not fixtures:
        st.info("Add a watchlist fixture before recording a quote.")
        return
    fixture = select_fixture(fixtures)
    if not fixture.kickoff:
        st.info("TIMING_UNKNOWN · This fixture has no claimed kickoff.")
    rows = notebook.observations(fixture.id)
    corrections = {r["id"]: r for r in rows if r["revision"] == fixture.revision and not r["superseded"]}
    correction = st.selectbox("Correct an observation (optional)", list(corrections), index=None,
                              format_func=lambda key: f"#{key} · {corrections[key]['bookmaker']}",
                              key=f"correction-{fixture.id}-{fixture.revision}")
    current = corrections.get(correction, {})
    with st.form(f"quote-{fixture.id}-{fixture.revision}-{correction}"):
        a, b, c, d = st.columns(4)
        bookmaker = a.text_input("Bookmaker", current.get("bookmaker", ""), max_chars=100)
        side = b.selectbox("Selection", ("HOME", "AWAY"), index=int(current.get("side") == "AWAY"))
        line = c.text_input("Signed AH line", current.get("raw_line", ""), placeholder="-0.25", max_chars=24)
        odds = d.text_input("Decimal odds", current.get("raw_odds", ""), placeholder="1.95", max_chars=32)
        source = st.text_input("Source reference (optional)", current.get("source", ""), max_chars=240)
        claimed = st.text_input("Claimed observation UTC (optional)", current.get("claimed", ""), max_chars=27)
        invented = st.checkbox("Invented demonstration quote", value=bool(current.get("invented")))
        if st.form_submit_button("Save observation", type="primary"):
            identity = notebook.save_observation(fixture, bookmaker=bookmaker, side=side, line=line, odds=odds,
                                                 source=source, claimed=claimed, invented=invented,
                                                 replaces=correction)
            saved(f"Observation #{identity} recorded.")
    st.subheader("Saved observations")
    if not rows:
        st.info("No observations saved for this fixture yet.")
        return
    table([
        {"ID": r["id"], "Bookmaker": r["bookmaker"], "Side": r["side"], "AH": r["raw_line"],
         "Decimal odds": r["raw_odds"], "Exact odds": r["exact_odds"],
         "Label": "Invented demonstration" if r["invented"] else ODDS_STATUS,
         "Timing": r["timing"], "Revision": r["revision"], "Superseded": bool(r["superseded"])}
        for r in rows
    ])
    with st.expander("Observation timestamps, source and revision details"):
        table([
            {"ID": r["id"], "Claimed UTC": r["claimed"] or None, "Local capture UTC": r["captured"],
             "Fixture": f"{club(r['home'])} vs {club(r['away'])} · {r['match_date']}",
             "Claimed kickoff UTC": r["kickoff"] or None, "Revision": r["revision"],
             "Replaces": r["replaces"], "Source reference": r["source"]}
            for r in rows
        ])
    st.caption("Timing uses each observation’s saved fixture revision. Local capture does not establish bookmaker publication time.")


st.set_page_config(page_title="EPL Match Notebook", layout="wide")
st.html("""
<style>
[data-testid="stMainBlockContainer"] { padding-top: 2rem; padding-bottom: 2rem; }
#epl-match-notebook { font-size: 2rem; }
</style>
""")
st.title("EPL Match Notebook")
st.caption("Historical results and manual market observations")
section = st.segmented_control("Section", ("Watchlist", "Historical statistics", "AH notebook"),
                               default="Watchlist", label_visibility="collapsed")
if "notice" in st.session_state:
    st.success(st.session_state.pop("notice"))
try:
    notebook = Notebook()
    fixtures = notebook.fixtures()
    if section == "Historical statistics":
        historical(fixtures)
    elif section == "AH notebook":
        market(notebook, fixtures)
    else:
        watchlist(notebook, fixtures)
except NotebookError as exc:
    st.error(str(exc))
