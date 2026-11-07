#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
@file ops.py
@description 运维管理API模块
@version 1.0.0
@author Menu Cloud Team
@date 2026-07-26

功能：
1. 数据库连接测试
2. 用户密码重置
3. 接口测试（本地API代理）
"""

from flask import jsonify, request, session
from dbconfig.database import get_db_connection, DB_CONFIG
from utils.logger import log_config
import time
import requests as http_requests
from routes.auth import md5_salted  # 统一密码口径：md5(login_name + 明文)

logger = log_config()


def require_admin():
    """
    管理员权限校验装饰器
    返回 (user_id, error_response) 元组
    """
    user_id = session.get('user_id')
    if not user_id:
        return None, (jsonify({'success': False, 'message': '未登录'}), 401)
    
    is_admin = session.get('is_admin')
    if not is_admin:
        return None, (jsonify({'success': False, 'message': '需要管理员权限'}), 403)
    
    return user_id, None


# md5_hash 已移除，请从 routes.auth 导入 md5_salted


def db_test():
    """
    数据库连接测试
    
    返回：
    - success: 是否成功
    - message: 提示信息
    - connection_time: 连接耗时（毫秒）
    """
    user_id, error = require_admin()
    if error:
        return error
    
    try:
        start_time = time.time()
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT 1 AS test')
        result = cursor.fetchone()
        conn.close()
        elapsed = round((time.time() - start_time) * 1000, 2)
        
        logger.info(f"数据库连接测试成功 - 耗时: {elapsed}ms")
        
        return jsonify({
            'success': True,
            'message': '数据库连接成功',
            'connection_time': elapsed,
            'database': DB_CONFIG.get('db', 'unknown'),
            'host': DB_CONFIG.get('host', 'unknown')
        }), 200
        
    except Exception as e:
        logger.error(f"数据库连接测试失败 - 错误: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'数据库连接失败: {str(e)}'
        }), 500


def reset_password():
    """
    用户密码重置（管理员操作）
    
    请求体：
    - user_id: 目标用户ID
    - new_password: 新密码
    
    返回：
    - success: 是否成功
    - message: 提示信息
    """
    user_id, error = require_admin()
    if error:
        return error
    
    data = request.json
    target_user_id = data.get('user_id')
    new_password = (data.get('new_password') or '').strip()
    
    # 参数校验
    if not target_user_id:
        return jsonify({'success': False, 'message': '请选择要重置密码的用户'}), 400
    
    if not new_password:
        return jsonify({'success': False, 'message': '请输入新密码'}), 400
    
    if len(new_password) < 4:
        return jsonify({'success': False, 'message': '新密码至少需要 4 位'}), 400
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('SELECT id, username, login_name FROM mu_users WHERE id = %s', (target_user_id,))
        user = cursor.fetchone()
        
        if user is None:
            return jsonify({'success': False, 'message': '用户不存在'}), 404
        
        # 新口径 md5(login_name + 明文密码) — 盐取 login_name 而非昵称
        login_name = (user.get('login_name') or user.get('username') or '').strip()
        new_hash = md5_salted(login_name, new_password)
        cursor.execute('UPDATE mu_users SET password = %s WHERE id = %s', (new_hash, target_user_id))
        conn.commit()
        
        logger.info(f"密码重置成功 - 管理员ID: {user_id}, 目标用户ID: {target_user_id}, login_name: {login_name}")
        
        return jsonify({
            'success': True,
            'message': f"用户 {user['username']}（登录名: {login_name}）的密码已重置"
        }), 200
        
    except Exception as e:
        conn.rollback()
        logger.error(f"密码重置失败 - 错误: {str(e)}")
        return jsonify({'success': False, 'message': f'密码重置失败: {str(e)}'}), 500
    finally:
        conn.close()


def get_user_list():
    """
    获取用户列表（用于密码重置选择用户）
    
    返回：
    - success: 是否成功
    - users: 用户列表
    """
    user_id, error = require_admin()
    if error:
        return error
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('SELECT id, username, is_admin, created_at FROM mu_users ORDER BY id')
        users = cursor.fetchall()
        
        logger.info(f"获取用户列表成功 - 管理员ID: {user_id}")
        
        return jsonify({
            'success': True,
            'users': [
                {
                    'id': u['id'],
                    'username': u['username'],
                    'is_admin': bool(u['is_admin']),
                    'created_at': str(u['created_at']) if u['created_at'] else None
                }
                for u in users
            ]
        }), 200
        
    except Exception as e:
        logger.error(f"获取用户列表失败 - 错误: {str(e)}")
        return jsonify({'success': False, 'message': f'获取用户列表失败: {str(e)}'}), 500
    finally:
        conn.close()


def api_test():
    """
    接口测试（本地API代理）
    
    请求体：
    - url: 接口地址（必须是本地 127.0.0.1）
    - method: 请求方法（GET/POST/PUT/DELETE）
    - body: 请求体（可选）
    
    返回：
    - success: 是否成功
    - status_code: 响应状态码
    - data: 响应数据
    - elapsed: 响应时间（毫秒）
    """
    user_id, error = require_admin()
    if error:
        return error
    
    data = request.json
    url = (data.get('url') or '').strip()
    method = (data.get('method') or 'GET').upper()
    body = data.get('body')
    headers = data.get('headers') or {}
    
    if not url:
        return jsonify({'success': False, 'message': '请输入接口地址'}), 400
    
    # 安全检查：只允许访问本地地址
    allowed_hosts = ['127.0.0.1', 'localhost', '0.0.0.0']
    from urllib.parse import urlparse
    parsed = urlparse(url)
    if parsed.hostname not in allowed_hosts:
        return jsonify({
            'success': False,
            'message': '安全限制：只允许访问本地接口（127.0.0.1 / localhost）'
        }), 403
    
    # 构造请求
    request_kwargs = {
        'timeout': 10,
        'headers': headers
    }
    
    if body and method in ['POST', 'PUT', 'PATCH']:
        request_kwargs['json'] = body
    
    try:
        start_time = time.time()
        response = http_requests.request(method, url, **request_kwargs)
        elapsed = round((time.time() - start_time) * 1000, 2)
        
        try:
            response_data = response.json()
        except ValueError:
            response_data = response.text
        
        logger.info(f"接口测试 - {method} {url} -> {response.status_code} ({elapsed}ms)")
        
        return jsonify({
            'success': True,
            'status_code': response.status_code,
            'data': response_data,
            'elapsed': elapsed
        }), 200
        
    except http_requests.exceptions.Timeout:
        return jsonify({
            'success': False,
            'message': '请求超时（10秒）'
        }), 504
    except http_requests.exceptions.ConnectionError as e:
        return jsonify({
            'success': False,
            'message': f'连接失败: {str(e)}'
        }), 502
    except Exception as e:
        logger.error(f"接口测试失败 - 错误: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'请求失败: {str(e)}'
        }), 500


def email_health():
    """
    邮件服务健康检查（管理员操作）
    调用 email 服务的 /health 接口

    返回：
    - success: 是否成功
    - message: 提示信息
    - elapsed: 接口耗时（毫秒）
    - email_status: 邮件服务状态
    - db_status: 邮件服务返回的数据库状态（如有）
    """
    user_id, error = require_admin()
    if error:
        return error

    import requests as req
    from utils.email_sender import EMAIL_API_URL
    from urllib.parse import urlparse

    # 从 http://email:8006/api/send 抽出 scheme://host:port + /health
    parsed = urlparse(EMAIL_API_URL)
    health_url = f"{parsed.scheme}://{parsed.netloc}/health"

    try:
        start_time = time.time()
        resp = req.get(health_url, timeout=8)
        elapsed = round((time.time() - start_time) * 1000, 2)

        try:
            data = resp.json()
        except Exception:
            data = {}

        db_status = data.get('db', 'unknown')
        svc_status = data.get('status', 'unknown')

        ok = resp.status_code == 200 and svc_status == 'ok'

        logger.info(f"邮件健康检查 - status: {resp.status_code}, svc: {svc_status}, db: {db_status}, 耗时: {elapsed}ms")

        return jsonify({
            'success': ok,
            'message': f"邮件服务: {svc_status}, 数据库: {db_status}" if ok else f"邮件服务异常（HTTP {resp.status_code}）",
            'elapsed': elapsed,
            'email_status': svc_status,
            'db_status': db_status,
            'url': health_url,
        }), (200 if ok else 502)

    except req.Timeout:
        return jsonify({
            'success': False,
            'message': '邮件服务请求超时（8秒）',
            'url': health_url,
        }), 504
    except Exception as e:
        logger.error(f"邮件健康检查失败 - 错误: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'邮件服务不可达: {str(e)}',
            'url': health_url,
        }), 502


def register_ops_routes(app):
    """
    注册运维管理相关路由
    
    参数：
    - app: Flask应用实例
    """
    app.route('/api/ops/db-test', methods=['POST'])(db_test)
    app.route('/api/ops/email-health', methods=['POST'])(email_health)
    app.route('/api/ops/reset-password', methods=['POST'])(reset_password)
    app.route('/api/ops/users', methods=['GET'])(get_user_list)
    app.route('/api/ops/api-test', methods=['POST'])(api_test)