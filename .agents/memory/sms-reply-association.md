---
name: SMS reply association
description: Rules for linking SMS numbers and describing conversation context without overstating certainty.
---

Treat staff-confirmed SMS number links as aliases to an existing directory person; do not overwrite that person's primary phone fields merely to link an inbound number.

**Why:** A person may legitimately use multiple numbers, and replacing a primary phone can damage existing contact data.

**How to apply:** Resolve normalized numbers dynamically first, use the explicit SMS alias when staff confirms an ambiguous or unmatched number, and keep the original message number unchanged.

Describe the nearest earlier outbound text as “the most recent outgoing SMS before this reply,” not as a proven reply target unless provider metadata establishes that relationship.

**Why:** Twilio inbound SMS payloads do not reliably identify which prior outbound SMS prompted a reply.

**How to apply:** Show chronological context and any case/campaign attached to the outbound record, while avoiding definitive association language.