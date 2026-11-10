"""Failure and recovery cases at the API boundary."""

from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest
from multidict import CIMultiDict, CIMultiDictProxy
from yarl import URL

from custom_components.delonghi_comfort.api import DeLonghiAPI
from custom_components.delonghi_comfort.exceptions import (
    DeLonghiAuthError,
    DeLonghiConnectionError,
)

pytestmark = pytest.mark.asyncio


def response(status=200, data=None, json_error=None):
    result = MagicMock()
    result.status = status
    result.__aenter__ = AsyncMock(return_value=result)
    result.__aexit__ = AsyncMock(return_value=False)
    if status >= 400:
        result.raise_for_status.side_effect = aiohttp.ClientResponseError(
            aiohttp.RequestInfo(
                URL("https://example.test"), "GET", CIMultiDictProxy(CIMultiDict()),
                URL("https://example.test"),
            ), (), status=status
        )
    result.json = AsyncMock(return_value=data, side_effect=json_error)
    return result


def api_with_responses(*responses) -> tuple[DeLonghiAPI, MagicMock]:
    session = MagicMock()
    session.request.side_effect = responses
    api = DeLonghiAPI("test@example.com", "test", session)
    api.access_token = "old-token"
    api.refresh_token = "refresh-token"
    return api, session


@pytest.mark.parametrize("status", [403, 404, 429, 500, 503])
async def test_http_failure_is_not_empty_properties(status):
    api, session = api_with_responses(response(status))
    with pytest.raises(DeLonghiConnectionError, match=f"HTTP {status}"):
        await api.get_device_properties("test")


@pytest.mark.parametrize("payload", [None, {}, {"error": "failed"}, [], [None], [{}],
    [{"property": {"name": "room_temp"}}], [{"property": {"name": None, "value": 1}}]])
async def test_missing_or_malformed_properties_fail(payload):
    api, session = api_with_responses(response(data=payload))
    with pytest.raises(DeLonghiConnectionError):
        await api.get_device_properties("test")


@pytest.mark.parametrize("payload", [None, {}, [None], [{"device": {}}]])
async def test_malformed_device_list_fails(payload):
    api, session = api_with_responses(response(data=payload))
    with pytest.raises(DeLonghiConnectionError):
        await api.get_devices()


async def test_empty_account_is_distinct_from_request_failure():
    api, session = api_with_responses(response(data=[]))
    assert await api.get_devices() == []


@pytest.mark.parametrize("method", ["GET", "POST"])
async def test_expired_token_refreshes_and_retries_once(method):
    payload = [{"property": {"name": "room_temp", "value": 22}}]
    api, session = api_with_responses(response(401), response(data=payload))
    api._refresh_access_token = AsyncMock(return_value="new-token")
    if method == "GET":
        assert await api.get_device_properties("test") == payload
    else:
        assert await api._post_request("test", {"datapoint": {"value": 1}}) == payload
        assert all(call.kwargs["json"] == {"datapoint": {"value": 1}}
                   for call in session.request.call_args_list)
    api._refresh_access_token.assert_awaited_once()
    assert session.request.call_count == 2
    assert session.request.call_args_list[0].kwargs["headers"]["Authorization"] == "auth_token old-token"
    assert session.request.call_args_list[1].kwargs["headers"]["Authorization"] == "auth_token new-token"


async def test_repeated_unauthorized_propagates_auth_failure():
    api, session = api_with_responses(response(401), response(401))
    api._refresh_access_token = AsyncMock(return_value="new-token")
    with pytest.raises(DeLonghiAuthError):
        await api.get_device_properties("test")
    assert api.access_token is None
    assert api.refresh_token is None
    assert session.request.call_count == 2


@pytest.mark.parametrize("failure", [DeLonghiAuthError("rejected"), DeLonghiConnectionError("offline")])
async def test_refresh_failure_propagates(failure):
    api, session = api_with_responses(response(401))
    api._refresh_access_token = AsyncMock(side_effect=failure)
    with pytest.raises(type(failure)):
        await api.get_device_properties("test")
    assert session.request.call_count == 1


@pytest.mark.parametrize("failure", [ValueError("bad JSON"), aiohttp.ClientPayloadError("incomplete body")])
async def test_response_decode_failure_is_not_empty_data(failure):
    api, session = api_with_responses(response(json_error=failure))
    with pytest.raises(DeLonghiConnectionError):
        await api.get_device_properties("test")


async def test_refresh_server_outage_does_not_trigger_full_login():
    api, session = api_with_responses()
    session.post.return_value = response(503)
    api._get_new_access_token = AsyncMock()
    with pytest.raises(DeLonghiConnectionError):
        await api.refresh_access_token()
    api._get_new_access_token.assert_not_awaited()


async def test_refresh_rejection_falls_back_to_login():
    api, session = api_with_responses()
    session.post.return_value = response(401)
    api._get_new_access_token = AsyncMock(return_value="new-token")
    assert await api.refresh_access_token() == "new-token"
    api._get_new_access_token.assert_awaited_once()


async def test_authentication_server_error_is_retryable():
    api, session = api_with_responses()
    session.get.return_value = response(503)
    with pytest.raises(DeLonghiConnectionError):
        await api.authenticate()


async def test_authentication_malformed_response_is_retryable():
    api, session = api_with_responses()
    initial = response()
    initial.headers = {}
    session.get.return_value = initial
    with pytest.raises(DeLonghiConnectionError):
        await api.authenticate()


async def test_missing_authorization_context_fails_before_login():
    api, session = api_with_responses()
    initial = response()
    initial.headers = {"Location": "https://example.test/?unrelated=value"}
    session.get.return_value = initial
    with pytest.raises(DeLonghiConnectionError, match="Missing context"):
        await api.authenticate()
    session.get.assert_called_once()
    session.post.assert_not_called()


@pytest.mark.parametrize("login_data, error", [
    ({"statusCode": 403, "errorDetails": "Invalid credentials"}, DeLonghiAuthError),
    ({"statusCode": 503}, DeLonghiConnectionError),
    ({}, DeLonghiConnectionError),
    ([], DeLonghiConnectionError),
])
async def test_login_failure_classification(login_data, error):
    import json

    api, session = api_with_responses()
    authorize = response()
    authorize.headers = {"Location": "https://example.test/?context=test"}
    identifiers = response()
    identifiers.text = AsyncMock(return_value=json.dumps({"ucid": "test", "gmid": "test", "gmidTicket": "test"}))
    login = response()
    login.text = AsyncMock(return_value=json.dumps(login_data))
    session.get.side_effect = [authorize, identifiers]
    session.post.return_value = login
    with pytest.raises(error):
        await api.authenticate()


def successful_login(session):
    """Synthetic responses for all eight auth stages; no real account data."""
    import json

    authorize = response()
    authorize.headers = {"Location": "https://example.test/?context=context"}
    identifiers = response()
    identifiers.text = AsyncMock(return_value=json.dumps({"ucid": "ucid", "gmid": "gmid", "gmidTicket": "ticket"}))
    login = response()
    login.text = AsyncMock(return_value=json.dumps({"statusCode": 200, "sessionInfo": {"login_token": "login-token"}}))
    user = response()
    user.text = AsyncMock(return_value=json.dumps({"UID": "uid", "UIDSignature": "uid-signature", "signatureTimestamp": "123"}))
    consent = response()
    consent.text = AsyncMock(return_value='const consentObj2Sig = "signature";')
    continuation = response()
    continuation.headers = {"Location": "https://example.test/?code=oidc-code"}
    token = response()
    token.text = AsyncMock(return_value=json.dumps({"access_token": "idp-token"}))
    ayla = response()
    ayla.text = AsyncMock(return_value=json.dumps({"access_token": "ayla-token", "refresh_token": "ayla-refresh"}))
    session.get.side_effect = [authorize, identifiers, consent, continuation]
    session.post.side_effect = [login, user, token, ayla]


async def test_complete_login_flow():
    from custom_components.delonghi_comfort.api import REQUEST_TIMEOUT

    api, session = api_with_responses()
    successful_login(session)
    assert await api.authenticate()
    assert api.access_token == "ayla-token"
    assert api.refresh_token == "ayla-refresh"
    assert [call[0] for call in session.method_calls] == ["get", "get", "post", "post", "get", "get", "post", "post"]
    for call in session.method_calls:
        assert call.kwargs["timeout"] == REQUEST_TIMEOUT
    assert session.get.call_args_list[2].kwargs["params"]["UIDSignature"] == "uid-signature"
    assert session.get.call_args_list[3].kwargs["params"]["login_token"] == "login-token"
    assert session.post.call_args_list[2].kwargs["data"]["code"] == "oidc-code"
    assert session.post.call_args_list[3].kwargs["data"]["token"] == "idp-token"


async def test_concurrent_login_is_shared():
    import asyncio

    api, session = api_with_responses()
    successful_login(session)
    # Force overlap while the first request is waiting for the network.
    authorize = session.get.side_effect
    # Keep the real eight-stage implementation and delay its first response.
    first = next(authorize)
    entered = asyncio.Event()
    release = asyncio.Event()
    async def enter():
        entered.set()
        await release.wait()
        return first
    first.__aenter__ = AsyncMock(side_effect=enter)
    session.get.side_effect = [first, *authorize]
    task = asyncio.create_task(api.authenticate())
    await entered.wait()
    other = asyncio.create_task(api.authenticate())
    await asyncio.sleep(0)
    release.set()
    assert await asyncio.gather(task, other) == [True, True]
    assert session.get.call_count == 4
    assert session.post.call_count == 4


async def test_concurrent_401s_share_one_refresh():
    import asyncio

    api, session = api_with_responses()
    initial_requests = 0
    both_started = asyncio.Event()
    def request(*args, **kwargs):
        nonlocal initial_requests
        if kwargs["headers"]["Authorization"] == "auth_token old-token":
            initial_requests += 1
            if initial_requests == 2:
                both_started.set()
            result = response(401)
            async def enter():
                await both_started.wait()
                return result
            result.__aenter__ = AsyncMock(side_effect=enter)
            return result
        return response(data=[])
    session.request.side_effect = request
    async def refresh():
        await asyncio.sleep(0)
        return "new-token"
    api._refresh_access_token = AsyncMock(side_effect=refresh)
    assert await asyncio.gather(api.get_devices(), api.get_devices()) == [[], []]
    api._refresh_access_token.assert_awaited_once()
    assert session.request.call_count == 4


async def test_auth_deadline_cancels_stalled_login(monkeypatch):
    import asyncio
    import custom_components.delonghi_comfort.api as module

    api, session = api_with_responses()
    stalled = response()
    async def enter():
        await asyncio.Event().wait()
    stalled.__aenter__ = AsyncMock(side_effect=enter)
    session.get.return_value = stalled
    monkeypatch.setattr(module, "AUTH_TIMEOUT", 0.01)
    with pytest.raises(DeLonghiConnectionError, match="OIDC authorization: TimeoutError"):
        await api.authenticate()
    assert not api._auth_lock.locked()


async def test_auth_transport_error_does_not_disclose_secrets():
    api, session = api_with_responses()
    session.get.side_effect = aiohttp.ClientConnectionError("password=private&token=secret")
    with pytest.raises(DeLonghiConnectionError) as error:
        await api.authenticate()
    assert str(error.value) == "Authentication failed during OIDC authorization: ClientConnectionError"


@pytest.mark.parametrize("error", [DeLonghiAuthError("rejected"), DeLonghiConnectionError("offline")])
async def test_command_preserves_api_errors(error):
    api, session = api_with_responses()
    api._post_request = AsyncMock(side_effect=error)
    with pytest.raises(type(error)):
        await api.set_device_status("test", 1)
