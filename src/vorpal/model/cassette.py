"""Record once, replay by request hash. The eval gate stops costing money.

An eval suite that bills for every run is a suite nobody runs on a pull
request. That is not a gate, it is a report somebody remembers to read.

The identity of a recording is **the request**, not the fixture name. A
name says which board we meant; a hash says which question we asked. The
key covers everything that can change the answer — the board, the system
prompt, the model id, the effort, the output schema. Change a prompt and
every key changes, so only the affected recordings go stale and the run
tells you which. Transport settings stay out of the key: a retry count
is not a different question.

Three rules, and the whole point is the last one:

- **Replay is the default.** A default run spends nothing.
- **`record=True` is the only thing that spends.** It fills a key up to
  the number of calls the run actually makes, and writes after each one
  so a crash keeps what it paid for.
- **A miss is an error.** A quiet live call on a miss is how an eval
  suite becomes a bill.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from vorpal.errors import PlatformError
from vorpal.model.call import MODEL_ID, Transport, build_request


def request_key(payload: dict[str, Any]) -> str:
    """`sha256` over the request the transport would send, plus the full board.

    Not over the payload alone: two runs that send the same board under a
    different system prompt are asking two questions and must not share a
    recording. And not over the request alone: the request now carries only the
    **lean** board, but the `detail` tool can surface any column the full board
    holds — so two payloads that differ only in a detail column would ask two
    questions from one key. Fold the full payload in so identity covers what the
    tool can reach.
    """
    try:
        blob = json.dumps(
            {"request": build_request(payload), "full": payload}, sort_keys=True
        )
    except (TypeError, ValueError) as exc:
        raise PlatformError(f"payload is not serializable: {exc}") from exc
    return hashlib.sha256(blob.encode()).hexdigest()


class CassetteStore:
    """One JSON file per key. Committed, and read in review.

    The file holds the assembled request beside the answers. A key on its
    own says nothing to a reader; the request is what makes a diff legible
    and what tells you why a miss missed.
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def path(self, key: str) -> Path:
        return self.root / f"{key}.json"

    def load(self, key: str) -> list[dict[str, Any]] | None:
        """Recorded answers for this key, or `None` if never recorded."""
        path = self.path(key)
        if not path.exists():
            return None
        try:
            body = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            raise PlatformError(f"cassette {path.name} is not JSON: {exc}") from exc
        samples = body.get("samples")
        if not isinstance(samples, list):
            raise PlatformError(f"cassette {path.name} has no samples list")
        return samples

    def save(
        self,
        key: str,
        samples: list[dict[str, Any]],
        *,
        payload: dict[str, Any],
    ) -> None:
        """Write the key. Sorted, indented, one trailing newline: diffable."""
        self.root.mkdir(parents=True, exist_ok=True)
        body = {
            "key": key,
            "model": MODEL_ID,
            "request": build_request(payload),
            "samples": samples,
        }
        self.path(key).write_text(
            json.dumps(body, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        )


class CassetteTransport:
    """Replay recorded answers. `record=True` is the only path that spends.

    Samples are walked in order and never wrap. `run_stability` asks the
    same board five times and wants five draws; handing it draw one five
    times would report a spread that was never measured. Running past the
    end is the same error as never having recorded at all.
    """

    def __init__(
        self,
        store: CassetteStore,
        *,
        live: Transport | None = None,
        record: bool = False,
    ) -> None:
        if record and live is None:
            raise PlatformError("record needs a live transport")
        self._store = store
        self._live = live
        self._record = record
        self._samples: dict[str, list[dict[str, Any]]] = {}
        self._cursor: dict[str, int] = {}

    def complete(self, payload: dict[str, Any]) -> dict[str, Any]:
        key = request_key(payload)
        if key not in self._samples:
            self._samples[key] = self._store.load(key) or []
            self._cursor[key] = 0
        samples = self._samples[key]
        index = self._cursor[key]
        if index < len(samples):
            self._cursor[key] = index + 1
            return dict(samples[index])
        if not self._record:
            raise PlatformError(self._miss(key, len(samples)))
        assert self._live is not None
        raw = self._live.complete(payload)
        samples.append(raw)
        # Write per call, not per run. A crash keeps what it paid for.
        self._store.save(key, samples, payload=payload)
        self._cursor[key] = index + 1
        return dict(raw)

    def _miss(self, key: str, recorded: int) -> str:
        where = f"cassette {key[:16]}"
        if recorded == 0:
            return (
                f"{where} not recorded; re-record with "
                "`uv run python -m evals.run --record`"
            )
        return (
            f"{where} has {recorded} sample(s) and call {recorded + 1} would be "
            "live; re-record with `uv run python -m evals.run --record`"
        )
