"""سیستم تیکت پشتیبانی ساده.

مدل: User -> SupportTicket -> SupportMessage  (و ادمین پاسخ‌دهنده)
عمداً ساده نگه داشته شده: هر کاربر یک تیکت باز دارد.
"""

from __future__ import annotations

import logging

from .. import store

logger = logging.getLogger("vodiwalker.botsys.support")

STATUS_OPEN = "open"
STATUS_ANSWERED = "answered"
STATUS_CLOSED = "closed"

STATUS_LABELS = {
    STATUS_OPEN: "باز",
    STATUS_ANSWERED: "پاسخ داده‌شده",
    STATUS_CLOSED: "بسته",
}


#: نوع پیام -> برچسب نمایشی. هر نوعی که تلگرام با copyMessage کپی کند پشتیبانی می‌شود.
KIND_LABELS = {
    "text": "💬 متن", "photo": "🖼 عکس", "video": "🎬 ویدیو", "animation": "🎞 GIF",
    "document": "📎 فایل", "voice": "🎤 ویس", "audio": "🎵 صوت", "video_note": "⭕️ ویدیو پیام",
    "sticker": "🏷 استیکر", "location": "📍 موقعیت", "contact": "👤 مخاطب", "poll": "📊 نظرسنجی",
}
MEDIA_KINDS = tuple(k for k in KIND_LABELS if k != "text")


def describe_message(message: dict | None) -> tuple[str, str]:
    """نوع و متن (یا Caption) یک پیام تلگرام را برمی‌گرداند."""
    message = message or {}
    text = str(message.get("text") or message.get("caption") or "").strip()
    for kind in MEDIA_KINDS:
        if kind in message:
            return kind, text
    return "text", text


def kind_label(kind: str) -> str:
    return KIND_LABELS.get(kind or "text", "📎 پیوست")


def media_messages(ticket_id: str, limit: int = 10) -> list[dict]:
    rows = [m for m in messages_of(ticket_id) if m.get("src_msg") and m.get("kind", "text") != "text"]
    return rows[-limit:]


def open_ticket_of(telegram_id: int) -> dict | None:
    for rec in store.TG_TICKETS.values():
        if str(rec.get("telegram_id")) == str(telegram_id) and rec.get("status") != STATUS_CLOSED:
            return rec
    return None


def get(ticket_id: str) -> dict | None:
    return store.TG_TICKETS.get(str(ticket_id))


def messages_of(ticket_id: str) -> list[dict]:
    rows = [m for m in store.TG_MESSAGES.values() if str(m.get("ticket_id")) == str(ticket_id)]
    rows.sort(key=lambda m: str(m.get("at") or ""))
    return rows


def listing(status: str | None = None, limit: int = 10) -> list[dict]:
    rows = list(store.TG_TICKETS.values())
    if status:
        rows = [r for r in rows if r.get("status") == status]
    rows.sort(key=lambda r: str(r.get("updated_at") or r.get("created_at") or ""), reverse=True)
    return rows[:limit]


def open_count() -> int:
    return sum(1 for r in store.TG_TICKETS.values() if r.get("status") == STATUS_OPEN)


async def add_user_message(telegram_id: int, text: str, message: dict | None = None) -> dict:
    """پیام کاربر را در تیکت باز او ثبت می‌کند (در صورت نبود، تیکت می‌سازد)."""
    ticket = open_ticket_of(telegram_id)
    if ticket is None:
        tid = store.next_id(store.TG_TICKETS)
        ticket = {
            "id": tid,
            "telegram_id": int(telegram_id),
            "status": STATUS_OPEN,
            "created_at": store.now_iso(),
            "updated_at": store.now_iso(),
        }
        store.TG_TICKETS[tid] = ticket
        store.bump_stat("tickets_opened")

    mid = store.next_id(store.TG_MESSAGES)
    record = {
        "id": mid,
        "ticket_id": ticket["id"],
        "sender": "user",
        "sender_id": int(telegram_id),
        "text": str(text or "")[:3500],
        "at": store.now_iso(),
        **_media_fields(message),
    }
    store.TG_MESSAGES[mid] = record
    ticket["status"] = STATUS_OPEN
    ticket["updated_at"] = store.now_iso()
    ticket["last_preview"] = (record["text"] or kind_label(record["kind"]))[:80]
    return ticket


def _media_fields(message: dict | None) -> dict:
    kind, _text = describe_message(message)
    fields = {"kind": kind}
    chat_id = ((message or {}).get("chat") or {}).get("id")
    if message and message.get("message_id") and chat_id is not None:
        fields["src_chat"] = int(chat_id)
        fields["src_msg"] = int(message["message_id"])
    return fields


async def add_admin_reply(actor_id: int, ticket_id: str, text: str, message: dict | None = None) -> dict | None:
    from .. import audit
    ticket = get(ticket_id)
    if not ticket:
        return None
    mid = store.next_id(store.TG_MESSAGES)
    store.TG_MESSAGES[mid] = {
        "id": mid,
        "ticket_id": str(ticket_id),
        "sender": "admin",
        "sender_id": int(actor_id),
        "text": str(text or "")[:3500],
        "at": store.now_iso(),
        **_media_fields(message),
    }
    ticket["status"] = STATUS_ANSWERED
    ticket["updated_at"] = store.now_iso()
    ticket["answered_by"] = int(actor_id)
    audit.record(actor_id, "support_reply", ticket.get("telegram_id"), "ticket", None, ticket_id)
    return ticket


async def close(actor_id: int, ticket_id: str) -> bool:
    from .. import audit
    ticket = get(ticket_id)
    if not ticket:
        return False
    before = ticket.get("status")
    ticket["status"] = STATUS_CLOSED
    ticket["updated_at"] = store.now_iso()
    audit.record(actor_id, "support_close", ticket.get("telegram_id"), "status", before, STATUS_CLOSED)
    return True
