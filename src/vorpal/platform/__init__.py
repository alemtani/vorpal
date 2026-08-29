"""League hosts. v1 ships Sleeper; ESPN is a later adapter on the same ABC."""

from vorpal.platform.base import LeagueHost
from vorpal.platform.client import LeagueClient
from vorpal.platform.sleeper import SleeperHost

__all__ = ["LeagueClient", "LeagueHost", "SleeperHost"]
