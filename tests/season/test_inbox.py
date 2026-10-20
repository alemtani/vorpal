"""Pending offers from Sleeper's web GraphQL. respx stands in for Sleeper."""

import httpx
import pytest
import respx

from vorpal.errors import PlatformError
from vorpal.season.fetch import Source
from vorpal.season.inbox import GRAPHQL, OP, Offer, parse_offers, pending_offers

ROWS = [
    {
        "transaction_id": 11,
        "status": "proposed",
        "creator": "kaodi",
        "roster_ids": [1, 7],
        "adds": {"goff": 7, "laporta": 7, "rodgers": 1, "hall": 1, "boston": 1},
        "drops": {"goff": 1, "laporta": 1, "rodgers": 7, "hall": 7, "boston": 7},
    },
    {"transaction_id": 12, "status": "complete", "creator": "x", "roster_ids": [7]},
    {"transaction_id": 13, "status": "proposed", "creator": "me", "roster_ids": [7]},
    {"transaction_id": 14, "status": "pending", "creator": "y", "roster_ids": [7]},
]


def test_parse_keeps_unfinished_offers_from_others() -> None:
    offers = parse_offers(ROWS, 7, "me")
    assert offers[0] == Offer(
        id="11",
        partner_roster=1,
        give=["rodgers", "hall", "boston"],
        get=["goff", "laporta"],
    )
    assert [o.id for o in offers] == ["11", "14"]
    assert offers[1].partner_roster == 0


@pytest.fixture
def source():
    http = httpx.Client()
    yield Source(http=http)
    http.close()


@respx.mock
def test_pending_offers_posts_the_query_with_the_token(source) -> None:
    route = respx.post(GRAPHQL).respond(json={"data": {OP: ROWS}})
    offers = pending_offers(source, "tok", "L", 7, "me")
    assert len(offers) == 2
    req = route.calls[0].request
    assert req.headers["authorization"] == "tok"
    assert b'league_id: \\"L\\", roster_id_filters: [7]' in req.content


@respx.mock
def test_graphql_errors_are_platform_errors(source) -> None:
    respx.post(GRAPHQL).respond(json={"errors": [{"message": "unauthorized"}]})
    with pytest.raises(PlatformError, match="unauthorized"):
        pending_offers(source, "bad", "L", 7, "me")


@respx.mock
def test_http_failure_is_a_platform_error(source) -> None:
    respx.post(GRAPHQL).respond(status_code=401)
    with pytest.raises(PlatformError, match="401"):
        pending_offers(source, "bad", "L", 7, "me")
