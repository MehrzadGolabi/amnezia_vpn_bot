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
    "btn_language": {
        "en": "🌐 Language / زبان",
        "fa": "🌐 Language / زبان",
    },
    "choose_language": {
        "en": "🌐 <b>Choose your language</b>\nزبان خود را انتخاب کنید",
        "fa": "🌐 <b>Choose your language</b>\nزبان خود را انتخاب کنید",
    },
    "no_servers": {
        "en": "⚠️ <b>No VPN servers are currently active.</b>\nPlease check back shortly or contact support.",
        "fa": "⚠️ <b>در حال حاضر هیچ سروری در دسترس نیست.</b>\nلطفا با پشتیبانی تماس بگیرید یا دقایقی دیگر مراجعه فرمایید.",
    },
    "your_subscriptions": {
        "en": "📋 <b>Your Subscriptions:</b>",
        "fa": "📋 <b>اشتراک‌های شما:</b>",
    },
    "btn_download_config": {
        "en": "📥 Download Config",
        "fa": "📥 دریافت کانفیگ",
    },
    "btn_redeliver": {
        "en": "🔄 Redeliver",
        "fa": "🔄 ارسال مجدد",
    },
    "btn_renew": {
        "en": "💳 Renew Plan",
        "fa": "💳 تمدید اشتراک",
    },
    "btn_reactivate": {
        "en": "💳 Reactivate / Renew",
        "fa": "💳 فعال‌سازی مجدد / تمدید",
    },
    "subscription_default_label": {
        "en": "VPN Subscription",
        "fa": "اشتراک VPN",
    },
    "status_provisioning": {"en": "PROVISIONING", "fa": "در حال ساخت"},
    "status_active": {"en": "ACTIVE", "fa": "فعال"},
    "status_expired": {"en": "EXPIRED", "fa": "منقضی شده"},
    "status_disabled": {"en": "DISABLED", "fa": "غیرفعال"},
    "status_failed": {"en": "FAILED", "fa": "ناموفق"},
    "status_revoked": {"en": "REVOKED", "fa": "لغو شده"},
    "server_not_found": {
        "en": "Server not found",
        "fa": "سرور پیدا نشد",
    },
    "server_unavailable": {
        "en": "Server not available",
        "fa": "این سرور در دسترس نیست",
    },
    "invalid_selection": {
        "en": "Invalid selection",
        "fa": "انتخاب نامعتبر است",
    },
    "subscription_not_found": {
        "en": "Subscription not found",
        "fa": "اشتراک پیدا نشد",
    },
    "redelivery_limit": {
        "en": "Redelivery limit reached ({limit} times). Please contact support.",
        "fa": "سقف ارسال مجدد ({limit} بار) پر شده است. لطفا با پشتیبانی تماس بگیرید.",
    },
    "redelivery_queued": {
        "en": "Your config will be sent again in a moment.",
        "fa": "کانفیگ شما تا لحظاتی دیگر دوباره ارسال می‌شود.",
    },
    "button_expired": {
        "en": "This button has expired. Send /start to open the menu.",
        "fa": "این دکمه منقضی شده است. برای باز کردن منو /start را ارسال کنید.",
    },
    "support_prompt": {
        "en": "💬 <b>Customer Support</b>\n\nPlease describe your question or issue below. You can also attach photos or documents if needed.",
        "fa": "💬 <b>پشتیبانی مشتریان</b>\n\nلطفا پیام، سوال یا مشکل خود را ارسال نمایید. در صورت نیاز می‌توانید عکس یا فایل هم بفرستید.",
    },
    "support_received": {
        "en": "✅ <b>Message Received!</b>\n\nTicket Code: <code>{ticket_code}</code>\nOur support team has been notified and will reply shortly.",
        "fa": "✅ <b>پیام شما ثبت شد!</b>\n\nکد پیگیری: <code>{ticket_code}</code>\nپاسخ پشتیبانی به زودی برای شما ارسال خواهد شد.",
    },
    "support_reply": {
        "en": "💬 <b>Support Reply:</b> <code>{ticket_code}</code>\n\n{body}\n\n<i>Send /support to continue the conversation.</i>",
        "fa": "💬 <b>پاسخ پشتیبانی:</b> <code>{ticket_code}</code>\n\n{body}\n\n<i>برای ادامه گفتگو /support را ارسال کنید.</i>",
    },
    "ticket_closed": {
        "en": "🔒 <b>Support Ticket Closed</b>\n\nTicket <code>{ticket_code}</code> has been marked as resolved.\nFeel free to open a new support request if you need further help.",
        "fa": "🔒 <b>تیکت پشتیبانی بسته شد</b>\n\nتیکت <code>{ticket_code}</code> حل‌شده علامت خورد.\nدر صورت نیاز می‌توانید درخواست جدیدی ثبت کنید.",
    },
    "payment_approved": {
        "en": "✅ <b>Payment Approved!</b>\n\nYour order <code>{order_code}</code> has been verified.\nYour VPN configuration is being generated and will be sent shortly.",
        "fa": "✅ <b>پرداخت تایید شد!</b>\n\nسفارش <code>{order_code}</code> تایید شد.\nکانفیگ شما در حال ساخت است و به زودی ارسال می‌شود.",
    },
    "renewal_of": {
        "en": "🔄 <b>Renewal of</b> <code>{label}</code>. Your current config keeps working.",
        "fa": "🔄 <b>تمدید</b> <code>{label}</code>. کانفیگ فعلی شما بدون تغییر کار می‌کند.",
    },
    "payment_approved_renewal": {
        "en": "✅ <b>Payment Approved!</b>\n\nYour subscription <code>{label}</code> now runs until <code>{expires_at}</code>.\nKeep using the same config. Nothing to import.",
        "fa": "✅ <b>پرداخت تایید شد!</b>\n\nاشتراک <code>{label}</code> تا <code>{expires_at}</code> تمدید شد.\nهمان کانفیگ قبلی را استفاده کنید. نیازی به وارد کردن فایل جدید نیست.",
    },
    "usage": {
        "en": "📶 <b>Data used:</b> {total} (download {down}, upload {up})\n🕒 <b>Last connected:</b> {last_seen}",
        "fa": "📶 <b>حجم مصرفی:</b> {total} (دانلود {down}، آپلود {up})\n🕒 <b>آخرین اتصال:</b> {last_seen}",
    },
    "usage_unavailable": {
        "en": "📶 Usage is not available right now.",
        "fa": "📶 اطلاعات مصرف در حال حاضر در دسترس نیست.",
    },
    "never_connected": {"en": "never", "fa": "هنوز وصل نشده"},
    "just_now": {"en": "just now", "fa": "همین الان"},
    "minutes_ago": {"en": "{n} min ago", "fa": "{n} دقیقه پیش"},
    "hours_ago": {"en": "{n} h ago", "fa": "{n} ساعت پیش"},
    "payment_rejected": {
        "en": "❌ <b>Payment Receipt Rejected</b>\n\nThe receipt for order <code>{order_code}</code> was rejected.\n\nPlease check your payment details or contact our support team.",
        "fa": "❌ <b>رسید پرداخت رد شد</b>\n\nرسید سفارش <code>{order_code}</code> تایید نشد.\n\nلطفا اطلاعات پرداخت را بررسی کنید یا با پشتیبانی تماس بگیرید.",
    },
    "config_ready": {
        "en": "✅ <b>Your VPN is Ready!</b>\n\n📍 <b>Location:</b> {server_name}\n⏳ <b>Expires:</b> <code>{expires_at}</code>\n\n📥 <i>Import this file into <b>AmneziaWG 3.1+</b> or <b>AmneziaVPN 5.0+</b>.</i>",
        "fa": "✅ <b>وی‌پی‌ان شما آماده است!</b>\n\n📍 <b>لوکیشن:</b> {server_name}\n⏳ <b>تاریخ انقضا:</b> <code>{expires_at}</code>\n\n📥 <i>این فایل را در <b>AmneziaWG 3.1+</b> یا <b>AmneziaVPN 5.0+</b> وارد کنید.</i>",
    },
    "config_redelivery": {
        "en": "🔄 <b>Config Redelivery</b> for {server_name}\n\n📥 <i>Import this file into <b>AmneziaWG 3.1+</b> or <b>AmneziaVPN 5.0+</b>.</i>",
        "fa": "🔄 <b>ارسال مجدد کانفیگ</b> برای {server_name}\n\n📥 <i>این فایل را در <b>AmneziaWG 3.1+</b> یا <b>AmneziaVPN 5.0+</b> وارد کنید.</i>",
    },
    "vpn_key": {
        "en": "🔗 <b>One-click key for AmneziaVPN:</b>\n<code>{vpn_url}</code>",
        "fa": "🔗 <b>کلید اتصال سریع برای AmneziaVPN:</b>\n<code>{vpn_url}</code>",
    },
    "expiring_soon": {
        "en": "⚠️ <b>VPN Subscription Expiring Soon</b>\n\n📍 <b>Location:</b> {server_name}\n⏳ <b>Expires:</b> <code>{expires_at}</code> (~{days} day(s) left)\n\nClick below to renew and keep your connection.",
        "fa": "⚠️ <b>اشتراک شما به زودی تمام می‌شود</b>\n\n📍 <b>لوکیشن:</b> {server_name}\n⏳ <b>تاریخ انقضا:</b> <code>{expires_at}</code> (حدود {days} روز مانده)\n\nبرای تمدید و قطع نشدن اتصال، دکمه زیر را بزنید.",
    },
    "expired": {
        "en": "❌ <b>VPN Subscription Expired</b>\n\n📍 <b>Location:</b> {server_name}\n\nYour VPN has been disabled. Renew now to restore access.",
        "fa": "❌ <b>اشتراک شما تمام شد</b>\n\n📍 <b>لوکیشن:</b> {server_name}\n\nوی‌پی‌ان شما غیرفعال شد. برای فعال‌سازی دوباره، اشتراک را تمدید کنید.",
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


LANGUAGES = ("en", "fa")

# Farsi country names for location buttons; other codes keep the configured DISPLAY_NAME.
COUNTRY_NAMES_FA = {
    "DE": "آلمان", "TR": "ترکیه", "US": "آمریکا", "NL": "هلند", "FI": "فنلاند",
    "GB": "انگلستان", "FR": "فرانسه", "AE": "امارات", "AM": "ارمنستان", "SE": "سوئد",
}


def normalize_lang(lang: Optional[str]) -> str:
    """Map a stored or Telegram language code to one the bot speaks."""
    lang = (lang or "en").lower()
    return "fa" if lang.startswith("fa") else "en"


def server_name(server: Any, lang: Optional[str] = "en") -> str:
    if normalize_lang(lang) == "fa":
        return COUNTRY_NAMES_FA.get((server.country_code or "").upper(), server.display_name)
    return server.display_name


def product_title(product: Any, lang: Optional[str] = "en") -> str:
    """Plan titles are stored in English; Farsi ones are built from the duration and device limit."""
    if normalize_lang(lang) != "fa":
        return product.title
    days = product.duration_days
    period = f"{days // 30} ماهه" if days % 30 == 0 else f"{days} روزه"
    devices = getattr(product, "device_limit", None)
    return f"{period} ({devices} کاربر)" if devices else period


def get_text(key: str, lang: Optional[str] = "en", **kwargs: Any) -> str:
    lang = normalize_lang(lang)
    
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
