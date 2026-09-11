"""Small Twilio Messaging client used for SMS and WhatsApp delivery."""

import re

import requests


TWILIO_API = "https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
TWILIO_MESSAGE_API = "https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages/{message_sid}.json"
TWILIO_ACCOUNT_API = "https://api.twilio.com/2010-04-01/Accounts/{account_sid}.json"
TWILIO_NUMBERS_API = "https://api.twilio.com/2010-04-01/Accounts/{account_sid}/IncomingPhoneNumbers.json"
TWILIO_SERVICES_API = "https://messaging.twilio.com/v1/Services"
TWILIO_WHATSAPP_SENDERS_API = "https://messaging.twilio.com/v2/Channels/Senders"


def _request(method, url, account_sid, auth_token, **kwargs):
    if not account_sid or not auth_token:
        return None, "Twilio Account SID and Auth Token are not configured."
    try:
        response = requests.request(
            method, url, auth=(account_sid, auth_token), timeout=15, **kwargs)
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        return None, f"Twilio could not be reached: {exc}"
    if not response.ok:
        return None, str(data.get("message") or f"Twilio returned HTTP {response.status_code}.")
    return data, None


def account_overview(account_sid, auth_token):
    """Return safe account, owned-number, service, and WhatsApp sender metadata."""
    account, error = _request(
        "GET", TWILIO_ACCOUNT_API.format(account_sid=account_sid),
        account_sid, auth_token)
    if error:
        return None, error
    numbers, numbers_error = _request(
        "GET", TWILIO_NUMBERS_API.format(account_sid=account_sid),
        account_sid, auth_token, params={"PageSize": 100})
    services, services_error = _request(
        "GET", TWILIO_SERVICES_API, account_sid, auth_token,
        params={"PageSize": 50})
    senders, senders_error = _request(
        "GET", TWILIO_WHATSAPP_SENDERS_API, account_sid, auth_token,
        params={"Channel": "whatsapp", "PageSize": 50})
    return {
        "account": {key: account.get(key) for key in ("friendly_name", "status", "type")},
        "numbers": [
            {key: row.get(key) for key in ("sid", "phone_number", "friendly_name", "capabilities")}
            for row in (numbers or {}).get("incoming_phone_numbers", [])
        ],
        "services": [
            {key: row.get(key) for key in ("sid", "friendly_name")}
            for row in (services or {}).get("services", [])
        ],
        "whatsapp_senders": [
            {key: row.get(key) for key in ("sid", "sender_id", "status")}
            for row in (senders or {}).get("senders", [])
        ],
        "warnings": [message for message in (numbers_error, services_error, senders_error) if message],
    }, None


def create_messaging_service(account_sid, auth_token, phone_number_sid):
    """Create Yazory's Messaging Service and attach one owned SMS number."""
    service, error = _request(
        "POST", TWILIO_SERVICES_API, account_sid, auth_token,
        data={"FriendlyName": "Yazory Messaging"})
    if error:
        return None, error
    service_sid = service.get("sid")
    _, error = _request(
        "POST", f"{TWILIO_SERVICES_API}/{service_sid}/PhoneNumbers",
        account_sid, auth_token, data={"PhoneNumberSid": phone_number_sid})
    if error:
        return None, error
    return service_sid, None


def find_messaging_service_for_number(account_sid, auth_token, services,
                                      phone_number_sid):
    """Return the Messaging Service that already owns a Twilio number."""
    for service in services:
        service_sid = service.get("sid")
        if not service_sid:
            continue
        numbers, error = _request(
            "GET", f"{TWILIO_SERVICES_API}/{service_sid}/PhoneNumbers",
            account_sid, auth_token, params={"PageSize": 100})
        if error:
            continue
        for number in (numbers or {}).get("phone_numbers", []):
            if number.get("sid") == phone_number_sid:
                return service_sid
    return None


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


def message_status(account_sid, auth_token, message_sid):
    """Return safe delivery details for one Twilio Message SID."""
    if not re.fullmatch(r"SM[a-fA-F0-9]{32}", message_sid or ""):
        return None, "Enter a valid Twilio message reference."
    data, error = _request(
        "GET",
        TWILIO_MESSAGE_API.format(
            account_sid=account_sid, message_sid=message_sid),
        account_sid, auth_token)
    if error:
        return None, error
    return {
        key: data.get(key)
        for key in ("sid", "status", "error_code", "error_message", "to", "from")
    }, None
