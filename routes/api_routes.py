# -*- coding: utf-8 -*-
"""
API 接口路由模块。

功能说明：
    定义 `/api/sales/*` 系列 RESTful 数据接口，为前端 ECharts 图表提供 JSON 数据。

接口清单（详见 rule.md 第 5 章）：
    GET /api/sales/province  按省份统计销售额
    GET /api/sales/trend     按日期统计每日销售额趋势
    GET /api/sales/category  按品类统计销售额占比
    GET /api/sales/top       销量 TOP10 商品

统一响应格式（rule.md 铁则 3）：
    {"code": 200, "msg": "success", "data": [...]}

权限说明：
    以下 4 个均为查询类接口，统一使用 @login_required 保护：
    未登录时由 utils/auth.py 中的 unauthorized_handler 返回 401 JSON
    （而不是跳转登录页，否则前端 fetch 会拿到 HTML 导致解析失败）。
    后续若新增管理类接口（如数据维护、账号管理），
    在 @login_required 之下再叠加 @admin_required 即可。

分层约定（rule.md 铁则 6）：
    路由层只负责「接收请求 → 调用 services 层 → 封装响应」，
    禁止在本层编写 SQL 语句、Pandas 计算与业务判断；
    所有统计计算均由 services/data_service.py 使用 Pandas 完成。

异常处理：
    每个接口均使用 try...except 捕获异常，
    异常时记录日志并返回 code=500 与错误信息，避免堆栈外泄到前端。

创建日期：2026-10-17
"""

from flask import Blueprint, current_app
from flask_login import login_required

from services import data_service
from utils.response import fail, ok

# 创建 API 蓝图：统一挂载在 /api 前缀下
api_bp = Blueprint("api", __name__, url_prefix="/api")


@api_bp.route("/sales/province", methods=["GET"])
@login_required
def get_province_sales():
    """
    按省份统计销售额

    接口路径：GET /api/sales/province
    请求参数：无
    返回格式：
        {
            "code": 200,
            "msg": "success",
            "data": [{"name": "广东省", "value": 123456.78}]
        }
    data 说明：按销售额降序排列，name 为省份名称，value 为该省销售额

    :return: JSON 响应
    """
    try:
        # 调用 services 层完成 Pandas 聚合计算，路由层不参与任何业务计算
        data = data_service.get_sales_by_province()
        return ok(data)
    except Exception as exc:  # NOQA: BLE001
        # 记录异常堆栈到日志，便于排查；前端只拿到精简的错误描述
        current_app.logger.error(
            "[省份销售额统计] 接口异常：%s", exc, exc_info=True
        )
        return fail(msg="服务器内部错误：{}".format(exc), code=500)


@api_bp.route("/sales/trend", methods=["GET"])
@login_required
def get_sales_trend():
    """
    按日期统计每日销售额趋势

    接口路径：GET /api/sales/trend
    请求参数：无
    返回格式：
        {
            "code": 200,
            "msg": "success",
            "data": [{"date": "2026-01-01", "sales": 8934.0}]
        }
    data 说明：按日期升序排列，date 为 YYYY-MM-DD 格式，sales 为当日销售额

    :return: JSON 响应
    """
    try:
        data = data_service.get_sales_trend()
        return ok(data)
    except Exception as exc:  # NOQA: BLE001
        current_app.logger.error(
            "[每日销售趋势] 接口异常：%s", exc, exc_info=True
        )
        return fail(msg="服务器内部错误：{}".format(exc), code=500)


@api_bp.route("/sales/category", methods=["GET"])
@login_required
def get_category_sales():
    """
    按品类统计销售额占比（内部通过三表关联查询取数）

    接口路径：GET /api/sales/category
    请求参数：无
    返回格式：
        {
            "code": 200,
            "msg": "success",
            "data": [{"name": "手机", "value": 234567.0}]
        }
    data 说明：按销售额降序排列，name 为品类名称，value 为该品类销售额；
              饼图会自动根据各项数值换算百分比

    :return: JSON 响应
    """
    try:
        data = data_service.get_sales_by_category()
        return ok(data)
    except Exception as exc:  # NOQA: BLE001
        current_app.logger.error(
            "[品类销售占比] 接口异常：%s", exc, exc_info=True
        )
        return fail(msg="服务器内部错误：{}".format(exc), code=500)


@api_bp.route("/sales/top", methods=["GET"])
@login_required
def get_top_products():
    """
    统计销量 TOP10 商品

    接口路径：GET /api/sales/top
    请求参数：无（商品数量在 services 层固定为 10）
    返回格式：
        {
            "code": 200,
            "msg": "success",
            "data": [{"name": "极光轻薄手机 Max", "value": 328}]
        }
    data 说明：按累计销量降序排列，name 为商品名称，value 为累计销量（整数）

    :return: JSON 响应
    """
    try:
        data = data_service.get_top_products(limit=10)
        return ok(data)
    except Exception as exc:  # NOQA: BLE001
        current_app.logger.error(
            "[商品销量 TOP10] 接口异常：%s", exc, exc_info=True
        )
        return fail(msg="服务器内部错误：{}".format(exc), code=500)
