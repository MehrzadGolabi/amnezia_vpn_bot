from typing import Dict, Any, Optional

STRINGS: Dict[str, Dict[str, str]] = {
    "welcome": {
        "en": "🛡️ <b>Welcome to AmneziaWG Secure VPN Bot!</b>\n\nHigh-speed, censorship-resistant VPN subscriptions powered by AmneziaWG.\nChoose an option below:",
        "fa": "🛡️ <b>به ربات خرید وی‌پی‌ان امن AmneziaWG خوش آمدید!</b>\n\nاشتراک پرسرعت و ضد فیلتر مبتنی بر پروتکل قدرتمند AmneziaWG.\nلطفا یکی از گزینه‌های زیر را انتخاب نمایید:",
    },
    "btn_buy_vpn": {
        "en": "🛒 Buy VPN",
        "fa": "🛒 خرید اشتراک",
    },
    "btn_my_subs": {
        "en": "📋 My Subscriptions",
        "fa": "📋 اشتراک‌های من",
    },
    "btn_support": {
        "en": "💬 Support",
        "fa": "💬 پشتیبانی",
    },
    "btn_cancel": {
        "en": "❌ Cancel",
        "fa": "❌ لغو عملیات",
    },
    "btn_back": {
        "en": "🔙 Back",
        "fa": "🔙 بازگشت",
    },
    "select_server": {
        "en": "📍 <b>Select VPN Server Location:</b>",
        "fa": "📍 <b>لطفا لوکیشن سرور مورد نظر را انتخاب کنید:</b>",
    },
    "select_plan": {
        "en": "📦 <b>Select Subscription Plan for {server_name}:</b>",
        "fa": "📦 <b>لطفا پلن اشتراک مورد نظر برای سرور {server_name} را انتخاب کنید:</b>",
    },
    "order_created": {
        "en": "🧾 <b>Order Code:</b> <code>{order_code}</code>\n📍 <b>Location:</b> {server_name}\n📦 <b>Plan:</b> {plan_title}\n💰 <b>Price:</b> <code>{price} {currency}</code>\n\n💳 <b>Payment Instructions:</b>\n{instructions}\n\n📸 <i>Please send your payment receipt (photo or document) now:</i>",
        "fa": "🧾 <b>کد سفارش:</b> <code>{order_code}</code>\n📍 <b>لوکیشن:</b> {server_name}\n📦 <b>پلن:</b> {plan_title}\n💰 <b>مبلغ:</b> <code>{price} {currency}</code>\n\n💳 <b>اطلاعات پرداخت:</b>\n{instructions}\n\n📸 <i>لطفا تصویر یا فایل رسید پرداخت خود را ارسال فرمایید:</i>",
    },
    "receipt_received": {
        "en": "✅ <b>Receipt Received!</b>\n\nYour receipt for order <code>{order_code}</code> has been submitted for manual verification by our administrators.\nOnce approved, your VPN configuration file will be delivered here automatically.",
        "fa": "✅ <b>رسید پرداخت دریافت شد!</b>\n\nرسید شما برای سفارش <code>{order_code}</code> جهت بررسی و تایید دستی توسط ادمین ارسال گردید.\nبلافاصله پس از تایید، فایل کانفیگ اختصاصی شما ارسال خواهد شد.",
    },
    "order_cancelled": {
        "en": "❌ Order was cancelled.",
        "fa": "❌ سفارش لغو شد.",
    },
    "no_subscriptions": {
        "en": "You do not have any active subscriptions yet.",
        "fa": "شما در حال حاضر هیچ اشتراک فعالی ندارید.",
    },
    "subscription_detail": {
        "en": "📍 <b>Location:</b> {server_name}\n📊 <b>Status:</b> {status}\n⏳ <b>Expires:</b> <code>{expires_at}</code>\n🏷️ <b>Label:</b> <code>{label}</code>",
        "fa": "📍 <b>لوکیشن:</b> {server_name}\n📊 <b>وضعیت:</b> {status}\n⏳ <b>تاریخ انقضا:</b> <code>{expires_at}</code>\n🏷️ <b>نام کانفیگ:</b> <code>{label}</code>",
    },
    "rate_limited": {
        "en": "⏳ You are sending requests too quickly. Please wait a moment.",
        "fa": "⏳ سرعت ارسال درخواست‌های شما بالاست. لطفا کمی صبر کنید.",
    },
    "blocked_user": {
        "en": "⛔ Your account has been suspended.",
        "fa": "⛔ حساب کاربری شما مسدود شده است.",
    },
}


def get_text(key: str, lang: Optional[str] = "en", **kwargs: Any) -> str:
    lang = lang or "en"
    if lang not in ("en", "fa"):
        lang = "en"
    
    key_dict = STRINGS.get(key)
    if not key_dict:
        return key
    
    template = key_dict.get(lang) or key_dict.get("en") or key
    if kwargs:
        try:
            return template.format(**kwargs)
        except Exception:
            return template
    return template
