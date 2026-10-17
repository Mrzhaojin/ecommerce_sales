# -*- coding: utf-8 -*-
"""
路由层包。

功能说明：
    统一导出各业务蓝图，供 app.py 中的 register_blueprints() 集中注册。

分层约定（rule.md 铁则 6）：
    本层只负责「接收请求 → 校验参数 → 调用 services 层 → 封装响应」，
    禁止在本层编写 SQL 语句、Pandas 计算与业务判断。

蓝图清单：
    page_bp 页面蓝图，提供 HTML 页面（如 / ）
    api_bp  API 蓝图，统一挂载在 /api 前缀下（如 /api/sales/province ）

创建日期：2026-10-17
"""

from .api_routes import api_bp
from .page_routes import page_bp

# 对外暴露的对象清单
__all__ = ["api_bp", "page_bp"]
