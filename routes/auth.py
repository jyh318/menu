#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
@file auth.py
@description 用户认证API模块
@version 1.0.0
@author Menu Cloud Team
@date 2026-05-24

功能：
1. 用户登录（账号密码验证，MD5加密）
2. 获取当前登录用户信息
3. 检查登录状态
4. 用户登出
5. 扣除用户余额
"""

from flask import jsonify, request, session
from dbconfig.database import get_db_connection
from utils.logger import log_config
from routes.message import send_message_to_admins, _ensure_messages_table
import hashlib
import base64
import binascii
import os
import time

logger = log_config()

# 头像保存目录（前端资源已移入 frontend/）
AVATAR_DIR = os.path.join('frontend', 'img', 'user_img')
# 头像大小限制 5MB
AVATAR_MAX_SIZE = 5 * 1024 * 1024

def md5_hash(password):
    """
    旧口径：单纯 md5(明文密码) — 仅用于兼容存量数据的校验，不再用于新写入。
    """
    return hashlib.md5(password.encode('utf-8')).hexdigest()


def md5_salted(login_name, plain_password):
    """
    新口径：md5(login_name + 明文密码)，盐固定取数据库 mu_users.login_name 列。
    与门户 SSO 推送 password_hash 的口径（md5(username+password)）完全对齐。
    """
    salted = f"{login_name}{plain_password}"
    return hashlib.md5(salted.encode('utf-8')).hexdigest()


def verify_password(user_row, plain_password):
    """
    统一密码校验 + 自动升级。

    按优先级依次尝试：
      1) 新口径 md5(login_name + password)
      2) 旧口径 md5(password)                  → 命中则需升级为新口径
      3) Werkzeug scrypt / pbkdf2 历史哈希      → 命中则需升级为新口径
      4) SSO 占位值 '!' + md5(login_name)      → 永不通过本地账密登录

    返回三元组 (ok, needs_upgrade, new_hash)：
      - ok=True, needs_upgrade=False  → 已是新口径，无需写库
      - ok=True, needs_upgrade=True   → 校验通过但需升级，new_hash 为新口径值，调用方写入
      - ok=False                      → 密码错误，new_hash=None
    """
    login_name = (user_row.get('login_name') or user_row.get('username') or '').strip()
    stored = (user_row.get('password') or '').strip()

    if not stored or not login_name:
        return False, False, None

    # 1) 新口径（优先）
    if stored == md5_salted(login_name, plain_password):
        return True, False, None

    # 2) 旧口径（单 md5 明文）
    if len(stored) == 32 and all(c in '0123456789abcdef' for c in stored):
        if stored == md5_hash(plain_password):
            return True, True, md5_salted(login_name, plain_password)

    # 3) Werkzeug scrypt / pbkdf2
    try:
        from werkzeug.security import check_password_hash
        # werkzeug 哈希形如 "scrypt$..." 或 "pbkdf2:sha256:...:盐:哈希"
        if ('$' in stored or ':' in stored) and check_password_hash(stored, plain_password):
            return True, True, md5_salted(login_name, plain_password)
    except Exception:
        pass

    return False, False, None

def login():
    """
    用户登录（使用登录名 login_name 验证，username 为昵称不可登录）
    请求体：
    - username: 登录名
    - password: 密码
    - remember: 是否30天自动登录

    返回：
    - success: 是否成功
    - message: 提示信息
    - user: 用户信息（登录成功时）
    """
    data = request.json
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    remember = bool(data.get('remember'))

    if not username or not password:
        return jsonify({'success': False, 'message': '请输入登录名和密码'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        _ensure_login_name_column(cursor)
        _ensure_email_columns(cursor)
        conn.commit()

        cursor.execute('SELECT * FROM mu_users WHERE login_name = %s', (username,))
        user = cursor.fetchone()

        if user is None:
            return jsonify({'success': False, 'message': '登录名不存在'}), 401

        ok, needs_upgrade, new_hash = verify_password(user, password)
        if not ok:
            return jsonify({'success': False, 'message': '密码错误'}), 401

        # 自动升级：旧口径 / scrypt 用户在成功登录时升级为新口径
        if needs_upgrade and new_hash:
            cursor.execute('UPDATE mu_users SET password = %s WHERE id = %s', (new_hash, user['id']))
            logger.info(f"密码口径自动升级 - 用户ID: {user['id']}, login_name: {user.get('login_name')}")
        
        session['user_id'] = user['id']
        session['username'] = user['username']
        session['is_admin'] = user['is_admin']
        # 勾选"自动登录"则 session cookie 30天有效，否则浏览器关闭即失效
        session.permanent = remember
        
        logger.info(f"用户登录成功 - 用户ID: {user['id']}, 用户名: {user['username']}, 是否管理员: {user['is_admin']}")
        
        return jsonify({
            'success': True,
            'message': '登录成功',
            'user': {
                'id': user['id'],
                'username': user['username'],
                'login_name': user.get('login_name'),
                'balance': float(user['balance']),
                'is_admin': bool(user['is_admin']),
                'avatar': user.get('avatar'),
                'email': user.get('email'),
                'email_notify': bool(user.get('email_notify')),
                'created_at': user['created_at']
            }
        }), 200
        
    except Exception as e:
        logger.error(f"登录失败 - 错误: {str(e)}")
        return jsonify({'success': False, 'message': '登录失败'}), 500
    finally:
        conn.close()

def logout():
    """
    用户登出
    """
    session.clear()
    logger.info("用户登出")
    return jsonify({'success': True, 'message': '登出成功'}), 200

def get_current_user():
    """
    获取当前登录用户信息
    """
    user_id = session.get('user_id')
    
    if not user_id:
        return jsonify({'success': False, 'message': '未登录'}), 401
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        _ensure_email_columns(cursor)
        cursor.execute('SELECT * FROM mu_users WHERE id = %s', (user_id,))
        user = cursor.fetchone()
        
        if user is None:
            session.clear()
            return jsonify({'success': False, 'message': '用户不存在'}), 401
        
        return jsonify({
            'success': True,
            'user': {
                'id': user['id'],
                'username': user['username'],
                'login_name': user.get('login_name'),
                'balance': float(user['balance']),
                'is_admin': bool(user['is_admin']),
                'avatar': user.get('avatar'),
                'email': user.get('email'),
                'email_notify': bool(user.get('email_notify')),
                'created_at': user['created_at']
            }
        }), 200
        
    except Exception as e:
        logger.error(f"获取用户信息失败 - 错误: {str(e)}")
        return jsonify({'success': False, 'message': '获取用户信息失败'}), 500
    finally:
        conn.close()

def check_login():
    """
    检查登录状态
    """
    user_id = session.get('user_id')
    
    if not user_id:
        return jsonify({'logged_in': False, 'is_admin': False}), 200
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('SELECT is_admin FROM mu_users WHERE id = %s', (user_id,))
        user = cursor.fetchone()
        
        if user is None:
            session.clear()
            return jsonify({'logged_in': False, 'is_admin': False}), 200
        
        return jsonify({
            'logged_in': True,
            'is_admin': bool(user['is_admin']),
            'user_id': user_id
        }), 200
        
    except Exception as e:
        logger.error(f"检查登录状态失败 - 错误: {str(e)}")
        return jsonify({'logged_in': False, 'is_admin': False}), 200
    finally:
        conn.close()

def deduct_balance(user_id, amount):
    """
    扣除用户余额
    参数：
    - user_id: 用户ID
    - amount: 扣除金额
    
    返回：
    - success: 是否成功
    - message: 提示信息
    - balance: 剩余余额
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('SELECT balance FROM mu_users WHERE id = %s FOR UPDATE', (user_id,))
        user = cursor.fetchone()
        
        if user is None:
            return jsonify({'success': False, 'message': '用户不存在'}), 404
        
        current_balance = float(user['balance'])
        
        if current_balance < amount:
            return jsonify({'success': False, 'message': '余额不足'}), 400
        
        new_balance = current_balance - amount
        cursor.execute('UPDATE mu_users SET balance = %s WHERE id = %s', (new_balance, user_id))
        conn.commit()
        
        logger.info(f"余额扣除成功 - 用户ID: {user_id}, 扣除金额: {amount}, 剩余余额: {new_balance}")
        
        return jsonify({
            'success': True,
            'message': '余额扣除成功',
            'balance': new_balance
        }), 200
        
    except Exception as e:
        conn.rollback()
        logger.error(f"余额扣除失败 - 错误: {str(e)}")
        return jsonify({'success': False, 'message': '余额扣除失败'}), 500
    finally:
        conn.close()

def _ensure_avatar_column(cursor):
    """
    确保 mu_users 表存在 avatar 字段（惰性添加）
    """
    cursor.execute("""
        SELECT COUNT(*) AS cnt FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'mu_users' AND COLUMN_NAME = 'avatar'
    """)
    if cursor.fetchone()['cnt'] == 0:
        cursor.execute("ALTER TABLE mu_users ADD COLUMN avatar VARCHAR(255) NULL DEFAULT NULL")


def _ensure_login_name_column(cursor):
    """
    确保 mu_users 表存在 login_name 字段（惰性添加）
    存量用户以原 username 作为登录名，保证可正常登录；username 转为昵称用途
    """
    cursor.execute("""
        SELECT COUNT(*) AS cnt FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'mu_users' AND COLUMN_NAME = 'login_name'
    """)
    if cursor.fetchone()['cnt'] == 0:
        cursor.execute("ALTER TABLE mu_users ADD COLUMN login_name VARCHAR(50) NULL DEFAULT NULL")
        cursor.execute("UPDATE mu_users SET login_name = username WHERE login_name IS NULL")
        cursor.execute("ALTER TABLE mu_users MODIFY COLUMN login_name VARCHAR(50) NOT NULL")
        cursor.execute("ALTER TABLE mu_users ADD UNIQUE KEY uk_login_name (login_name)")


def _ensure_email_columns(cursor):
    """
    确保 mu_users 表存在 email 和 email_notify 字段（惰性添加）
    """
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


def _ensure_registrations_table(cursor):
    """
    确保注册申请表 mu_registrations 存在（惰性建表）
    status: pending 待审核 / approved 已通过 / rejected 已拒绝
    """
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS mu_registrations (
            id INT AUTO_INCREMENT PRIMARY KEY,
            login_name VARCHAR(50) NOT NULL,
            password VARCHAR(64) NOT NULL,
            nickname VARCHAR(50) NOT NULL,
            status VARCHAR(10) NOT NULL DEFAULT 'pending',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uk_reg_login_name (login_name)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def register():
    """
    提交注册申请（管理员审核通过后才能登录）

    请求体：
    - login_name: 登录名（3-32位，中英文/数字/下划线）
    - nickname: 昵称（可选，默认取登录名）
    - password: 密码（至少6位）
    - confirm: 确认密码
    """
    import re
    data = request.json or {}
    login_name = (data.get('login_name') or '').strip()
    nickname = (data.get('nickname') or '').strip()
    password = data.get('password', '')
    confirm = data.get('confirm', '')

    if not login_name or not password:
        return jsonify({'success': False, 'message': '登录名和密码不能为空'}), 400
    if len(login_name) < 3 or len(login_name) > 32:
        return jsonify({'success': False, 'message': '登录名长度需在 3~32 位之间'}), 400
    if not re.match(r'^[A-Za-z0-9_一-龥]+$', login_name):
        return jsonify({'success': False, 'message': '登录名只能包含中英文、数字、下划线'}), 400
    if len(password) < 6:
        return jsonify({'success': False, 'message': '密码至少 6 位'}), 400
    if password != confirm:
        return jsonify({'success': False, 'message': '两次输入的密码不一致'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        _ensure_login_name_column(cursor)
        _ensure_registrations_table(cursor)

        # 登录名在正式用户表与注册申请表中都不能冲突
        cursor.execute('SELECT id FROM mu_users WHERE login_name = %s', (login_name,))
        if cursor.fetchone():
            return jsonify({'success': False, 'message': '该登录名已被注册'}), 400
        cursor.execute("SELECT id FROM mu_registrations WHERE login_name = %s AND status = 'pending'", (login_name,))
        if cursor.fetchone():
            return jsonify({'success': False, 'message': '该登录名已提交注册，等待管理员审核'}), 400
        # 曾被拒绝的同名申请，先删除旧记录再重新申请
        cursor.execute("DELETE FROM mu_registrations WHERE login_name = %s AND status = 'rejected'", (login_name,))

        # login_name 已是最终登录名（用户选定 + 唯一性校验通过），
        # 直接用新口径 md5(login_name + 明文密码) 存到注册申请表
        cursor.execute(
            'INSERT INTO mu_registrations (login_name, password, nickname) VALUES (%s, %s, %s)',
            (login_name, md5_salted(login_name, password), nickname or login_name)
        )
        reg_id = cursor.lastrowid  # 先取申请 id，后面的建表 DDL 会重置 lastrowid

        # 有新用户注册：给所有管理员发送注册消息
        try:
            _ensure_messages_table(cursor)
            send_message_to_admins(
                cursor, 'register', '新注册申请',
                f"用户 {login_name}（昵称：{nickname or login_name}）提交了注册申请，请审核",
                related_id=str(reg_id)
            )
        except Exception as msg_err:
            logger.warning(f"发送注册通知失败 - 登录名: {login_name}, 错误: {str(msg_err)}")

        # 同时给开启了邮件通知的管理员发邮件
        try:
            from utils.email_sender import send_email, render_register_email
            cursor.execute('SELECT email FROM mu_users WHERE is_admin = 1 AND email_notify = 1 AND email IS NOT NULL AND email != ""')
            admins_with_email = [row['email'] for row in cursor.fetchall()]
            if admins_with_email:
                send_email(
                    subject=f"【小贾私房菜】新注册申请 - {login_name}",
                    content=render_register_email(cursor.lastrowid, login_name, nickname or login_name),
                    recipients=admins_with_email,
                )
        except Exception as email_err:
            logger.warning(f"发送注册邮件通知失败 - 登录名: {login_name}, 错误: {str(email_err)}")

        conn.commit()

        logger.info(f"注册申请提交 - 登录名: {login_name}, 昵称: {nickname or login_name}")
        return jsonify({'success': True, 'message': '注册申请已提交，请等待管理员审核'}), 200

    except Exception as e:
        conn.rollback()
        logger.error(f"注册申请失败 - 错误: {str(e)}")
        return jsonify({'success': False, 'message': '注册失败'}), 500
    finally:
        conn.close()


def get_registrations():
    """
    获取注册申请列表（仅管理员）
    查询参数：status（pending/approved/rejected，默认 pending）
    """
    if not session.get('is_admin'):
        return jsonify({'success': False, 'message': '无权限'}), 403

    status = request.args.get('status', 'pending')

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        _ensure_registrations_table(cursor)
        cursor.execute(
            'SELECT id, login_name, nickname, status, created_at FROM mu_registrations WHERE status = %s ORDER BY created_at DESC',
            (status,)
        )
        rows = cursor.fetchall()
        registrations = [{
            'id': r['id'],
            'login_name': r['login_name'],
            'nickname': r['nickname'],
            'status': r['status'],
            'created_at': r['created_at'].strftime('%Y-%m-%d %H:%M:%S') if r['created_at'] else None
        } for r in rows]
        return jsonify({'success': True, 'registrations': registrations}), 200

    except Exception as e:
        logger.error(f"获取注册申请列表失败 - 错误: {str(e)}")
        return jsonify({'success': False, 'message': '获取列表失败'}), 500
    finally:
        conn.close()


def review_registration(reg_id):
    """
    审核注册申请（仅管理员）

    请求体：
    - action: approve 通过 / reject 拒绝
    """
    if not session.get('is_admin'):
        return jsonify({'success': False, 'message': '无权限'}), 403

    data = request.json or {}
    action = data.get('action')

    if action not in ('approve', 'reject'):
        return jsonify({'success': False, 'message': '参数错误'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        _ensure_login_name_column(cursor)
        _ensure_registrations_table(cursor)

        cursor.execute("SELECT * FROM mu_registrations WHERE id = %s AND status = 'pending'", (reg_id,))
        reg = cursor.fetchone()
        if reg is None:
            return jsonify({'success': False, 'message': '申请不存在或已审核'}), 404

        if action == 'approve':
            # 再次确认登录名未被占用
            cursor.execute('SELECT id FROM mu_users WHERE login_name = %s', (reg['login_name'],))
            if cursor.fetchone():
                return jsonify({'success': False, 'message': '该登录名已被占用，无法通过'}), 400
            cursor.execute(
                'INSERT INTO mu_users (username, login_name, password, balance, is_admin, created_at) VALUES (%s, %s, %s, 0, 0, NOW())',
                (reg['nickname'], reg['login_name'], reg['password'])
            )

        cursor.execute('UPDATE mu_registrations SET status = %s WHERE id = %s',
                       ('approved' if action == 'approve' else 'rejected', reg_id))
        conn.commit()

        logger.info(f"注册审核 - 申请ID: {reg_id}, 登录名: {reg['login_name']}, 结果: {action}")
        return jsonify({'success': True, 'message': '已通过' if action == 'approve' else '已拒绝'}), 200

    except Exception as e:
        conn.rollback()
        logger.error(f"注册审核失败 - 错误: {str(e)}")
        return jsonify({'success': False, 'message': '审核失败'}), 500
    finally:
        conn.close()


def upload_avatar():
    """
    上传用户头像（前端裁剪为圆形后以 base64 PNG 提交）

    请求体：
    - image: data:image/png;base64,... 格式的图片数据

    返回：
    - success: 是否成功
    - avatar: 头像访问路径
    """
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'message': '未登录'}), 401

    data = request.json or {}
    image_data = (data.get('image') or '').strip()

    if not image_data.startswith('data:image/') or ',' not in image_data:
        return jsonify({'success': False, 'message': '图片格式错误'}), 400

    try:
        _, encoded = image_data.split(',', 1)
        image_bytes = base64.b64decode(encoded)
    except (ValueError, binascii.Error):
        return jsonify({'success': False, 'message': '图片解码失败'}), 400

    if len(image_bytes) > AVATAR_MAX_SIZE:
        return jsonify({'success': False, 'message': '图片不能超过 5MB'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        _ensure_avatar_column(cursor)

        cursor.execute('SELECT avatar FROM mu_users WHERE id = %s', (user_id,))
        user = cursor.fetchone()
        if user is None:
            return jsonify({'success': False, 'message': '用户不存在'}), 404

        os.makedirs(AVATAR_DIR, exist_ok=True)
        filename = f"avatar_{user_id}_{int(time.time())}.png"
        filepath = os.path.join(AVATAR_DIR, filename)

        with open(filepath, 'wb') as f:
            f.write(image_bytes)

        # 删除旧头像文件
        old_avatar = user.get('avatar')
        if old_avatar and old_avatar.startswith(AVATAR_DIR.replace(os.sep, '/')):
            old_path = old_avatar.replace('/', os.sep)
            if os.path.exists(old_path):
                try:
                    os.remove(old_path)
                except OSError:
                    pass

        avatar_url = f"img/user_img/{filename}"
        cursor.execute('UPDATE mu_users SET avatar = %s WHERE id = %s', (avatar_url, user_id))
        conn.commit()

        logger.info(f"头像上传成功 - 用户ID: {user_id}, 文件: {avatar_url}")

        return jsonify({'success': True, 'message': '头像上传成功', 'avatar': avatar_url}), 200

    except Exception as e:
        conn.rollback()
        logger.error(f"头像上传失败 - 错误: {str(e)}")
        return jsonify({'success': False, 'message': '头像上传失败'}), 500
    finally:
        conn.close()


def update_email_setting():
    """
    更新邮箱及邮件通知开关

    请求体：
    - email: 邮箱地址（可为空，清空即关闭所有邮件通知）
    - email_notify: 是否开启邮件通知（bool）
    """
    import re
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'message': '未登录'}), 401

    data = request.json or {}
    email = (data.get('email') or '').strip()
    email_notify = bool(data.get('email_notify'))

    # 邮箱格式校验
    if email:
        if not re.match(r'^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$', email):
            return jsonify({'success': False, 'message': '邮箱格式不正确'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        _ensure_email_columns(cursor)
        cursor.execute(
            'UPDATE mu_users SET email = %s, email_notify = %s WHERE id = %s',
            (email or None, 1 if email_notify and email else 0, user_id)
        )
        conn.commit()

        logger.info(f"邮箱设置更新 - 用户ID: {user_id}, email: {email}, notify: {email_notify}")
        return jsonify({'success': True, 'message': '设置已更新', 'email': email, 'email_notify': bool(email_notify and email)}), 200
    except Exception as e:
        conn.rollback()
        logger.error(f"邮箱设置更新失败 - 错误: {str(e)}")
        return jsonify({'success': False, 'message': '更新失败'}), 500
    finally:
        conn.close()


def register_auth_routes(app):
    """
    注册用户认证相关路由
    
    参数：
    - app: Flask应用实例
    """
    app.route('/api/login', methods=['POST'])(login)
    app.route('/api/logout', methods=['POST'])(logout)
    app.route('/api/register', methods=['POST'])(register)
    app.route('/api/registrations', methods=['GET'])(get_registrations)
    app.route('/api/registration/<int:reg_id>/review', methods=['POST'])(review_registration)
    app.route('/api/user', methods=['GET'])(get_current_user)
    app.route('/api/check_login', methods=['GET'])(check_login)
    app.route('/api/user/avatar', methods=['POST'])(upload_avatar)
    app.route('/api/user/deduct_balance', methods=['POST'])(deduct_balance_route)
    app.route('/api/user/password', methods=['POST'])(change_password)
    app.route('/api/user/email', methods=['POST'])(update_email_setting)

def deduct_balance_route():
    """
    扣除余额API路由包装函数
    """
    data = request.json
    user_id = data.get('user_id')
    amount = data.get('amount')
    
    if not user_id or amount is None:
        return jsonify({'success': False, 'message': '参数错误'}), 400
    
    return deduct_balance(user_id, float(amount))


def change_password():
    """
    修改密码
    
    请求体：
    - old_password: 历史密码
    - new_password: 新密码
    - confirm_password: 确认新密码
    
    返回：
    - success: 是否成功
    - message: 提示信息
    """
    data = request.json
    old_password = (data.get('old_password') or '').strip()
    new_password = (data.get('new_password') or '').strip()
    confirm_password = (data.get('confirm_password') or '').strip()
    
    # 1. 基础校验
    errors = {}
    if not old_password:
        errors['old_password'] = '请输入历史密码'
    if not new_password:
        errors['new_password'] = '请输入新密码'
    elif len(new_password) < 4:
        errors['new_password'] = '新密码至少需要 4 位'
    if not confirm_password:
        errors['confirm_password'] = '请再次输入新密码'
    
    if errors:
        return jsonify({'success': False, 'message': '请完整填写密码信息', 'errors': errors}), 400
    
    # 2. 新旧密码一致校验
    if new_password == old_password:
        return jsonify({'success': False, 'message': '新密码不能与历史密码相同', 'errors': {'new_password': '新密码不能与历史密码相同'}}), 400
    
    # 3. 两次新密码一致校验
    if new_password != confirm_password:
        return jsonify({'success': False, 'message': '两次输入的新密码不一致', 'errors': {'confirm_password': '两次输入的新密码不一致'}}), 400
    
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'message': '未登录'}), 401
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # 4. 取用户完整信息（含 login_name）用于新口径验密和哈希
        cursor.execute('SELECT id, username, login_name, password FROM mu_users WHERE id = %s', (user_id,))
        user = cursor.fetchone()
        
        if user is None:
            return jsonify({'success': False, 'message': '用户不存在'}), 404

        # 旧密码校验：统一入口，兼容三格式（新口径 / 旧 md5 / werkzeug scrypt）
        ok, _, _ = verify_password(user, old_password)
        if not ok:
            return jsonify({
                'success': False,
                'message': '历史密码不正确，请重新输入',
                'errors': {'old_password': '历史密码不正确，请重新输入'}
            }), 401
        
        # 5. 更新为新口径 md5(login_name + 新密码)
        login_name = (user.get('login_name') or user.get('username') or '').strip()
        new_hash = md5_salted(login_name, new_password)
        cursor.execute('UPDATE mu_users SET password = %s WHERE id = %s', (new_hash, user_id))
        conn.commit()
        
        logger.info(f"密码修改成功 - 用户ID: {user_id}")
        
        return jsonify({
            'success': True,
            'message': '密码修改成功'
        }), 200
        
    except Exception as e:
        conn.rollback()
        logger.error(f"密码修改失败 - 错误: {str(e)}")
        return jsonify({'success': False, 'message': '密码修改失败'}), 500
    finally:
        conn.close()
