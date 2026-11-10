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
        self.access_token = await self._get_new_access_token()
        return self.access_token is not None

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
        try:
            # ----------------------------------------------------------
            # Step 1: Start OIDC authorisation – obtain `context`
            # ----------------------------------------------------------
            async with self.session.get(
                f"https://fidm.eu1.gigya.com/oidc/op/v1.0/{API_KEY}/authorize",
                headers={"User-Agent": BROWSER_USER_AGENT},
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

            # ----------------------------------------------------------
            # Step 2: Fetch Gigya session identifiers (ucid / gmid)
            # ----------------------------------------------------------
            async with self.session.get(
                "https://socialize.eu1.gigya.com/socialize.getIDs",
                headers={"User-Agent": BROWSER_USER_AGENT},
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
                error_detail = login_data.get("errorDetails", "Unknown error")
                _LOGGER.error("Login rejected by Gigya: %s", error_detail)
                raise DeLonghiAuthError(
                    f"Gigya login failed (statusCode "
                    f"{login_data.get('statusCode')}): {error_detail}"
                )

            login_token = login_data["sessionInfo"]["login_token"]

            # ----------------------------------------------------------
            # Step 4: Get user info (UID + signature)
            # ----------------------------------------------------------
            async with self.session.post(
                "https://socialize.eu1.gigya.com/socialize.getUserInfo",
                headers={"User-Agent": BROWSER_USER_AGENT},
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
            async with self.session.get(
                "https://aylaopenid.delonghigroup.com/OIDCConsentPage.php",
                headers={"User-Agent": BROWSER_USER_AGENT},
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
            async with self.session.get(
                f"https://fidm.eu1.gigya.com/oidc/op/v1.0/{API_KEY}/authorize/continue",
                headers={"User-Agent": BROWSER_USER_AGENT},
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
            async with self.session.post(
                f"https://fidm.eu1.gigya.com/oidc/op/v1.0/{API_KEY}/token",
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
            async with self.session.post(
                "https://user-field-eu.aylanetworks.com/api/v1/token_sign_in",
                headers={"User-Agent": TOKEN_USER_AGENT},
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
        except DeLonghiAuthError:
            raise

        # ── Transient transport/network errors → DeLonghiConnectionError ─────
        except aiohttp.ClientResponseError as err:
            if err.status in (401, 403):
                raise DeLonghiAuthError("Authentication was rejected") from err
            raise DeLonghiConnectionError(
                f"Authentication service returned HTTP {err.status}"
            ) from err
        except _CONN_ERRORS as err:
            raise DeLonghiConnectionError(
                f"Network error during authentication: {err}"
            ) from err

        # A malformed response is not evidence of invalid credentials.
        except (KeyError, IndexError, TypeError, ValueError) as err:
            raise DeLonghiConnectionError(
                "Unexpected authentication response structure"
            ) from err

    async def refresh_access_token(self) -> str | None:
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
                f"Network error while refreshing access token: {err}"
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
                network errors so the caller's retry loop can handle it.
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
    # Device-control helpers (fire-and-forget style – return bool)
    # ------------------------------------------------------------------

    async def set_device_mode(self, dsn: str, mode: int) -> bool:
        """Set device mode (1=Cooling, 2=Dehumidification, 3=Fan)."""
        try:
            response = await self._post_request(
                f"apiv1/dsns/{dsn}/properties/set_device_mode/datapoints.json",
                {"datapoint": {"value": mode}},
            )
            return response is not None
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("Failed to set device mode for %s: %s", dsn, err)
            return False

    async def set_temperature_setpoint(self, dsn: str, temperature: float) -> bool:
        """Set temperature setpoint (16–32 °C)."""
        try:
            response = await self._post_request(
                f"apiv1/dsns/{dsn}/properties/set_temp_setpoint/datapoints.json",
                {"datapoint": {"value": temperature}},
            )
            return response is not None
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("Failed to set temperature setpoint for %s: %s", dsn, err)
            return False

    async def set_status(self, dsn: str, status: int) -> bool:
        """Set device status (1=ON, 2=OFF)."""
        try:
            response = await self._post_request(
                f"apiv1/dsns/{dsn}/properties/set_status/datapoints.json",
                {"datapoint": {"value": status}},
            )
            return response is not None
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("Failed to set status for %s: %s", dsn, err)
            return False

    async def set_silent_mode(self, dsn: str, status: int) -> bool:
        """Set silent mode (1=ON, 2=OFF)."""
        try:
            response = await self._post_request(
                f"apiv1/dsns/{dsn}/properties/set_silent_function/datapoints.json",
                {"datapoint": {"value": status}},
            )
            return response is not None
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("Failed to set silent mode for %s: %s", dsn, err)
            return False

    async def set_humidity_setpoint(self, dsn: str, humidity: int) -> bool:
        """Set humidity setpoint (0–100 %)."""
        try:
            response = await self._post_request(
                f"apiv1/dsns/{dsn}/properties/humidity_setpoint/datapoints.json",
                {"datapoint": {"value": humidity}},
            )
            return response is not None
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("Failed to set humidity setpoint for %s: %s", dsn, err)
            return False

    async def set_fan_speed(self, dsn: str, fan_speed: int) -> bool:
        """Set fan speed (1=Low, 2=Mid, 3=High, 4=Auto)."""
        try:
            response = await self._post_request(
                f"apiv1/dsns/{dsn}/properties/set_int_fan_speed/datapoints.json",
                {"datapoint": {"value": str(fan_speed)}},
            )
            return response is not None
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("Failed to set fan speed for %s: %s", dsn, err)
            return False

    async def set_device_status(self, dsn: str, status: int) -> bool:
        """Set device status via the set_device_status property."""
        try:
            response = await self._post_request(
                f"apiv1/dsns/{dsn}/properties/set_device_status/datapoints.json",
                {"datapoint": {"value": str(status)}},
            )
            return response is not None
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("Failed to set device status for %s: %s", dsn, err)
            return False

    async def set_device_property(self, dsn: str, propName: str, value: Any) -> bool:
        """Set an arbitrary device property by name."""
        try:
            response = await self._post_request(
                f"apiv1/dsns/{dsn}/properties/{propName}/datapoints.json",
                {"datapoint": {"value": value}},
            )
            return response is not None
        except Exception as err:  # noqa: BLE001
            _LOGGER.error(
                "Failed to set device property %s/%s=%s: %s", dsn, propName, value, err
            )
            return False

    # ------------------------------------------------------------------
    # Low-level HTTP helpers
    # ------------------------------------------------------------------

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
            headers = {
                "User-Agent": API_USER_AGENT,
                "Authorization": f"auth_token {self.access_token}",
                "Accept": "application/json",
            }
            kwargs: dict[str, Any] = {"headers": headers}
            if method == "POST":
                kwargs["json"] = data

            try:
                async with self.session.request(method, url, **kwargs) as response:
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
            self.access_token = await self.refresh_access_token()
            if not self.access_token:
                raise DeLonghiConnectionError("Token refresh returned no access token")
