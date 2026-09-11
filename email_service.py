"""Small transactional-email adapter with no provider SDK dependency."""
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def deliver(api_key, sender, recipient, subject, html, text, timeout=10):
    """Send through Resend and return (provider_id, error_message)."""
    if not api_key or not sender:
        return None, 'Email delivery is not configured.'
    payload = json.dumps({
        'from': sender, 'to': [recipient], 'subject': subject,
        'html': html, 'text': text,
    }).encode()
    request = Request('https://api.resend.com/emails', data=payload, method='POST', headers={
        'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json',
        'User-Agent': 'Yazory/1.0',
    })
    try:
        with urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode())
            provider_id = body.get('id')
            if not provider_id:
                return None, 'Email provider accepted the request without returning a delivery ID.'
            return provider_id, None
    except HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode()).get('message')
        except (ValueError, AttributeError):
            detail = None
        return None, detail or f'Email provider returned HTTP {exc.code}.'
    except (URLError, TimeoutError) as exc:
        return None, f'Email provider could not be reached: {exc.reason if hasattr(exc, "reason") else exc}'
