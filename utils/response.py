# -*- coding: utf-8 -*-
"""
统一 JSON 响应封装模块。

功能说明：
    为所有数据接口提供统一的响应信封（Envelope），
    保证前端能够用同一套逻辑处理成功与失败两种情况。

统一响应格式（rule.md 铁则 3）：
    {"code": 200, "msg": "success", "data": []}

字段说明：
    code  业务状态码，与 HTTP 状态码保持一致，取值见下方状态码表
    msg   提示信息，成功时固定为 "success"，失败时为具体错误描述
    data  业务数据，可为数组、对象或空数组（不会为 null，便于前端统一处理）

状态码约定（rule.md 第 5.4 节）：
    200  成功
    400  请求参数错误（参数缺失或格式非法）
    401  未登录或登录已失效（接口场景；页面场景为 302 跳转登录页）
    403  权限不足（已登录但角色不够）
    404  资源不存在（路径错误）
    500  服务端异常（数据库异常 / Pandas 处理异常）

创建日期：2026-10-17
"""

from flask import jsonify


def ok(data=None, msg="success", code=200):
    """
    成功响应统一封装

    :param data: 业务数据，通常为 list 或 dict；为空时返回空数组
    :param msg: 提示信息，默认 "success"
    :param code: 业务状态码，默认 200
    :return: (Response 对象, HTTP 状态码) 元组，可直接作为路由返回值
    """
    return jsonify({
        "code": code,
        "msg": msg,
        # data 为 None 时统一返回空数组，避免前端出现 null 判断分支
        "data": data if data is not None else [],
    }), code


def fail(msg="请求失败", code=500, data=None):
    """
    失败响应统一封装

    :param msg: 错误描述信息，会直接展示给调用方
    :param code: 业务状态码，常用 400（参数错误）/ 404（资源不存在）/ 500（服务端异常）
    :param data: 附加数据，通常省略
    :return: (Response 对象, HTTP 状态码) 元组，可直接作为路由返回值
    """
    return jsonify({
        "code": code,
        "msg": msg,
        "data": data if data is not None else [],
    }), code
