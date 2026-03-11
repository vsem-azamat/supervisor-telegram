import json

from aiogram import Router, types
from aiogram.filters import Command

from app.presentation.telegram.utils import other

router = Router()


@router.message(Command("json", prefix="!/"))
async def json_message(message: types.Message) -> None:
    json_text = json.dumps(message.model_dump(exclude_none=True), indent=4)
    text = f"```json\n{json_text}\n```"
    answer = await message.answer(text, parse_mode="MarkdownV2")
    await message.delete()
    other.sleep_and_delete(answer, 30)
