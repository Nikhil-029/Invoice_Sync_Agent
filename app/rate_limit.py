"""
Minimal in-memory rate limiter — good enough for a single-instance public
demo deploy. Not distributed-safe (fine here: Render free tier runs one
instance), and resets on restart, which is acceptable for a portfolio demo.
"""
import os
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

MAX_UPLOADS_PER_HOUR = int(os.getenv("DEMO_MAX_UPLOADS_PER_HOUR", "8"))
WINDOW_SECONDS = 3600

_hits: dict[str, deque] = defaultdict(deque)


def enforce_upload_rate_limit(request: Request) -> None:
    if os.getenv("DEMO_MODE", "false").lower() != "true":
        return  # only throttle the public demo deployment

    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    bucket = _hits[client_ip]

    while bucket and now - bucket[0] > WINDOW_SECONDS:
        bucket.popleft()

    if len(bucket) >= MAX_UPLOADS_PER_HOUR:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Demo limit reached ({MAX_UPLOADS_PER_HOUR} uploads/hour per visitor). "
                "Try again later, or clone the repo to run it with your own API key."
            ),
        )
    bucket.append(now)
