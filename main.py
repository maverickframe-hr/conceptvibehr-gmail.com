import os
import json
import logging
from pathlib import Path
from typing import Optional, Any, Dict
from urllib.parse import urlencode, urlparse

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

APP_NAME = "Maverickframe HH + Rabota.by MVP Bridge"
TOKEN_DIR = Path("/tmp")

LOG_LEVEL = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("maverickframe_hh_bridge")
logger.setLevel(LOG_LEVEL)


def token_store_url() -> Optional[str]:
    return os.getenv("TOKEN_STORE_URL") or os.getenv("GOOGLE_APPS_SCRIPT_URL")


PROVIDERS = {
    "hh": {
        "api": os.getenv("HH_API_URL", "https://api.hh.ru"),
        "auth": os.getenv("HH_AUTH_URL", "https://hh.ru/oauth/authorize"),
        "token": os.getenv("HH_TOKEN_URL", "https://api.hh.ru/token"),
        "client_id": "HH_CLIENT_ID",
        "client_secret": "HH_CLIENT_SECRET",
        "redirect_uri": "HH_REDIRECT_URI",
        "user_agent": "HH_USER_AGENT",
        "default_ua": "Maverickframe HR Assistant (conceptvibehr@gmail.com)",
        "token_file": TOKEN_DIR / "hh_tokens.json",
        "source": "HH",
    },
    "rabota": {
        "api": os.getenv("RABOTA_API_URL", "https://api.hh.ru"),
        "auth": os.getenv("RABOTA_AUTH_URL", "https://rabota.by/oauth/authorize"),
        "token": os.getenv("RABOTA_TOKEN_URL", "https://api.hh.ru/token"),
        "client_id": "RABOTA_CLIENT_ID",
        "client_secret": "RABOTA_CLIENT_SECRET",
        "redirect_uri": "RABOTA_REDIRECT_URI",
        "user_agent": "RABOTA_USER_AGENT",
        "default_ua": "Maverickframe HR Assistant (conceptvibehr@gmail.com)",
        "token_file": TOKEN_DIR / "rabota_tokens.json",
        "source": "Rabota.by",
    },
}

app = FastAPI(title=APP_NAME, version="0.5.0")


def env(name: str, required: bool = True) -> Optional[str]:
    value = os.getenv(name)
    if required and not value:
        raise HTTPException(status_code=500, detail=f"Missing environment variable: {name}")
    return value


def provider(name: str) -> Dict[str, Any]:
    if name not in PROVIDERS:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {name}")
    return PROVIDERS[name]


def _safe_json(response: httpx.Response) -> Dict[str, Any]:
    try:
        data = response.json()
        if isinstance(data, dict):
            return data
        return {"ok": False, "raw": data}
    except Exception:
        return {"ok": False, "text": response.text[:2000]}


def _token_summary(tokens: Any) -> Dict[str, Any]:
    if not isinstance(tokens, dict):
        return {"has_tokens": False}
    return {
        "has_tokens": True,
        "has_access_token": bool(tokens.get("access_token")),
        "has_refresh_token": bool(tokens.get("refresh_token")),
        "token_type": tokens.get("token_type"),
        "expires_in": tokens.get("expires_in"),
        "keys": sorted(tokens.keys()),
    }


def _response_summary(data: Any) -> Any:
    if not isinstance(data, dict):
        return data

    summary: Dict[str, Any] = {}
    for key, value in data.items():
        if key == "tokens":
            summary[key] = _token_summary(value)
        elif key in {"access_token", "refresh_token", "id_token"}:
            summary[key] = "<redacted>"
        elif isinstance(value, str) and len(value) > 500:
            summary[key] = value[:500] + "...<truncated>"
        else:
            summary[key] = value
    return summary


def _apps_script_host(url: str) -> str:
    parsed = urlparse(url)
    return parsed.netloc or "unknown-host"


def _cache_tokens_local(provider_name: str, tokens: Dict[str, Any], source: str) -> bool:
    token_file = PROVIDERS.get(provider_name, {}).get("token_file")
    if not token_file:
        logger.info("Skipping local token cache for %s from %s: no local token file configured", provider_name, source)
        return False

    try:
        token_file.write_text(json.dumps(tokens, ensure_ascii=False), encoding="utf-8")
        logger.info("Cached %s tokens locally from %s: %s", provider_name, source, _token_summary(tokens))
        return True
    except Exception as exc:
        logger.warning("Could not cache %s tokens locally from %s: %s", provider_name, source, exc)
        return False


def _bounded_int(value: int, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, number))


def _compact_user(me_data: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": me_data.get("id"),
        "email": me_data.get("email"),
        "first_name": me_data.get("first_name"),
        "last_name": me_data.get("last_name"),
        "is_employer": me_data.get("is_employer"),
        "is_hiring_manager": me_data.get("is_hiring_manager"),
    }


def _compact_employer(employer: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": str(employer.get("id")) if employer.get("id") is not None else None,
        "name": employer.get("name"),
        "alternate_url": employer.get("alternate_url"),
    }


def extract_employer_info(me_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    employer = me_data.get("employer")
    if isinstance(employer, dict) and employer.get("id"):
        return _compact_employer(employer)

    employers = me_data.get("employers")
    if isinstance(employers, list):
        for item in employers:
            if isinstance(item, dict) and item.get("id"):
                return _compact_employer(item)

    manager = me_data.get("manager")
    if isinstance(manager, dict):
        manager_employer = manager.get("employer")
        if isinstance(manager_employer, dict) and manager_employer.get("id"):
            return _compact_employer(manager_employer)

    return None


def require_employer_info(provider_name: str, me_data: Dict[str, Any]) -> Dict[str, Any]:
    employer_info = extract_employer_info(me_data)
    if employer_info and employer_info.get("id"):
        return employer_info
    raise HTTPException(
        status_code=400,
        detail={
            "error": f"No employer account found for this {provider_name} user.",
            "provider": provider_name,
            "me_keys": sorted(me_data.keys()),
        },
    )


async def apps_script_post_json(url: str, payload: Dict[str, Any]) -> tuple[int, Dict[str, Any], str]:
    """Post JSON to Google Apps Script and read the redirected ContentService body.

    Google Web Apps often respond to /exec POST with 302 to script.googleusercontent.com.
    The original POST has already executed doPost; the redirect URL should be fetched with
    GET for 301/302/303 responses so the JSON body generated by ContentService is returned.
    """
    current_url = url
    last_text = ""
    method = "POST"
    action = payload.get("action", "save_candidate")
    provider_name = payload.get("provider")
    async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
        for attempt in range(1, 6):
            if method == "POST":
                response = await client.post(current_url, json=payload)
            else:
                response = await client.get(current_url)
            last_text = response.text
            logger.info(
                "Apps Script %s action=%s provider=%s attempt=%s host=%s status=%s",
                method,
                action,
                provider_name,
                attempt,
                _apps_script_host(str(response.url)),
                response.status_code,
            )
            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("location")
                if not location:
                    logger.warning("Apps Script redirect without Location for action=%s provider=%s", action, provider_name)
                    return response.status_code, {"ok": False, "error": "redirect without location", "text": last_text[:1000]}, last_text
                current_url = str(response.url.join(location))
                if response.status_code in (301, 302, 303):
                    method = "GET"
                logger.info(
                    "Apps Script redirect action=%s provider=%s status=%s next_method=%s next_host=%s",
                    action,
                    provider_name,
                    response.status_code,
                    method,
                    _apps_script_host(current_url),
                )
                continue
            data = _safe_json(response)
            logger.info(
                "Apps Script response action=%s provider=%s status=%s ok=%s keys=%s",
                action,
                provider_name,
                response.status_code,
                data.get("ok") if isinstance(data, dict) else None,
                sorted(data.keys()) if isinstance(data, dict) else [],
            )
            return response.status_code, data, last_text
    logger.warning("Apps Script too many redirects for action=%s provider=%s", action, provider_name)
    return 599, {"ok": False, "error": "too many redirects", "text": last_text[:1000]}, last_text


async def apps_script_action(action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    url = env("GOOGLE_APPS_SCRIPT_URL")
    status_code, data, text = await apps_script_post_json(url, {**payload, "action": action})

    if status_code >= 400:
        raise HTTPException(status_code=status_code, detail=text)

    if isinstance(data, dict) and data.get("ok") is False:
        raise HTTPException(status_code=502, detail=data)

    return data


async def save_tokens_remote(provider_name: str, tokens: Dict[str, Any]) -> bool:
    url = token_store_url()
    if not url:
        logger.warning("No TOKEN_STORE_URL / GOOGLE_APPS_SCRIPT_URL configured")
        return False
    payload = {"action": "save_token", "provider": provider_name, "tokens": tokens}
    try:
        logger.info("Saving %s tokens remotely via %s: %s", provider_name, _apps_script_host(url), _token_summary(tokens))
        status_code, data, _text = await apps_script_post_json(url, payload)
        if status_code >= 400 or data.get("ok") is False or data.get("saved") is not True:
            logger.warning("Token remote save failed for %s: status=%s response=%s", provider_name, status_code, _response_summary(data))
            return False
        logger.info("Token remote save succeeded for %s", provider_name)
        return True
    except Exception as exc:
        logger.exception("Token remote save error for %s: %s", provider_name, exc)
        return False


async def load_tokens_remote(provider_name: str) -> Optional[Dict[str, Any]]:
    url = token_store_url()
    if not url:
        logger.info("No remote token store configured while loading %s tokens", provider_name)
        return None

    # Primary method: POST JSON to Apps Script doPost and fetch the redirected ContentService response.
    payload = {"action": "load_token", "provider": provider_name}
    try:
        logger.info("Loading %s tokens remotely via POST from %s", provider_name, _apps_script_host(url))
        status_code, data, _text = await apps_script_post_json(url, payload)
        tokens = data.get("tokens") if isinstance(data, dict) else None
        if isinstance(tokens, dict) and tokens.get("access_token"):
            _cache_tokens_local(provider_name, tokens, "remote POST load")
            logger.info("Token remote POST load succeeded for %s: %s", provider_name, _token_summary(tokens))
            return tokens
        logger.warning("Token remote POST load did not return token for %s: status=%s response=%s", provider_name, status_code, _response_summary(data))
    except Exception as exc:
        logger.exception("Token remote POST load error for %s: %s", provider_name, exc)

    # Fallback method: GET query to Apps Script doGet. This is useful for debugging and avoids POST redirect issues.
    try:
        logger.info("Loading %s tokens remotely via GET fallback from %s", provider_name, _apps_script_host(url))
        params = {"action": "load_token", "provider": provider_name}
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            response = await client.get(url, params=params)
        data = _safe_json(response)
        logger.info(
            "Token remote GET fallback response for %s: status=%s redirects=%s ok=%s keys=%s",
            provider_name,
            response.status_code,
            len(response.history),
            data.get("ok") if isinstance(data, dict) else None,
            sorted(data.keys()) if isinstance(data, dict) else [],
        )
        tokens = data.get("tokens") if isinstance(data, dict) else None
        if isinstance(tokens, dict) and tokens.get("access_token"):
            _cache_tokens_local(provider_name, tokens, "remote GET load")
            logger.info("Token remote GET load succeeded for %s: %s", provider_name, _token_summary(tokens))
            return tokens
        logger.warning("Token remote GET load did not return token for %s: status=%s response=%s", provider_name, response.status_code, _response_summary(data))
    except Exception as exc:
        logger.exception("Token remote GET load error for %s: %s", provider_name, exc)

    return None


async def save_tokens(provider_name: str, tokens: Dict[str, Any]) -> bool:
    provider(provider_name)
    _cache_tokens_local(provider_name, tokens, "provider save")
    return await save_tokens_remote(provider_name, tokens)


async def load_tokens(provider_name: str) -> Dict[str, Any]:
    token_file = provider(provider_name)["token_file"]
    if token_file.exists():
        try:
            tokens = json.loads(token_file.read_text(encoding="utf-8"))
            if tokens.get("access_token"):
                logger.info("Loaded %s tokens from local cache: %s", provider_name, _token_summary(tokens))
                return tokens
            logger.warning("Local token cache for %s did not contain an access token: %s", provider_name, _token_summary(tokens))
        except Exception as exc:
            logger.warning("Could not read local token cache for %s: %s", provider_name, exc)
    else:
        logger.info("No local token cache exists for %s; trying remote store", provider_name)
    remote_tokens = await load_tokens_remote(provider_name)
    if remote_tokens:
        return remote_tokens
    logger.warning("No usable tokens found for %s in local cache or remote store", provider_name)
    raise HTTPException(status_code=401, detail=f"{provider_name} is not authorized yet. Open /auth/{provider_name}/start first.")


async def refresh_tokens(provider_name: str, tokens: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        return None
    p = provider(provider_name)
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": env(p["client_id"]),
        "client_secret": env(p["client_secret"]),
    }
    headers = {"HH-User-Agent": env(p["user_agent"], required=False) or p["default_ua"]}
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            response = await client.post(p["token"], data=data, headers=headers)
        if response.status_code >= 400:
            logger.warning("Token refresh failed for %s: status=%s text=%s", provider_name, response.status_code, response.text[:1000])
            return None
        new_tokens = response.json()
        if "refresh_token" not in new_tokens and refresh_token:
            new_tokens["refresh_token"] = refresh_token
        await save_tokens(provider_name, new_tokens)
        logger.info("Token refresh succeeded for %s: %s", provider_name, _token_summary(new_tokens))
        return new_tokens
    except Exception as exc:
        logger.exception("Token refresh error for %s: %s", provider_name, exc)
        return None


async def api_request_with_tokens(provider_name: str, tokens: Dict[str, Any], method: str, path: str, **kwargs):
    p = provider(provider_name)
    headers = kwargs.pop("headers", {})
    headers.update({
        "Authorization": f"Bearer {tokens['access_token']}",
        "HH-User-Agent": env(p["user_agent"], required=False) or p["default_ua"],
    })
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        response = await client.request(method, f"{p['api']}{path}", headers=headers, **kwargs)

    # If access token expired, refresh once and retry.
    if response.status_code == 401:
        new_tokens = await refresh_tokens(provider_name, tokens)
        if new_tokens and new_tokens.get("access_token"):
            headers["Authorization"] = f"Bearer {new_tokens['access_token']}"
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                response = await client.request(method, f"{p['api']}{path}", headers=headers, **kwargs)

    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    return response.json()


async def api_request(provider_name: str, method: str, path: str, **kwargs):
    tokens = await load_tokens(provider_name)
    return await api_request_with_tokens(provider_name, tokens, method, path, **kwargs)


@app.get("/")
def root():
    return {
        "ok": True,
        "service": APP_NAME,
        "hh_start": "/auth/hh/start",
        "hh_employer_start": "/auth/hh/employer/start",
        "hh_employer": "/hh/employer",
        "hh_emails": "/gmail/hh/emails",
        "rabota_start": "/auth/rabota/start",
        "hh_me": "/hh/me",
        "rabota_me": "/rabota/me",
        "token_status": "/debug/rabota/token_status",
    }


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/auth/{provider_name}/start")
def auth_start(provider_name: str, state: Optional[str] = None):
    p = provider(provider_name)
    auth_params = {
        "response_type": "code",
        "client_id": env(p["client_id"]),
        "redirect_uri": env(p["redirect_uri"]),
    }
    if state:
        auth_params["state"] = state
    params = urlencode(auth_params)
    return RedirectResponse(f"{p['auth']}?{params}")


@app.get("/auth/hh/employer/start")
def hh_employer_auth_start():
    return auth_start("hh", state="hh_employer")


@app.get("/auth/{provider_name}/callback")
async def auth_callback(provider_name: str, code: str, state: Optional[str] = None):
    p = provider(provider_name)
    data = {
        "grant_type": "authorization_code",
        "client_id": env(p["client_id"]),
        "client_secret": env(p["client_secret"]),
        "redirect_uri": env(p["redirect_uri"]),
        "code": code,
    }
    headers = {"HH-User-Agent": env(p["user_agent"], required=False) or p["default_ua"]}
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        response = await client.post(p["token"], data=data, headers=headers)
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    tokens = response.json()
    logger.info("OAuth callback received %s tokens: %s", provider_name, _token_summary(tokens))

    employer_info = None
    if provider_name == "hh" and state == "hh_employer":
        me_data = await api_request_with_tokens("hh", tokens, "GET", "/me")
        employer_info = require_employer_info("hh", me_data)

    remote_saved = await save_tokens(provider_name, tokens)
    result = {
        "ok": True,
        "remote_saved": remote_saved,
        "state": state,
        "message": f"{provider_name} authorized successfully. You can now use /{provider_name}/me and /{provider_name}/vacancies."
    }
    if employer_info:
        result["employer"] = employer_info
    return result


@app.get("/{provider_name}/me")
async def me(provider_name: str):
    provider(provider_name)
    return await api_request(provider_name, "GET", "/me")


@app.get("/hh/employer")
async def hh_employer():
    me_data = await api_request("hh", "GET", "/me")
    employer_info = require_employer_info("hh", me_data)
    return {
        "ok": True,
        "provider": "hh",
        "user": _compact_user(me_data),
        "employer": employer_info,
    }


@app.get("/{provider_name}/vacancies")
async def vacancies(provider_name: str, employer_id: Optional[str] = None, page: int = 0, per_page: int = 20):
    provider(provider_name)
    employer_info = None
    if not employer_id:
        me_data = await api_request(provider_name, "GET", "/me")
        employer_info = require_employer_info(provider_name, me_data)
        employer_id = employer_info["id"]

    if provider_name == "rabota":
        params = {"employer_id": employer_id, "page": page, "per_page": per_page}
        return await api_request(provider_name, "GET", "/vacancies", params=params)

    params = {"page": page, "per_page": per_page}
    data = await api_request(provider_name, "GET", f"/employers/{employer_id}/vacancies", params=params)
    if isinstance(data, dict) and employer_info:
        data.setdefault("employer", employer_info)
    return data


@app.get("/hh/employer/vacancies")
async def hh_employer_vacancies(employer_id: Optional[str] = None, page: int = 0, per_page: int = 20):
    return await vacancies("hh", employer_id=employer_id, page=page, per_page=per_page)


@app.get("/{provider_name}/negotiations")
async def negotiations(provider_name: str, vacancy_id: str, page: int = 0, per_page: int = 20):
    provider(provider_name)
    params = {"vacancy_id": vacancy_id, "page": page, "per_page": per_page}
    return await api_request(provider_name, "GET", "/negotiations", params=params)


@app.get("/hh/employer/negotiations")
async def hh_employer_negotiations(vacancy_id: str, page: int = 0, per_page: int = 20):
    return await negotiations("hh", vacancy_id=vacancy_id, page=page, per_page=per_page)


@app.get("/{provider_name}/responses")
async def responses(provider_name: str, vacancy_id: str, page: int = 0, per_page: int = 20):
    provider(provider_name)
    params = {"vacancy_id": vacancy_id, "page": page, "per_page": per_page}
    return await api_request(provider_name, "GET", "/negotiations/response", params=params)


@app.get("/hh/employer/responses")
async def hh_employer_responses(vacancy_id: str, page: int = 0, per_page: int = 20):
    return await responses("hh", vacancy_id=vacancy_id, page=page, per_page=per_page)


@app.get("/{provider_name}/responses_short")
async def responses_short(provider_name: str, vacancy_id: str, page: int = 0, per_page: int = 20):
    provider(provider_name)
    data = await responses(provider_name, vacancy_id, page, per_page)
    short_items = []
    for item in data.get("items", []):
        resume = item.get("resume") or {}
        short_items.append({
            "id": item.get("id"),
            "state": (item.get("state") or {}).get("name") if isinstance(item.get("state"), dict) else item.get("state"),
            "created_at": item.get("created_at"),
            "updated_at": item.get("updated_at"),
            "resume_id": resume.get("id"),
            "first_name": resume.get("first_name"),
            "last_name": resume.get("last_name"),
            "middle_name": resume.get("middle_name"),
            "title": resume.get("title"),
            "age": resume.get("age"),
            "area": (resume.get("area") or {}).get("name") if isinstance(resume.get("area"), dict) else resume.get("area"),
            "url": resume.get("alternate_url") or resume.get("url"),
        })
    return {"found": data.get("found"), "page": data.get("page"), "pages": data.get("pages"), "per_page": data.get("per_page"), "items": short_items}


@app.get("/hh/employer/responses_short")
async def hh_employer_responses_short(vacancy_id: str, page: int = 0, per_page: int = 20):
    return await responses_short("hh", vacancy_id=vacancy_id, page=page, per_page=per_page)


@app.get("/{provider_name}/resume/{resume_id}")
async def resume(provider_name: str, resume_id: str):
    provider(provider_name)
    return await api_request(provider_name, "GET", f"/resumes/{resume_id}")


@app.get("/gmail/hh/emails")
async def gmail_hh_emails(
    query: Optional[str] = None,
    max_results: int = 10,
    newer_than_days: int = 30,
    unread_only: bool = False,
    include_body: bool = False,
):
    payload = {
        "query": query,
        "max_results": _bounded_int(max_results, 10, 1, 50),
        "newer_than_days": _bounded_int(newer_than_days, 30, 1, 365),
        "unread_only": unread_only,
        "include_body": include_body,
    }
    logger.info(
        "Reading HH emails via Apps Script: max_results=%s newer_than_days=%s unread_only=%s include_body=%s custom_query=%s",
        payload["max_results"],
        payload["newer_than_days"],
        unread_only,
        include_body,
        bool(query),
    )
    return await apps_script_action("read_hh_emails", payload)


@app.get("/debug/{provider_name}/token_status")
async def token_status(provider_name: str):
    provider(provider_name)
    local_exists = provider(provider_name)["token_file"].exists()
    remote_tokens = await load_tokens_remote(provider_name)
    return {
        "ok": True,
        "provider": provider_name,
        "token_store_url_configured": bool(token_store_url()),
        "local_token_exists": local_exists,
        "remote_token_exists": bool(remote_tokens and remote_tokens.get("access_token")),
    }


@app.get("/debug/{provider_name}/remote_token")
async def remote_token(provider_name: str):
    provider(provider_name)
    tokens = await load_tokens_remote(provider_name)
    if not tokens:
        return {"ok": False, "provider": provider_name, "message": "No remote token found"}
    return {"ok": True, "provider": provider_name, "has_access_token": bool(tokens.get("access_token")), "has_refresh_token": bool(tokens.get("refresh_token"))}


@app.get("/debug/{provider_name}/oauth_config")
def oauth_config(provider_name: str):
    p = provider(provider_name)
    return {
        "ok": True,
        "provider": provider_name,
        "auth_url": p["auth"],
        "token_url": p["token"],
        "api_url": p["api"],
        "client_id_configured": bool(os.getenv(p["client_id"])),
        "client_secret_configured": bool(os.getenv(p["client_secret"])),
        "redirect_uri_configured": bool(os.getenv(p["redirect_uri"])),
        "redirect_uri": os.getenv(p["redirect_uri"]),
        "user_agent_configured": bool(os.getenv(p["user_agent"])),
    }


@app.get("/debug/{provider_name}/token_store_roundtrip")
@app.post("/debug/{provider_name}/token_store_roundtrip")
async def token_store_roundtrip(provider_name: str):
    provider(provider_name)
    test_provider = provider_name + "_test"
    test_tokens = {"access_token": "test-access-token", "refresh_token": "test-refresh-token"}
    saved = await save_tokens_remote(test_provider, test_tokens)
    loaded = await load_tokens_remote(test_provider)
    return {
        "ok": bool(saved and loaded and loaded.get("access_token") == "test-access-token"),
        "provider": provider_name,
        "saved": saved,
        "loaded_has_access_token": bool(loaded and loaded.get("access_token")),
    }


class CandidateRow(BaseModel):
    date_added: Optional[str] = None
    source: str = "HH"
    vacancy: Optional[str] = None
    candidate_name: Optional[str] = None
    location: Optional[str] = None
    experience: Optional[str] = None
    skills: Optional[str] = None
    gpt_score: Optional[int] = None
    status: Optional[str] = None
    recruiter_comment: Optional[str] = None
    resume_link: Optional[str] = None
    suggested_reply: Optional[str] = None
    gpt_summary: Optional[str] = None


@app.post("/sheets/save_candidate")
async def save_candidate(row: CandidateRow):
    data = await apps_script_action("save_candidate", row.model_dump())

    return {
        "ok": True,
        "saved": bool(isinstance(data, dict) and data.get("saved") is True),
        "apps_script_response": data,
    }
