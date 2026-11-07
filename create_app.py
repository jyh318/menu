#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
@file create_app.py
@description Flask应用工厂 - 创建并配置Flask应用实例
@version 1.0.0
@author Menu Cloud Team
@date 2026-07-29

功能：
1. 创建Flask应用实例
2. 配置CORS和密钥
3. 注册静态文件服务
4. 注册所有业务路由
5. 提供健康检查接口
"""

import os
import json
from datetime import timedelta
from functools import wraps
from flask import Flask, jsonify, send_from_directory, request, session, redirect, url_for
from flask_cors import CORS
from utils.logger import log_config
from utils.sso_client import sso_is_enabled, sso_is_ready, sso_base, sso_client_id

# 导入路由模块
from routes.dish import register_dish_routes
from routes.tag import register_tag_routes
from routes.order import register_order_routes, create_order, checkout_order, get_order_list, get_order_detail
from routes.auth import register_auth_routes
from routes.daily import register_daily_routes
from routes.ops import register_ops_routes
from routes.message import register_message_routes
from routes.stats import register_stats_routes
from routes.sso import bp as sso_bp

logger = log_config()


def login_required(f):
    """登录保护装饰器：未登录用户访问受保护页面时跳转到 /login
    所有原始 query 参数（包括 ticket/state）会被完整透传过去，
    这样 serve_login 的 SSO 容错分支能正确接住门户回调。
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('user_id'):
            from urllib.parse import urlencode
            next_url = request.path
            qs = request.query_string.decode('utf-8')
            # 把原始 query 全部塞到 next 参数里（带回去让 serve_login 解析）
            # 但更干净的做法是拼到 url_for 之后
            if qs:
                # query_string 是 bytes，已经带 URL 编码，直接拼
                return redirect(
                    url_for('serve_login', next=next_url) + '&' + qs
                )
            return redirect(url_for('serve_login', next=next_url))
        return f(*args, **kwargs)
    return decorated


def create_app():
    """
    应用工厂函数 - 创建并配置Flask应用实例
    
    返回：
    - 配置完成的Flask应用实例
    """
    app = Flask(__name__)
    app.secret_key = 'menu_cloud_secret_key_2026'
    # 30天自动登录：permanent session 有效期30天，每次请求自动续期
    app.permanent_session_lifetime = timedelta(days=30)
    app.config['SESSION_REFRESH_EACH_REQUEST'] = True
    CORS(app, supports_credentials=True)

    # ==================== 页面路由 ====================

    # 前端资源根目录
    FRONTEND_DIR = 'frontend'

    @app.route('/login')
    def serve_login():
        """登录/注册页面"""
        if session.get('user_id'):
            next_url = request.args.get('next', '/')
            return redirect(next_url)

        # SSO 回调直接到达 /login?next=...&ticket=...&state=... 的场景（容错）
        # 门户 redirect_uri 填成根路径或 /login 时，ticket 会在 query 里一路透传过来
        ticket = request.args.get('ticket')
        if ticket and sso_is_ready():
            # state 优先用门户传来的，没有就用 next 参数作为回跳地址
            state = request.args.get('state') or request.args.get('next', '/')
            return redirect(
                url_for('sso.sso_callback') + f"?ticket={ticket}&state={state}"
            )

        # 注入 SSO 配置到 HTML（通过 JS 全局变量）
        login_html_path = os.path.join(FRONTEND_DIR, 'login.html')
        try:
            with open(login_html_path, 'r', encoding='utf-8') as f:
                html = f.read()
            sso_json = json.dumps({
                'enabled': sso_is_ready(),
                'portal_name': os.getenv('SSO_PORTAL_NAME', '统一门户'),
            })
            # 在 </head> 前注入 window.__SSO_CONFIG__
            inject = f"<script>window.__SSO_CONFIG__ = {sso_json};</script>"
            if '</head>' in html:
                html = html.replace('</head>', inject + '</head>', 1)
            else:
                html += inject
            from flask import Response
            return Response(html, mimetype='text/html')
        except Exception as e:
            logger.warning(f"注入 SSO 配置失败，回退到纯静态: {e}")
            return send_from_directory(FRONTEND_DIR, 'login.html')

    @app.route('/')
    @login_required
    def serve_index():
        """服务首页（需登录）"""
        return send_from_directory(FRONTEND_DIR, 'index.html')

    @app.route('/orders')
    @login_required
    def serve_orders():
        """订单页面（需登录）"""
        return send_from_directory(FRONTEND_DIR, 'orders.html')

    @app.route('/receipt')
    @login_required
    def serve_receipt():
        """小票页面"""
        return send_from_directory(FRONTEND_DIR, 'receipt.html')

    # ---- 独立功能页面（短链接别名；页面内再做登录/管理员守卫） ----
    # 前端统一使用 xxx.html 相对路径跳转，兼容门户桥接 /bridge/N/ 前缀
    @app.route('/messages')
    def serve_messages_page():
        return send_from_directory(FRONTEND_DIR, 'messages.html')

    @app.route('/ops')
    def serve_ops_page():
        return send_from_directory(FRONTEND_DIR, 'ops.html')

    @app.route('/registrations')
    def serve_registrations_page():
        return send_from_directory(FRONTEND_DIR, 'registrations.html')

    @app.route('/stats')
    def serve_stats_page():
        return send_from_directory(FRONTEND_DIR, 'stats.html')

    @app.route('/<path:path>')
    def serve_static(path):
        """静态文件服务（优先从 frontend/ 查找）"""
        return send_from_directory(FRONTEND_DIR, path)

    # ==================== 健康检查 ====================

    @app.route('/api/health')
    def health_check():
        """健康检查接口"""
        logger.info('健康检查')
        return jsonify({'status': 'ok', 'message': 'Server is running'})

    # ==================== 订单管理路由 ====================

    @app.route('/api/order', methods=['POST'])
    def create_order_route():
        return create_order()

    @app.route('/api/order/<order_id>/checkout', methods=['POST'])
    def checkout_order_route(order_id):
        return checkout_order(order_id)

    @app.route('/api/orders', methods=['GET'])
    def get_order_list_route():
        return get_order_list()

    @app.route('/api/order/<order_id>', methods=['GET'])
    def get_order_detail_route(order_id):
        return get_order_detail(order_id)

    @app.route('/api/receipt/info', methods=['GET'])
    def get_receipt_info_route():
        from routes.order import get_receipt_info
        return get_receipt_info()

    # ==================== 注册路由 ====================

    register_dish_routes(app)
    register_tag_routes(app)
    register_auth_routes(app)
    register_daily_routes(app)
    register_ops_routes(app)
    register_order_routes(app)
    register_message_routes(app)
    register_stats_routes(app)

    # 注册 SSO 蓝图（/sso/* 路径）
    app.register_blueprint(sso_bp)

    # 【SSO 调试】打印每个请求的原始 URL，精确定位 ticket 是否在传输中被吞
    @app.before_request
    def _debug_all_requests():
        full_url = request.url
        raw_qry = request.query_string.decode('utf-8', errors='replace')
        logger.info(f"HTTP {request.method} {request.path} ?{raw_qry}  full={full_url}")

    # 启动时打一行日志提示 SSO 状态
    if sso_is_enabled():
        if sso_is_ready():
            logger.info(f"SSO 已启用 - 门户: {sso_base()}, client_id: {sso_client_id()}")
        else:
            logger.warning("SSO_ENABLED=true 但配置不全（缺少 PORTAL_BASE / CLIENT_ID / CLIENT_SECRET），SSO 不会生效")
    else:
        logger.info("SSO 未启用（SSO_ENABLED 未设置或为 false），保持原有账密登录")

    return app
