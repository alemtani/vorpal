"""`vorpal season` wiring, with the fake league and a fake SMTP."""

import io
from datetime import UTC, datetime

from vorpal import cli as draft_cli
from vorpal.errors import PlatformError
from vorpal.season import cli
from vorpal.season.inbox import Offer

ENV = {"SLEEPER_LEAGUE_ID": "L", "SLEEPER_USER_ID": "me"}


class SMTP:
    sent: list = []

    def __init__(self, host, port) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a) -> None:
        return None

    def login(self, user, password) -> None:
        self.user = user

    def send_message(self, msg) -> None:
        SMTP.sent.append((self.user, msg["To"], msg["Subject"]))


def run(argv, make_source, tmp_path, env=None, source=None, when=None):
    out = io.StringIO()
    code = cli.main(
        [*argv, "--sims", "40"] if argv[0] != "fit" else argv,
        env={**ENV, "VORPAL_STATE_DIR": str(tmp_path), **(env or {})},
        source=source or make_source(),
        now=lambda: when or datetime(2026, 10, 21, 9, 45, tzinfo=UTC),
        out=out,
        smtp=SMTP,
    )
    return code, out.getvalue()


def test_lineup_prints_without_sending(make_source, tmp_path) -> None:
    code, out = run(["lineup"], make_source, tmp_path)
    assert code == 0
    assert out.startswith("Week 7 lineup: 2 changes")
    assert "Win chance vs Nuyen" in out


def test_lineup_without_an_opponent(make_source, tmp_path) -> None:
    src = make_source()
    src.matchups = lambda league, week: []
    code, out = run(["lineup"], make_source, tmp_path, source=src)
    assert code == 0 and "Win chance" not in out


def test_send_emails_and_records(make_source, tmp_path) -> None:
    env = {"EMAIL_TO": "a@x.com, b@y.com", "GMAIL_APP_PASSWORD": "pw"}
    code, out = run(["lineup", "--send"], make_source, tmp_path, env=env)
    assert code == 0
    assert SMTP.sent[-1][:2] == ("a@x.com", "a@x.com, b@y.com")
    assert "lineup: sent to 2 address(es)" in out
    assert (tmp_path / "sent.json").exists()


def test_send_without_mail_settings_is_refused(make_source, tmp_path, capsys) -> None:
    code, _ = run(["lineup", "--send"], make_source, tmp_path)
    assert code == 2
    assert "EMAIL_TO" in capsys.readouterr().err


def test_missing_league_is_refused(make_source, tmp_path, capsys) -> None:
    out = io.StringIO()
    code = cli.main(["lineup"], env={}, source=make_source(), out=out)
    assert code == 2
    assert "SLEEPER_LEAGUE_ID" in capsys.readouterr().err


def test_waivers(make_source, tmp_path) -> None:
    code, out = run(["waivers"], make_source, tmp_path)
    assert code == 0 and out.startswith("Waivers:")


def test_trade_by_name(make_source, tmp_path) -> None:
    argv = ["trade", "--give", "Breece Hall, Kyle Pitts", "--get", "Josh Jacobs"]
    code, out = run(argv, make_source, tmp_path)
    assert code == 0
    assert out.startswith("Trade from Rohan312: DECLINE")
    assert "you give 3514, get 2733" in out


def test_trade_with_a_free_agent(make_source, tmp_path) -> None:
    argv = ["trade", "--give", "Dameon Pierce", "--get", "RJ Harvey"]
    code, out = run(argv, make_source, tmp_path)
    assert code == 0 and "free agency offers" in out


def test_trade_needs_both_sides(make_source, tmp_path, capsys) -> None:
    code, _ = run(["trade", "--give", "Kyle Pitts"], make_source, tmp_path)
    assert code == 2
    assert "--give and --get" in capsys.readouterr().err


def test_trade_unknown_name(make_source, tmp_path, capsys) -> None:
    argv = ["trade", "--give", "Nobody Real", "--get", "Josh Jacobs"]
    code, _ = run(argv, make_source, tmp_path)
    assert code == 2
    assert "no single player named 'Nobody Real'" in capsys.readouterr().err


def test_trade_of_a_player_you_do_not_own(make_source, tmp_path, capsys) -> None:
    argv = ["trade", "--give", "Josh Jacobs", "--get", "Kyle Pitts"]
    code, _ = run(argv, make_source, tmp_path)
    assert code == 2
    assert "not on your roster" in capsys.readouterr().err


def test_name_tie_prefers_the_rostered_player(make_source, tmp_path) -> None:
    src = make_source()
    real = src.players

    def players():
        out = real()
        out["dupe"] = {"full_name": "Kyle Pitts", "position": "TE", "team": "KC"}
        return out

    src.players = players
    argv = ["trade", "--give", "Kyle Pitts", "--get", "Josh Jacobs"]
    code, out = run(argv, make_source, tmp_path, source=src)
    assert code == 0


def test_trades_is_off_without_a_token(make_source, tmp_path) -> None:
    code, out = run(["trades"], make_source, tmp_path)
    assert code == 0 and "inbox watch is off" in out


def test_trades_reviews_each_new_offer_once(make_source, tmp_path, monkeypatch) -> None:
    offer = Offer(id="t1", partner_roster=10, give=["hall", "pitts"], get=["jacobs"])
    monkeypatch.setattr(cli.inbox, "pending_offers", lambda *a: [offer])
    env = {"SLEEPER_TOKEN": "tok", "EMAIL_TO": "a@x.com", "GMAIL_APP_PASSWORD": "p"}
    code, out = run(["trades", "--send"], make_source, tmp_path, env=env)
    assert code == 0 and "Trade from Rohan312: DECLINE" in out
    code, out = run(["trades", "--send"], make_source, tmp_path, env=env)
    assert "trade:t1: unchanged since last send" in out


def test_trades_with_no_offers(make_source, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(cli.inbox, "pending_offers", lambda *a: [])
    code, out = run(["trades"], make_source, tmp_path, env={"SLEEPER_TOKEN": "t"})
    assert code == 0 and out == ""


def test_rejected_token_warns_once(make_source, tmp_path, monkeypatch) -> None:
    def rejected(*a):
        raise PlatformError("POST https://sleeper.com/graphql: 401")

    monkeypatch.setattr(cli.inbox, "pending_offers", rejected)
    env = {"SLEEPER_TOKEN": "old", "EMAIL_TO": "a@x.com", "GMAIL_APP_PASSWORD": "p"}
    code, out = run(["trades", "--send"], make_source, tmp_path, env=env)
    assert code == 0 and "Sleeper token rejected" in out
    code, out = run(["trades", "--send"], make_source, tmp_path, env=env)
    assert "trades-token: unchanged since last send" in out
    monkeypatch.setattr(cli.inbox, "pending_offers", lambda *a: [])
    run(["trades", "--send"], make_source, tmp_path, env=env)
    monkeypatch.setattr(cli.inbox, "pending_offers", rejected)
    code, out = run(["trades", "--send"], make_source, tmp_path, env=env)
    assert "Sleeper token rejected" in out


def test_auto_runs_what_is_due(make_source, tmp_path) -> None:
    tue = datetime(2026, 10, 20, 13, 45, tzinfo=UTC)
    code, out = run(["auto"], make_source, tmp_path, when=tue)
    assert code == 0 and "Waivers:" in out and "inbox watch is off" in out
    wed = datetime(2026, 10, 21, 13, 45, tzinfo=UTC)
    code, out = run(["auto"], make_source, tmp_path, when=wed)
    assert "Week 7 lineup" in out


def test_auto_only_if_changed_lineup(make_source, tmp_path) -> None:
    env = {"EMAIL_TO": "a@x.com", "GMAIL_APP_PASSWORD": "p"}
    sun = datetime(2026, 10, 25, 15, 45, tzinfo=UTC)
    run(["auto", "--send"], make_source, tmp_path, env=env, when=sun)
    code, out = run(["auto", "--send"], make_source, tmp_path, env=env, when=sun)
    assert "Week 7 lineup" not in out and "lineup:" not in out
    later = datetime(2026, 10, 25, 18, 45, tzinfo=UTC)  # Sun 11:45, the next slot
    code, out = run(["auto", "--send"], make_source, tmp_path, env=env, when=later)
    assert "lineup: unchanged since last send" in out


def test_platform_error_exits_2(make_source, tmp_path, capsys) -> None:
    src = make_source()

    def boom():
        raise PlatformError("Sleeper down")

    src.state = boom
    code, _ = run(["lineup"], make_source, tmp_path, source=src)
    assert code == 2
    assert "Sleeper down" in capsys.readouterr().err


def test_fit_needs_a_season(make_source, tmp_path, capsys) -> None:
    code, _ = run(["fit"], make_source, tmp_path)
    assert code == 2 and "--season" in capsys.readouterr().err


def test_fit_prints_tables(make_source, tmp_path) -> None:
    code, out = run(["fit", "--season", "2026"], make_source, tmp_path)
    assert code == 0 and "Half-life" in out


def test_draft_cli_routes_season(monkeypatch) -> None:
    seen = {}
    monkeypatch.setattr(
        "vorpal.season.cli.main", lambda argv: seen.setdefault("argv", argv) and 0
    )
    monkeypatch.setattr(draft_cli, "load_dotenv", lambda path, env: ())
    assert draft_cli.main(["season", "lineup"]) == 0
    assert seen["argv"] == ["lineup"]


def test_token_near_expiry_warns_once(make_source, tmp_path, monkeypatch) -> None:
    import base64
    import json

    exp = int(datetime(2026, 10, 22, tzinfo=UTC).timestamp())
    body = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode()
    env = {
        "SLEEPER_TOKEN": f"h.{body}.s",
        "EMAIL_TO": "a@x.com",
        "GMAIL_APP_PASSWORD": "p",
    }
    monkeypatch.setattr(cli.inbox, "pending_offers", lambda *a: [])
    code, out = run(["trades", "--send"], make_source, tmp_path, env=env)
    assert "Sleeper token expires 2026-10-22 00:00 UTC" in out
    code, out = run(["trades", "--send"], make_source, tmp_path, env=env)
    assert "trades-expiry: unchanged since last send" in out
