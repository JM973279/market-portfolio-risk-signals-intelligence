"""When a data batch keeps the published data and retries instead of failing.

Every collection workflow publishes only verified data, so a run that cannot verify new data
writes nothing and the service keeps serving the last published snapshot. Such a run is not a
reception failure while the provider is merely unreachable, late, or out of step with data that
was already verified, so it ends with a warning and the next scheduled run collects again:

- the error is one of DEFERRABLE (provider unreachable, a session not posted yet, a provider
  withholding or moving back a verified session, a factor late), and
- the published data is at most MAX_BEHIND completed sessions behind.

Everything else still fails the run, because retrying cannot fix it or the gap has become long
enough to need a person: nothing published yet, more than MAX_BEHIND sessions behind, a missing
or rejected key ('config_error'), or invalid data, hash or verification mismatches.
"""
from __future__ import annotations

DEFERRABLE = frozenset({'collection_failed', 'missing_price', 'provider_withheld', 'provider_delayed', 'stale_data'})
# About three trading days: covers a provider that is a day or two late and GitHub dropping
# a few scheduled runs, and still alerts within the same week.
MAX_BEHIND = 3


def sessions_behind(sessions, published):
    """Completed sessions after the published date."""
    return sum(1 for day in sessions if day > published)


def deferral(exc, sessions, published, max_behind=MAX_BEHIND):
    """A warning message when the run may keep the published data and retry, else None."""
    if getattr(exc, 'code', None) not in DEFERRABLE or not published or not sessions:
        return None
    behind = sessions_behind(sessions, published)
    if behind > max_behind:
        return None
    return (f'{exc} 게시본 {published} 유지 (완료 세션 {behind}개 지연, 허용 {max_behind}개); '
            '다음 일정에서 다시 수집합니다.')


def transient_network_error(exc):
    """No answer, a timeout, a dropped connection, or HTTP 429/5xx (a 4xx such as 404 is not transient)."""
    import http.client
    import urllib.error
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code == 429 or exc.code >= 500
    return isinstance(exc, (urllib.error.URLError, TimeoutError, ConnectionError, http.client.HTTPException))


def warn(message):
    print(f'::warning::{message}', flush=True)
