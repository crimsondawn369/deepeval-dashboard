"""
CookieManager: extracts auth credentials from a Magnolai web UI URL
using Playwright (headless=False — user logs in interactively via SSO).

Auth extraction priority:
  1. Bearer token intercepted from outgoing requests to aichat-api.*
  2. Bearer token from browser storage (MSAL v2, oidc-client-ts, angular-oauth2-oidc)
  3. Session cookie fallback

Credentials are cached for 55 minutes and never written to disk.
"""
import logging
import time
from typing import Optional

from playwright.sync_api import sync_playwright

logger = logging.getLogger(__name__)

COOKIE_TTL_SECONDS = 55 * 60

_PRIORITY_COOKIE_NAMES = {
    "session",
    "access_token",
    "__Secure-next-auth.session-token",
    "connect.sid",
    "jwt",
    # ASP.NET Core cookie-auth (seen alongside the antiforgery cookie this
    # Magnolai backend sets, which strongly suggests cookie, not JWT, auth)
    ".AspNetCore.Cookies",
    ".AspNetCore.Identity.Application",
}

# Cookies that are never valid API auth, even though they can be long and
# JWT-shaped-looking. Matched case-insensitively as a substring, since ASP.NET
# Core appends a random suffix (".AspNetCore.Antiforgery.VyLW6ORzMgk"). Seeing
# one of these picked as "the auth cookie" (previously possible via the
# longest-value fallback below) is a strong signal that no real session/auth
# cookie exists yet — e.g. because login didn't fully complete, or this app
# stores its session token in a shape this file doesn't yet recognize.
_EXCLUDED_COOKIE_SUBSTRINGS = (
    "antiforgery",
    "__requestverificationtoken",
    "correlation",
    "tempdata",
    "ai_session",
    "ai_user",
    "_ga",
    "_gid",
)

# Handles MSAL v2 (@azure/msal-browser), oidc-client-ts, angular-oauth2-oidc
_STORAGE_TOKEN_SCRIPT = """
() => {
    const stores = [localStorage, sessionStorage];
    for (const store of stores) {
        // Direct simple keys (angular-oauth2-oidc stores plain JWT at "access_token")
        for (const key of ['access_token', 'id_token', 'token', 'auth_token', 'jwt']) {
            const val = store.getItem(key) || '';
            if (val.startsWith('ey') && val.split('.').length === 3) return val;
        }

        const accessTokens = [];
        const idTokens = [];

        for (let i = 0; i < store.length; i++) {
            const raw = store.getItem(store.key(i)) || '';
            try {
                const obj = JSON.parse(raw);
                if (!obj || typeof obj !== 'object') continue;

                // MSAL v2: credentialType + secret field
                if (obj.credentialType === 'AccessToken' && obj.secret && obj.secret.startsWith('ey')) {
                    accessTokens.push({ secret: obj.secret, expiresOn: parseInt(obj.expiresOn || '0') });
                    continue;
                }
                if (obj.credentialType === 'IdToken' && obj.secret && obj.secret.startsWith('ey')) {
                    idTokens.push(obj.secret);
                    continue;
                }

                // oidc-client-ts: { access_token: "eyJ..." }
                if (obj.access_token && typeof obj.access_token === 'string' && obj.access_token.startsWith('ey')) {
                    return obj.access_token;
                }

                // Any JSON object with a JWT-valued field
                for (const v of Object.values(obj)) {
                    if (typeof v === 'string' && v.startsWith('ey') && v.split('.').length === 3) {
                        return v;
                    }
                }
            } catch (_) {}

            // Raw JWT stored directly
            if (raw.startsWith('ey') && raw.split('.').length === 3) return raw;
        }

        // Return the most recently valid MSAL access token
        if (accessTokens.length > 0) {
            const now = Math.floor(Date.now() / 1000);
            const valid = accessTokens
                .filter(t => t.expiresOn > now)
                .sort((a, b) => b.expiresOn - a.expiresOn);
            if (valid.length > 0) return valid[0].secret;
            // All expired — return newest anyway (server will decide)
            accessTokens.sort((a, b) => b.expiresOn - a.expiresOn);
            return accessTokens[0].secret;
        }
        if (idTokens.length > 0) return idTokens[0];
    }
    return null;
}
"""

# Dumps all storage keys for debugging
_STORAGE_DUMP_SCRIPT = """
() => {
    const out = {};
    for (const store of [localStorage, sessionStorage]) {
        for (let i = 0; i < store.length; i++) {
            const k = store.key(i);
            const v = store.getItem(k) || '';
            out[k] = v.length > 80 ? v.slice(0, 80) + '...' : v;
        }
    }
    return out;
}
"""


class CookieManager:
    def __init__(self, chat_url: str):
        self._chat_url = chat_url
        self._auth_value: Optional[str] = None   # "Bearer <token>" or "name=value"
        self._extracted_at: Optional[float] = None

    def get_auth_value(self, force_refresh: bool = False) -> str:
        if force_refresh or self._is_expired():
            self._extract_auth()
        if self._auth_value is None:
            raise RuntimeError(
                f"Auth extraction failed for {self._chat_url}. "
                "No token or cookie was found after login."
            )
        return self._auth_value

    def get_cookie_header(self, force_refresh: bool = False) -> str:
        return self.get_auth_value(force_refresh=force_refresh)

    def _is_expired(self) -> bool:
        if self._auth_value is None or self._extracted_at is None:
            return True
        return (time.time() - self._extracted_at) > COOKIE_TTL_SECONDS

    def _extract_auth(self) -> None:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="msedge", headless=False)
            context = browser.new_context()

            captured_bearer: dict = {"value": None}

            def _on_request(request):
                if "aichat-api" in request.url and not captured_bearer["value"]:
                    auth = request.headers.get("authorization", "")
                    if auth.startswith("Bearer "):
                        captured_bearer["value"] = auth[7:]
                        logger.info("[auth] Intercepted Bearer from request to %s", request.url[:80])

            context.on("request", _on_request)
            page = context.new_page()

            try:
                page.goto(self._chat_url, timeout=30_000)
                # Wait long enough for the SSO redirect chain to start
                page.wait_for_timeout(5_000)

                # Wait until fully back on Magnolai (post-SSO) — but skip if we never
                # left (Windows SSO can complete silently within the first 5 s)
                page.wait_for_function(
                    """() => {
                        const url = window.location.href;
                        return url.includes('magnolai.lilly.com') &&
                               !url.includes('login') &&
                               !url.includes('signin') &&
                               !url.includes('microsoftonline.com');
                    }""",
                    timeout=120_000,
                )
                page.wait_for_load_state("networkidle", timeout=30_000)

                # Hold browser open so the user can inspect console/network tabs
                page.wait_for_timeout(15_000)

                # --- 1. Bearer from intercepted network request ---
                if captured_bearer["value"]:
                    self._auth_value = f"Bearer {captured_bearer['value']}"
                    self._extracted_at = time.time()
                    self._notify_browser(page, "✅ Auth captured via network — closing browser…")
                    page.wait_for_timeout(3_000)
                    logger.info("[auth] Bearer captured via network interception")
                    return

                # --- 2. Bearer from browser storage (MSAL / oidc-client-ts / etc.) ---
                token = page.evaluate(_STORAGE_TOKEN_SCRIPT)
                if token:
                    self._auth_value = f"Bearer {token}"
                    self._extracted_at = time.time()
                    self._notify_browser(page, "✅ Auth captured from storage — closing browser…")
                    page.wait_for_timeout(3_000)
                    logger.info("[auth] Bearer captured from browser storage (first 20 chars: %s)", token[:20])
                    return

                # Debug: show what IS in storage so we can tune the script
                storage_dump = page.evaluate(_STORAGE_DUMP_SCRIPT)
                logger.info("[auth] Storage dump (%d keys):", len(storage_dump))
                for k, v in list(storage_dump.items())[:20]:
                    logger.info("[auth]   %s: %s", k, v)

                # --- 3. Cookie fallback ---
                cookies = context.cookies()
                logger.info("[auth] Trying cookie fallback — %d cookies found", len(cookies))
                found = self._find_auth_cookie(cookies)
                if found:
                    self._auth_value = f"{found['name']}={found['value']}"
                    self._extracted_at = time.time()
                    self._notify_browser(page, f"✅ Cookie captured ({found['name']}) — closing browser…")
                    page.wait_for_timeout(3_000)
                    logger.info("[auth] Cookie captured: %s", found['name'])
                else:
                    names = [c["name"] for c in cookies]
                    raise RuntimeError(
                        f"No auth token or cookie found at {self._chat_url}. "
                        f"Cookies: {names}"
                    )
            finally:
                browser.close()

    @staticmethod
    def _notify_browser(page, message: str) -> None:
        try:
            page.evaluate(f"""() => {{
                const d = document.createElement('div');
                d.innerText = {repr(message)};
                d.style.cssText = 'position:fixed;top:20px;left:50%;transform:translateX(-50%);'
                    + 'background:#1a1a2e;color:#00e5c3;border:2px solid #00e5c3;'
                    + 'padding:16px 28px;border-radius:10px;font-size:18px;font-weight:bold;'
                    + 'z-index:999999;font-family:sans-serif;';
                document.body.appendChild(d);
            }}""")
        except Exception:
            pass

    @staticmethod
    def _find_auth_cookie(cookies: list[dict]) -> Optional[dict]:
        if not cookies:
            return None
        candidates = [
            c for c in cookies
            if not any(bad in c["name"].lower() for bad in _EXCLUDED_COOKIE_SUBSTRINGS)
        ]
        if not candidates:
            logger.warning(
                "[auth] All %d cookie(s) matched an excluded name (antiforgery/telemetry/etc) "
                "— none look like real auth cookies. Cookie names seen: %s",
                len(cookies), [c["name"] for c in cookies],
            )
            return None
        for c in candidates:
            if c["name"] in _PRIORITY_COOKIE_NAMES:
                return c
        for c in candidates:
            v = c.get("value", "")
            if v.startswith("ey") and v.count(".") == 2:
                return c
        # No named/JWT-shaped match — refuse to guess. Returning "whatever
        # cookie happens to be longest" previously picked non-auth cookies
        # (e.g. an ASP.NET Core antiforgery token) that the backend silently
        # rejects, producing empty answers with no obvious error.
        logger.warning(
            "[auth] No priority-named or JWT-shaped cookie found among candidates: %s",
            [c["name"] for c in candidates],
        )
        return None


# ---------------------------------------------------------------------------
# Module-level cache — one manager per chat URL
# ---------------------------------------------------------------------------

_managers: dict[str, CookieManager] = {}


def get_cookie_manager(chat_url: str) -> CookieManager:
    if chat_url not in _managers:
        _managers[chat_url] = CookieManager(chat_url)
    return _managers[chat_url]
