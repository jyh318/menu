#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
@file routes_order.py
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
from dataconf import get_db_connection
from logconfig import log_config
import uuid
import time
import sys

logger = log_config()

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
        # 生成订单编号
        order_number = generate_order_number()
        current_time = time.strftime('%Y-%m-%d %H:%M:%S')

        # 插入 mu_order 表（支持备注字段和创建用户ID）
        try:
            cursor.execute('''
                INSERT INTO mu_order (odnum, oddate, heji, remark, creatuserid)
                VALUES (%s, %s, %s, %s, %s)
            ''', (order_number, current_time, int(total), note_str, creatuserid))
            logger.info("订单插入成功（带备注字段和用户ID）- 订单编号: %s" % order_number)
        except Exception as e:
            logger.warning("带备注字段和用户ID插入失败，尝试不带备注: %s" % str(e))
            try:
                cursor.execute('''
                    INSERT INTO mu_order (odnum, oddate, heji, creatuserid)
                    VALUES (%s, %s, %s, %s)
                ''', (order_number, current_time, int(total), creatuserid))
                logger.info("订单插入成功（带用户ID）- 订单编号: %s" % order_number)
            except Exception as e2:
                logger.warning("带用户ID插入失败，尝试不带用户ID: %s" % str(e2))
                cursor.execute('''
                    INSERT INTO mu_order (odnum, oddate, heji)
                    VALUES (%s, %s, %s)
                ''', (order_number, current_time, int(total)))

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

    if is_admin:
        cursor.execute('SELECT * FROM mu_order ORDER BY oddate DESC')
    elif user_id:
        cursor.execute('SELECT * FROM mu_order WHERE creatuserid = %s ORDER BY oddate DESC', (user_id,))
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

    # 获取订单基本信息
    cursor.execute('SELECT * FROM mu_order WHERE odnum = %s', (order_id,))
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

def register_order_routes(app):
    """
    注册订单管理相关路由

    参数：
    - app: Flask应用实例
    """
    app.route('/api/order', methods=['POST'])(create_order)
    app.route('/api/order/<order_id>/checkout', methods=['POST'])(checkout_order)
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
    order_date = time.strftime('%Y-%m-%d %H:%M:%S')

    logger.info("生成小票信息 - 订单编号: %s, 日期: %s" % (order_number, order_date))

    return jsonify({
        'order_number': order_number,
        'order_date': order_date
    })
