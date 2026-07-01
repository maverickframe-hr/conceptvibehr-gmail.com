# /// script
# requires-python = ">=3.10"
# dependencies = ["mcp[cli]", "httpx"]
# ///
"""HR Bridge MCP Server — resumes, chat, Telegram via maverickframe-hh-bridge.onrender.com"""

import httpx
from mcp.server.fastmcp import FastMCP

BRIDGE = "https://maverickframe-hh-bridge.onrender.com"
mcp = FastMCP("hr-bridge")

# Допустимые статусы отклика (см. правило работы с рабочими сайтами)
VALID_ACTIONS = {
    "discard_by_employer",      # Отказ
    "consider",                 # Рассмотреть / в работу
    "phone_interview",
    "interview",
    "assessment",
    "offer",
    "hired",
    "discard_no_interaction",
    "discard_vacancy_closed",
}


@mcp.tool()
def list_responses(vacancy_id: str = "134229811", page: int = 0, per_page: int = 20, provider: str = "rabota") -> dict:
    """List candidate responses. Returns id (use as nid for send_message), resume_id, name."""
    r = httpx.get(f"{BRIDGE}/{provider}/responses_short",
                  params={"vacancy_id": vacancy_id, "page": page, "per_page": per_page}, timeout=30)
    return r.json()

@mcp.tool()
def get_resume(resume_id: str, provider: str = "rabota") -> dict:
    """Get FULL resume: experience, education, skills, salary, contacts (phone, email, telegram).
    resume_id comes from list_responses. provider: 'hh' or 'rabota'."""
    r = httpx.get(f"{BRIDGE}/{provider}/resume/{resume_id}", timeout=30)
    return r.json()

@mcp.tool()
def read_messages(nid: str, provider: str = "rabota", page: int = 0, per_page: int = 20) -> dict:
    """Read chat with candidate. nid = id field from list_responses. provider: 'hh' or 'rabota'."""
    r = httpx.get(f"{BRIDGE}/{provider}/employer/negotiations/{nid}/messages",
                  params={"page": page, "per_page": per_page}, timeout=30)
    return r.json()

@mcp.tool()
def send_message(nid: str, text: str, provider: str = "rabota") -> dict:
    """Send message to candidate in HH.ru or Rabota.by chat.
    Only call when user explicitly requests. nid = id from list_responses."""
    r = httpx.post(f"{BRIDGE}/{provider}/negotiations/{nid}/messages",
                   json={"message": text}, timeout=30)
    return r.json()

@mcp.tool()
def change_status(nid: str, action: str = "discard_by_employer", message: str = "", provider: str = "rabota") -> dict:
    """Change a candidate response status (move between employer folders) in HH.ru / Rabota.by.

    action: discard_by_employer (Отказ/reject), consider, phone_interview, interview,
    assessment, offer, hired, discard_no_interaction, discard_vacancy_closed.
    nid = id from list_responses. Optional `message` is delivered to the candidate.

    IRREVERSIBLE from the integration (rollback only manually on the site UI).
    Only call when the user explicitly requests it. For bulk actions, confirm the
    target list with the user first."""
    if action not in VALID_ACTIONS:
        return {"ok": False, "error": f"invalid action '{action}'", "valid_actions": sorted(VALID_ACTIONS)}
    payload = {"action": action}
    if message:
        payload["message"] = message
    r = httpx.post(f"{BRIDGE}/{provider}/negotiations/{nid}/change_state",
                   json=payload, timeout=30)
    try:
        return r.json()
    except Exception:
        return {"ok": r.status_code < 400, "status_code": r.status_code, "text": r.text}

@mcp.tool()
def send_telegram_message(chat_id: str, text: str, bot_token: str) -> dict:
    """Send Telegram message via bot API.
    chat_id = @username or numeric id (from get_resume contacts).
    bot_token from @BotFather. Candidate must have messaged your bot first."""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    r = httpx.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"}, timeout=20)
    return r.json()

@mcp.tool()
def list_vacancies(employer_id: str, provider: str = "rabota") -> dict:
    """List vacancies. Rabota employer_id=772836, HH employer_id=12669364."""
    r = httpx.get(f"{BRIDGE}/{provider}/vacancies",
                  params={"employer_id": employer_id}, timeout=30)
    return r.json()

@mcp.tool()
def get_me(provider: str = "rabota") -> dict:
    """Get current account info. provider: 'hh' or 'rabota'."""
    r = httpx.get(f"{BRIDGE}/{provider}/me", timeout=20)
    return r.json()

@mcp.tool()
def token_status(provider: str = "rabota") -> dict:
    """Check OAuth token status."""
    r = httpx.get(f"{BRIDGE}/debug/{provider}/token_status", timeout=20)
    return r.json()

if __name__ == "__main__":
    mcp.run()
