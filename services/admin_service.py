# -*- coding: utf-8 -*-
"""
业务逻辑层：管理员数据管理服务。

功能说明：
    为管理员专属的「数据管理」页面提供三张业务表（category / product /
    sales_order）的明细浏览、关键字搜索、排序与分页能力，
    并统计各表的概览指标。

标准数据流（rule.md 铁则 4，必须严格遵守）：
    models 层 ORM 查询（仅取原始行，不做任何分组聚合）
        ↓
    df = pd.DataFrame([row.to_dict() for row in rows])
        ↓
    Pandas 完成：merge 关联 → groupby 分组 → agg 聚合
        ↓
    sort_values 排序 → 关键字筛选 → iloc 分页切片
        ↓
    转换为 Python 原生类型的 list[dict]，返回给 routes 层

    说明：本项目数据量较小（1500 条订单），
    因此分页与排序也在 Pandas 中完成（使用 iloc 切片），
    而不是交给 ORM 的 limit / offset。
    这样做的好处是整条数据链路清晰可见，
    能够完整展示「ORM 取数 + Pandas 处理」的分工，符合实验教学目的。
    若数据量增长到十万级以上，再考虑把分页下推到 ORM 层。

分层约定（rule.md 铁则 6）：
    本层不接触 request、jsonify 等 Flask 请求响应对象，
    对外统一返回纯 Python 数据结构（list / dict / tuple）。

创建日期：2026-10-17
"""

import pandas as pd

from models.db_models import Category, Product, SalesOrder

# ---------------- 分页相关常量 ----------------
# 默认每页显示的记录条数
DEFAULT_PER_PAGE = 10
# 每页允许显示的最大条数，避免一次性渲染过多行导致页面卡顿
MAX_PER_PAGE = 100
# 页码下限
MIN_PAGE = 1


# ==================== 私有工具函数 ====================

def _safe_int(value, default, min_value=None, max_value=None):
    """
    将任意输入安全转换为整数，并进行取值范围收敛

    说明：分页参数来自 URL 查询字符串，属于不可信输入。
    若直接用于切片，传入非数字（如 ?page=abc）会抛出 ValueError，
    传入超大值（如 ?per_page=99999）则会导致一次性加载过多数据。
    因此统一在此处做类型转换与范围收敛。

    :param value: 待转换的输入值（通常为字符串）
    :param default: 转换失败时使用的默认值
    :param min_value: 取值下限，小于该值时收敛到该值
    :param max_value: 取值上限，大于该值时收敛到该值
    :return: 收敛后的 int 值
    """
    try:
        result = int(value)
    except (TypeError, ValueError):
        return default

    # 依次收敛下界与上界，保证返回值始终落在合法区间内
    if min_value is not None and result < min_value:
        return min_value
    if max_value is not None and result > max_value:
        return max_value
    return result


def _build_dataframe(records):
    """
    将字典记录列表转换为 DataFrame（ORM → Pandas 的统一入口）

    :param records: 字典记录列表，通常来自模型对象的 to_dict()
    :return: pandas.DataFrame；传入空列表时返回空 DataFrame
    """
    if not records:
        # 返回空 DataFrame 交由调用方统一处理，避免后续 groupby 报错
        return pd.DataFrame()

    return pd.DataFrame(records)


def _filter_by_keyword(df, columns, keyword):
    """
    按关键字对指定文本列做模糊筛选（不区分大小写）

    实现说明：
        先把目标列统一转为字符串并填充空串，
        再用 str.contains 逐列匹配，最后用「或」逻辑合并各列的匹配结果。
        这样只要任意一列命中关键字，该行就会被保留。

    :param df: 待筛选的 DataFrame
    :param columns: 参与匹配的列名列表
    :param keyword: 搜索关键字；为空字符串时不作筛选
    :return: 筛选后的 DataFrame；关键字为空时原样返回
    """
    if df.empty or not keyword:
        return df

    keyword = str(keyword).strip()
    if not keyword:
        return df

    # 用 False 初始化匹配掩码，逐列累积匹配结果
    mask = pd.Series(False, index=df.index)
    for column in columns:
        if column not in df.columns:
            continue
        # case=False 关闭大小写敏感；na=False 把缺失值视为不匹配
        column_values = df[column].astype("string").fillna("")
        mask = mask | column_values.str.contains(keyword, case=False, na=False)

    return df[mask]


def _sort_dataframe(
    df,
    sort_by,
    allowed_columns,
    default_column,
    descending=True,
):
    """
    按指定列排序，列名必须通过白名单校验

    安全性说明：
        排序列名直接来自 URL 查询参数，属于不可信输入。
        若直接传给 sort_values()，传入不存在的列名会抛出 KeyError
        导致接口 500。因此必须先校验列名是否在允许清单内，
        不在清单内时回退到默认排序列。

    :param df: 待排序的 DataFrame
    :param sort_by: 期望的排序列名
    :param allowed_columns: 允许排序的列名白名单
    :param default_column: 校验失败时使用的默认排序列
    :param descending: 是否降序排列，默认 True
    :return: 排序后的 DataFrame
    """
    if df.empty:
        return df

    # 白名单校验：非法列名回退到默认列，避免 KeyError
    column = sort_by if sort_by in allowed_columns else default_column
    if column not in df.columns:
        return df

    return df.sort_values(column, ascending=not descending)


def _paginate_dataframe(df, page, per_page):
    """
    对 DataFrame 做分页切片，返回当前页数据与分页信息

    分页信息字段说明：
        page         当前页码
        per_page     每页条数
        total        过滤后的总记录数
        total_pages  总页数（总记录数为 0 时为 1）
        has_prev     是否有上一页
        has_next     是否有下一页

    :param df: 已完成筛选与排序的 DataFrame
    :param page: 当前页码（从 1 开始）
    :param per_page: 每页条数
    :return: (当前页记录列表, 分页信息字典) 元组
    """
    page = _safe_int(page, MIN_PAGE, min_value=MIN_PAGE)
    per_page = _safe_int(
        per_page, DEFAULT_PER_PAGE, min_value=1, max_value=MAX_PER_PAGE
    )

    total = int(len(df))

    # 总页数为 0 时按 1 处理，保证前端分页器不会出现「第 1 / 0 页」的显示
    total_pages = max(1, (total + per_page - 1) // per_page)

    # 页码超出总页数时收敛到最后一页，避免返回空列表
    if page > total_pages:
        page = total_pages

    # 计算切片区间：iloc 的结束位置超出长度时 Pandas 会自动截断
    start_index = (page - 1) * per_page
    end_index = start_index + per_page
    page_df = df.iloc[start_index:end_index]

    pagination = {
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": total_pages,
        "has_prev": page > 1,
        "has_next": page < total_pages,
    }

    return _to_record_list(page_df), pagination


def _to_record_list(df):
    """
    将 DataFrame 转换为接口可直接序列化的记录列表

    类型转换说明：
        numpy.int64 并非 Python int 的子类，
        若不转换会导致 jsonify 抛出
        「Object of type int64 is not JSON serializable」；
        因此此处逐行将数值显式转换为 Python 原生类型，
        浮点统一保留 2 位小数。

    :param df: 待转换的 DataFrame
    :return: list[dict]；DataFrame 为空时返回空列表
    """
    if df is None or df.empty:
        return []

    records = []
    # itertuples 比 iterrows 更快，且能保留列名
    for row in df.itertuples(index=False):
        record = {}
        for column in df.columns:
            value = getattr(row, column)
            if isinstance(value, bool):
                record[column] = value
            elif isinstance(value, (int, float)):
                # 浮点保留 2 位小数，整数直接转 int
                record[column] = (
                    round(float(value), 2)
                    if isinstance(value, float)
                    else int(value)
                )
            elif value is None or pd.isna(value):
                # 缺失值（None / NaN / pd.NA）统一转为空字符串，便于模板渲染
                record[column] = ""
            else:
                record[column] = str(value)
        records.append(record)

    return records


def _calc_amount_ratio(df, amount_column):
    """
    在 DataFrame 中新增一列「销售额占比」（百分比，保留 2 位小数）

    :param df: 含金额列的 DataFrame，函数内部会复制后再修改
    :param amount_column: 金额列名
    :return: 新增占比列后的 DataFrame 副本
    """
    df = df.copy()

    total = df[amount_column].sum() if not df.empty else 0.0
    if total:
        df["amount_ratio"] = (df[amount_column] / total * 100).round(2)
    else:
        # 总额为 0 时占比统一为 0，避免出现除零错误或 NaN
        df["amount_ratio"] = 0.0

    return df


# ==================== 一、概览统计 ====================

def _calc_order_metrics(df_order):
    """
    基于订单 DataFrame 计算与订单相关的概览指标（Pandas 聚合）

    计算口径：
        订单总数    金额有效（非缺失且 >= 0）的订单行数
        销售总额    上述订单的金额合计
        客单价      销售总额 ÷ 订单总数
        覆盖省份数  订单中出现的省份去重计数
        数据起始日  最早的下单日期
        数据截止日  最晚的下单日期

    :param df_order: 订单原始行构成的 DataFrame，可为空
    :return: 订单指标字典
    """
    empty_result = {
        "order_count": 0,
        "total_amount": 0.0,
        "avg_order_amount": 0.0,
        "province_count": 0,
        "date_start": "",
        "date_end": "",
    }

    if df_order.empty:
        return empty_result

    # 1. 金额列强制转数值，无法解析的值置为 NaN
    df_order["total_amount"] = pd.to_numeric(
        df_order["total_amount"], errors="coerce"
    )

    # 2. 剔除金额缺失与为负的异常记录
    valid = df_order.dropna(subset=["total_amount"])
    valid = valid[valid["total_amount"] >= 0]

    order_count = int(len(valid))
    if order_count == 0:
        return empty_result

    # 3. Pandas 聚合求和得到销售总额
    total_amount = round(float(valid["total_amount"].sum()), 2)

    # 4. 日期列转为 datetime 后取最早与最晚日期（NaT 自动忽略）
    dates = pd.to_datetime(valid["order_date"], errors="coerce").dropna()

    return {
        "order_count": order_count,
        "total_amount": total_amount,
        # 客单价 = 销售总额 / 订单数，保留 2 位小数
        "avg_order_amount": round(total_amount / order_count, 2),
        "province_count": int(valid["province"].nunique()),
        "date_start": (
            dates.min().strftime("%Y-%m-%d") if not dates.empty else ""
        ),
        "date_end": (
            dates.max().strftime("%Y-%m-%d") if not dates.empty else ""
        ),
    }


def get_admin_overview():
    """
    统计数据管理页顶部的整体概览指标，并组织为卡片列表

    指标清单：
        品类总数、商品总数、订单总数、销售总额、客单价、
        覆盖省份数、数据日期跨度

    实现方式：
        品类数与商品数直接取表记录数（无需聚合）；
        订单相关指标统一交给 _calc_order_metrics() 用 Pandas 计算。

    返回结构说明：
        统一返回「卡片字典列表」而非裸字典，
        这样模板只需一个 {% for %} 即可完成渲染，
        与首页 data_service.get_overview_cards() 的返回风格保持一致。

    :return: 卡片列表，每项含 key / label / text / unit 字段；
             text 为带千分位的展示文本
    """
    # 1. ORM 取出订单原始行（不做任何聚合）
    orders = SalesOrder.query.all()
    df_order = _build_dataframe([order.to_dict() for order in orders])

    # 2. Pandas 计算订单相关指标
    order_metrics = _calc_order_metrics(df_order)

    # 3. 品类数与商品数直接取记录数
    category_count = int(Category.query.count())
    product_count = int(Product.query.count())

    # 4. 日期跨度：有数据时展示起止日期，无数据时给出统一占位文案
    date_start = order_metrics["date_start"]
    date_end = order_metrics["date_end"]
    date_range = (
        "{} ~ {}".format(date_start, date_end) if date_start else "暂无数据"
    )

    return [
        {
            "key": "category_count",
            "label": "品类总数",
            "text": "{:,}".format(category_count),
            "unit": "个",
        },
        {
            "key": "product_count",
            "label": "商品总数",
            "text": "{:,}".format(product_count),
            "unit": "件",
        },
        {
            "key": "order_count",
            "label": "订单总数",
            "text": "{:,}".format(order_metrics["order_count"]),
            "unit": "笔",
        },
        {
            "key": "total_amount",
            "label": "销售总额",
            "text": "{:,.2f}".format(order_metrics["total_amount"]),
            "unit": "元",
        },
        {
            "key": "avg_order_amount",
            "label": "客单价",
            "text": "{:,.2f}".format(order_metrics["avg_order_amount"]),
            "unit": "元",
        },
        {
            "key": "province_count",
            "label": "覆盖省份数",
            "text": "{}".format(order_metrics["province_count"]),
            "unit": "个",
        },
        {
            "key": "date_range",
            "label": "数据日期跨度",
            "text": date_range,
            "unit": "",
        },
    ]


# ==================== 二、品类明细 ====================

def _attach_product_count(df_category, df_product):
    """
    为每个品类附加「商品数量」列（Pandas 分组计数）

    :param df_category: 品类 DataFrame
    :param df_product: 商品 DataFrame，可为空
    :return: 附加 product_count 列后的品类 DataFrame
    """
    if df_product.empty:
        # 无商品数据时，各品类商品数统一为 0
        df_category["product_count"] = 0
        return df_category

    # Pandas 按品类分组计数，得到每个品类下的商品数量
    product_count = (
        df_product.groupby("category_id")
        .size()
        .rename("product_count")
        .reset_index()
    )

    # 左连接保证「没有任何商品的品类」依然出现在结果中
    return df_category.merge(product_count, on="category_id", how="left")


def _attach_order_stat(df_category, df_order, df_product):
    """
    为每个品类附加「订单数量」与「销售额」列（Pandas 多表关联聚合）

    处理链路：
        订单表（含 product_id）与商品表（含 category_id）先做 merge，
        把订单归属到品类；再按品类分组聚合，得到订单数与销售额。

    :param df_category: 品类 DataFrame
    :param df_order: 订单 DataFrame，可为空
    :param df_product: 商品 DataFrame，可为空
    :return: 附加 order_count、total_amount 列后的品类 DataFrame
    """
    if df_order.empty or df_product.empty:
        df_category["order_count"] = 0
        df_category["total_amount"] = 0.0
        return df_category

    # 1. 金额列转数值并剔除无效记录
    df_order["total_amount"] = pd.to_numeric(
        df_order["total_amount"], errors="coerce"
    )
    valid_orders = df_order.dropna(subset=["total_amount"])
    valid_orders = valid_orders[valid_orders["total_amount"] >= 0]

    if valid_orders.empty:
        df_category["order_count"] = 0
        df_category["total_amount"] = 0.0
        return df_category

    # 2. 订单表关联商品表：为每笔订单补上其所属品类ID
    linked = valid_orders.merge(
        df_product[["product_id", "category_id"]],
        on="product_id",
        how="inner",
    )

    # 3. Pandas 分组聚合：同时统计订单笔数与金额合计
    order_stat = (
        linked.groupby("category_id")
        .agg(
            order_count=("order_id", "count"),
            total_amount=("total_amount", "sum"),
        )
        .reset_index()
    )

    return df_category.merge(order_stat, on="category_id", how="left")


def _fill_missing_number(df_category):
    """
    填充品类统计结果中的缺失值并统一字段类型

    说明：merge 使用左连接时，没有订单的品类对应统计列会是 NaN，
          直接渲染会出现「nan」字样，因此统一填充为 0。

    :param df_category: 已附加统计列的品类 DataFrame
    :return: 缺失值填充并类型转换后的 DataFrame
    """
    for column in ("product_count", "order_count"):
        if column in df_category.columns:
            df_category[column] = (
                df_category[column].fillna(0).astype(int)
            )

    if "total_amount" in df_category.columns:
        df_category["total_amount"] = (
            df_category["total_amount"].fillna(0.0).round(2)
        )

    return df_category


def get_category_rows(keyword="", page=1, per_page=DEFAULT_PER_PAGE,
                      sort_by="category_id", descending=True):
    """
    查询品类明细列表（含商品数、订单数、销售额与销售占比）

    处理流程：
        1. ORM 分别取出品类、商品、订单三张表的原始行；
        2. Pandas 统计每个品类的商品数量；
        3. Pandas 通过「订单 merge 商品」再分组，统计订单数与销售额；
        4. 计算销售额占比；
        5. 关键字筛选 → 排序 → 分页切片。

    :param keyword: 搜索关键字，对品类名称做模糊匹配；为空表示不筛选
    :param page: 当前页码，从 1 开始
    :param per_page: 每页条数，默认 10，上限 100
    :param sort_by: 排序列名，必须是白名单内的列名
    :param descending: 是否降序排列
    :return: (当前页记录列表, 分页信息字典) 元组
    """
    # 1. ORM 取出三张表的原始行（不做任何聚合）
    df_category = _build_dataframe(
        [item.to_dict() for item in Category.query.all()]
    )
    df_product = _build_dataframe(
        [item.to_dict() for item in Product.query.all()]
    )
    df_order = _build_dataframe(
        [item.to_dict() for item in SalesOrder.query.all()]
    )

    if df_category.empty:
        return [], build_empty_pagination(page, per_page)

    # 2. Pandas 统计各品类的商品数量
    df_category = _attach_product_count(df_category, df_product)

    # 3. Pandas 统计各品类的订单数量与销售额
    df_category = _attach_order_stat(df_category, df_order, df_product)

    # 4. 填充缺失的统计值并统一类型
    df_category = _fill_missing_number(df_category)

    # 5. Pandas 计算销售额占比
    df_category = _calc_amount_ratio(df_category, "total_amount")

    # 6. 关键字筛选：仅对品类名称做模糊匹配
    df_category = _filter_by_keyword(df_category, ["category_name"], keyword)

    # 7. 排序：排序列必须在白名单内，防止传入非法列名导致异常
    df_category = _sort_dataframe(
        df_category,
        sort_by,
        allowed_columns=["category_id", "category_name", "product_count",
                         "order_count", "total_amount"],
        default_column="category_id",
        descending=descending,
    )

    # 8. 分页切片并返回
    return _paginate_dataframe(df_category, page, per_page)


# ==================== 三、商品明细 ====================

def _attach_category_name(df_product, df_category):
    """
    为商品 DataFrame 附加「品类名称」列（Pandas 关联品类表）

    :param df_product: 商品 DataFrame
    :param df_category: 品类 DataFrame，可为空
    :return: 附加 category_name 列后的商品 DataFrame
    """
    if df_category.empty:
        df_product["category_name"] = ""
        return df_product

    return df_product.merge(
        df_category[["category_id", "category_name"]],
        on="category_id",
        how="left",
    )


def _attach_product_sales(df_product, df_order):
    """
    为每个商品附加「累计销量」与「累计销售额」列（Pandas 分组聚合）

    :param df_product: 商品 DataFrame
    :param df_order: 订单 DataFrame，可为空
    :return: 附加 total_quantity、total_amount 列后的商品 DataFrame
    """
    if df_order.empty:
        df_product["total_quantity"] = 0
        df_product["total_amount"] = 0.0
        return df_product

    # 1. 数量与金额列转数值
    df_order["quantity"] = pd.to_numeric(df_order["quantity"], errors="coerce")
    df_order["total_amount"] = pd.to_numeric(
        df_order["total_amount"], errors="coerce"
    )

    # 2. 剔除数量或金额缺失的异常记录
    valid_orders = df_order.dropna(subset=["quantity", "total_amount"])
    valid_orders = valid_orders[
        (valid_orders["quantity"] >= 1) & (valid_orders["total_amount"] >= 0)
    ]

    if valid_orders.empty:
        df_product["total_quantity"] = 0
        df_product["total_amount"] = 0.0
        return df_product

    # 3. Pandas 按商品ID分组，同时聚合销量与销售额
    sales_stat = (
        valid_orders.groupby("product_id")
        .agg(
            total_quantity=("quantity", "sum"),
            total_amount=("total_amount", "sum"),
        )
        .reset_index()
    )

    return df_product.merge(sales_stat, on="product_id", how="left")


def get_product_rows(keyword="", page=1, per_page=DEFAULT_PER_PAGE,
                     sort_by="product_id", descending=True):
    """
    查询商品明细列表（含品类名称、单价、累计销量与累计销售额）

    处理流程：
        1. ORM 取出商品、品类、订单三张表的原始行；
        2. Pandas 关联品类表，为每个商品补上品类名称；
        3. Pandas 按商品分组聚合，统计累计销量与累计销售额；
        4. 关键字筛选（商品名或品类名）→ 排序 → 分页切片。

    :param keyword: 搜索关键字，对商品名称与品类名称做模糊匹配
    :param page: 当前页码，从 1 开始
    :param per_page: 每页条数，默认 10，上限 100
    :param sort_by: 排序列名，必须是白名单内的列名
    :param descending: 是否降序排列
    :return: (当前页记录列表, 分页信息字典) 元组
    """
    # 1. ORM 取出三张表的原始行
    df_product = _build_dataframe(
        [item.to_dict() for item in Product.query.all()]
    )
    df_category = _build_dataframe(
        [item.to_dict() for item in Category.query.all()]
    )
    df_order = _build_dataframe(
        [item.to_dict() for item in SalesOrder.query.all()]
    )

    if df_product.empty:
        return [], build_empty_pagination(page, per_page)

    # 2. Pandas 关联品类表，补上品类名称
    df_product = _attach_category_name(df_product, df_category)

    # 3. Pandas 统计各商品的累计销量与累计销售额
    df_product = _attach_product_sales(df_product, df_order)

    # 4. 填充缺失值：无订单的商品销量与销售额为 0
    df_product["total_quantity"] = (
        df_product["total_quantity"].fillna(0).astype(int)
    )
    df_product["total_amount"] = (
        df_product["total_amount"].fillna(0.0).round(2)
    )
    df_product["category_name"] = (
        df_product["category_name"].fillna("未分类")
    )

    # 5. 关键字筛选：商品名称或品类名称命中即可
    df_product = _filter_by_keyword(
        df_product, ["product_name", "category_name"], keyword
    )

    # 6. 排序
    df_product = _sort_dataframe(
        df_product,
        sort_by,
        allowed_columns=["product_id", "product_name", "price",
                         "total_quantity", "total_amount"],
        default_column="product_id",
        descending=descending,
    )

    # 7. 分页切片并返回
    return _paginate_dataframe(df_product, page, per_page)


# ==================== 四、订单明细 ====================

def _attach_order_product(df_order, df_product, df_category):
    """
    为订单 DataFrame 附加「商品名称」与「品类名称」列（Pandas 两表关联）

    处理链路：
        订单表（含 product_id）先 merge 商品表得到商品名与品类ID，
        再 merge 品类表得到品类名称，形成完整的「订单 → 商品 → 品类」链路。

    :param df_order: 订单 DataFrame
    :param df_product: 商品 DataFrame，可为空
    :param df_category: 品类 DataFrame，可为空
    :return: 附加 product_name、category_name 列后的订单 DataFrame
    """
    if df_product.empty:
        df_order["product_name"] = ""
        df_order["category_name"] = ""
        return df_order

    # 第一次关联：订单 → 商品，得到商品名称与品类ID
    df_order = df_order.merge(
        df_product[["product_id", "product_name", "category_id"]],
        on="product_id",
        how="left",
    )

    if df_category.empty:
        df_order["category_name"] = ""
        return df_order

    # 第二次关联：商品 → 品类，得到品类名称
    return df_order.merge(
        df_category[["category_id", "category_name"]],
        on="category_id",
        how="left",
    )


def get_order_rows(keyword="", page=1, per_page=DEFAULT_PER_PAGE,
                   sort_by="order_id", descending=True):
    """
    查询订单明细列表（含商品名称、品类名称、地区与下单日期）

    处理流程：
        1. ORM 取出订单、商品、品类三张表的原始行；
        2. Pandas 两次 merge 补全商品名称与品类名称；
        3. 关键字筛选（商品名、品类、省份、城市）→ 排序 → 分页切片。

    :param keyword: 搜索关键字，对商品名、品类、省份、城市做模糊匹配
    :param page: 当前页码，从 1 开始
    :param per_page: 每页条数，默认 10，上限 100
    :param sort_by: 排序列名，必须是白名单内的列名
    :param descending: 是否降序排列
    :return: (当前页记录列表, 分页信息字典) 元组
    """
    # 1. ORM 取出三张表的原始行
    df_order = _build_dataframe(
        [item.to_dict() for item in SalesOrder.query.all()]
    )
    df_product = _build_dataframe(
        [item.to_dict() for item in Product.query.all()]
    )
    df_category = _build_dataframe(
        [item.to_dict() for item in Category.query.all()]
    )

    if df_order.empty:
        return [], build_empty_pagination(page, per_page)

    # 2. Pandas 关联商品表与品类表，补全名称字段
    df_order = _attach_order_product(df_order, df_product, df_category)

    # 3. 填充缺失值与金额精度处理
    df_order["product_name"] = df_order["product_name"].fillna("未知商品")
    df_order["category_name"] = df_order["category_name"].fillna("未分类")
    df_order["city"] = df_order["city"].fillna("")
    df_order["total_amount"] = (
        pd.to_numeric(df_order["total_amount"], errors="coerce")
        .fillna(0.0)
        .round(2)
    )

    # 4. 关键字筛选：商品名、品类、省份、城市任一命中即保留
    df_order = _filter_by_keyword(
        df_order,
        ["product_name", "category_name", "province", "city"],
        keyword,
    )

    # 5. 排序：默认按下单日期倒序，让最新订单排在最前
    df_order = _sort_dataframe(
        df_order,
        sort_by,
        allowed_columns=["order_id", "product_name", "quantity",
                         "total_amount", "province", "order_date"],
        default_column="order_id",
        descending=descending,
    )

    # 6. 分页切片并返回
    return _paginate_dataframe(df_order, page, per_page)


def build_empty_pagination(page, per_page):
    """
    构造「无数据」场景下的分页信息，保证前端分页器可正常渲染

    使用场景：
        1. 某张表本身没有任何记录；
        2. 查询过程抛出异常，路由层降级为空数据时。
    两种情况下前端都需要一份结构完整的分页信息才能正常渲染分页器。

    :param page: 当前页码
    :param per_page: 每页条数
    :return: 分页信息字典，total 为 0、has_prev / has_next 为 False
    """
    return {
        "page": _safe_int(page, MIN_PAGE, min_value=MIN_PAGE),
        "per_page": _safe_int(
            per_page, DEFAULT_PER_PAGE, min_value=1, max_value=MAX_PER_PAGE
        ),
        "total": 0,
        "total_pages": 1,
        "has_prev": False,
        "has_next": False,
    }
