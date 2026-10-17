# -*- coding: utf-8 -*-
"""
业务逻辑层包。

功能说明：
    封装「数据获取 → 清洗 → 聚合 → 计算」的完整业务流程，
    是 Pandas 统计计算的唯一归属地（rule.md 铁则 4）。

标准数据流（必须严格遵守）：
    models 层 ORM 查询（仅取原始行，不做任何分组聚合）
        ↓
    df = pd.DataFrame([row.to_dict() for row in rows])
        ↓
    Pandas 完成清洗 / groupby / sum / sort_values / head 等操作
        ↓
    df 转换为 Python 原生类型的 list[dict]
        ↓
    返回给 routes 层封装为统一 JSON 响应

分层约定（rule.md 铁则 6）：
    本层禁止直接操作 request、jsonify 等 Flask 请求响应对象；
    所有对外接口统一以「纯 Python 数据结构（list / dict）」返回。

模块清单：
    data_service.py   销售数据统计服务（面向数据看板首页），对外接口：
        get_sales_by_province()  按省份统计销售额（降序）
        get_sales_trend()        按日期统计每日销售额（升序，缺失日期补 0）
        get_sales_by_category()  按品类统计销售额（三表关联，降序）
        get_top_products(limit)  统计销量 TOP N 商品（降序）
        get_overview_cards()     计算首页顶部 4 个数据卡片指标

    admin_service.py  管理员数据管理服务（面向「数据管理」页），对外接口：
        get_admin_overview()     统计数据管理页顶部的 7 个概览指标卡片
        get_category_rows()      品类明细：商品数 / 订单数 / 销售额 / 占比
        get_product_rows()       商品明细：品类名称 / 累计销量 / 累计销售额
        get_order_rows()         订单明细：商品名称 / 品类 / 地区 / 下单日期
        build_empty_pagination() 构造无数据场景下的分页信息

        以上三个明细查询均支持关键字搜索、按列排序与分页，
        排序与分页同样在 Pandas 中完成（详见各函数文档字符串）。

创建日期：2026-10-17
"""
