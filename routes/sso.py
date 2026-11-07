#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
@file sso.py
@description 菜单系统的 SSO 入口 — 处理门户单点登录回调 + 接收用户同步推送
@version 1.0.0
@date 2026-11-01
"""

import hmac
import hashlib
import json

from flask import Blueprint, request, session, redirect, url_for, jsonify, current_app
from dbconfig.database import get_db_connection
from utils.logger import log_config
from utils.sso_client import (
    sso_is_enabled, sso_is_ready, sso_client_id, sso_client_secret,
    build_authorize_url, exchange_ticket, upsert_local_user,
)

logger = log_config()

bp = Blueprint('sso', __name__, url_prefix='/sso')


def _error_json(message, status=400):
    return jsonify({'success': False, 'message': message}), status


def _ensure_email_columns(cursor):
    """复用 auth.py 里的惰性字段，保证 email/email_notify 列存在"""
    cursor.execute("""
        SELECT COUNT(*) AS cnt FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'mu_users' AND COLUMN_NAME = 'email'
    """)
    if cursor.fetchone()['cnt'] == 0:
        cursor.execute("ALTER TABLE mu_users ADD COLUMN email VARCHAR(120) NULL DEFAULT NULL")
    cursor.execute("""
        SELECT COUNT(*) AS cnt FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'mu_users' AND COLUMN_NAME = 'email_notify'
    """)
    if cursor.fetchone()['cnt'] == 0:
        cursor.execute("ALTER TABLE mu_users ADD COLUMN email_notify TINYINT(1) NOT NULL DEFAULT 0")


@bp.route('/login')
def sso_login():
    """
    Step 1: 入口 —— 把浏览器重定向到门户授权页

    流程：
      浏览器 → /sso/login → 302 到门户 /sso/authorize
      （门户发现未登录会自动跳 /login，用户登录成功后生成 ticket 302 回来）
    """
    if not sso_is_ready():
        logger.warning('SSO 未启用或配置不全，无法跳转门户登录')
        return redirect(url_for('serve_login', next=request.args.get('next', '/'),
                                error='SSO 未配置'))

    next_url = request.args.get('next', '/')
    state = next_url  # state 同时存目标地址，回调时用

    # 把 state 存 session（双重保险：URL 带 + session 存）
    session['sso_state'] = state

    auth_url = build_authorize_url(state=state)
    logger.info(f"SSO 跳转门户授权 - state={state}")
    return redirect(auth_url)


@bp.route('/callback', methods=['GET', 'POST'])
def sso_callback():
    """
    Step 2: 门户回调 —— 拿 ticket，换 JWT，建本地用户 + session
    同时支持 GET (query param) 和 POST (form body) —— 门户 authorize 会用 POST form 自动提交
    """
    # POST form body 优先（避免浏览器吞 GET query），GET query 次之
    if request.method == 'POST':
        ticket = (request.form.get('ticket') or '').strip()
        state = (request.form.get('state') or '').strip() or '/'
    else:
        ticket = request.args.get('ticket', '').strip()
        state = request.args.get('state', '').strip() or '/'
    session_state = session.pop('sso_state', None)

    # 调试级日志：完整打印门户回调
    logger.info(
        f"SSO /callback 收到请求 - ticket_len={len(ticket)}, "
        f"state={state!r}, session_state={session_state!r}, "
        f"all_args={dict(request.args)}"
    )

    if not sso_is_ready():
        logger.warning("SSO 未启用或配置不全")
        return redirect(url_for('serve_login', error='SSO 未配置'))

    if not ticket:
        logger.warning("SSO /callback 没拿到 ticket 参数")
        return redirect(url_for('serve_login', error='缺少 SSO ticket 参数'))

    # 简单校验 state（防 CSRF 的一层；门户 ticket 本身也是一次性的所以更关键）
    if session_state and state and state != session_state:
        logger.warning(f"SSO state 不匹配，session={session_state}, url={state}")
        # 不阻断，ticket 才是硬凭据；state 只是方便回跳
        state = session_state or state

    # ---- Step 3: ticket 换 JWT + 用户信息 ----
    result = exchange_ticket(ticket)
    if not result.get('ok'):
        err_msg = result.get('error') or 'ticket 兑换失败'
        logger.error(f"SSO ticket 换 JWT 失败: {err_msg}")
        return redirect(url_for('serve_login', error=err_msg))

    portal_user = result.get('user') or {}
    access_token = result.get('access_token', '')

    if not portal_user.get('username'):
        logger.error('SSO 门户返回的 user 缺少 username')
        return redirect(url_for('serve_login', error='门户返回用户信息异常'))

    # ---- Step 4: 本地 upsert 用户 + 建 session ----
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # 确保 login_name 列存在（auth.py 里的惰性逻辑）
        from routes.auth import _ensure_login_name_column
        _ensure_login_name_column(cursor)
        _ensure_email_columns(cursor)
        local_user, created = upsert_local_user(cursor, portal_user)
        conn.commit()

        # 建立 Flask session（菜单系统原有登录态格式）
        session['user_id'] = local_user['id']
        session['username'] = local_user.get('username')
        session['is_admin'] = bool(local_user.get('is_admin'))
        session['sso'] = True                    # 标记这是 SSO 登录的，方便前端/后续逻辑识别
        session.permanent = True                 # SSO 登录默认持久化

        logger.info(
            f"SSO 登录成功 - 本地用户ID: {local_user['id']}, "
            f"login_name: {portal_user['username']}, "
            f"is_admin: {portal_user.get('is_admin')}, "
            f"新建: {created}"
        )

        # JWT 存 session 以备后续需要（校验续期、调用门户接口等）
        if access_token:
            session['sso_jwt'] = access_token
            from datetime import datetime, timezone, timedelta
            try:
                exp_seconds = int(result.get('expires_in', 7200))
                session['sso_jwt_expires_at'] = (
                    datetime.now(timezone(timedelta(hours=8))) + timedelta(seconds=exp_seconds)
                ).isoformat()
            except Exception:
                pass

        # 跳到目标页 —— 确保是绝对路径（以 / 开头），否则 Flask redirect 会当相对路径拼接到当前 URL
        target = state or '/'
        if not target.startswith('/'):
            target = '/' + target
        # 但要排除掉一些明显不是我们系统的 state（比如门户传来的 "portal" 只是标记）
        if target in ('/portal', '/'):
            target = '/'
        return redirect(target)

    except Exception as e:
        conn.rollback()
        logger.error(f"SSO 回调处理异常: {str(e)}")
        return redirect(url_for('serve_login', error=f'SSO 登录异常: {str(e)[:80]}'))
    finally:
        conn.close()


@bp.route('/sync', methods=['POST'])
def sso_sync_push():
    """
    接收门户主动推送的用户同步数据

    请求头：
      X-Portal-Client:     client_id
      X-Portal-Signature:  sha256=hmac(client_secret, body, sha256).hexdigest()
    请求体（JSON）:
      {
        "source": "portal",
        "generated_at": "2026-11-01T15:30:00+08:00",
        "users": [
          {"username": "...", "display_name": "...", "is_active": true,
           "is_admin": false, "password_hash": "...", "created_at": "..."}
        ]
      }
    """
    if not sso_is_ready():
        return _error_json('SSO 未配置', 403)

    client_id = request.headers.get('X-Portal-Client', '').strip()
    signature = request.headers.get('X-Portal-Signature', '').strip()
    body = request.get_data() or b''

    # 1. client_id 校验
    if client_id != sso_client_id():
        logger.warning(f"SSO sync 推送 client_id 不匹配: {client_id}")
        return _error_json('unknown client', 403)

    # 2. HMAC 签名校验（与门户 sync.py 约定一致）
    if not sso_client_secret():
        return _error_json('client_secret 未配置', 500)

    expected = 'sha256=' + hmac.new(
        sso_client_secret().encode('utf-8'), body, hashlib.sha256
    ).hexdigest()

    # compare_digest 防止时序攻击
    if not hmac.compare_digest(expected, signature):
        logger.warning(f"SSO sync 签名校验失败: 收到={signature}, 期望={expected[:30]}...")
        return _error_json('bad signature', 403)

    # 3. 解析 payload
    try:
        payload = json.loads(body.decode('utf-8')) if body else {}
    except Exception:
        return _error_json('invalid JSON body', 400)

    users = payload.get('users', [])
    if not users:
        return jsonify({'ok': True, 'synced': 0})

    # 4. 批量 upsert
    conn = get_db_connection()
    cursor = conn.cursor()
    synced = 0
    try:
        from routes.auth import _ensure_login_name_column
        _ensure_login_name_column(cursor)
        _ensure_email_columns(cursor)
        from utils.sso_client import _ensure_portal_user_id_column
        _ensure_portal_user_id_column(cursor)

        for u in users:
            portal_login = (u.get('username') or '').strip()   # 门户登录名 → 本地 login_name
            if not portal_login:
                continue

            portal_name = (u.get('display_name') or portal_login).strip()  # 门户显示名 → 本地 username（昵称）
            portal_email = (u.get('email') or '').strip()
            is_admin = bool(u.get('is_admin'))
            is_active = bool(u.get('is_active', True))
            password_hash = (u.get('password_hash') or '').strip()

            # ---- 查重：先按 login_name（登录名唯一），再按 username（昵称）兜底 ----
            cursor.execute('SELECT * FROM mu_users WHERE login_name = %s', (portal_login,))
            existing = cursor.fetchone()

            if not existing:
                # 兜底：按昵称查（极少数场景 login_name 没匹配到但昵称相同）
                cursor.execute('SELECT * FROM mu_users WHERE username = %s', (portal_name,))
                existing = cursor.fetchone()

            if existing:
                # ---- 同步更新 ----
                updates = []
                args = []
                # 昵称不同才更新（避免覆盖用户本地改过的昵称）
                if portal_name and existing.get('username') != portal_name:
                    updates.append('username = %s')
                    args.append(portal_name)
                updates.append('is_admin = %s')
                args.append(1 if is_admin else 0)
                updates.append('is_active = %s')
                args.append(1 if is_active else 0)
                # email 同步（门户推送的邮箱优先覆盖）
                if portal_email and existing.get('email') != portal_email:
                    updates.append('email = %s')
                    args.append(portal_email)
                # SSO 密码策略：
                #   已存在用户 —— 默认不覆盖（用户可能已通过本地改密 / 管理员重置设置了自己的密码）
                #   例外：如果现有密码以 '!' 开头（SSO 占位值，从未设置过本地密码），
                #         允许一次性补写门户推送的 password_hash
                if password_hash and len(password_hash) == 32:
                    cur_pwd = (existing.get('password') or '').strip()
                    if cur_pwd.startswith('!'):
                        updates.append('password = %s')
                        args.append(password_hash)
                        logger.info(f"SSO sync 为占位用户补写密码 - login_name: {portal_login}")
                # 补 login_name：如果本地用户之前没 login_name（迁移遗留），补上
                if not existing.get('login_name'):
                    updates.append('login_name = %s')
                    args.append(portal_login)
                args.append(existing['id'])
                if updates:
                    cursor.execute(f"UPDATE mu_users SET {', '.join(updates)} WHERE id = %s", args)
            else:
                # ---- 新建 ----
                # 处理昵称冲突：若本地已有人用了 portal_name，自动加后缀避免撞 UNIQUE
                safe_name = portal_name or portal_login
                cursor.execute('SELECT id FROM mu_users WHERE username = %s', (safe_name,))
                if cursor.fetchone():
                    # 冲突了，用 "显示名(登录名)" 格式区分
                    safe_name = f"{portal_name}({portal_login})"
                    # 如果还撞，加数字后缀
                    idx = 2
                    while True:
                        cursor.execute('SELECT id FROM mu_users WHERE username = %s', (safe_name,))
                        if not cursor.fetchone():
                            break
                        safe_name = f"{portal_name}({portal_login})_{idx}"
                        idx += 1

                pwd = password_hash if password_hash else ('!' + hashlib.md5(portal_login.encode()).hexdigest())
                cursor.execute(
                    "INSERT INTO mu_users "
                    "(username, login_name, password, balance, is_admin, is_active, email, created_at) "
                    "VALUES (%s, %s, %s, 0, %s, %s, %s, NOW())",
                    (safe_name, portal_login, pwd,
                     1 if is_admin else 0,
                     1 if is_active else 0,
                     portal_email or None)
                )
                logger.info(f"SSO sync 新建本地用户 - login_name: {portal_login}, nickname: {safe_name}")

            synced += 1

        conn.commit()
        logger.info(f"SSO sync 推送处理完成 - 同步用户数: {synced}, source: {payload.get('source')}")
        return jsonify({'ok': True, 'synced': synced})

    except Exception as e:
        conn.rollback()
        logger.error(f"SSO sync 推送处理异常: {str(e)}")
        return _error_json(f'sync failed: {str(e)[:100]}', 500)
    finally:
        conn.close()


@bp.route('/ping')
def sso_ping():
    """心跳接口，门户可以探测 SSO 回调/同步端点是否可达"""
    return jsonify({
        'ok': True,
        'sso_enabled': sso_is_enabled(),
        'client_id': sso_client_id(),
    }), 200

