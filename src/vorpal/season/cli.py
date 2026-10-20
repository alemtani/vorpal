"""`vorpal season <job>`. Wiring only; every number comes from a module."""

from __future__ import annotations

import argparse
import os
import smtplib
import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO

from vorpal.errors import UserRefusal, VorpalError
from vorpal.season import email, inbox
from vorpal.season.context import Season, build_season
from vorpal.season.fetch import Source
from vorpal.season.fit import backtest
from vorpal.season.lineup import lineup_report
from vorpal.season.report import Report
from vorpal.season.schedule import SentLog, jobs_due
from vorpal.season.trade import trade_report
from vorpal.season.vendors import normalize_name
from vorpal.season.waivers import median_winning_bid, waiver_report

DEFAULT_SIMS = 1500
DEFAULT_STATE = Path(".season-state")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="vorpal season")
    p.add_argument(
        "job", choices=["lineup", "waivers", "trade", "trades", "auto", "fit"]
    )
    p.add_argument("--send", action="store_true", help="email it (default: print)")
    p.add_argument("--week", type=int, help="override the current NFL week")
    p.add_argument("--sims", type=int, default=DEFAULT_SIMS)
    p.add_argument("--give", default="", help="trade: your players, comma separated")
    p.add_argument("--get", default="", help="trade: their players, comma separated")
    p.add_argument("--season", type=int, help="fit: the season to backtest")
    return p


class Config:
    def __init__(self, env: Mapping[str, str]) -> None:
        self.league_id = env.get("SLEEPER_LEAGUE_ID", "")
        self.user_id = env.get("SLEEPER_USER_ID", "")
        self.to = [a.strip() for a in env.get("EMAIL_TO", "").split(",") if a.strip()]
        self.sender = env.get("EMAIL_FROM") or (self.to[0] if self.to else "")
        self.password = env.get("GMAIL_APP_PASSWORD", "")
        self.token = env.get("SLEEPER_TOKEN", "")
        self.state = Path(env.get("VORPAL_STATE_DIR") or DEFAULT_STATE)

    def require_league(self) -> None:
        if not (self.league_id and self.user_id):
            raise UserRefusal("set SLEEPER_LEAGUE_ID and SLEEPER_USER_ID")

    def require_mail(self) -> None:
        if not (self.to and self.password):
            raise UserRefusal("set EMAIL_TO and GMAIL_APP_PASSWORD to --send")


def find_player(s: Season, name: str) -> str:
    """Sleeper id for a typed name. Rostered players win a tie."""
    want = normalize_name(name)
    hits = [
        pid
        for pid, p in s.players.items()
        if p.get("team") and normalize_name(p.get("full_name", "")) == want
    ]
    rostered = {q for r in s.rosters for q in r.get("players") or []}
    if len(hits) > 1:
        hits = [h for h in hits if h in rostered] or hits
    if len(hits) != 1:
        raise UserRefusal(f"no single player named {name!r} ({len(hits)} matches)")
    return hits[0]


def _names(s: Season, text: str) -> list[str]:
    return [find_player(s, n) for n in text.split(",") if n.strip()]


def market(source: Source, s: Season) -> dict[str, float]:
    qbs = 2 if "SUPER_FLEX" in s.slots else 1
    teams = int(s.league.get("total_rosters") or 10)
    rows = source.fantasycalc(teams, qbs, s.scoring.get("rec", 0.0))
    return {
        str(r["player"].get("sleeperId")): r["value"]
        for r in rows
        if r.get("player", {}).get("sleeperId")
    }


class Runner:
    def __init__(
        self,
        args: argparse.Namespace,
        cfg: Config,
        source: Source,
        out: TextIO,
        smtp: Callable,
    ) -> None:
        self.args, self.cfg, self.source, self.out, self.smtp = (
            args,
            cfg,
            source,
            out,
            smtp,
        )
        self.log = SentLog(cfg.state / "sent.json")
        self._season: Season | None = None

    @property
    def season(self) -> Season:
        if self._season is None:
            self.cfg.require_league()
            self._season = build_season(
                self.source, self.cfg.league_id, self.cfg.user_id, self.args.week
            )
        return self._season

    def deliver(self, job: str, report: Report, always: bool) -> None:
        if not always and not self.log.changed(job, report.key):
            print(f"{job}: unchanged since last send", file=self.out)
            return
        print(email.render_text(report), file=self.out)
        if self.args.send:
            self.cfg.require_mail()
            email.send(
                report, self.cfg.to, self.cfg.sender, self.cfg.password, self.smtp
            )
            self.log.record(job, report.key)
            print(f"{job}: sent to {len(self.cfg.to)} address(es)", file=self.out)

    def lineup(self, always: bool = True) -> None:
        s = self.season
        games = self.source.matchups(self.cfg.league_id, s.week)
        mine = next((m for m in games if m["roster_id"] == s.me["roster_id"]), None)
        opp = next(
            (
                m
                for m in games
                if mine
                and m.get("matchup_id") == mine.get("matchup_id")
                and m["roster_id"] != mine["roster_id"]
            ),
            None,
        )
        if opp is None:
            report = lineup_report(s)
        else:
            roster = s.roster(opp["roster_id"])
            report = lineup_report(s, s.active(roster), s.owners[opp["roster_id"]])
        self.deliver("lineup", report, always)

    def waivers(self) -> None:
        s = self.season
        tx = [
            t
            for w in range(1, s.week + 1)
            for t in self.source.transactions(self.cfg.league_id, w)
        ]
        report = waiver_report(s, s.sim(self.args.sims), median_winning_bid(tx))
        self.deliver("waivers", report, True)

    def trade(self) -> None:
        s = self.season
        give, get = _names(s, self.args.give), _names(s, self.args.get)
        if not give or not get:
            raise UserRefusal("trade needs --give and --get")
        owner = s.owner_of(get[0])
        partner = s.owners[owner["roster_id"]] if owner else "free agency"
        report = trade_report(
            s, s.sim(self.args.sims), give, get, partner, market(self.source, s)
        )
        self.deliver("trade", report, True)

    def trades(self) -> None:
        if not self.cfg.token:
            print("trades: SLEEPER_TOKEN not set; inbox watch is off", file=self.out)
            return
        s = self.season
        offers = inbox.pending_offers(
            self.source, self.cfg.token, self.cfg.league_id, s.me["roster_id"]
        )
        values = market(self.source, s) if offers else {}
        for offer in offers:
            report = trade_report(
                s,
                s.sim(self.args.sims),
                offer.give,
                offer.get,
                s.owners.get(offer.partner_roster, "?"),
                values,
            )
            self.deliver(f"trade:{offer.id}", report, False)

    def auto(self, now: datetime) -> None:
        for due in jobs_due(now):
            if due.job == "lineup":
                self.lineup(always=due.always)
            elif due.job == "waivers":
                self.waivers()
            else:
                self.trades()

    def fit(self) -> None:
        season = self.args.season
        if not season:
            raise UserRefusal("fit needs --season")
        self.cfg.require_league()
        scoring = self.source.league(self.cfg.league_id)["scoring_settings"]
        stats = {w: self.source.stats(season, w) for w in range(1, 19)}
        proj = {w: self.source.projections(season, w) for w in range(4, 19)}
        report = backtest(stats, proj, self.source.players(), scoring)
        print(email.render_text(report), file=self.out)


def main(
    argv: Sequence[str] | None = None,
    *,
    env: Mapping[str, str] | None = None,
    source: Source | None = None,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    out: TextIO = sys.stdout,
    smtp: Callable = smtplib.SMTP_SSL,
) -> int:
    args = build_parser().parse_args(argv)
    cfg = Config(os.environ if env is None else env)
    runner = Runner(args, cfg, source or Source(), out, smtp)
    try:
        if args.job == "auto":
            runner.auto(now())
        else:
            getattr(runner, args.job)()
    except VorpalError as exc:
        print(f"error: {exc.message}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0
