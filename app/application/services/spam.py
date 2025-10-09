from app.domain.repositories import IMessageRepository


class SpamService:
    """Application service for basic spam heuristics."""

    def __init__(self, message_repository: IMessageRepository) -> None:
        self.message_repository = message_repository

    async def detect(self, chat_id: int, user_id: int, text: str | None) -> bool:
        """Detect potential spam for a user's message."""
        if not text:
            return False

        if not await self.message_repository.is_first_message(chat_id=chat_id, user_id=user_id):
            return False

        return bool(await self.message_repository.is_similar_spam_message(text))
