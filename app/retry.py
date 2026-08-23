import logging
import time

import httpx

logger = logging.getLogger(__name__)

ATTEMPTS = 3
BACKOFF_SECONDS = 1.0
MAX_SLEEP_SECONDS = 30.0
RETRY_STATUSES = {429, 500, 502, 503, 504}


def _sleep_for(resp: httpx.Response | None, attempt: int) -> float:
    """Honour Retry-After when the server sends it, else back off exponentially."""
    if resp is not None:
        header = resp.headers.get("Retry-After", "").strip()
        if header.isdigit():
            return min(float(header), MAX_SLEEP_SECONDS)
    return min(BACKOFF_SECONDS * (2**attempt), MAX_SLEEP_SECONDS)


def request(client: httpx.Client, method: str, url: str, **kwargs) -> httpx.Response:
    """Make a request, retrying throttling, server errors and transport failures.

    Returns the final response. The caller still checks the status: a 404 is an
    answer, not a failure, and is never retried.
    """
    last_error: Exception | None = None
    for attempt in range(ATTEMPTS):
        resp = None
        try:
            resp = client.request(method, url, **kwargs)
            if resp.status_code not in RETRY_STATUSES:
                return resp
            last_error = None
        except httpx.TransportError as exc:
            last_error = exc

        if attempt == ATTEMPTS - 1:
            break
        delay = _sleep_for(resp, attempt)
        logger.warning(
            "[HTTP] Retrying request",
            extra={
                "url": str(url),
                "attempt": attempt + 1,
                "of": ATTEMPTS,
                "status": resp.status_code if resp is not None else None,
                "delay_seconds": delay,
            },
        )
        time.sleep(delay)

    if last_error is not None:
        raise last_error
    return resp


def get(client: httpx.Client, url: str, **kwargs) -> httpx.Response:
    return request(client, "GET", url, **kwargs)


def post(client: httpx.Client, url: str, **kwargs) -> httpx.Response:
    return request(client, "POST", url, **kwargs)
