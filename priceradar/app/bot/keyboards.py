"""Inline keyboard builders for the PriceRadar Telegram bot."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

if TYPE_CHECKING:
    from app.models.product import TrackedProduct


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_markup(buttons: list[list[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    """Shortcut to create an InlineKeyboardMarkup from a 2-D button list."""
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _fmt_price(value) -> str:
    """Format a numeric price with thousands separator and ruble sign."""
    if value is None:
        return "N/A"
    return f"{value:,.0f} \u20bd".replace(",", "\u202f")


# ---------------------------------------------------------------------------
# Main menu
# ---------------------------------------------------------------------------

def main_menu_keyboard() -> InlineKeyboardMarkup:
    """Main menu with core bot actions."""
    return _build_markup(
        [
            [InlineKeyboardButton(text="\U0001f50d \u0414\u043e\u0431\u0430\u0432\u0438\u0442\u044c \u0442\u043e\u0432\u0430\u0440", callback_data="add_product")],
            [InlineKeyboardButton(text="\U0001f4ca \u041c\u043e\u0438 \u0442\u043e\u0432\u0430\u0440\u044b", callback_data="my_products")],
            [InlineKeyboardButton(text="\U0001f514 \u041d\u0430\u0441\u0442\u0440\u043e\u0438\u0442\u044c \u0430\u043b\u0435\u0440\u0442\u044b", callback_data="alerts_settings")],
            [InlineKeyboardButton(text="\U0001f4b3 \u041f\u043e\u0434\u043f\u0438\u0441\u043a\u0430", callback_data="subscription")],
            [InlineKeyboardButton(text="\u2753 \u041f\u043e\u043c\u043e\u0449\u044c", callback_data="help")],
        ]
    )


# ---------------------------------------------------------------------------
# Product actions
# ---------------------------------------------------------------------------

def product_actions_keyboard(product_id: int) -> InlineKeyboardMarkup:
    """Actions available for a single tracked product."""
    return _build_markup(
        [
            [
                InlineKeyboardButton(
                    text="\U0001f4c8 \u0418\u0441\u0442\u043e\u0440\u0438\u044f \u0446\u0435\u043d",
                    callback_data=f"price_history:{product_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="\U0001f514 \u0414\u043e\u0431\u0430\u0432\u0438\u0442\u044c \u0430\u043b\u0435\u0440\u0442",
                    callback_data=f"add_alert:{product_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="\U0001f504 \u041e\u0431\u043d\u043e\u0432\u0438\u0442\u044c \u0446\u0435\u043d\u0443",
                    callback_data=f"refresh_price:{product_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="\U0001f5d1 \u0423\u0434\u0430\u043b\u0438\u0442\u044c",
                    callback_data=f"delete_product:{product_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="\u25c0\ufe0f \u041d\u0430\u0437\u0430\u0434",
                    callback_data="my_products",
                ),
            ],
        ]
    )


# ---------------------------------------------------------------------------
# Alert type selection
# ---------------------------------------------------------------------------

def alert_type_keyboard(product_id: int) -> InlineKeyboardMarkup:
    """Choose alert type after adding / for an existing product."""
    return _build_markup(
        [
            [
                InlineKeyboardButton(
                    text="\U0001f4c9 \u0421\u043d\u0438\u0436\u0435\u043d\u0438\u0438 \u0446\u0435\u043d\u044b",
                    callback_data=f"alert_drop:{product_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="\U0001f4e6 \u041f\u043e\u044f\u0432\u043b\u0435\u043d\u0438\u0438 \u0432 \u043d\u0430\u043b\u0438\u0447\u0438\u0438",
                    callback_data=f"alert_stock:{product_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="\u270f\ufe0f \u0421\u0432\u043e\u044f \u0446\u0435\u043d\u0430",
                    callback_data=f"alert_custom:{product_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="\u25c0\ufe0f \u041d\u0430\u0437\u0430\u0434",
                    callback_data=f"product_detail:{product_id}",
                ),
            ],
        ]
    )


# ---------------------------------------------------------------------------
# Subscription plan selection
# ---------------------------------------------------------------------------

def subscription_keyboard() -> InlineKeyboardMarkup:
    """Plan selection keyboard for subscription upgrade."""
    return _build_markup(
        [
            [
                InlineKeyboardButton(
                    text="\u2b50 Basic \u2014 990 \u20bd/\u043c\u0435\u0441",
                    callback_data="subscribe:basic",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="\U0001f451 Pro \u2014 2 490 \u20bd/\u043c\u0435\u0441",
                    callback_data="subscribe:pro",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="\u25c0\ufe0f \u0413\u043b\u0430\u0432\u043d\u043e\u0435 \u043c\u0435\u043d\u044e",
                    callback_data="main_menu",
                ),
            ],
        ]
    )


# ---------------------------------------------------------------------------
# Paginated product list
# ---------------------------------------------------------------------------

PRODUCTS_PER_PAGE: int = 5


def products_pagination_keyboard(
    products: list[TrackedProduct],
    page: int,
    total_pages: int,
) -> InlineKeyboardMarkup:
    """Build a paginated list of products with navigation buttons.

    Each product is shown as a single button with its title and current price.
    """
    buttons: list[list[InlineKeyboardButton]] = []

    start = page * PRODUCTS_PER_PAGE
    end = start + PRODUCTS_PER_PAGE
    page_products = products[start:end]

    for product in page_products:
        price_str = _fmt_price(product.current_price)
        label = f"{product.title[:40]} \u2014 {price_str}"
        buttons.append(
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"product_detail:{product.id}",
                )
            ]
        )

    # Navigation row
    nav_row: list[InlineKeyboardButton] = []
    if page > 0:
        nav_row.append(
            InlineKeyboardButton(text="\u25c0\ufe0f", callback_data=f"products_page:{page - 1}")
        )
    if page < total_pages - 1:
        nav_row.append(
            InlineKeyboardButton(text="\u25b6\ufe0f", callback_data=f"products_page:{page + 1}")
        )
    if nav_row:
        buttons.append(nav_row)

    # Footer
    buttons.append(
        [InlineKeyboardButton(text="\U0001f3e0 \u0413\u043b\u0430\u0432\u043d\u043e\u0435 \u043c\u0435\u043d\u044e", callback_data="main_menu")]
    )

    return _build_markup(buttons)


# ---------------------------------------------------------------------------
# Confirm deletion
# ---------------------------------------------------------------------------

def confirm_delete_keyboard(product_id: int) -> InlineKeyboardMarkup:
    """Confirm / cancel product deletion."""
    return _build_markup(
        [
            [
                InlineKeyboardButton(
                    text="\u2705 \u0414\u0430, \u0443\u0434\u0430\u043b\u0438\u0442\u044c",
                    callback_data=f"confirm_delete:{product_id}",
                ),
                InlineKeyboardButton(
                    text="\u274c \u041e\u0442\u043c\u0435\u043d\u0430",
                    callback_data=f"product_detail:{product_id}",
                ),
            ],
        ]
    )


# ---------------------------------------------------------------------------
# Back to main menu (utility)
# ---------------------------------------------------------------------------

def back_to_menu_keyboard() -> InlineKeyboardMarkup:
    """Single-button keyboard that returns to the main menu."""
    return _build_markup(
        [
            [InlineKeyboardButton(text="\U0001f3e0 \u0413\u043b\u0430\u0432\u043d\u043e\u0435 \u043c\u0435\u043d\u044e", callback_data="main_menu")],
        ]
    )
