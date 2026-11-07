#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
@file message.py
@description 站内消息API模块
@version 1.0.0
@author Menu Cloud Team
@date 2026-10-13

功能：
1. 获取当前用户消息列表
2. 获取未读消息数量（角标）
3. 标记单条/全部消息已读
4. 向指定用户/所有管理员发送消息的辅助函数（供订单、注册等模块调用）

消息类型：
- order: 新订单提醒（发给管理员，related_id 为订单编号）
- order_accepted: 订单已接单（发给下单用户，related_id 为订单编号）
- register: 新注册申请（发给管理员，related_id 为注册申请ID）
"""

from flask import jsonify, session
from dbconfig.database import get_db_connection
from utils.logger import log_config

logger = log_config()


def _ensure_messages_table(cursor):
    """
    确保消息表 mu_messages 存在（惰性建表）
    """
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS mu_messages (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            type VARCHAR(20) NOT NULL DEFAULT 'system',
            title VARCHAR(100) NOT NULL,
            content TEXT,
            is_read TINYINT(1) NOT NULL DEFAULT 0,
            related_id VARCHAR(64) NULL DEFAULT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_user_read (user_id, is_read)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def send_message(cursor, user_id, msg_type, title, content, related_id=None):
    """
    向指定用户发送消息（使用调用方的游标，随调用方事务一起提交）

    参数：
    - cursor: 数据库游标
    - user_id: 接收用户ID
    - msg_type: 消息类型（order/order_accepted/register/system）
    - title: 消息标题
    - content: 消息内容
    - related_id: 关联业务ID（订单编号/注册申请ID）
    """
    cursor.execute(
        'INSERT INTO mu_messages (user_id, type, title, content, related_id) VALUES (%s, %s, %s, %s, %s)',
        (user_id, msg_type, title, content, related_id)
    )


def send_message_to_admins(cursor, msg_type, title, content, related_id=None):
    """
    向所有管理员发送消息

    返回：发送的管理员数量
    """
    cursor.execute('SELECT id FROM mu_users WHERE is_admin = 1')
    admins = cursor.fetchall()
    for admin in admins:
        send_message(cursor, admin['id'], msg_type, title, content, related_id)
    return len(admins)


def get_messages():
    """
    获取当前登录用户的消息列表（最新100条）

    返回：
    - messages: 消息列表
    - unread_count: 未读数量
    """
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'message': '未登录'}), 401

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        _ensure_messages_table(cursor)
        cursor.execute(
            'SELECT id, type, title, content, is_read, related_id, created_at FROM mu_messages '
            'WHERE user_id = %s ORDER BY created_at DESC, id DESC LIMIT 100',
            (user_id,)
        )
        rows = cursor.fetchall()
        messages = [{
            'id': r['id'],
            'type': r['type'],
            'title': r['title'],
            'content': r['content'],
            'is_read': bool(r['is_read']),
            'related_id': r['related_id'],
            'created_at': r['created_at'].strftime('%Y-%m-%d %H:%M:%S') if r['created_at'] else None
        } for r in rows]

        # 注册类消息附带审核状态（已审核的显示"已审核"而不是"去审核"）
        # 历史消息 related_id 可能为 '0'，按内容里的登录名兜底匹配
        reg_status_by_id = {}
        import re as _re
        login_names = set()
        for m in messages:
            if m['type'] != 'register':
                continue
            rid = None
            try:
                rid = int(m['related_id']) if m['related_id'] is not None else None
            except (TypeError, ValueError):
                rid = None
            if rid:
                reg_status_by_id[rid] = None
            else:
                mt = _re.search(r'用户\s*(.+?)（', m['content'] or '')
                if mt:
                    login_names.add(mt.group(1).strip())
        if reg_status_by_id:
            fmt = ','.join(['%s'] * len(reg_status_by_id))
            cursor.execute(f'SELECT id, status FROM mu_registrations WHERE id IN ({fmt})',
                           tuple(reg_status_by_id.keys()))
            for r in cursor.fetchall():
                reg_status_by_id[r['id']] = r['status']
        reg_status_by_name = {}
        if login_names:
            fmt = ','.join(['%s'] * len(login_names))
            cursor.execute(f'SELECT login_name, status FROM mu_registrations WHERE login_name IN ({fmt})',
                           tuple(login_names))
            for r in cursor.fetchall():
                reg_status_by_name[r['login_name']] = r['status']
        for m in messages:
            if m['type'] != 'register':
                continue
            status = None
            try:
                rid = int(m['related_id']) if m['related_id'] is not None else None
            except (TypeError, ValueError):
                rid = None
            if rid and reg_status_by_id.get(rid):
                status = reg_status_by_id[rid]
            else:
                mt = _re.search(r'用户\s*(.+?)（', m['content'] or '')
                if mt:
                    status = reg_status_by_name.get(mt.group(1).strip())
            m['reg_status'] = status

        cursor.execute(
            'SELECT COUNT(*) AS cnt FROM mu_messages WHERE user_id = %s AND is_read = 0',
            (user_id,)
        )
        unread_count = cursor.fetchone()['cnt']

        return jsonify({'success': True, 'messages': messages, 'unread_count': unread_count}), 200

    except Exception as e:
        logger.error(f"获取消息列表失败 - 错误: {str(e)}")
        return jsonify({'success': False, 'message': '获取消息失败'}), 500
    finally:
        conn.close()


def get_unread_count():
    """
    获取当前登录用户的未读消息数量
    """
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'message': '未登录'}), 401

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        _ensure_messages_table(cursor)
        cursor.execute(
            'SELECT COUNT(*) AS cnt FROM mu_messages WHERE user_id = %s AND is_read = 0',
            (user_id,)
        )
        count = cursor.fetchone()['cnt']
        return jsonify({'success': True, 'unread_count': count}), 200

    except Exception as e:
        logger.error(f"获取未读消息数失败 - 错误: {str(e)}")
        return jsonify({'success': False, 'message': '获取未读数失败'}), 500
    finally:
        conn.close()


def mark_message_read(msg_id):
    """
    标记单条消息为已读（仅限本人消息）
    """
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'message': '未登录'}), 401

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            'UPDATE mu_messages SET is_read = 1 WHERE id = %s AND user_id = %s',
            (msg_id, user_id)
        )
        conn.commit()
        return jsonify({'success': True, 'message': '已标记已读'}), 200

    except Exception as e:
        conn.rollback()
        logger.error(f"标记消息已读失败 - 错误: {str(e)}")
        return jsonify({'success': False, 'message': '操作失败'}), 500
    finally:
        conn.close()


def mark_all_messages_read():
    """
    标记当前用户所有消息为已读
    """
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'message': '未登录'}), 401

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            'UPDATE mu_messages SET is_read = 1 WHERE user_id = %s AND is_read = 0',
            (user_id,)
        )
        conn.commit()
        return jsonify({'success': True, 'message': '全部已读'}), 200

    except Exception as e:
        conn.rollback()
        logger.error(f"全部标记已读失败 - 错误: {str(e)}")
        return jsonify({'success': False, 'message': '操作失败'}), 500
    finally:
        conn.close()


def register_message_routes(app):
    """
    注册消息相关路由

    参数：
    - app: Flask应用实例
    """
    app.route('/api/messages', methods=['GET'])(get_messages)
    app.route('/api/messages/unread_count', methods=['GET'])(get_unread_count)
    app.route('/api/messages/<int:msg_id>/read', methods=['POST'])(mark_message_read)
    app.route('/api/messages/read_all', methods=['POST'])(mark_all_messages_read)
