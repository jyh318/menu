#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
@file order.py
@description 订单管理API模块
@version 1.0.0
@author Menu Cloud Team
@date 2026-05-19

功能：
1. 创建订单（点菜）- 写入 mu_order 和 mu_orderlink 表
2. 结算订单
3. 查询订单列表
4. 查询单个订单详情
"""

from flask import jsonify, request, session
from dbconfig.database import get_db_connection
from utils.logger import log_config
from routes.message import send_message, send_message_to_admins, _ensure_messages_table
from routes.stats import ensure_order_user_column
import uuid
import time
import sys

logger = log_config()


def _build_items_html(cursor, order_number):
    """
    根据订单编号构建邮件小票的菜品明细 HTML 行
    """
    cursor.execute('SELECT disid, coun, danjia FROM mu_orderlink WHERE odnum = %s', (order_number,))
    links = cursor.fetchall()
    rows_html = []
    for link in links:
        cursor.execute('SELECT name FROM dishes WHERE id = %s', (link['disid'],))
        dish = cursor.fetchone()
        name = dish['name'] if dish else f"菜品#{link['disid']}"
        qty = link['coun']
        price = float(link['danjia'])
        subtotal = price * qty
        rows_html.append(
            f'<tr><td>{name}</td><td>¥{price:.2f}</td><td>{qty}</td><td>¥{subtotal:.2f}</td></tr>'
        )
    return ''.join(rows_html)

# ==================== 辅助函数 ====================

def generate_order_number():
    """
    生成唯一的订单编号
    格式：OD + 时间戳 + 随机字符串
    """
    timestamp = int(time.time())
    random_str = str(uuid.uuid4()).replace('-', '')[:8]
    return f"OD-{timestamp}{random_str.upper()}"

# ==================== API路由函数 ====================

def create_order():
    """
    创建订单（点菜）
    
    请求体：
    - items: 菜品列表 [{id, name, price, quantity}, ...]
    - total: 总价
    
    返回：
    - order_id: 订单ID
    - order_number: 订单编号
    - message: 下单成功消息
    """
    data = request.json
    items = data.get('items', [])
    total = data.get('total', 0)
    
    note = data.get('note', '')
    
    creatuserid = session.get('user_id')
    
    # 调试：打印原始数据
    logger.info("DEBUG - raw note type: %s" % type(note))
    logger.info("DEBUG - raw note repr: %s" % repr(note))
    
    # 处理中文备注
    if note:
        try:
            note_str = str(note).encode('utf-8').decode('utf-8')
        except Exception as e:
            logger.info("DEBUG - encoding error: %s" % str(e))
            note_str = str(note)
    else:
        note_str = ''
    
    logger.info("DEBUG - note_str: %s" % repr(note_str))
    logger.info("创建订单 - 菜品数量: %d, 总价: %s, 备注: %s, 创建用户ID: %s" % (len(items), total, note_str, creatuserid))

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # 保证订单头能记录下单人（点菜次数统计依赖 creatuserid 列）
        ensure_order_user_column(cursor)

        # 生成订单编号
        order_number = generate_order_number()

        # 插入 mu_order 表（使用 NOW() 取 MySQL 会话时区，避免容器 OS 时区差异）
        try:
            cursor.execute('''
                INSERT INTO mu_order (odnum, oddate, heji, remark, creatuserid)
                VALUES (%s, NOW(), %s, %s, %s)
            ''', (order_number, int(total), note_str, creatuserid))
            logger.info("订单插入成功（带备注字段和用户ID）- 订单编号: %s" % order_number)
        except Exception as e:
            logger.warning("带备注字段和用户ID插入失败，尝试不带备注: %s" % str(e))
            try:
                cursor.execute('''
                    INSERT INTO mu_order (odnum, oddate, heji, creatuserid)
                    VALUES (%s, NOW(), %s, %s)
                ''', (order_number, int(total), creatuserid))
                logger.info("订单插入成功（带用户ID）- 订单编号: %s" % order_number)
            except Exception as e2:
                logger.warning("带用户ID插入失败，尝试不带用户ID: %s" % str(e2))
                cursor.execute('''
                    INSERT INTO mu_order (odnum, oddate, heji)
                    VALUES (%s, NOW(), %s)
                ''', (order_number, int(total)))

        # 插入 mu_orderlink 表
        for item in items:
            cursor.execute('''
                INSERT INTO mu_orderlink (odnum, disid, coun, danjia)
                VALUES (%s, %s, %s, %s)
            ''', (order_number, item.get('id'), item.get('quantity'), int(item.get('price'))))

        conn.commit()
        conn.close()

        logger.info("创建订单成功 - 订单编号: %s, 总价: %s" % (order_number, total))
        return jsonify({'order_id': order_number, 'order_number': order_number, 'message': '下单成功'}), 201
        
    except Exception as e:
        logger.error("创建订单失败 - 错误: %s" % str(e))
        conn.close()
        return jsonify({'error': '下单失败'}), 500

def checkout_order(order_id):
    """
    结算订单
    
    请求参数：
    - order_id: 订单编号（URL参数）
    
    返回：
    - message: 结算成功消息
    """
    logger.info("结算订单 - 订单编号: %s" % order_id)

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # 检查订单是否存在
        cursor.execute('SELECT * FROM mu_order WHERE odnum = %s', (order_id,))
        order = cursor.fetchone()
        
        if order is None:
            conn.close()
            logger.warning("结算订单失败 - 订单编号: %s 不存在" % order_id)
            return jsonify({'error': '订单不存在'}), 404

        order_dict = dict(order)
        total_amount = order_dict.get('heji', 0)
        user_id = order_dict.get('creatuserid')

        logger.info("结算订单 - 订单编号: %s, 金额: %s, 用户ID: %s" % (order_id, total_amount, user_id))

        # 如果有用户ID，扣除用户余额
        if user_id:
            # 获取用户当前余额
            cursor.execute('SELECT balance FROM mu_users WHERE id = %s', (user_id,))
            user = cursor.fetchone()
            
            if user:
                current_balance = user.get('balance', 0)
                new_balance = current_balance - total_amount
                
                logger.info("结算订单 - 用户ID: %s, 当前余额: %s, 扣除金额: %s, 新余额: %s" % (user_id, current_balance, total_amount, new_balance))
                
                # 更新用户余额
                cursor.execute('UPDATE mu_users SET balance = %s WHERE id = %s', (new_balance, user_id))
                logger.info("结算订单 - 用户余额更新成功")
            else:
                logger.warning("结算订单 - 用户ID: %s 不存在" % user_id)

        # 点餐成功：给所有管理员发送新订单消息
        try:
            _ensure_messages_table(cursor)
            creator_name = ''
            if user_id:
                cursor.execute('SELECT username FROM mu_users WHERE id = %s', (user_id,))
                creator = cursor.fetchone()
                if creator:
                    creator_name = creator['username']
            display_name = creator_name or (f"用户ID: {user_id}" if user_id else '游客')
            note = order_dict.get('remark', '') or ''
            items_html = _build_items_html(cursor, order_id)

            notify_count = send_message_to_admins(
                cursor, 'order', '新订单提醒',
                "用户 %s 提交了订单 %s，金额 ¥%s" % (display_name, order_id, total_amount),
                related_id=order_id
            )
            logger.info("已通知管理员 - 订单编号: %s, 管理员数: %d" % (order_id, notify_count))

            # 给开启了邮件通知的管理员发邮件（含小票）
            try:
                from utils.email_sender import send_email, render_new_order_email
                cursor.execute('SELECT email FROM mu_users WHERE is_admin = 1 AND email_notify = 1 AND email IS NOT NULL AND email != ""')
                admins_with_email = [row['email'] for row in cursor.fetchall()]
                if admins_with_email:
                    send_email(
                        subject=f"【小贾私房菜】新订单 - {order_id}",
                        content=render_new_order_email(
                            order_id, display_name, items_html,
                            float(total_amount), note
                        ),
                        recipients=admins_with_email,
                    )
            except Exception as email_err:
                logger.warning("发送新订单邮件失败 - 订单编号: %s, 错误: %s" % (order_id, str(email_err)))

        except Exception as msg_err:
            logger.warning("发送订单通知失败 - 订单编号: %s, 错误: %s" % (order_id, str(msg_err)))

        conn.commit()
        conn.close()

        logger.info("结算订单成功 - 订单编号: %s" % order_id)
        return jsonify({'message': '结算成功', 'order_number': order_id})
        
    except Exception as e:
        logger.error("结算订单失败 - 订单编号: %s, 错误: %s" % (order_id, str(e)))
        conn.close()
        return jsonify({'error': '结算失败: %s' % str(e)}), 500

def get_order_list():
    """
    获取订单列表
    
    请求参数：
    - page: 页码（默认0）
    - page_size: 每页数量（默认10）
    
    返回：
    - orders: 订单列表
    - total: 总数
    """
    page = request.args.get('page', 0, type=int)
    page_size = request.args.get('page_size', 10, type=int)

    user_id = session.get('user_id')
    is_admin = session.get('is_admin', 0)

    logger.info("查询订单列表 - 页码: %d, 每页数量: %d, 用户ID: %s, 是否管理员: %d" % (page, page_size, user_id, is_admin))

    conn = get_db_connection()
    cursor = conn.cursor()

    # 惰性添加订单状态字段，订单列表需要展示接单状态
    _ensure_order_status_column(cursor)
    conn.commit()

    # 关联用户表取昵称（username 为昵称），订餐人显示昵称而非用户ID
    base_sql = ('SELECT o.*, u.username AS creator_name FROM mu_order o '
                'LEFT JOIN mu_users u ON o.creatuserid = u.id')

    if is_admin:
        cursor.execute(base_sql + ' ORDER BY o.oddate DESC')
    elif user_id:
        cursor.execute(base_sql + ' WHERE o.creatuserid = %s ORDER BY o.oddate DESC', (user_id,))
    else:
        conn.close()
        return jsonify({
            'orders': [],
            'total': 0,
            'page': page,
            'page_size': page_size,
            'has_more': False
        })

    all_orders = [dict(row) for row in cursor.fetchall()]
    
    conn.close()

    total = len(all_orders)
    start = page * page_size
    end = start + page_size
    orders = all_orders[start:end]

    logger.info("查询订单列表成功 - 总数: %d, 返回数量: %d" % (total, len(orders)))

    return jsonify({
        'orders': orders,
        'total': total,
        'page': page,
        'page_size': page_size,
        'has_more': end < total
    })

def get_order_detail(order_id):
    """
    获取订单详情
    
    请求参数：
    - order_id: 订单编号（URL参数）
    
    返回：
    - order: 订单信息
    - items: 订单菜品列表
    """
    logger.info("查询订单详情 - 订单编号: %s" % order_id)

    conn = get_db_connection()
    cursor = conn.cursor()

    # 获取订单基本信息（关联用户表取昵称）
    cursor.execute('SELECT o.*, u.username AS creator_name FROM mu_order o LEFT JOIN mu_users u ON o.creatuserid = u.id WHERE o.odnum = %s', (order_id,))
    order = cursor.fetchone()
    
    if order is None:
        conn.close()
        logger.warning("查询订单详情失败 - 订单编号: %s 不存在" % order_id)
        return jsonify({'error': '订单不存在'}), 404

    order = dict(order)

    # 获取订单菜品列表
    cursor.execute('SELECT * FROM mu_orderlink WHERE odnum = %s', (order_id,))
    order_items = [dict(row) for row in cursor.fetchall()]

    conn.close()

    # 获取菜品名称
    for item in order_items:
        dish_id = item.get('disid')
        conn_temp = get_db_connection()
        cursor_temp = conn_temp.cursor()
        cursor_temp.execute('SELECT name FROM dishes WHERE id = %s', (dish_id,))
        dish = cursor_temp.fetchone()
        if dish:
            item['dish_name'] = dish['name']
        conn_temp.close()

    logger.info("查询订单详情成功 - 订单编号: %s, 菜品数量: %d" % (order_id, len(order_items)))

    return jsonify({
        'order': order,
        'items': order_items
    })

# ==================== 注册路由 ====================

def _ensure_order_status_column(cursor):
    """
    确保 mu_order 表存在 status 字段（惰性添加）
    status: pending 待接单 / accepted 已接单
    """
    cursor.execute("""
        SELECT COUNT(*) AS cnt FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'mu_order' AND COLUMN_NAME = 'status'
    """)
    if cursor.fetchone()['cnt'] == 0:
        cursor.execute("ALTER TABLE mu_order ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'pending'")


def accept_order(order_id):
    """
    管理员接单（仅管理员）
    接单成功后给下单用户发送消息
    """
    if not session.get('is_admin'):
        return jsonify({'success': False, 'message': '无权限'}), 403

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        _ensure_order_status_column(cursor)
        _ensure_messages_table(cursor)

        cursor.execute('SELECT odnum, status, creatuserid, remark, heji FROM mu_order WHERE odnum = %s', (order_id,))
        order = cursor.fetchone()
        if order is None:
            return jsonify({'success': False, 'message': '订单不存在'}), 404

        if order.get('status') == 'accepted':
            return jsonify({'success': False, 'message': '该订单已接单'}), 400

        cursor.execute("UPDATE mu_order SET status = 'accepted' WHERE odnum = %s", (order_id,))

        # 接单后给下单用户发送消息
        user_id = order.get('creatuserid')
        if user_id:
            send_message(
                cursor, user_id, 'order_accepted',
                '订单已接单',
                "您的订单 %s 已被接单，请耐心等待" % order_id,
                related_id=order_id
            )

            # 同时给开启了邮件通知的下单用户发邮件（含小票）
            try:
                from utils.email_sender import send_email, render_order_accepted_email
                cursor.execute(
                    'SELECT email, email_notify, username FROM mu_users WHERE id = %s',
                    (user_id,)
                )
                u = cursor.fetchone()
                if u and u.get('email_notify') and u.get('email'):
                    items_html = _build_items_html(cursor, order_id)
                    send_email(
                        subject=f"【小贾私房菜】订单已接单 - {order_id}",
                        content=render_order_accepted_email(
                            order_id, items_html, float(order['heji']),
                            order.get('remark', '') or '',
                            u.get('username') or ''
                        ),
                        recipients=[u['email']],
                    )
            except Exception as email_err:
                logger.warning("发送接单邮件失败 - 订单编号: %s, 错误: %s" % (order_id, str(email_err)))

        conn.commit()
        logger.info("接单成功 - 订单编号: %s, 下单用户ID: %s" % (order_id, order.get('creatuserid')))
        return jsonify({'success': True, 'message': '接单成功'}), 200

    except Exception as e:
        conn.rollback()
        logger.error("接单失败 - 订单编号: %s, 错误: %s" % (order_id, str(e)))
        return jsonify({'success': False, 'message': '接单失败'}), 500
    finally:
        conn.close()


def register_order_routes(app):
    """
    注册订单管理相关路由

    参数：
    - app: Flask应用实例
    """
    app.route('/api/order', methods=['POST'])(create_order)
    app.route('/api/order/<order_id>/checkout', methods=['POST'])(checkout_order)
    app.route('/api/order/<order_id>/accept', methods=['POST'])(accept_order)
    app.route('/api/orders', methods=['GET'])(get_order_list)
    app.route('/api/order/<order_id>', methods=['GET'])(get_order_detail)
    app.route('/api/receipt/info', methods=['GET'])(get_receipt_info)

def get_receipt_info():
    """
    获取小票所需的订单编号和日期信息

    返回：
    - order_number: 订单编号
    - order_date: 订单日期（格式：YYYY-MM-DD HH:MM:SS）
    """
    order_number = generate_order_number()
    # 使用 UTC+8 固定时区生成日期，避免容器 OS 时区差异
    from datetime import datetime, timezone, timedelta
    order_date = datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')

    logger.info("生成小票信息 - 订单编号: %s, 日期: %s" % (order_number, order_date))

    return jsonify({
        'order_number': order_number,
        'order_date': order_date
    })
