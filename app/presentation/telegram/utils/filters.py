"""Filters used when routing an update.

Permission checks are not here. They used to be — an `AdminFilter` and a
`SuperAdminFilter` that nothing ever referenced, answering the same question as
the middlewares in a slightly different way. A second answer to "who may do
this" is worse than no answer, because only one of them gets updated. See
``middlewares/admin.py``, which is the one that runs.
"""

from aiogram import types
from aiogram.filters import BaseFilter


class ChatTypeFilter(BaseFilter):
    def __init__(self, chat_type: str | list[str]):
        self.chat_type = chat_type

    async def __call__(self, message: types.Message) -> bool:
        if isinstance(self.chat_type, str):
            return message.chat.type == self.chat_type
        return message.chat.type in self.chat_type
