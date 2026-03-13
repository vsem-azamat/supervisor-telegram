"""Domain exceptions for the moderation bot."""

# ruff: noqa: N818


class DomainError(Exception):
    """Base domain exception."""

    pass


class UserNotFoundException(DomainError):
    """Raised when user is not found."""

    def __init__(self, user_id: int):
        self.user_id = user_id
        super().__init__(f"User with ID {user_id} not found")
