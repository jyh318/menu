#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
@file email_sender.py
@description 邮件发送工具模块
@version 1.0.0
@author Menu Cloud Team
@date 2026-10-18

调用内部邮件服务发送通知邮件。
接口地址和 Token 通过模块级常量配置，便于后续迁移到 .env。
"""

import json
import threading
from pathlib import Path

import requests
from utils.logger import log_config

logger = log_config()

# ===== 邮件服务配置 =====
EMAIL_API_URL = 'http://email:8006/api/send'
EMAIL_TOKEN = '243678d02a62ed208c5e7427dd9409a804cf3a7891c68064c5fa3e814ab8db0f'
EMAIL_CONFIG_ID = 1
REQUEST_TIMEOUT = 20  # 秒

# 构建请求头
HEADERS = {
    'Authorization': f'Bearer {EMAIL_TOKEN}',
    'Content-Type': 'application/json',
}


def _do_send(subject, content, recipients, cc=None):
    """
    实际发送邮件（同步，内部调用）
    """
    if not recipients:
        return False

    payload = {
        'config_id': EMAIL_CONFIG_ID,
        'recipients': list(recipients),
        'subject': subject,
        'content': content,
        'content_type': 'html',
    }
    if cc:
        payload['cc'] = list(cc)

    try:
        resp = requests.post(EMAIL_API_URL, headers=HEADERS, json=payload, timeout=REQUEST_TIMEOUT)
        data = resp.json()
        if data.get('success'):
            logger.info(f"邮件发送成功 - 主题: {subject}, 收件人: {recipients}")
            return True
        else:
            logger.warning(f"邮件发送失败 - 主题: {subject}, 响应: {data}")
            return False
    except requests.Timeout:
        logger.warning(f"邮件发送超时 - 主题: {subject}")
        return False
    except Exception as e:
        logger.warning(f"邮件发送异常 - 主题: {subject}, 错误: {str(e)}")
        return False


def send_email(subject, content, recipients, cc=None, async_mode=True):
    """
    发送邮件

    参数：
    - subject: 邮件主题
    - content: HTML 正文内容
    - recipients: 收件人列表
    - cc: 抄送人列表（可选）
    - async_mode: 是否异步发送（默认 True，不阻塞主流程）

    返回：
    - 异步模式：始终返回 None，结果写入日志
    - 同步模式：返回 bool
    """
    if async_mode:
        t = threading.Thread(
            target=_do_send,
            args=(subject, content, recipients, cc),
            daemon=True,
        )
        t.start()
        return None
    else:
        return _do_send(subject, content, recipients, cc)


# ==================== 邮件模板 ====================

# 邮件正文无法引用站内相对路径，直接读取 frontend/img/icon 下的 SVG 内联进 HTML
_ICON_DIR = Path(__file__).resolve().parent.parent / 'frontend' / 'img' / 'icon'


def _inline_icon(name, color='#c85a2b', size=20):
    """
    把统一图标集的 SVG 内联到邮件 HTML（显式描边色，客户端无需访问站点）。
    图标文件缺失时降级为空字符串，不影响邮件正文可读性。
    """
    try:
        svg = (_ICON_DIR / f'{name}.svg').read_text(encoding='utf-8')
    except OSError:
        logger.warning(f'邮件图标缺失: {name}.svg')
        return ''
    svg = svg.replace('stroke="#000000"', f'stroke="{color}"')
    svg = svg.replace(
        '<svg ',
        f'<svg style="width:{size}px;height:{size}px;flex:none;vertical-align:-4px" ',
        1,
    )
    return svg.replace('\n', '')


_TPL_BASE = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
body{{font-family:'Noto Sans SC',system-ui,-apple-system,sans-serif;background:#f6f3ef;color:#333;margin:0;padding:24px}}
.card{{max-width:560px;margin:0 auto;background:#fff;border-radius:14px;padding:28px 32px;box-shadow:0 4px 20px rgba(0,0,0,.06)}}
.hdr{{font-size:20px;font-weight:600;color:#c85a2b;margin-bottom:16px;display:flex;align-items:center;gap:10px}}
.hdr::before{{content:'';display:inline-block;width:4px;height:20px;background:#c85a2b;border-radius:2px}}
.meta{{color:#888;font-size:13px;margin-bottom:18px}}
table{{width:100%;border-collapse:collapse;margin:12px 0;font-size:14px}}
th,td{{padding:10px 12px;border-bottom:1px solid #f0ece7;text-align:left}}
th{{color:#888;font-weight:500;background:#faf7f3}}
.total{{font-size:18px;font-weight:700;color:#c85a2b;margin-top:14px}}
.tag{{display:inline-block;background:#fff0e6;color:#c85a2b;font-size:12px;padding:2px 10px;border-radius:10px;margin-right:6px}}
.note{{background:#faf7f3;border-left:3px solid #c85a2b;padding:10px 14px;margin:14px 0;font-size:13px;color:#666;border-radius:4px}}
.ftr{{text-align:center;color:#bbb;font-size:12px;margin-top:22px}}
</style></head><body><div class="card">{body}<div class="ftr">小贾私房菜 · 系统自动发送</div></div></body></html>"""


def render_new_order_email(order_number, creator_name, items_html, total, note, status='pending'):
    """
    渲染新订单通知邮件（发给管理员）
    """
    body = f"""
    <div class="hdr">{_inline_icon('clipboard')} 新订单提醒</div>
    <div class="meta">订单号：<b>{order_number}</b>　下单人：<b>{creator_name}</b></div>
    <div>菜品明细：</div>
    <table><thead><tr><th>菜品</th><th>单价</th><th>数量</th><th>小计</th></tr></thead>
    <tbody>{items_html}</tbody></table>
    {f'<div class="note">{_inline_icon("note", size=15)} 备注：{note}</div>' if note else ''}
    <div class="total">合计：¥{total}</div>
    <div class="tag">状态：待接单</div>
    """
    return _TPL_BASE.format(body=body)


def render_order_accepted_email(order_number, items_html, total, note, creator_name):
    """
    渲染订单已接单邮件（发给下单用户）
    """
    body = f"""
    <div class="hdr">{_inline_icon('check-circle')} 您的订单已接单</div>
    <div class="meta">订单号：<b>{order_number}</b>　下单人：<b>{creator_name}</b></div>
    <div>菜品明细：</div>
    <table><thead><tr><th>菜品</th><th>单价</th><th>数量</th><th>小计</th></tr></thead>
    <tbody>{items_html}</tbody></table>
    {f'<div class="note">{_inline_icon("note", size=15)} 备注：{note}</div>' if note else ''}
    <div class="total">合计：¥{total}</div>
    <div style="color:#666;font-size:13px;margin-top:14px;">餐品正在准备中，感谢您的预订！</div>
    """
    return _TPL_BASE.format(body=body)


def render_register_email(reg_id, login_name, nickname):
    """
    渲染新注册申请邮件（发给管理员）
    """
    body = f"""
    <div class="hdr">{_inline_icon('user')} 新用户注册申请</div>
    <div class="meta">申请ID：<b>{reg_id}</b></div>
    <table>
    <tr><th>登录名</th><td>{login_name}</td></tr>
    <tr><th>昵称</th><td>{nickname}</td></tr>
    </table>
    <div style="color:#666;font-size:13px;margin-top:14px;">请到管理员面板「注册审核」处理。</div>
    """
    return _TPL_BASE.format(body=body)
