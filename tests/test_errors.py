"""Refusal classes stay distinct. Each message is safe for stderr."""

import pytest

from vorpal.errors import (
    DataRefusal,
    PlatformError,
    UnsupportedLeague,
    UserRefusal,
    VorpalError,
)


@pytest.mark.parametrize(
    "cls",
    [UnsupportedLeague, DataRefusal, PlatformError, UserRefusal],
)
def test_each_refusal_is_a_vorpal_error_and_prints_its_message(
    cls: type[VorpalError],
) -> None:
    err = cls("safe message")
    assert isinstance(err, VorpalError)
    assert err.message == "safe message"
    assert str(err) == "safe message"
    with pytest.raises(VorpalError, match="safe message"):
        raise err


def test_refusal_classes_are_not_collapsed() -> None:
    assert UnsupportedLeague is not DataRefusal
    assert DataRefusal is not PlatformError
    assert PlatformError is not UserRefusal
    assert UserRefusal is not UnsupportedLeague
    assert not issubclass(DataRefusal, UnsupportedLeague)
    assert not issubclass(UnsupportedLeague, DataRefusal)
    assert not issubclass(PlatformError, DataRefusal)
    assert not issubclass(UserRefusal, DataRefusal)


def test_taxonomy_matches_the_spec() -> None:
    assert UnsupportedLeague.__doc__ is not None
    assert "permanent" in UnsupportedLeague.__doc__.lower()
    assert DataRefusal.__doc__ is not None
    assert "file" in DataRefusal.__doc__.lower()
    assert PlatformError.__doc__ is not None
    assert "api" in PlatformError.__doc__.lower()
    assert UserRefusal.__doc__ is not None
