#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
@file sso_client.py
@description 门户 SSO 客户端 — 封装与门户系统的单点登录 HTTP 交互
@version 1.0.0
@date 2026-11-01

完整流程（与门户运维手册一致）:
  Step 1  build_authorize_url() — 构建门户授权跳转 URL
  Step 2  门户回调回来带 ticket
  Step 3  exchange_ticket()     — 后端用 ticket 换 JWT（拿 user 信息）
  Step 4  fetch_userinfo()     — 可选：用 JWT 拉详细用户信息
  Step 5  upsert_local_user()  — 在本地 mu_users 表建/更用户 + 建 session
"""

import os
import hashlib
from urllib.parse import urljoin, quote, urlparse
import requests

from utils.logger import log_config

logger = log_config()


# ---------------------------------------------------------------------------
# SSO 配置（每次调用重新读 os.getenv，确保 dotenv.load_dotenv() 生效后才取值）
# ---------------------------------------------------------------------------

def _sso_val(key, default=''):
    return os.getenv(key, default)


def sso_is_enabled():
    """只检查 SSO 开关是否打开（用于日志提示）"""
    return _sso_val('SSO_ENABLED', 'false').lower() in ('true', '1', 'yes')


def sso_is_ready():
    """所有必要配置齐全才认为 SSO 可用"""
    return bool(
        sso_is_enabled()
        and _sso_val('SSO_PORTAL_BASE')
        and _sso_val('SSO_CLIENT_ID')
        and _sso_val('SSO_CLIENT_SECRET')
    )


def sso_base():
    return (_sso_val('SSO_PORTAL_BASE') or '').rstrip('/')


def sso_client_id():
    return _sso_val('SSO_CLIENT_ID', '')


def sso_client_secret():
    return _sso_val('SSO_CLIENT_SECRET', '')


# ---------------------------------------------------------------------------
# SSO HTTP 交互
# ---------------------------------------------------------------------------

def build_authorize_url(state='', redirect_uri=None):
    """
    构建门户授权跳转 URL（Step 1）
    """
    if not sso_is_ready():
        return ''
    url = f"{sso_base()}/sso/authorize?client_id={sso_client_id()}"
    if state:
        url += f"&state={quote(state, safe='')}"
    return url


def exchange_ticket(ticket):
    """
    ticket 换 JWT + 用户信息（Step 3）
    """
    if not sso_is_ready():
        return {'ok': False, 'error': 'SSO 未配置'}

    try:
        resp = requests.post(
            f"{sso_base()}/sso/api/token",
            json={
                'client_id': sso_client_id(),
                'client_secret': sso_client_secret(),
                'ticket': ticket,
            },
            timeout=10,
        )
    except requests.RequestException as e:
        logger.error(f"SSO ticket 换 JWT 网络错误: {str(e)}")
        return {'ok': False, 'error': f'门户不可达: {str(e)}', 'http_status': 0}

    body = {}
    try:
        body = resp.json()
    except Exception:
        pass

    if resp.status_code != 200:
        logger.warning(
            f"SSO ticket 换 JWT 失败 HTTP {resp.status_code}: "
            f"{body.get('error') or body.get('message') or resp.text[:200]}"
        )
        return {
            'ok': False,
            'error': body.get('message') or body.get('error') or f'HTTP {resp.status_code}',
            'http_status': resp.status_code,
        }

    return {
        'ok': True,
        'access_token': body.get('access_token', ''),
        'user': body.get('user', {}),
        'expires_in': body.get('expires_in', 7200),
    }


def fetch_userinfo(jwt_token):
    """
    用 JWT 拉详细用户信息（Step 4，可选，exchange_ticket 已经带 user 了）
    """
    if not sso_is_ready():
        return {'ok': False, 'error': 'SSO 未配置'}

    try:
        resp = requests.get(
            f"{sso_base()}/sso/api/userinfo",
            headers={'Authorization': f'Bearer {jwt_token}'},
            timeout=10,
        )
    except requests.RequestException as e:
        return {'ok': False, 'error': f'门户不可达: {str(e)}'}

    if resp.status_code != 200:
        body = {}
        try:
            body = resp.json()
        except Exception:
            pass
        return {'ok': False, 'error': body.get('message') or 'userinfo 拉取失败'}

    body = resp.json()
    return {'ok': True, 'user': body.get('user', {})}


# ---------------------------------------------------------------------------
# 本地用户 upsert（依赖 PyMySQL，从 routes 层传入 cursor）
# ---------------------------------------------------------------------------

def upsert_local_user(cursor, portal_user):
    """
    根据门户返回的 user dict，在 mu_users 里建/更新本地用户

    映射规则：
      门户 username → 本地 login_name（登录名）
      门户 name     → 本地 username（昵称）
      门户 is_admin → 本地 is_admin
      本地 portal_user_id → 门户 user dict 里的 id（方便反查）

    SSO 创建的用户密码存占位符 '!' + MD5(login_name)，不可通过本地密码登录
    （SSO 用户每次都走门户 ticket 流程，绕过本地密码校验）。

    返回 (user_row, created) 其中 created=True 表示新创建
    """
    username = (portal_user.get('username') or '').strip()
    name = (portal_user.get('name') or username or '').strip()
    is_admin = bool(portal_user.get('is_admin'))
    portal_user_id = portal_user.get('id')

    if not username:
        raise ValueError('门户返回的用户缺少 username')

    # 惰性确保 portal_user_id 列存在
    _ensure_portal_user_id_column(cursor)

    # 先查 portal_user_id（最精确），再查 login_name
    cursor.execute('SELECT * FROM mu_users WHERE portal_user_id = %s', (portal_user_id,))
    user = cursor.fetchone()
    if not user:
        cursor.execute('SELECT * FROM mu_users WHERE login_name = %s', (username,))
        user = cursor.fetchone()

    if user:
        # 更新现有用户
        updates = []
        args = []
        # 昵称不同才更新，避免覆盖用户本地改过的昵称
        if name and user.get('username') != name:
            updates.append('username = %s')
            args.append(name)
        updates.append('is_admin = %s')
        args.append(1 if is_admin else 0)
        updates.append('portal_user_id = %s')
        args.append(portal_user_id)
        args.append(user['id'])
        if updates:
            cursor.execute(f"UPDATE mu_users SET {', '.join(updates)} WHERE id = %s", args)
            logger.info(f"SSO upsert 用户已存在，已更新 - login_name: {username}, id: {user['id']}")
        # 重新查一遍拿到最新数据
        cursor.execute('SELECT * FROM mu_users WHERE id = %s', (user['id'],))
        return cursor.fetchone(), False

    # 新建用户
    placeholder_pwd = '!' + hashlib.md5(username.encode('utf-8')).hexdigest()
    cursor.execute(
        "INSERT INTO mu_users "
        "(username, login_name, password, balance, is_admin, created_at, portal_user_id) "
        "VALUES (%s, %s, %s, 0, %s, NOW(), %s)",
        (name or username, username, placeholder_pwd, 1 if is_admin else 0, portal_user_id)
    )
    new_id = cursor.lastrowid
    logger.info(f"SSO 新建本地用户 - login_name: {username}, nickname: {name or username}, id: {new_id}")
    cursor.execute('SELECT * FROM mu_users WHERE id = %s', (new_id,))
    return cursor.fetchone(), True


def _ensure_portal_user_id_column(cursor):
    """惰性确保 mu_users 表存在 portal_user_id 字段"""
    cursor.execute("""
        SELECT COUNT(*) AS cnt FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'mu_users' AND COLUMN_NAME = 'portal_user_id'
    """)
    if cursor.fetchone()['cnt'] == 0:
        cursor.execute("ALTER TABLE mu_users ADD COLUMN portal_user_id INT NULL DEFAULT NULL")
