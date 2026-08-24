from typing import List, Optional
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from src.app.bot.locales.strings import get_text
from src.app.db.models.product import Product
from src.app.db.models.server import VPNServer
from src.app.db.models.subscription import Subscription, SubscriptionStatus


def get_main_menu_keyboard(lang: str = "en") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=get_text("btn_buy_vpn", lang), callback_data="menu_buy"),
            ],
            [
                InlineKeyboardButton(text=get_text("btn_my_subs", lang), callback_data="menu_subs"),
                InlineKeyboardButton(text=get_text("btn_support", lang), callback_data="menu_support"),
            ],
        ]
    )


def get_servers_keyboard(servers: List[VPNServer], lang: str = "en") -> InlineKeyboardMarkup:
    buttons = []
    for s in servers:
        flag = "🌐"
        if s.country_code == "DE": flag = "🇩🇪"
        elif s.country_code == "TR": flag = "🇹🇷"
        elif s.country_code == "NL": flag = "🇳🇱"
        elif s.country_code == "FI": flag = "🇫🇮"
        elif s.country_code == "US": flag = "🇺🇸"
        
        btn_text = f"{flag} {s.display_name}"
        buttons.append([InlineKeyboardButton(text=btn_text, callback_data=f"srv_{s.slug}")])
    
    buttons.append([InlineKeyboardButton(text=get_text("btn_cancel", lang), callback_data="cancel_order")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_products_keyboard(server_slug: str, products: List[Product], lang: str = "en") -> InlineKeyboardMarkup:
    buttons = []
    for p in products:
        btn_text = f"📦 {p.title} - {p.price_amount} {p.price_currency}"
        buttons.append([InlineKeyboardButton(text=btn_text, callback_data=f"plan_{server_slug}_{p.code}")])
    
    buttons.append([InlineKeyboardButton(text=get_text("btn_back", lang), callback_data="menu_buy")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_cancel_keyboard(lang: str = "en") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=get_text("btn_cancel", lang), callback_data="cancel_order")]
        ]
    )


def get_subscriptions_keyboard(subscriptions: List[Subscription], lang: str = "en") -> InlineKeyboardMarkup:
    buttons = []
    for sub in subscriptions:
        is_active = (sub.status == SubscriptionStatus.ACTIVE)
        status_emoji = "🟢" if is_active else "🔴"
        btn_text = f"{status_emoji} {sub.peer_label or 'VPN Subscription'}"
        buttons.append([InlineKeyboardButton(text=btn_text, callback_data=f"sub_view_{sub.id}")])

    buttons.append([InlineKeyboardButton(text=get_text("btn_back", lang), callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_subscription_detail_keyboard(subscription_id: str, is_active: bool, lang: str = "en") -> InlineKeyboardMarkup:
    buttons = []
    if is_active:
        buttons.append([
            InlineKeyboardButton(text="📥 Download Config", callback_data=f"sub_dl_{subscription_id}"),
            InlineKeyboardButton(text="🔄 Redeliver", callback_data=f"sub_redeliver_{subscription_id}"),
        ])
    buttons.append([
        InlineKeyboardButton(text="💳 Renew Plan", callback_data=f"renew_{subscription_id}"),
    ])
    buttons.append([
        InlineKeyboardButton(text=get_text("btn_back", lang), callback_data="menu_subs"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
