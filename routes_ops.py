#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
@file routes_ops.py
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
from dataconf import get_db_connection, DB_CONFIG
from logconfig import log_config
import hashlib
import time
import requests as http_requests

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


def md5_hash(password):
    """
    MD5加密函数
    """
    return hashlib.md5(password.encode('utf-8')).hexdigest()


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
        cursor.execute('SELECT id, username FROM mu_users WHERE id = %s', (target_user_id,))
        user = cursor.fetchone()
        
        if user is None:
            return jsonify({'success': False, 'message': '用户不存在'}), 404
        
        new_hash = md5_hash(new_password)
        cursor.execute('UPDATE mu_users SET password = %s WHERE id = %s', (new_hash, target_user_id))
        conn.commit()
        
        logger.info(f"密码重置成功 - 管理员ID: {user_id}, 目标用户ID: {target_user_id}, 用户名: {user['username']}")
        
        return jsonify({
            'success': True,
            'message': f"用户 {user['username']} 的密码已重置"
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


def register_ops_routes(app):
    """
    注册运维管理相关路由
    
    参数：
    - app: Flask应用实例
    """
    app.route('/api/ops/db-test', methods=['POST'])(db_test)
    app.route('/api/ops/reset-password', methods=['POST'])(reset_password)
    app.route('/api/ops/users', methods=['GET'])(get_user_list)
    app.route('/api/ops/api-test', methods=['POST'])(api_test)
