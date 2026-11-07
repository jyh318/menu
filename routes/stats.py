#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
@file stats.py
@description 点菜次数记录与历史统计API模块
@version 1.0.0
@author Menu Cloud Team
@date 2026-11-04

数据来源：mu_order（订单头，creatuserid 记录下单人）JOIN mu_orderlink（订单明细，disid/coun/danjia）
不额外建冗余表，直接对订单明细做聚合，历史订单自动纳入统计。

功能：
1. GET /api/dishes/my-order-counts  当前用户每道菜的点菜次数/份数（供首页菜品卡片展示）
2. GET /api/stats/orders            管理员点菜历史统计（概览/菜品排行/用户排行/每日趋势/最近明细）
3. ensure_order_user_column()       惰性补齐 mu_order.creatuserid 列，保证新订单一定记录下单人
"""

from decimal import Decimal
from datetime import datetime, date

from flask import jsonify, request, session
from dbconfig.database import get_db_connection
from utils.logger import log_config

logger = log_config()


# ==================== 表结构保障 ====================

def _column_exists(cursor, table, column):
    """判断列是否存在（兼容旧库缺列的情况）"""
    cursor.execute("""
        SELECT COUNT(*) AS cnt FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = %s
    """, (table, column))
    return cursor.fetchone()['cnt'] > 0


def ensure_order_user_column(cursor):
    """
    确保 mu_order 存在 creatuserid 列。
    老版本 create_order 会逐级降级插入，缺列时订单不带用户ID，
    补列之后所有新订单都能被准确统计到点菜人。
    """
    if not _column_exists(cursor, 'mu_order', 'creatuserid'):
        cursor.execute('ALTER TABLE mu_order ADD COLUMN creatuserid INT NULL DEFAULT NULL')
        logger.info('已为 mu_order 补齐 creatuserid 列')


# ==================== 序列化辅助 ====================

def _to_jsonable(value):
    """把 MySQL 返回的 Decimal / datetime 转成可 JSON 序列化的值"""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.strftime('%Y-%m-%d %H:%M:%S')
    if isinstance(value, date):
        return value.strftime('%Y-%m-%d')
    return value


def _row_to_dict(row):
    return {k: _to_jsonable(v) for k, v in row.items()}


def _date_filter(days, start=None, end=None):
    """
    构造时间筛选条件
    - 自定义起止日期（start/end）优先于 days 预设；end 含当天
    - days <= 0 表示全部历史
    """
    if start or end:
        conds, params = [], []
        if start:
            conds.append(' AND o.oddate >= %s')
            params.append(start)
        if end:
            conds.append(' AND o.oddate < DATE_ADD(%s, INTERVAL 1 DAY)')
            params.append(end)
        return ''.join(conds), params
    if days and days > 0:
        return ' AND o.oddate >= DATE_SUB(NOW(), INTERVAL %s DAY)', [days]
    return '', []


def _limit_clause(value, default):
    """
    构造 LIMIT 子句
    value 为正整数时生效；0 / 负数 / 非法值表示不限制（全部），或回落到 default
    """
    try:
        n = int(value)
    except (TypeError, ValueError):
        n = default
    if n is None or n <= 0:
        return '', []
    return ' LIMIT %s', [n]


def _parse_date_param(value):
    """校验 YYYY-MM-DD 日期参数，非法返回 None"""
    if not value:
        return None
    try:
        return datetime.strptime(value, '%Y-%m-%d').strftime('%Y-%m-%d')
    except ValueError:
        return None


# ==================== 本人点菜次数 ====================

def get_my_order_counts():
    """
    当前登录用户对每道菜的历史点菜次数

    返回：
    - counts:      {菜品ID: 点菜次数(订单笔数)}
    - quantities:  {菜品ID: 累计份数}
    - last_ordered:{菜品ID: 最近点菜时间}
    - total_orders: 累计订单笔数
    - total_items:  累计点菜份数
    """
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'counts': {}, 'quantities': {},
                        'last_ordered': {}, 'total_orders': 0, 'total_items': 0}), 200

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        ensure_order_user_column(cursor)

        cursor.execute("""
            SELECT ol.disid AS dish_id,
                   COUNT(DISTINCT o.odnum) AS order_count,
                   COALESCE(SUM(ol.coun), 0) AS quantity,
                   MAX(o.oddate) AS last_ordered_at
            FROM mu_orderlink ol
            JOIN mu_order o ON o.odnum = ol.odnum
            WHERE o.creatuserid = %s
            GROUP BY ol.disid
        """, (user_id,))
        rows = cursor.fetchall()

        counts, quantities, last_ordered = {}, {}, {}
        for r in rows:
            key = str(r['dish_id'])
            counts[key] = int(r['order_count'])
            quantities[key] = int(r['quantity'])
            last_ordered[key] = _to_jsonable(r['last_ordered_at'])

        cursor.execute('SELECT COUNT(DISTINCT odnum) AS cnt FROM mu_order WHERE creatuserid = %s',
                       (user_id,))
        total_orders = int(cursor.fetchone()['cnt'] or 0)

        return jsonify({
            'success': True,
            'counts': counts,
            'quantities': quantities,
            'last_ordered': last_ordered,
            'total_orders': total_orders,
            'total_items': sum(quantities.values())
        }), 200

    except Exception as e:
        logger.error(f"查询本人点菜次数失败 - 错误: {str(e)}")
        return jsonify({'success': False, 'message': '获取点菜次数失败'}), 500
    finally:
        conn.close()


# ==================== 管理员点菜历史统计 ====================

def get_order_stats():
    """
    管理员点菜历史统计（仅 is_admin）

    查询参数：
    - days:        统计时间范围天数，0/不传表示全部；支持 7 / 30 / 90 / 365
    - start / end: 自定义起止日期（YYYY-MM-DD，end 含当天），优先于 days
    - trend_limit: 趋势日期数，默认 20，0 表示全部
    - dish_limit:  菜品排行条数，默认 20，0 表示全部
    - user_limit:  用户排行条数，默认 5，0 表示全部
    - recent_limit:明细条数，默认 20，0 表示全部

    返回：
    - summary: 总订单数 / 点菜次数 / 总份数 / 总金额 / 点菜人数 / 覆盖菜品数
    - by_dish: 按菜品聚合（点菜次数、份数、金额、点过的人数）
    - by_user: 按用户聚合
    - trend:   按日趋势（最近 N 个有订单的日期，正序）
    - recent:  最近 N 条点菜明细
    """
    if not session.get('is_admin'):
        return jsonify({'success': False, 'message': '需要管理员权限'}), 403

    days = request.args.get('days', 0, type=int) or 0
    start = _parse_date_param((request.args.get('start') or '').strip())
    end = _parse_date_param((request.args.get('end') or '').strip())
    if (request.args.get('start') or '').strip() and not start:
        return jsonify({'success': False, 'message': '起始日期格式应为 YYYY-MM-DD'}), 400
    if (request.args.get('end') or '').strip() and not end:
        return jsonify({'success': False, 'message': '结束日期格式应为 YYYY-MM-DD'}), 400
    if start and end and start > end:
        return jsonify({'success': False, 'message': '起始日期不能晚于结束日期'}), 400

    trend_limit = request.args.get('trend_limit', 20, type=str)
    dish_limit = request.args.get('dish_limit', 20, type=str)
    user_limit = request.args.get('user_limit', 5, type=str)
    recent_limit = request.args.get('recent_limit', 20, type=str)

    where_sql, params = _date_filter(days, start, end)

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        ensure_order_user_column(cursor)

        # ---- 概览 ----
        cursor.execute("""
            SELECT COUNT(DISTINCT o.odnum) AS order_count,
                   COUNT(*) AS line_count,
                   COALESCE(SUM(ol.coun), 0) AS quantity,
                   COALESCE(SUM(ol.coun * ol.danjia), 0) AS amount,
                   COUNT(DISTINCT o.creatuserid) AS user_count,
                   COUNT(DISTINCT ol.disid) AS dish_count
            FROM mu_order o
            JOIN mu_orderlink ol ON ol.odnum = o.odnum
            WHERE 1 = 1
        """ + where_sql, params)
        summary = _row_to_dict(cursor.fetchone())

        # ---- 菜品排行 ----
        dish_limit_sql, dish_limit_params = _limit_clause(dish_limit, 20)
        cursor.execute("""
            SELECT ol.disid AS dish_id,
                   MAX(d.name) AS dish_name,
                   COUNT(*) AS order_count,
                   COALESCE(SUM(ol.coun), 0) AS quantity,
                   COALESCE(SUM(ol.coun * ol.danjia), 0) AS amount,
                   COUNT(DISTINCT o.creatuserid) AS user_count
            FROM mu_order o
            JOIN mu_orderlink ol ON ol.odnum = o.odnum
            LEFT JOIN dishes d ON d.id = ol.disid
            WHERE 1 = 1
        """ + where_sql + """
            GROUP BY ol.disid
            ORDER BY quantity DESC, order_count DESC
        """ + dish_limit_sql, params + dish_limit_params)
        by_dish = [_row_to_dict(r) for r in cursor.fetchall()]
        for item in by_dish:
            item['dish_name'] = item['dish_name'] or f"已删除菜品#{item['dish_id']}"

        # ---- 用户排行 ----
        user_limit_sql, user_limit_params = _limit_clause(user_limit, 5)
        cursor.execute("""
            SELECT COALESCE(o.creatuserid, 0) AS user_id,
                   MAX(u.username) AS username,
                   COUNT(DISTINCT o.odnum) AS order_count,
                   COUNT(*) AS line_count,
                   COALESCE(SUM(ol.coun), 0) AS quantity,
                   COALESCE(SUM(ol.coun * ol.danjia), 0) AS amount
            FROM mu_order o
            JOIN mu_orderlink ol ON ol.odnum = o.odnum
            LEFT JOIN mu_users u ON u.id = o.creatuserid
            WHERE 1 = 1
        """ + where_sql + """
            GROUP BY COALESCE(o.creatuserid, 0)
            ORDER BY quantity DESC, order_count DESC
        """ + user_limit_sql, params + user_limit_params)
        by_user = [_row_to_dict(r) for r in cursor.fetchall()]
        for item in by_user:
            item['username'] = item['username'] or ('未记录用户' if item['user_id'] == 0 else f"用户#{item['user_id']}")

        # ---- 每日趋势（最近 N 个有订单的日期，倒序后前端再翻转） ----
        trend_limit_sql, trend_limit_params = _limit_clause(trend_limit, 20)
        cursor.execute("""
            SELECT DATE(o.oddate) AS day,
                   COUNT(DISTINCT o.odnum) AS order_count,
                   COALESCE(SUM(ol.coun), 0) AS quantity,
                   COALESCE(SUM(ol.coun * ol.danjia), 0) AS amount
            FROM mu_order o
            JOIN mu_orderlink ol ON ol.odnum = o.odnum
            WHERE 1 = 1
        """ + where_sql + """
            GROUP BY DATE(o.oddate)
            ORDER BY day DESC
        """ + trend_limit_sql, params + trend_limit_params)
        trend = list(reversed([_row_to_dict(r) for r in cursor.fetchall()]))

        # ---- 最近点菜明细 ----
        recent_limit_sql, recent_limit_params = _limit_clause(recent_limit, 20)
        cursor.execute("""
            SELECT o.odnum, o.oddate, ol.disid AS dish_id,
                   d.name AS dish_name, ol.coun AS quantity,
                   ol.danjia AS price, u.username
            FROM mu_order o
            JOIN mu_orderlink ol ON ol.odnum = o.odnum
            LEFT JOIN dishes d ON d.id = ol.disid
            LEFT JOIN mu_users u ON u.id = o.creatuserid
            WHERE 1 = 1
        """ + where_sql + """
            ORDER BY o.oddate DESC, o.odnum DESC
        """ + recent_limit_sql, params + recent_limit_params)
        recent = []
        for r in cursor.fetchall():
            item = _row_to_dict(r)
            item['dish_name'] = item['dish_name'] or f"已删除菜品#{item['dish_id']}"
            item['username'] = item['username'] or '未记录用户'
            recent.append(item)

        range_desc = f"{start}~{end}" if (start or end) else f"days={days}"
        logger.info(f"点菜历史统计查询成功 - {range_desc}, 订单数={summary['order_count']}")
        return jsonify({
            'success': True,
            'days': days,
            'start': start,
            'end': end,
            'summary': summary,
            'by_dish': by_dish,
            'by_user': by_user,
            'trend': trend,
            'recent': recent
        }), 200

    except Exception as e:
        logger.error(f"查询点菜历史统计失败 - 错误: {str(e)}")
        return jsonify({'success': False, 'message': '获取点菜历史统计失败'}), 500
    finally:
        conn.close()


def register_stats_routes(app):
    """注册点菜统计相关路由"""
    app.route('/api/dishes/my-order-counts', methods=['GET'])(get_my_order_counts)
    app.route('/api/stats/orders', methods=['GET'])(get_order_stats)
