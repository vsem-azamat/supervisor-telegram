"""Blacklist management utilities."""

from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.core.text import escape_html
from app.infrastructure.db.models import User
from app.presentation.telegram.utils import BlacklistPagination, UnblockUser


def build_blacklist_keyboard(
    users: list[User], current_page: int, total_pages: int, page_size: int = 10, query: str = ""
) -> InlineKeyboardBuilder:
    """Build keyboard for blacklist display with pagination."""
    builder = InlineKeyboardBuilder()

    # Add user buttons
    start_idx = current_page * page_size
    end_idx = min(start_idx + page_size, len(users))
    page_users = users[start_idx:end_idx]

    for user in page_users:
        display_name = user.display_name
        if len(display_name) > 30:
            display_name = display_name[:27] + "..."

        builder.button(text=f"\U0001f6ab {display_name}", callback_data=UnblockUser(user_id=user.id).pack())

    builder.adjust(1)

    # Add pagination controls if needed
    if total_pages > 1:
        pagination_row = []

        # Previous page button
        if current_page > 0:
            pagination_row.append(("\u25c0\ufe0f Prev", BlacklistPagination(page=current_page - 1, query=query).pack()))

        # Page indicator
        pagination_row.append((f"{current_page + 1}/{total_pages}", "noop"))

        # Next page button
        if current_page < total_pages - 1:
            pagination_row.append(("Next \u25b6\ufe0f", BlacklistPagination(page=current_page + 1, query=query).pack()))

        # Add pagination buttons
        for text, callback_data in pagination_row:
            builder.button(text=text, callback_data=callback_data)

        builder.adjust(*([1] * len(page_users) + [len(pagination_row)]))

    return builder


def build_blacklist_text(
    total_count: int, current_page: int, total_pages: int, page_size: int = 10, query: str = ""
) -> str:
    """Build text message for blacklist display."""
    if query:
        text = f"<b>Search results for '{escape_html(query)}':</b>\n"
        text += f"Found {total_count} users"
    else:
        text = f"<b>Blacklist ({total_count} users):</b>"

    if total_pages > 1:
        start_idx = current_page * page_size + 1
        end_idx = min((current_page + 1) * page_size, total_count)
        text += f"\n\nShowing {start_idx}-{end_idx} of {total_count}"
        text += f"\nPage {current_page + 1} of {total_pages}"

    return text


def build_user_details_keyboard(user: User) -> InlineKeyboardBuilder:
    """Build keyboard for individual user details."""
    builder = InlineKeyboardBuilder()
    builder.button(text="\U0001f6ab Unblock User", callback_data=UnblockUser(user_id=user.id).pack())
    return builder


def build_user_details_text(user: User) -> str:
    """Build text for individual user details."""
    text = "<b>Found in blacklist:</b>\n\n"
    text += f"\U0001f464 {escape_html(user.display_name)}\n"
    text += f"\U0001f194 ID: <code>{user.id}</code>"

    if user.username:
        text += f"\n\U0001f4dd Username: @{escape_html(user.username)}"

    if user.created_at:
        text += f"\n\U0001f4c5 Added: {user.created_at.strftime('%Y-%m-%d %H:%M')}"

    return text
