"""Rendering the blacklist: who is out, and the one button that lets them back."""

from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.core.text import escape_html, plural
from app.db.models import User
from app.presentation.telegram.utils import BlacklistPagination, UnblockUser


def build_blacklist_keyboard(
    users: list[User], current_page: int, total_pages: int, page_size: int = 10, query: str = ""
) -> InlineKeyboardBuilder:
    """One button per person on this page, plus the page controls."""
    builder = InlineKeyboardBuilder()

    start_idx = current_page * page_size
    end_idx = min(start_idx + page_size, len(users))
    page_users = users[start_idx:end_idx]

    for user in page_users:
        display_name = user.display_name
        if len(display_name) > 30:
            display_name = display_name[:27] + "..."

        builder.button(text=f"🚫 {display_name}", callback_data=UnblockUser(user_id=user.id).pack())

    builder.adjust(1)

    if total_pages > 1:
        pagination_row = []

        if current_page > 0:
            pagination_row.append(("◀️ Назад", BlacklistPagination(page=current_page - 1, query=query).pack()))

        pagination_row.append((f"{current_page + 1}/{total_pages}", "noop"))

        if current_page < total_pages - 1:
            pagination_row.append(("Вперёд ▶️", BlacklistPagination(page=current_page + 1, query=query).pack()))

        for text, callback_data in pagination_row:
            builder.button(text=text, callback_data=callback_data)

        builder.adjust(*([1] * len(page_users) + [len(pagination_row)]))

    return builder


def build_blacklist_text(
    total_count: int, current_page: int, total_pages: int, page_size: int = 10, query: str = ""
) -> str:
    """The heading above the page of names."""
    people = plural(total_count, "человек", "человека", "человек")
    if query:
        text = f"<b>Поиск «{escape_html(query)}»</b>\nНайдено: {total_count} {people}"
    else:
        text = f"<b>Чёрный список</b> — {total_count} {people}"

    if total_pages > 1:
        start_idx = current_page * page_size + 1
        end_idx = min((current_page + 1) * page_size, total_count)
        text += f"\n\nПоказаны {start_idx}–{end_idx} из {total_count}"
        text += f"\nСтраница {current_page + 1} из {total_pages}"

    return text


def build_user_details_keyboard(user: User) -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Разблокировать", callback_data=UnblockUser(user_id=user.id).pack())
    return builder


def build_user_details_text(user: User) -> str:
    text = "<b>Найден в чёрном списке</b>\n\n"
    text += f"👤 {escape_html(user.display_name)}\n"
    text += f"🆔 ID: <code>{user.id}</code>"

    if user.username:
        text += f"\n📝 Ник: @{escape_html(user.username)}"

    if user.created_at:
        text += f"\n📅 Добавлен: {user.created_at.strftime('%d.%m.%Y %H:%M')}"

    return text
