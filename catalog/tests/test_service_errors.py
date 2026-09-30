"""How a rule a service raises becomes a status code.

A pure mapping, tested as one: no database, no client, no fixtures.
"""

from students_cz.main import status_for
from students_cz.services import errors


def test_each_error_answers_with_its_own_status() -> None:
    assert status_for(errors.NotFound("no such request")) == 404
    assert status_for(errors.Forbidden("this profile is blocked")) == 403
    assert status_for(errors.Conflict("you already answered this")) == 409
    assert status_for(errors.Invalid("unknown subject_id: 9")) == 422


def test_a_subclass_keeps_the_status_of_the_family_it_extends() -> None:
    """The mapping is walked along the class hierarchy, not looked up by type.

    An exact lookup turns a new subclass into a KeyError raised *inside* the
    error handler, which reaches the caller as a bodyless 500.
    """

    class TooManyOffers(errors.Invalid):
        pass

    assert status_for(TooManyOffers("sixty is the limit")) == 422


def test_the_base_class_is_not_quietly_given_a_plausible_status() -> None:
    """Raising `ServiceError` itself is a programming error, and says so."""
    assert status_for(errors.ServiceError("raised by mistake")) == 500


def test_the_two_input_errors_keep_the_statuses_the_api_already_answered() -> None:
    """400 and 422 both existed before any of this moved into services."""
    assert status_for(errors.BadRequest("this is your own request")) == 400
    assert status_for(errors.Invalid("unknown subject_id: 9")) == 422
