"""Email rendering and sending; the PT schedule; the sent log."""

from datetime import UTC, datetime

from vorpal.season.email import render_html, render_text, send
from vorpal.season.report import Report, Table
from vorpal.season.schedule import Due, SentLog, jobs_due

REPORT = Report(
    subject="Week 7 lineup: 2 changes",
    lines=["START Jahmyr Gibbs (26.8)", "SIT <Tuten>"],
    tables=[
        Table("Best", ("Slot", "Player"), [("RB", "Jahmyr Gibbs"), ("QB", "Maye")]),
        Table("Empty", ("A",), []),
    ],
)


def test_render_text_aligns_columns() -> None:
    text = render_text(REPORT)
    assert text.splitlines()[0] == "Week 7 lineup: 2 changes"
    assert "Slot  Player" in text
    assert "RB    Jahmyr Gibbs" in text
    assert "Empty\n(none)" in text


def test_render_html_escapes() -> None:
    page = render_html(REPORT)
    assert "SIT &lt;Tuten&gt;" in page
    assert "text-align:left'>Maye</td>" in page


class FakeSMTP:
    sent: list = []

    def __init__(self, host, port) -> None:
        self.host, self.port = host, port

    def __enter__(self):
        return self

    def __exit__(self, *a) -> None:
        return None

    def login(self, user, password) -> None:
        self.user = user

    def send_message(self, msg) -> None:
        FakeSMTP.sent.append((self.host, self.user, msg))


def test_send_builds_a_two_part_message() -> None:
    send(REPORT, ["a@x.com", "b@y.com"], "me@gmail.com", "pw", smtp=FakeSMTP)
    host, user, msg = FakeSMTP.sent[-1]
    assert host == "smtp.gmail.com" and user == "me@gmail.com"
    assert msg["To"] == "a@x.com, b@y.com"
    assert msg["Subject"] == "Week 7 lineup: 2 changes"
    assert [p.get_content_type() for p in msg.iter_parts()] == [
        "text/plain",
        "text/html",
    ]


def _utc(*a) -> datetime:
    return datetime(*a, tzinfo=UTC)


def test_tuesday_morning_pt_runs_waivers_in_pdt_and_pst() -> None:
    pdt = jobs_due(_utc(2026, 10, 20, 13, 45))  # Tue 06:45 PDT
    pst = jobs_due(_utc(2026, 11, 3, 14, 45))  # Tue 06:45 PST
    assert Due("waivers", True) in pdt and Due("waivers", True) in pst


def test_wednesday_lineup_always_other_days_only_if_changed() -> None:
    assert Due("lineup", True) in jobs_due(_utc(2026, 10, 21, 13, 45))
    assert Due("lineup", False) in jobs_due(_utc(2026, 10, 25, 15, 45))  # Sun 08:45


def test_trades_every_hour_and_nothing_else_at_night() -> None:
    assert jobs_due(_utc(2026, 10, 21, 9, 45)) == [Due("trades", False)]


def test_a_missed_slot_stays_due_for_its_pt_day(tmp_path) -> None:
    log = SentLog(tmp_path / "sent.json")
    late = jobs_due(_utc(2026, 10, 20, 15, 7), log)  # Tue 08:07 PDT
    assert [d.slot for d in late if d.job == "waivers"] == ["2026-10-20T06"]
    assert Due("waivers", True) not in jobs_due(_utc(2026, 10, 20, 12, 13))  # 05:13
    assert Due("waivers", True) not in jobs_due(_utc(2026, 10, 21, 7, 0))  # Wed 00:00


def test_a_recorded_slot_is_not_due_again(tmp_path) -> None:
    log = SentLog(tmp_path / "sent.json")
    log.record("slot:waivers", "2026-10-20T06")
    assert jobs_due(_utc(2026, 10, 20, 16, 45), log) == [Due("trades", False)]


def test_the_latest_lineup_slot_replaces_a_missed_one() -> None:
    due = jobs_due(_utc(2026, 10, 25, 19, 45))  # Sun 12:45 PDT; 08:00 and 11:00 passed
    assert [(d.job, d.slot) for d in due[1:]] == [("lineup", "2026-10-25T11")]


def test_sent_log_round_trip(tmp_path) -> None:
    path = tmp_path / "state" / "sent.json"
    log = SentLog(path)
    assert log.changed("lineup", "a")
    log.record("lineup", "a")
    again = SentLog(path)
    assert not again.changed("lineup", "a")
    assert again.changed("lineup", "b")
