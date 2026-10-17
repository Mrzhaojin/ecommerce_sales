# -*- coding: utf-8 -*-
"""
Jinja2 模板过滤器模块。

功能说明：
    向 Jinja2 模板环境注册若干格式化过滤器，
    使模板只需书写 `{{ value|cell('money') }}` 即可完成金额、数量、百分比的格式化，
    无需在 HTML 中编写任何格式化逻辑。

为什么需要本模块（分层考量）：
    rule.md 铁则 1 明确要求「禁止在模板中编写复杂业务逻辑」。
    若在模板里直接写 `{{ "%.2f"|format(value) }}` 或嵌套 if 判断类型，
    既难以维护，也违背了「业务逻辑留在 Python 侧」的原则。
    因此把格式化能力下沉为模板过滤器，由 Python 侧统一实现。

可用过滤器：
    money   → 金额：1234.5  → ¥1,234.50
    int_comma → 整数：12345 → 12,345
    percent → 百分比：12.345 → 12.35%
    cell    → 通用单元格格式化，按传入的格式名分派到上述过滤器

分层约定（rule.md 铁则 6）：
    本层属于工具层，只做展示层格式化，不包含任何业务统计逻辑。

创建日期：2026-10-17
"""


def format_money(value):
    """
    将数值格式化为带货币符号与千分位的金额文本

    :param value: 待格式化的数值（可为 None、空字符串或非数字）
    :return: 形如 "¥1,234.50" 的字符串；无法解析时返回 "¥0.00"
    """
    try:
        amount = float(value)
    except (TypeError, ValueError):
        # 空值或非数字统一展示为 0.00，避免页面出现 "nan" 或报错
        return "¥0.00"

    return "¥{:,.2f}".format(amount)


def format_int(value):
    """
    将数值格式化为带千分位的整数文本

    :param value: 待格式化的数值（可为 None、空字符串或非数字）
    :return: 形如 "12,345" 的字符串；无法解析时返回 "0"
    """
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return "0"

    return "{:,}".format(number)


def format_percent(value):
    """
    将数值格式化为百分比文本（保留 2 位小数）

    :param value: 待格式化的数值（可为 None、空字符串或非数字）
    :return: 形如 "12.35%" 的字符串；无法解析时返回 "0.00%"
    """
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "0.00%"

    return "{:.2f}%".format(number)


def format_cell(value, fmt="text"):
    """
    通用的表格单元格格式化过滤器：按格式名分派到对应的格式化函数

    使用方式（模板中）：
        {{ row.total_amount|cell('money') }}
        {{ row.total_quantity|cell('int') }}
        {{ row.amount_ratio|cell('percent') }}
        {{ row.product_name|cell }}

    :param value: 待格式化的原始值
    :param fmt: 格式名，取值 money / int / percent / text（默认）
    :return: 格式化后的字符串
    """
    if fmt == "money":
        return format_money(value)
    if fmt == "int":
        return format_int(value)
    if fmt == "percent":
        return format_percent(value)

    # 默认按纯文本处理：None 与缺失值统一转为空字符串
    if value is None:
        return ""
    return str(value)


def register_filters(app):
    """
    将本模块中的格式化函数注册到 Flask 应用的 Jinja2 环境

    :param app: Flask 应用实例
    :return: None
    """
    app.jinja_env.filters["money"] = format_money
    app.jinja_env.filters["int_comma"] = format_int
    app.jinja_env.filters["percent"] = format_percent
    app.jinja_env.filters["cell"] = format_cell
