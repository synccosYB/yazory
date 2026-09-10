"""Generate editable supporter-email drafts without exposing family details."""
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def draft_initial_email(api_key, model='gpt-5-mini', language='en', timeout=20):
    if not api_key:
        raise ValueError('AI email writing is not configured.')
    language_instruction = {
        'yi': ('Write in natural heimish Yiddish using Hebrew letters, in the '
               'warm everyday style used by Satmar-speaking community staff.'),
        'he': 'Write in warm, natural Hebrew.',
        'en': 'Write in warm, natural English.',
    }.get(language, 'Write in warm, natural English.')
    prompt = (
        'Write a short, warm, respectful email from a Jewish family-support '
        'organization after a supporter did not answer a phone call. Ask what '
        'time is convenient to speak. Do not mention medical, financial, family, '
        'or other private case details. Keep the placeholders {supporter_name} '
        'and {staff_name} exactly as written. Return only the email body, no '
        f'subject line, markdown, commentary, or signature. {language_instruction}')
    payload = json.dumps({
        'model': model, 'input': prompt, 'store': False,
        'text': {'verbosity': 'low'},
    }).encode()
    request = Request('https://api.openai.com/v1/responses', data=payload,
                      method='POST', headers={
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
        'User-Agent': 'Yazory/1.0',
    })
    try:
        with urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode())
    except HTTPError as exc:
        raise ValueError(f'AI email service returned HTTP {exc.code}.') from None
    except (URLError, TimeoutError, ValueError, KeyError, TypeError):
        raise ValueError('AI email service could not be reached.') from None
    text = ''.join(
        part.get('text', '')
        for item in data.get('output', []) if item.get('type') == 'message'
        for part in item.get('content', []) if part.get('type') == 'output_text'
    ).strip()
    if not text or len(text) > 5000:
        raise ValueError('AI email service did not return a usable draft.')
    return text
