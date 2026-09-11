"""Small Twilio Messaging client used for SMS and WhatsApp delivery."""

import re

import requests


TWILIO_API = "https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"


def normalize_phone(value):
    """Return an E.164 number; Yazory currently defaults 10-digit numbers to US."""
    raw = (value or "").strip()
    digits = re.sub(r"\D", "", raw)
    if raw.startswith("+") and 8 <= len(digits) <= 15:
        return "+" + digits
    if len(digits) == 10:
        return "+1" + digits
    if len(digits) == 11 and digits.startswith("1"):
        return "+" + digits
    raise ValueError("Enter a valid mobile number, including the country code when outside the US.")


def deliver_message(account_sid, auth_token, recipient, body, *, channel,
                    sms_from="", whatsapp_from="", messaging_service_sid="",
                    timeout=15):
    """Send one outbound message and return ``(provider_id, error)``."""
    if not account_sid or not auth_token:
        return None, "Twilio Account SID and Auth Token are not configured."
    try:
        recipient = normalize_phone(recipient)
    except ValueError as exc:
        return None, str(exc)

    payload = {"Body": body}
    if channel == "whatsapp":
        if not whatsapp_from:
            return None, "The Twilio WhatsApp sender is not configured."
        try:
            sender = normalize_phone(whatsapp_from.replace("whatsapp:", "", 1))
        except ValueError:
            return None, "The configured Twilio WhatsApp sender is invalid."
        payload.update(To="whatsapp:" + recipient, From="whatsapp:" + sender)
    elif channel == "sms":
        payload["To"] = recipient
        if messaging_service_sid:
            payload["MessagingServiceSid"] = messaging_service_sid
        elif sms_from:
            try:
                payload["From"] = normalize_phone(sms_from)
            except ValueError:
                return None, "The configured Twilio SMS sender is invalid."
        else:
            return None, "A Twilio SMS sender or Messaging Service SID is not configured."
    else:
        return None, "Unsupported messaging channel."

    try:
        response = requests.post(
            TWILIO_API.format(account_sid=account_sid), data=payload,
            auth=(account_sid, auth_token), timeout=timeout)
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        return None, f"Twilio could not be reached: {exc}"
    if not response.ok:
        return None, str(data.get("message") or f"Twilio returned HTTP {response.status_code}.")
    return data.get("sid"), None
