# -*- coding: utf-8 -*-
"""多账号管理：每个账号独立 Chrome profile + cookies，长期保存，可切换。
- 账号目录: accounts/<名称>/profile（浏览器登录态）+ cookies.txt（接口备用）
- 活跃账号: accounts/active.json
- 兼容旧版：BASE/chrome_profile + BASE/cookies.txt 视为「default」账号
"""
import os, json, re, shutil

from _paths import BASE

ACCOUNTS_DIR = os.path.join(BASE, "accounts")
ACTIVE_FILE = os.path.join(ACCOUNTS_DIR, "active.json")
LEGACY_PROFILE = os.path.join(BASE, "chrome_profile")
LEGACY_COOKIES = os.path.join(BASE, "cookies.txt")


def safe_name(name):
    name = (name or "").strip()
    name = re.sub(r"[^0-9A-Za-z_\-\u4e00-\u9fff]", "", name)
    return name[:32]


def _read_cookie_has_session(path):
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            return "sessionid" in f.read()
    except OSError:
        return False


def list_accounts():
    """返回 [{name, logged_in, cookies, profile, legacy}]，default 为旧登录态"""
    accs = []
    seen = set()
    if os.path.isdir(ACCOUNTS_DIR):
        for n in sorted(os.listdir(ACCOUNTS_DIR)):
            d = os.path.join(ACCOUNTS_DIR, n)
            if not os.path.isdir(d) or n in ("active.json",):
                continue
            ck = os.path.join(d, "cookies.txt")
            accs.append({"name": n, "cookies": os.path.exists(ck),
                         "logged_in": _read_cookie_has_session(ck), "profile": os.path.join(d, "profile"),
                         "legacy": False})
            seen.add(n)
    # default 是内置账号：始终可选，首次登录会创建 chrome_profile/cookies.txt
    if "default" not in seen:
        accs.insert(0, {"name": "default", "cookies": os.path.exists(LEGACY_COOKIES),
                        "logged_in": _read_cookie_has_session(LEGACY_COOKIES),
                        "profile": LEGACY_PROFILE, "legacy": True})
    return accs


def active_name():
    try:
        with open(ACTIVE_FILE, encoding="utf-8") as f:
            n = (json.load(f).get("active") or "").strip()
        return safe_name(n)
    except Exception:
        return ""


def set_active(name):
    name = safe_name(name)
    if not name:
        raise ValueError("账号名不能为空")
    names = {a["name"] for a in list_accounts()}
    if name not in names:
        raise ValueError("账号不存在")
    os.makedirs(ACCOUNTS_DIR, exist_ok=True)
    with open(ACTIVE_FILE, "w", encoding="utf-8") as f:
        json.dump({"active": name}, f, ensure_ascii=False)
    return name


def ensure_account(name):
    name = safe_name(name)
    if not name:
        raise ValueError("账号名仅支持字母/数字/中文/_/-")
    d = os.path.join(ACCOUNTS_DIR, name)
    os.makedirs(os.path.join(d, "profile"), exist_ok=True)
    return name


def profile_dir(name=None):
    """活跃账号的浏览器 profile；无账号时回退旧版 chrome_profile"""
    name = safe_name(name) if name else active_name()
    if name:
        if name == "default" and os.path.isdir(LEGACY_PROFILE):
            return LEGACY_PROFILE
        return os.path.join(ACCOUNTS_DIR, name, "profile")
    return LEGACY_PROFILE


def cookies_path(name=None):
    """活跃账号的 cookies.txt；无账号时回退旧版 cookies.txt"""
    name = safe_name(name) if name else active_name()
    if name:
        if name == "default" and not os.path.isdir(os.path.join(ACCOUNTS_DIR, "default")):
            return LEGACY_COOKIES
        return os.path.join(ACCOUNTS_DIR, name, "cookies.txt")
    return LEGACY_COOKIES


def account_dir(name):
    return os.path.join(ACCOUNTS_DIR, safe_name(name))
