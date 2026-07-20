"""One-way push into MealGenie's shopping list (SPEC §6 Supplies).

Tada deliberately has NO shopping list of its own — the owner already
uses and loves MealGenie's. When a supply is marked low/out we POST it to
MealGenie's first-party endpoint, tagged (source "tada", category
"household") so household supplies stay distinguishable from groceries.

Endpoint contract (as built in the MealGenie repo,
backend/app/api/shopping.py `upsert_external_item`):

    POST {MEALGENIE_API_URL}/api/shopping/external/items
    Header: X-API-Key: {MEALGENIE_API_KEY}   # = MealGenie's INTEGRATION_API_KEY
    Body: { "name": ..., "source": "tada", "category": "household" }
    -> 201 (inserted) or 200 (updated existing), both success

MealGenie upserts by (name, source) onto its INTEGRATION_USER_ID
account, so even if Tada's own dedupe (Supply.last_pushed_at) is ever
bypassed, no duplicate rows appear. Failures are logged and swallowed:
marking a supply low must never fail just because the other app is down
— the caller keeps last_pushed_at unset so the next status change
retries naturally.
"""

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

API_KEY_HEADER = "X-API-Key"
REQUEST_TIMEOUT_SECONDS = 5.0


def is_configured() -> bool:
    return bool(settings.mealgenie_api_url and settings.mealgenie_api_key)


def push_item(name: str) -> bool:
    """Add one household item to MealGenie's shopping list. Returns True
    only when MealGenie accepted it — the caller uses that to stamp
    Supply.last_pushed_at."""
    if not is_configured():
        logger.info("MealGenie not configured; skipping push of %r", name)
        return False

    url = f"{settings.mealgenie_api_url.rstrip('/')}/api/shopping/external/items"
    try:
        response = httpx.post(
            url,
            json={"name": name, "source": "tada", "category": "household"},
            headers={API_KEY_HEADER: settings.mealgenie_api_key},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        logger.info("Pushed %r to MealGenie's shopping list", name)
        return True
    except httpx.HTTPError as exc:
        logger.error("MealGenie push failed for %r: %s", name, exc)
        return False
