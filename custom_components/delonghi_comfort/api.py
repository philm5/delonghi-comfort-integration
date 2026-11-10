"""API client for De'Longhi Comfort devices."""

import asyncio
import json
import logging
import urllib.parse
from datetime import datetime
from typing import Any

import aiohttp

from .const import (
    API_KEY,
    CLIENT_ID,
    AUTHORIZATION_HEADER,
    APP_ID,
    APP_SECRET,
    BROWSER_USER_AGENT,
    TOKEN_USER_AGENT,
    API_USER_AGENT,
    SDK_BUILD,
)
from .exceptions import DeLonghiAuthError, DeLonghiConnectionError

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=15, connect=10)
AUTH_TIMEOUT = 60

# ---------------------------------------------------------------------------
# Transport-level errors that indicate a *transient* network problem.
# These are caught at each aiohttp call site and re-raised as
# DeLonghiConnectionError so callers can apply retry logic.
# ---------------------------------------------------------------------------
_CONN_ERRORS: tuple[type[Exception], ...] = (
    aiohttp.ClientError,
    asyncio.TimeoutError,
)


class DeLonghiAPI:
    """API client for De'Longhi Comfort devices."""

    def __init__(
        self,
        username: str,
        password: str,
        session: aiohttp.ClientSession,
        language: str = "en",
    ) -> None:
        """Initialize the API client."""
        self.username = username
        self.password = password
        self.language = language
        self.session = session
        self.access_token: str | None = None
        self.refresh_token: str | None = None
        self._auth_lock = asyncio.Lock()
        self._token_generation = 0

    # ------------------------------------------------------------------
    # Helper utilities
    # ------------------------------------------------------------------

    def get_query_param(self, url: str, param: str) -> str | None:
        """Extract a query parameter from a URL."""
        query = urllib.parse.urlparse(url).query
        params = urllib.parse.parse_qs(query)
        return params.get(param, [None])[0]

    def url_encode(self, value: str) -> str:
        """URL-encode a value."""
        return urllib.parse.quote(value)

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    async def authenticate(self) -> bool:
        """Authenticate with the De'Longhi API.

        Exceptions are intentionally NOT caught here so they propagate to the
        caller (async_setup_entry) which applies the appropriate retry/fail logic.

        Raises:
            DeLonghiAuthError: Credentials rejected.
            DeLonghiConnectionError: Transient network/transport error.
        """
        generation = self._token_generation
        async with self._auth_lock:
            if generation == self._token_generation:
                self.access_token = await self._get_new_access_token()
                self._token_generation += 1
            return bool(self.access_token)

    async def _refresh_if_needed(self, generation: int) -> str:
        """Renew once for concurrent requests using the same token generation."""
        async with self._auth_lock:
            if generation == self._token_generation:
                self.access_token = await self._refresh_access_token()
                self._token_generation += 1
            if not self.access_token:
                raise DeLonghiConnectionError("Token refresh returned no access token")
            return self.access_token

    async def refresh_access_token(self) -> str:
        """Refresh the account token, sharing concurrent renewal attempts."""
        return await self._refresh_if_needed(self._token_generation)

    async def _get_new_access_token(self) -> str:
        """Execute the full 8-step Gigya → Ayla authentication flow.

        Returns the Ayla access token string on success.

        Raises:
            DeLonghiAuthError: Login rejected by Gigya.
            DeLonghiConnectionError: Transport error or malformed response.
        """
        # Thanks to https://github.com/duckwc/ECAMpy for the code→token conversion.
        # Thanks to https://github.com/rtfpessoa/delonghi-comfort-client for the
        # authentication flow implementation.
        stage = "OIDC authorization"
        try:
            async with asyncio.timeout(AUTH_TIMEOUT):
                # ----------------------------------------------------------
                # Step 1: Start OIDC authorisation – obtain `context`
                # ----------------------------------------------------------
                stage = "OIDC authorization"
                async with self.session.get(
                    f"https://fidm.eu1.gigya.com/oidc/op/v1.0/{API_KEY}/authorize",
                    headers={"User-Agent": BROWSER_USER_AGENT},
                    timeout=REQUEST_TIMEOUT,
                    params={
                        "client_id": CLIENT_ID,
                        "response_type": "code",
                        "redirect_uri": "https://google.it",
                        "scope": "openid email profile UID comfort en alexa",
                        "nonce": str(int(datetime.now().timestamp())),
                    },
                    allow_redirects=False,
                ) as response:
                    response.raise_for_status()
                    context = self.get_query_param(response.headers["Location"], "context")

                if not context:
                    raise DeLonghiConnectionError("Missing context in authorization redirect")

                # ----------------------------------------------------------
                # Step 2: Fetch Gigya session identifiers (ucid / gmid)
                # ----------------------------------------------------------
                stage = "Gigya session identifiers"
                async with self.session.get(
                    "https://socialize.eu1.gigya.com/socialize.getIDs",
                    headers={"User-Agent": BROWSER_USER_AGENT},
                    timeout=REQUEST_TIMEOUT,
                    params={
                        "APIKey": API_KEY,
                        "includeTicket": "true",
                        "pageURL": "https://aylaopenid.delonghigroup.com/",
                        "sdk": "js_latest",
                        "sdkBuild": SDK_BUILD,
                        "format": "json",
                    },
                ) as response:
                    response.raise_for_status()
                    data = json.loads(await response.text())

                ucid = data["ucid"]
                gmid = data["gmid"]
                gmid_ticket = data["gmidTicket"]

                # ----------------------------------------------------------
                # Step 3: Login with credentials
                # ----------------------------------------------------------
                stage = "Gigya login"
                risk_context_json = json.dumps(
                    {
                        "b0": 4494,
                        "b1": [0, 2, 2, 0],
                        "b2": 2,
                        "b3": [],
                        "b4": 2,
                        "b5": 1,
                        "b6": BROWSER_USER_AGENT,
                        "b7": [
                            {
                                "name": "PDF Viewer",
                                "filename": "internal-pdf-viewer",
                                "length": 2,
                            },
                            {
                                "name": "Chrome PDF Viewer",
                                "filename": "internal-pdf-viewer",
                                "length": 2,
                            },
                            {
                                "name": "Chromium PDF Viewer",
                                "filename": "internal-pdf-viewer",
                                "length": 2,
                            },
                            {
                                "name": "Microsoft Edge PDF Viewer",
                                "filename": "internal-pdf-viewer",
                                "length": 2,
                            },
                            {
                                "name": "WebKit built-in PDF",
                                "filename": "internal-pdf-viewer",
                                "length": 2,
                            },
                        ],
                        "b8": datetime.now().strftime("%H:%M:%S"),
                        "b9": 0,
                        "b10": {"state": "denied"},
                        "b11": False,
                        "b13": [5, "440|956|24", False, True],
                    }
                )

                async with self.session.post(
                    "https://accounts.eu1.gigya.com/accounts.login",
                    headers={"User-Agent": BROWSER_USER_AGENT},
                    timeout=REQUEST_TIMEOUT,
                    data={
                        "loginID": self.username,
                        "password": self.password,
                        "sessionExpiration": 7884009,
                        "targetEnv": "jssdk",
                        "include": "profile,data,emails,subscriptions,preferences",
                        "includeUserInfo": "true",
                        "loginMode": "standard",
                        "lang": self.language,
                        "riskContext": self.url_encode(risk_context_json),
                        "APIKey": API_KEY,
                        "source": "showScreenSet",
                        "sdk": "js_latest",
                        "authMode": "cookie",
                        "pageURL": "https://aylaopenid.delonghigroup.com/",
                        "gmid": gmid,
                        "ucid": ucid,
                        "sdkBuild": SDK_BUILD,
                        "format": "json",
                    },
                ) as response:
                    response.raise_for_status()
                    login_data = json.loads(await response.text())

                status = login_data["statusCode"]
                if not isinstance(status, int):
                    raise DeLonghiConnectionError("Invalid Gigya login status")
                # Server failures and throttling do not mean the password is wrong.
                if status == 429 or status >= 500:
                    raise DeLonghiConnectionError("Gigya login is temporarily unavailable")

                # ── Hard-failure: wrong credentials ──────────────────────
                if status != 200:
                    raise DeLonghiAuthError(
                        f"Gigya login failed (statusCode {status})"
                    )

                login_token = login_data["sessionInfo"]["login_token"]

                # ----------------------------------------------------------
                # Step 4: Get user info (UID + signature)
                # ----------------------------------------------------------
                stage = "Gigya user info"
                async with self.session.post(
                    "https://socialize.eu1.gigya.com/socialize.getUserInfo",
                    headers={"User-Agent": BROWSER_USER_AGENT},
                    timeout=REQUEST_TIMEOUT,
                    data={
                        "enabledProviders": "*",
                        "APIKey": API_KEY,
                        "sdk": "js_latest",
                        "login_token": login_token,
                        "authMode": "cookie",
                        "pageURL": "https://aylaopenid.delonghigroup.com/",
                        "gmid": gmid,
                        "ucid": ucid,
                        "sdkBuild": SDK_BUILD,
                        "format": "json",
                    },
                ) as response:
                    response.raise_for_status()
                    user_data = json.loads(await response.text())

                user_uid = user_data["UID"]
                user_uid_signature = user_data["UIDSignature"]
                user_signature_timestamp = user_data["signatureTimestamp"]

                # ----------------------------------------------------------
                # Step 5: Consent page – extract `sig`
                # ----------------------------------------------------------
                stage = "OIDC consent"
                async with self.session.get(
                    "https://aylaopenid.delonghigroup.com/OIDCConsentPage.php",
                    headers={"User-Agent": BROWSER_USER_AGENT},
                    timeout=REQUEST_TIMEOUT,
                    params={
                        "lang": self.language,
                        "context": context,
                        "clientID": CLIENT_ID,
                        "scope": "openid+email+profile+UID+comfort+en+alexa",
                        "UID": user_uid,
                        "UIDSignature": user_uid_signature,
                        "signatureTimestamp": user_signature_timestamp,
                    },
                ) as response:
                    response.raise_for_status()
                    consent_text = await response.text()

                signature = consent_text.split('const consentObj2Sig = "')[1].split('";')[0]

                # ----------------------------------------------------------
                # Step 6: Authorisation continuation – obtain OIDC `code`
                # ----------------------------------------------------------
                stage = "OIDC continuation"
                async with self.session.get(
                    f"https://fidm.eu1.gigya.com/oidc/op/v1.0/{API_KEY}/authorize/continue",
                    headers={"User-Agent": BROWSER_USER_AGENT},
                    timeout=REQUEST_TIMEOUT,
                    params={
                        "context": context,
                        "login_token": login_token,
                        "consent": json.dumps(
                            {
                                "scope": "openid email profile UID comfort en alexa",
                                "clientID": CLIENT_ID,
                                "context": context,
                                "UID": user_uid,
                                "consent": True,
                            },
                            separators=(",", ":"),
                        ),
                        "sig": signature,
                        "gmidTicket": gmid_ticket,
                    },
                    allow_redirects=False,
                ) as response:
                    response.raise_for_status()
                    code = self.get_query_param(response.headers["Location"], "code")

                # ----------------------------------------------------------
                # Step 7: Exchange OIDC code for IDP access token
                # ----------------------------------------------------------
                stage = "OIDC token exchange"
                async with self.session.post(
                    f"https://fidm.eu1.gigya.com/oidc/op/v1.0/{API_KEY}/token",
                    timeout=REQUEST_TIMEOUT,
                    headers={
                        "User-Agent": TOKEN_USER_AGENT,
                        "Authorization": AUTHORIZATION_HEADER,
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                    data={
                        "code": code,
                        "grant_type": "authorization_code",
                        "redirect_uri": "https://google.it",
                    },
                ) as response:
                    response.raise_for_status()
                    token_data = json.loads(await response.text())

                idp_token = token_data["access_token"]

                # ----------------------------------------------------------
                # Step 8: Exchange IDP token for Ayla Networks token
                # ----------------------------------------------------------
                stage = "Ayla token exchange"
                async with self.session.post(
                    "https://user-field-eu.aylanetworks.com/api/v1/token_sign_in",
                    headers={"User-Agent": TOKEN_USER_AGENT},
                    timeout=REQUEST_TIMEOUT,
                    data={
                        "app_id": APP_ID,
                        "app_secret": APP_SECRET,
                        "token": idp_token,
                    },
                ) as response:
                    response.raise_for_status()
                    ayla_data = json.loads(await response.text())

                self.refresh_token = ayla_data["refresh_token"]
                access_token = ayla_data["access_token"]
                if not isinstance(access_token, str) or not access_token:
                    raise DeLonghiConnectionError("Missing access token in login response")
                return access_token

        # ── Re-raise auth errors untouched ───────────────────────────────────
        except DeLonghiAuthError as err:
            raise DeLonghiAuthError(f"{stage}: {err}") from err
        except DeLonghiConnectionError as err:
            raise DeLonghiConnectionError(f"{stage}: {err}") from err

        # ── Transient transport/network errors → DeLonghiConnectionError ─────
        except aiohttp.ClientResponseError as err:
            if err.status in (401, 403):
                raise DeLonghiAuthError(f"Authentication rejected during {stage}: HTTP {err.status}") from err
            raise DeLonghiConnectionError(
                f"Authentication failed during {stage}: HTTP {err.status}"
            ) from err
        except _CONN_ERRORS as err:
            raise DeLonghiConnectionError(
                f"Authentication failed during {stage}: {type(err).__name__}"
            ) from err

        # A malformed response is not evidence of invalid credentials.
        except (KeyError, IndexError, TypeError, ValueError) as err:
            raise DeLonghiConnectionError(
                f"Unexpected authentication response structure during {stage}"
            ) from err

    async def _refresh_access_token(self) -> str:
        """Refresh the Ayla access token.

        Falls back to a full re-authentication if the refresh token is absent
        or the refresh endpoint rejects the token.

        Raises:
            DeLonghiConnectionError: If a transient network error occurs.
            DeLonghiAuthError: Propagated from _get_new_access_token on
                credential failures during fallback authentication.
        """
        if not self.refresh_token:
            return await self._get_new_access_token()

        try:
            async with self.session.post(
                "https://user-field-eu.aylanetworks.com/users/refresh_token.json",
                timeout=REQUEST_TIMEOUT,
                headers={
                    "User-Agent": TOKEN_USER_AGENT,
                    "Content-Type": "application/json",
                },
                json={"user": {"refresh_token": self.refresh_token}},
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    new_access_token = data["access_token"]
                    if new_refresh_token := data.get("refresh_token"):
                        self.refresh_token = new_refresh_token
                    if not isinstance(new_access_token, str) or not new_access_token:
                        raise DeLonghiConnectionError("Missing refreshed access token")
                    return new_access_token

                if response.status in (400, 401, 403, 422):
                    _LOGGER.debug("Refresh token rejected; attempting full login")
                    return await self._get_new_access_token()
                response.raise_for_status()
                raise DeLonghiConnectionError("Unexpected token refresh response")

        except (DeLonghiAuthError, DeLonghiConnectionError):
            raise
        except _CONN_ERRORS as err:
            raise DeLonghiConnectionError(
                f"Token refresh failed: {type(err).__name__}"
            ) from err
        except (KeyError, TypeError, ValueError) as err:
            raise DeLonghiConnectionError("Invalid token refresh response") from err

    # ------------------------------------------------------------------
    # Device-level API helpers
    # ------------------------------------------------------------------

    async def get_devices(self) -> list[dict[str, Any]]:
        """Return all devices registered to the account.

        Raises:
            DeLonghiConnectionError: Propagated from _get_request on transient
                network errors so Home Assistant can handle retry/recovery.
            DeLonghiAuthError: If re-authentication is required and fails hard.
        """
        if not self.access_token:
            await self.authenticate()

        response = await self._get_request("apiv1/devices.json")
        if not isinstance(response, list) or any(
            not isinstance(item, dict)
            or not isinstance(item.get("device"), dict)
            or not isinstance(item["device"].get("dsn"), str)
            or not item["device"]["dsn"]
            for item in response
        ):
            raise DeLonghiConnectionError("Invalid device list response")
        return response

    async def get_device_properties(self, dsn: str) -> list[dict[str, Any]]:
        """Return all properties for *dsn*.

        Raises:
            DeLonghiConnectionError: Propagated from _get_request.
        """
        if not self.access_token:
            await self.authenticate()

        response = await self._get_request(f"apiv1/dsns/{dsn}/properties.json")
        if not isinstance(response, list) or not response:
            raise DeLonghiConnectionError(f"Missing device properties for {dsn}")
        for item in response:
            prop = item.get("property") if isinstance(item, dict) else None
            if (
                not isinstance(prop, dict)
                or not isinstance(prop.get("name"), str)
                or not prop["name"]
                or "value" not in prop
            ):
                raise DeLonghiConnectionError(f"Invalid device properties for {dsn}")
        return response

    def get_property_value(
        self, properties: list[dict], property_name: str
    ) -> Any | None:
        """Extract a single property value from the properties list."""
        for prop in properties:
            if "property" in prop and prop["property"]["name"] == property_name:
                return prop["property"]["value"]
        return None

    # ------------------------------------------------------------------
    # Device-control helpers: success returns True; failures always raise.
    # ------------------------------------------------------------------

    async def set_device_mode(self, dsn: str, mode: int) -> bool:
        return await self.set_device_property(dsn, "set_device_mode", mode)

    async def set_temperature_setpoint(self, dsn: str, temperature: float) -> bool:
        return await self.set_device_property(dsn, "set_temp_setpoint", temperature)

    async def set_status(self, dsn: str, status: int) -> bool:
        return await self.set_device_property(dsn, "set_status", status)

    async def set_silent_mode(self, dsn: str, status: int) -> bool:
        return await self.set_device_property(dsn, "set_silent_function", status)

    async def set_humidity_setpoint(self, dsn: str, humidity: float) -> bool:
        return await self.set_device_property(dsn, "humidity_setpoint", humidity)

    async def set_fan_speed(self, dsn: str, fan_speed: int) -> bool:
        return await self.set_device_property(dsn, "set_int_fan_speed", str(fan_speed))

    async def set_device_status(self, dsn: str, status: int) -> bool:
        return await self.set_device_property(dsn, "set_device_status", str(status))

    async def set_device_property(self, dsn: str, propName: str, value: Any) -> bool:
        """Submit a datapoint, preserving failures for the HA entity boundary."""
        result = await self._post_request(
            f"apiv1/dsns/{dsn}/properties/{propName}/datapoints.json",
            {"datapoint": {"value": value}},
        )
        if result is None:
            raise DeLonghiConnectionError("Empty device command response")
        return True

    async def _get_request(self, path: str) -> Any:
        """Read API data, retrying once after an expired access token."""
        return await self._request("GET", path)

    async def _post_request(self, path: str, data: dict[str, Any]) -> Any:
        """Write API data, retrying once after an expired access token."""
        return await self._request("POST", path, data)

    async def _request(
        self, method: str, path: str, data: dict[str, Any] | None = None
    ) -> Any:
        """Return decoded data or raise; a failed request is never empty data."""
        url = f"https://ads-eu.aylanetworks.com/{path}"
        for attempt in range(2):
            generation = self._token_generation
            request_token = self.access_token
            headers = {
                "User-Agent": API_USER_AGENT,
                "Authorization": f"auth_token {request_token}",
                "Accept": "application/json",
            }
            kwargs: dict[str, Any] = {"headers": headers}
            if method == "POST":
                kwargs["json"] = data

            try:
                async with self.session.request(method, url, timeout=REQUEST_TIMEOUT, **kwargs) as response:
                    response.raise_for_status()
                    return await response.json()
            except aiohttp.ContentTypeError as err:
                raise DeLonghiConnectionError(
                    f"{method} {path} returned an invalid JSON response"
                ) from err
            except aiohttp.ClientResponseError as err:
                if err.status != 401:
                    raise DeLonghiConnectionError(
                        f"{method} {path} returned HTTP {err.status}"
                    ) from err
                if attempt:
                    if generation == self._token_generation:
                        self.access_token = None
                        self.refresh_token = None
                    raise DeLonghiAuthError(
                        "API rejected the renewed access token"
                    ) from err
            except _CONN_ERRORS as err:
                raise DeLonghiConnectionError(
                    f"{method} {path} failed: {err}"
                ) from err
            except ValueError as err:
                raise DeLonghiConnectionError(
                    f"{method} {path} returned an invalid JSON response"
                ) from err

            # Leave the failed response context before refreshing the token.
            # Authentication errors must reach setup/the coordinator unchanged.
            await self._refresh_if_needed(generation)
            if not self.access_token:
                raise DeLonghiConnectionError("Token refresh returned no access token")
