#!/usr/bin/env python3
"""
watch.py  (ban single-run cho GitHub Actions - pools.fun)
--------------------------------------------------------------------------
Theo doi https://pools.fun/ va gui thong bao qua Telegram khi:
  1) Trang chuyen tu "coming soon on Sushi" sang trang thai khac
  2) Noi dung HTML thay doi (deploy moi, code moi)
  3) Cu moi STATUS_REPORT_INTERVAL_MINUTES phut, gui bao cao dinh ky

Ban CHAY MOT LAN, duoc GitHub Actions goi theo lich cron. State duoc luu
vao state.json va commit lai vao repo giua cac lan chay.
"""

import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

import requests

URL = os.environ.get("WATCH_URL", "https://pools.fun/")
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
STATE_FILE = os.environ.get("STATE_FILE", "state.json")
REQUEST_TIMEOUT = 15
COMING_SOON_MARKERS = ["coming soon"]

STATUS_REPORT_INTERVAL_MINUTES = int(os.environ.get("STATUS_REPORT_INTERVAL_MINUTES", "60"))
STATUS_REPORT_INTERVAL_SECONDS = STATUS_REPORT_INTERVAL_MINUTES * 60


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{ts}] {msg}", flush=True)


def send_telegram_message(text: str) -> None:
    if not BOT_TOKEN or not CHAT_ID:
        log("Thieu TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID (kiem tra GitHub Secrets).")
        log(f"[Thong bao le ra se gui]: {text}")
        return
    api_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    try:
        resp = requests.post(api_url, data=payload, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            log(f"Gui Telegram that bai: {resp.status_code} {resp.text}")
        else:
            log("Da gui thong bao Telegram.")
    except requests.RequestException as e:
        log(f"Loi khi gui Telegram: {e}")


def fetch_page():
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        )
    }
    try:
        resp = requests.get(URL, headers=headers, timeout=REQUEST_TIMEOUT)
        return resp.text, resp.status_code
    except requests.RequestException as e:
        log(f"Loi khi tai trang: {e}")
        return None, None


def normalize_html(html: str) -> str:
    return re.sub(r"\s+", " ", html).strip()


def compute_hash(html: str) -> str:
    return hashlib.sha256(normalize_html(html).encode("utf-8")).hexdigest()


def is_coming_soon(html: str) -> bool:
    lower = html.lower()
    return any(marker in lower for marker in COMING_SOON_MARKERS)


def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            log("state.json loi, khoi tao lai tu dau.")
    return {"hash": None, "coming_soon": None, "last_report_ts": None, "last_changed_ts": None}


def save_state(state: dict) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def maybe_send_periodic_report(state: dict, current_coming_soon, status_code, changed_this_round: bool) -> None:
    now = time.time()
    last_report_ts = state.get("last_report_ts")

    should_report = (last_report_ts is None) or (now - last_report_ts >= STATUS_REPORT_INTERVAL_SECONDS)
    if not should_report:
        return

    status_text = "Van dang 'coming soon on Sushi'" if current_coming_soon else "KHONG con 'coming soon' (co the da mo!)"
    change_text = "Co thay doi moi trong ky vua qua" if changed_this_round else "Khong co gi thay doi trong ky vua qua"
    last_changed_ts = state.get("last_changed_ts")
    last_changed_str = (
        datetime.fromtimestamp(last_changed_ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        if last_changed_ts else "chua ghi nhan thay doi nao"
    )

    send_telegram_message(
        "<b>Bao cao dinh ky - Pools.fun Watcher (GitHub Actions)</b>\n\n"
        f"URL: {URL}\n"
        f"Trang thai hien tai: {status_text}\n"
        f"Tinh hinh ky nay ({STATUS_REPORT_INTERVAL_MINUTES} phut qua): {change_text}\n"
        f"Lan thay doi gan nhat: {last_changed_str}\n"
        f"HTTP status lan check gan nhat: {status_code}\n\n"
        f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"
    )

    state["last_report_ts"] = now


def main():
    state = load_state()
    html, status_code = fetch_page()

    if html is None:
        log("Bo qua lan nay do loi mang khi tai trang.")
        sys.exit(0)

    current_hash = compute_hash(html)
    current_coming_soon = is_coming_soon(html)
    first_run = state.get("hash") is None
    changed_this_round = False

    if not first_run and state.get("coming_soon") is True and current_coming_soon is False:
        changed_this_round = True
        send_telegram_message(
            "<b>PHAT HIEN THAY DOI QUAN TRONG!</b>\n\n"
            f"Trang <a href='{URL}'>{URL}</a> co ve da <b>KHONG CON o trang thai 'coming soon'</b> nua!\n"
            "Rat co the site cua Sushi da mo / co the thao tac duoc. Kiem tra ngay!\n\n"
            f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"
        )
    elif not first_run and current_hash != state.get("hash"):
        changed_this_round = True
        send_telegram_message(
            "<b>Phat hien thay doi noi dung/code tren trang</b>\n\n"
            f"URL: {URL}\n"
            f"Trang thai 'coming soon': {'Co' if current_coming_soon else 'KHONG (da doi!)'}\n"
            f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"
        )
    elif first_run:
        log(f"Khoi tao state ban dau. Coming soon = {current_coming_soon}, status_code={status_code}")
    else:
        log("Khong co thay doi.")

    if changed_this_round:
        state["last_changed_ts"] = time.time()

    state["hash"] = current_hash
    state["coming_soon"] = current_coming_soon
    state["last_checked"] = datetime.now(timezone.utc).isoformat()
    state["last_status_code"] = status_code

    maybe_send_periodic_report(state, current_coming_soon, status_code, changed_this_round)

    save_state(state)


if __name__ == "__main__":
    main()
