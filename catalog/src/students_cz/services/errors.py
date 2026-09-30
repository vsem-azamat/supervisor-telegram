"""What a service raises when the caller broke a rule.

Five of them, stated without reference to HTTP. A service that raises
`HTTPException` has an opinion about a protocol, which is exactly what stops
the bot from calling it — and the bot answering "422 Unprocessable Content" to
somebody typing into a chat is not an answer.

`main.py` maps each to a status code in one place. Anything else that calls a
service catches them and says something in words.
"""


class ServiceError(Exception):
    """A rule the caller broke. Never raised directly — one of the five below."""


class NotFound(ServiceError):
    """The thing addressed does not exist, or the caller may not know it does."""


class Forbidden(ServiceError):
    """It exists, the caller may not do this to it."""


class Conflict(ServiceError):
    """The state moved on: already answered, already chosen, already closed."""


class Invalid(ServiceError):
    """The request names something that is not there, or contradicts itself.

    The default for anything wrong with what was sent: an unknown id, the same
    offer twice, a field that cannot mean what it says. Answers 422.
    """


class BadRequest(ServiceError):
    """Answers 400, and exists only because two endpoints already did.

    Not a category — `Invalid` is the category. This is here so that "you
    cannot answer your own request" and "that is your own profile", which
    answered 400 long before either moved into a service, still answer 400.
    Reach for `Invalid` unless you are preserving an existing 400.
    """
