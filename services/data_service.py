# -*- coding: utf-8 -*-
"""
业务逻辑层：销售数据统计服务。

功能说明：
    封装数据看板所需的全部统计计算逻辑，是 Pandas 数据处理的唯一归属地。

标准数据流（rule.md 铁则 4，必须严格遵守）：
    models 层 ORM 查询（仅取原始行，不做任何分组聚合）
        ↓
    df = pd.DataFrame([row.to_dict() for row in rows])
        ↓
    Pandas 完成：清洗（缺失值/异常值） → groupby 分组 → sum 求和
        ↓
    sort_values 排序 → head 取 TOP N → 字段重命名
        ↓
    转换为 Python 原生类型的 list[dict]，返回给 routes 层

    严禁使用 func.sum、GROUP BY 等 SQL 层聚合方式直接返回结果；
    ORM 只负责把原始行取出来，所有计算必须在 Pandas 中完成。

分层约定（rule.md 铁则 6）：
    本层不接触 request、jsonify 等 Flask 请求响应对象，
    所有对外接口统一返回纯 Python 数据结构（list / dict）。

创建日期：2026-10-17
"""

import pandas as pd

from models import db
from models.db_models import Category, Product, SalesOrder


# ==================== 私有工具函数 ====================

def _build_dataframe(records):
    """
    将字典记录列表转换为 DataFrame（ORM → Pandas 的统一入口）

    :param records: 字典记录列表，通常来自模型对象的 to_dict()
    :return: pandas.DataFrame；若传入空列表则返回空 DataFrame
    """
    if not records:
        # 返回空 DataFrame，交由调用方统一处理，避免后续 groupby 报错
        return pd.DataFrame()

    return pd.DataFrame(records)


def _clean_sales_dataframe(df):
    """
    对订单数据 DataFrame 执行统一的清洗流程

    清洗内容：
        1. 金额列强制转数值，无法转换的值置为 NaN（缺失值）；
        2. 数量列强制转数值，无法转换的值置为 NaN；
        3. 省份列去除首尾空格，空字符串 / 'nan' / 'None' 统一视为缺失值；
        4. 日期列统一转为 datetime 类型，非法日期置为 NaT。

    实现说明：
        函数开头先对入参做一次 copy()。这样做的原因是：
        调用方传入的可能是某个 DataFrame 的切片视图，
        直接对视图做列赋值会触发 pandas 的 SettingWithCopyWarning，
        且在 pandas 3.x 的 Copy-on-Write 模式下行为会发生变化。
        显式复制可以保证本函数的修改不会意外影响上游数据。

    :param df: 原始订单数据 DataFrame
    :return: 清洗后的 DataFrame 副本（不在此处删除行，由各统计函数按需 dropna）
    """
    # 先复制一份，避免在切片视图上就地修改带来的版本兼容问题
    df = df.copy()

    # 1. 金额列：errors="coerce" 会把无法解析的值统一置为 NaN
    if "total_amount" in df.columns:
        df["total_amount"] = pd.to_numeric(
            df["total_amount"], errors="coerce"
        )

    # 2. 数量列：同上处理
    if "quantity" in df.columns:
        df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce")

    # 3. 省份列：先转字符串并去空格，再把空值与占位字符串标记为缺失
    if "province" in df.columns:
        df["province"] = df["province"].astype("string").str.strip()
        df.loc[
            df["province"].isin(["", "nan", "None"]), "province"
        ] = pd.NA

    # 4. 日期列：统一转为 datetime，非法日期置为 NaT
    if "order_date" in df.columns:
        df["order_date"] = pd.to_datetime(
            df["order_date"], errors="coerce"
        )

    return df


def _filter_valid_amount(df):
    """
    剔除金额缺失或为负数的异常记录，保证统计口径准确

    :param df: 已完成清洗的 DataFrame
    :return: 仅保留金额有效（非缺失且 >= 0）记录的 DataFrame
    """
    # 先剔除金额缺失的记录
    df = df.dropna(subset=["total_amount"])
    # 再剔除金额为负的异常记录（如退款、脏数据）
    return df[df["total_amount"] >= 0]


def _to_records(
    df,
    label_column,
    value_column,
    label_field="name",
    value_field="value",
    value_type="float",
):
    """
    将 Pandas 聚合结果转换为接口约定的标准结构

    本函数同时完成三件事：
        1. 统一字段命名（如趋势图需要 date / sales，饼图需要 name / value）；
        2. 将 numpy 数值类型显式转换为 Python 原生类型——
           numpy.int64 并非 Python int 的子类，若不转换会导致
           jsonify 抛出「Object of type int64 is not JSON serializable」；
        3. 保证返回结构为 list[dict]，可直接被统一响应封装。

    :param df: 聚合结果 DataFrame
    :param label_column: df 中作为标签的列名
    :param value_column: df 中作为数值的列名
    :param label_field: 输出字典中的标签字段名，默认 "name"
    :param value_field: 输出字典中的数值字段名，默认 "value"
    :param value_type: 数值转换目标类型，"float"（保留 2 位小数）或 "int"
    :return: 形如 [{label_field: 标签, value_field: 数值}] 的列表
    """
    records = []

    # 空 DataFrame 兜底：直接返回空列表，避免后续 iterrows 产生隐式错误
    if df is None or df.empty:
        return records

    # iterrows 逐行遍历并在循环内完成原生类型转换，确保 JSON 可序列化
    for _, row in df.iterrows():
        if value_type == "int":
            value = int(row[value_column])
        else:
            value = round(float(row[value_column]), 2)

        records.append({
            label_field: str(row[label_column]),
            value_field: value,
        })

    return records


# ==================== 对外统计接口 ====================

def get_sales_by_province():
    """
    按省份统计销售额（降序排列）

    处理流程：
        1. ORM 查询 sales_order 全量原始行（不做任何分组聚合）；
        2. 转 DataFrame 后清洗缺失值与异常值；
        3. Pandas 按省份分组求和；
        4. 按销售额降序排列。

    :return: [{"name": 省份名称, "value": 销售额}, ...]，按 value 降序
    """
    # 1. ORM 只负责取出原始行数据
    orders = SalesOrder.query.all()
    df = _build_dataframe([order.to_dict() for order in orders])
    if df.empty:
        return []

    # 2. 数据清洗：统一类型、处理缺失值
    df = _clean_sales_dataframe(df)

    # 3. 剔除省份缺失的记录（省份是分组依据，缺失则无法归类）
    df = df.dropna(subset=["province"])

    # 4. 剔除金额缺失或为负的异常记录
    df = _filter_valid_amount(df)
    if df.empty:
        return []

    # 5. Pandas 聚合：按省份分组求和
    result = df.groupby("province", as_index=False)["total_amount"].sum()

    # 6. 按销售额降序排列
    result = result.sort_values("total_amount", ascending=False)

    # 7. 统一字段命名并转换为 Python 原生类型后返回
    return _to_records(result, "province", "total_amount")


def get_sales_trend():
    """
    按日期统计每日销售额（按日期升序排列）

    处理流程：
        1. ORM 查询 sales_order 全量原始行；
        2. 转 DataFrame 后清洗，日期列统一转为 datetime；
        3. Pandas 按日期分组求和；
        4. 补齐缺失日期（无订单的日期补 0），避免折线图跨过空白日；
        5. 按日期升序排列，保证折线图时间轴从左到右递增。

    缺失日期补零的必要性：
        groupby 只会返回「数据中真实出现过的日期」。
        若某一天没有任何订单，该日期不会出现在结果中，
        前端折线图会把这两天直接连起来，视觉上表现为「数据缺失」而非「销量为 0」，
        这是趋势图中非常隐蔽且容易被误判为 Bug 的问题。

    :return: [{"date": "YYYY-MM-DD", "sales": 当日销售额}, ...]，按 date 升序
    """
    # 1. ORM 取出原始行数据
    orders = SalesOrder.query.all()
    df = _build_dataframe([order.to_dict() for order in orders])
    if df.empty:
        return []

    # 2. 数据清洗：日期转 datetime，金额转数值
    df = _clean_sales_dataframe(df)

    # 3. 剔除日期或金额缺失的记录
    df = df.dropna(subset=["order_date", "total_amount"])

    # 4. 剔除金额为负的异常记录
    df = _filter_valid_amount(df)
    if df.empty:
        return []

    # 5. 提取日期字符串，避免 datetime 对象无法被 JSON 直接序列化
    df["date"] = df["order_date"].dt.strftime("%Y-%m-%d")

    # 6. Pandas 聚合：按日期分组求和
    result = df.groupby("date", as_index=False)["total_amount"].sum()

    # 7. 构造完整的日期区间，把没有订单的日期补齐为 0
    full_date_range = pd.date_range(
        start=df["order_date"].min(),
        end=df["order_date"].max(),
        freq="D",
    ).strftime("%Y-%m-%d")

    #    以日期为索引重新取样：原有日期保留原值，缺失日期填充 0.0
    result = (
        result.set_index("date")
        .reindex(full_date_range, fill_value=0.0)
        .rename_axis("date")
        .reset_index()
    )

    # 8. 按日期升序排列（字符串形式的 YYYY-MM-DD 字典序即时间序）
    result = result.sort_values("date", ascending=True)

    # 9. 统一字段命名（趋势图接口约定为 date / sales）
    return _to_records(
        result,
        label_column="date",
        value_column="total_amount",
        label_field="date",
        value_field="sales",
    )


def get_sales_by_category():
    """
    按品类统计销售额（用于品类占比饼图）

    处理流程：
        1. 通过 ORM 三表关联查询
           （sales_order JOIN product JOIN category）取出原始行；
        2. 转 DataFrame 后清洗缺失值与异常值；
        3. Pandas 按品类名称分组求和；
        4. 按销售额降序排列。

    :return: [{"name": 品类名称, "value": 销售额}, ...]，按 value 降序
    """
    # 1. ORM 三表关联查询：仅取统计所需的字段，不做任何聚合
    rows = (
        db.session.query(
            SalesOrder.order_id,
            SalesOrder.total_amount,
            Category.category_name,
        )
        # 订单表关联商品表
        .join(Product, SalesOrder.product_id == Product.product_id)
        # 商品表关联品类表
        .join(Category, Product.category_id == Category.category_id)
        .all()
    )

    # 关联查询返回的是 Row 对象，此处显式构造字典列表后再转 DataFrame
    df = _build_dataframe([
        {
            "order_id": row.order_id,
            "total_amount": row.total_amount,
            "category_name": row.category_name,
        }
        for row in rows
    ])
    if df.empty:
        return []

    # 2. 数据清洗
    df = _clean_sales_dataframe(df)

    # 3. 剔除品类缺失的记录
    df = df.dropna(subset=["category_name"])

    # 4. 剔除金额缺失或为负的异常记录
    df = _filter_valid_amount(df)
    if df.empty:
        return []

    # 5. Pandas 聚合：按品类分组求和
    result = df.groupby("category_name", as_index=False)["total_amount"].sum()

    # 6. 按销售额降序排列
    result = result.sort_values("total_amount", ascending=False)

    # 7. 统一字段命名后返回
    return _to_records(result, "category_name", "total_amount")


def get_top_products(limit=10):
    """
    统计销量 TOP N 商品（降序排列）

    处理流程：
        1. 通过 ORM 两表关联查询（sales_order JOIN product）取出原始行；
        2. 转 DataFrame 后清洗，剔除数量缺失或非正的异常记录；
        3. Pandas 按商品分组求和得到累计销量；
        4. 按销量降序排列后取前 limit 条。

    分组依据说明：
        这里同时按 product_id 与 product_name 分组，而不是只按商品名分组。
        若只按名称分组，当数据库中存在同名商品时，
        Pandas 会把它们的销量错误地合并成一条记录。

    :param limit: 返回的商品数量，默认取前 10 名
    :return: [{"name": 商品名称, "value": 累计销量}, ...]，按 value 降序
    """
    # 1. ORM 两表关联查询：取出商品 ID、商品名称与购买数量
    rows = (
        db.session.query(
            SalesOrder.order_id,
            SalesOrder.quantity,
            Product.product_id,
            Product.product_name,
        )
        .join(Product, SalesOrder.product_id == Product.product_id)
        .all()
    )

    df = _build_dataframe([
        {
            "order_id": row.order_id,
            "quantity": row.quantity,
            "product_id": row.product_id,
            "product_name": row.product_name,
        }
        for row in rows
    ])
    if df.empty:
        return []

    # 2. 数据清洗
    df = _clean_sales_dataframe(df)

    # 3. 剔除商品名称或数量缺失的记录
    df = df.dropna(subset=["product_name", "quantity"])

    # 4. 剔除数量非正的异常记录（购买数量必须 >= 1）
    df = df[df["quantity"] >= 1]
    if df.empty:
        return []

    # 5. Pandas 聚合：按商品 ID 与名称分组求和，得到每个商品的累计销量
    result = df.groupby(
        ["product_id", "product_name"], as_index=False
    )["quantity"].sum()

    # 6. 按销量降序排列后取前 limit 条
    result = result.sort_values("quantity", ascending=False).head(limit)

    # 7. 统一字段命名；销量为整数，使用 int 类型转换
    return _to_records(result, "product_name", "quantity", value_type="int")


def get_overview_cards():
    """
    计算首页顶部 4 个数据卡片的指标值

    卡片口径：
        总销售额   订单金额合计（剔除缺失与负值后求和）
        总订单量   有效订单行数
        商品总数   product 表记录数
        覆盖省份数 订单中出现的省份去重计数

    :return: 卡片字典列表，每项含 key / label / value / text / unit 字段；
             text 为带千分位的展示文本，便于模板直接渲染
    """
    # 1. ORM 取出订单原始行
    orders = SalesOrder.query.all()
    df = _build_dataframe([order.to_dict() for order in orders])

    if df.empty:
        total_sales = 0.0
        total_orders = 0
        province_count = 0
    else:
        # 2. 清洗后剔除无效金额记录，保证卡片口径与统计接口一致
        df = _clean_sales_dataframe(df)
        df = _filter_valid_amount(df)

        # 3. Pandas 计算：金额求和、行数统计、省份去重计数
        total_sales = round(float(df["total_amount"].sum()), 2)
        total_orders = int(len(df))
        # nunique() 默认忽略缺失值，与「剔除省份缺失记录」的口径一致
        province_count = int(df["province"].nunique())

    # 4. 商品总数直接取自商品表记录数
    product_count = int(Product.query.count())

    return [
        {
            "key": "total_sales",
            "label": "总销售额",
            "value": total_sales,
            "text": "{:,.2f}".format(total_sales),
            "unit": "元",
        },
        {
            "key": "total_orders",
            "label": "总订单量",
            "value": total_orders,
            "text": "{:,}".format(total_orders),
            "unit": "笔",
        },
        {
            "key": "product_count",
            "label": "商品总数",
            "value": product_count,
            "text": "{:,}".format(product_count),
            "unit": "件",
        },
        {
            "key": "province_count",
            "label": "覆盖省份数",
            "value": province_count,
            "text": "{}".format(province_count),
            "unit": "个",
        },
    ]
