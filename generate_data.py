# -*- coding: utf-8 -*-
"""
模拟数据生成脚本。

功能说明：
    向 MySQL 数据库写入一套「分布合理、高低区分明显」的模拟业务数据，
    为数据可视化看板提供数据源。

生成规模（均可通过命令行参数覆盖）：
    品类   5 条
    商品   20 条
    订单   1500 条

数据分布设计（不使用任何硬编码的业务记录）：
    1. 商品数量：每个品类先保底 1 个商品，剩余名额按随机权重分配，
                各品类商品数量有明显差异，不做平均分配；
    2. 商品热度：为每个商品生成幂律分布的随机权重，
                形成「爆款商品」与「滞销商品」的明显区分；
    3. 商品单价：按所属品类的价格区间随机生成，不同品类价位带不同；
    4. 省份分布：全国 31 个省份按幂律权重抽样，区域销量高低差异明显；
    5. 时间分布：覆盖最近 3 个月，整体呈缓慢增长趋势，周末订单量上浮；
    6. 购买数量：1~10 件，取值越小概率越高，符合真实购买习惯。

    上述所有权重均由随机数生成；固定随机种子保证多次生成结果可复现。

使用方式：
    python generate_data.py                 # 使用默认配置生成
    python generate_data.py --seed 2024     # 指定随机种子
    python generate_data.py --orders 3000   # 指定订单数量
    python generate_data.py --keep          # 保留已有数据（追加模式）

注意事项：
    1. 默认会先清空三张业务表（sales_order / product / category）再重新生成；
       如需保留原数据请加 --keep 参数；
    2. 本脚本**不会**触碰 user 认证表，
       因此重复生成数据不会影响已有的登录账号；
    3. 清空数据时必须按外键逆序删除：sales_order → product → category，
       否则会触发外键约束错误；
    4. 运行前请确保 MySQL 已启动，且已创建 ecommerce_db 数据库：
           CREATE DATABASE ecommerce_db CHARACTER SET utf8mb4;

创建日期：2026-10-17
"""

import argparse
import random
from datetime import date, timedelta

from app import create_app
from models import db
from models.db_models import Category, Product, SalesOrder

# ==================== 基础配置常量 ====================

# 默认随机种子：固定种子可保证多次生成的数据完全一致（结果可复现）
DEFAULT_SEED = 42

# 默认生成规模
CATEGORY_COUNT = 5
PRODUCT_COUNT = 20
ORDER_COUNT = 1500

# 订单日期窗口：最近 3 个月（按 90 天计算）
DATE_WINDOW_DAYS = 90

# 5 个品类名称
CATEGORY_NAMES = ["手机", "电脑", "服装", "食品", "家居"]

# 各品类的商品名称关键词：用于随机拼接商品名称，保证名称与品类语义相符
PRODUCT_KEYWORDS = {
    "手机": ["智能手机", "折叠屏手机", "影像旗舰", "轻薄手机", "游戏手机"],
    "电脑": ["轻薄笔记本", "高性能游戏本", "一体机", "台式主机", "便携平板"],
    "服装": ["加绒羽绒服", "三合一冲锋衣", "休闲卫衣", "直筒牛仔裤", "针织衫"],
    "食品": ["每日坚果礼盒", "冻干咖啡", "海盐苏打饼", "黑巧克力", "手撕牛肉干"],
    "家居": ["记忆棉枕", "实木餐桌", "全棉四件套", "落地收纳柜", "香薰助眠灯"],
}

# 各品类的单价区间（单位：元）：使不同品类的价格带具备明显区分
CATEGORY_PRICE_RANGE = {
    "手机": (999.0, 7999.0),
    "电脑": (2999.0, 12999.0),
    "服装": (59.0, 899.0),
    "食品": (9.9, 299.0),
    "家居": (99.0, 2999.0),
}

# 虚构品牌名称：用于拼接商品名称，避免使用真实商标
BRAND_NAMES = [
    "星辰", "云驰", "极光", "瀚海", "苍岭", "风行", "方圆", "青柠",
]

# 商品型号后缀：随机拼接在商品名称末尾，增强商品名称的真实感
MODEL_SUFFIXES = [
    "", " Pro", " Max", " Air", " Plus", " 青春版", " 旗舰版",
]

# 购买数量的可选值
QUANTITY_CHOICES = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]

# 购买数量对应的权重：数量越小概率越高，符合真实购买习惯
QUANTITY_WEIGHTS = [30, 20, 14, 10, 7, 6, 5, 4, 3, 2]

# 全国 31 个省份（不含港澳台）及其代表城市，
# 用于随机生成订单的收货地区；城市从对应省份的列表中随机抽取
PROVINCE_CITIES = {
    "北京市": ["北京市"],
    "天津市": ["天津市"],
    "上海市": ["上海市"],
    "重庆市": ["重庆市"],
    "河北省": ["石家庄市", "唐山市", "保定市", "邯郸市"],
    "山西省": ["太原市", "大同市", "临汾市", "运城市"],
    "内蒙古自治区": ["呼和浩特市", "包头市", "鄂尔多斯市"],
    "辽宁省": ["沈阳市", "大连市", "鞍山市", "锦州市"],
    "吉林省": ["长春市", "吉林市", "延吉市", "四平市"],
    "黑龙江省": ["哈尔滨市", "大庆市", "齐齐哈尔市"],
    "江苏省": ["南京市", "苏州市", "无锡市", "南通市", "徐州市"],
    "浙江省": ["杭州市", "宁波市", "温州市", "嘉兴市"],
    "安徽省": ["合肥市", "芜湖市", "阜阳市", "安庆市"],
    "福建省": ["福州市", "厦门市", "泉州市", "漳州市"],
    "江西省": ["南昌市", "赣州市", "九江市", "上饶市"],
    "山东省": ["济南市", "青岛市", "烟台市", "潍坊市", "临沂市"],
    "河南省": ["郑州市", "洛阳市", "南阳市", "新乡市"],
    "湖北省": ["武汉市", "宜昌市", "襄阳市", "荆州市"],
    "湖南省": ["长沙市", "株洲市", "岳阳市", "衡阳市"],
    "广东省": ["广州市", "深圳市", "东莞市", "佛山市", "珠海市"],
    "广西壮族自治区": ["南宁市", "柳州市", "桂林市"],
    "海南省": ["海口市", "三亚市"],
    "四川省": ["成都市", "绵阳市", "德阳市", "宜宾市"],
    "贵州省": ["贵阳市", "遵义市", "六盘水市"],
    "云南省": ["昆明市", "大理市", "曲靖市"],
    "西藏自治区": ["拉萨市", "日喀则市"],
    "陕西省": ["西安市", "宝鸡市", "咸阳市", "渭南市"],
    "甘肃省": ["兰州市", "天水市", "酒泉市"],
    "青海省": ["西宁市", "海东市"],
    "宁夏回族自治区": ["银川市", "吴忠市"],
    "新疆维吾尔自治区": ["乌鲁木齐市", "喀什市", "伊宁市"],
}


# ==================== 工具函数 ====================

def build_weighted_pool(items, power=3.0, base=0.02):
    """
    为一组元素生成「幂律分布」的随机权重，形成明显的高低区分

    实现思路：
        1. 先为每个元素生成一个 [0, 1) 区间内的随机数；
        2. 对其求 power 次幂，幂次越大部分元素衰减越明显，
           从而拉开头部元素与尾部元素的差距；
        3. 最后统一加上 base，保证每个元素都有被抽中的机会。

    :param items: 需要生成权重的元素列表
    :param power: 幂次，值越大头部与尾部的差异越明显
    :param base: 权重基数，避免尾部元素权重为 0
    :return: 与 items 等长的权重列表（未归一化，可直接交给 random.choices）
    """
    return [random.random() ** power + base for _ in items]


def build_product_name(keywords, used_names):
    """
    随机拼接商品名称，并保证同一批次内名称不重复

    拼接规则：品牌名 + 品类关键词 + 型号后缀

    :param keywords: 该品类下的商品关键词列表
    :param used_names: 已使用的商品名称集合，用于去重
    :return: 商品名称字符串
    """
    # 最多尝试 50 次随机拼接，正常情况下足以生成不重复的名称
    for _ in range(50):
        name = "{}{}{}".format(
            random.choice(BRAND_NAMES),
            random.choice(keywords),
            random.choice(MODEL_SUFFIXES),
        )
        if name not in used_names:
            used_names.add(name)
            return name

    # 极端兜底：追加随机编号，确保名称唯一
    name = "{}{}-{}".format(
        random.choice(BRAND_NAMES),
        random.choice(keywords),
        random.randint(100, 999),
    )
    used_names.add(name)
    return name


# ==================== 数据生成函数 ====================

def generate_categories(category_names):
    """
    批量创建品类数据

    :param category_names: 品类名称列表
    :return: 已写入会话的 Category 对象列表
    """
    categories = [Category(category_name=name) for name in category_names]

    db.session.add_all(categories)
    # flush 会立即执行 INSERT 语句，从而在后续步骤中
    # 能够拿到数据库自增生成的 category_id
    db.session.flush()

    return categories


def generate_products(categories, product_count):
    """
    批量创建商品数据

    分配规则：
        1. 每个品类先保底分配 1 个商品；
        2. 剩余名额按随机权重分配给各品类，使各品类商品数量不平均；
        3. 商品单价在所属品类的价格区间内随机生成。

    :param categories: 已创建的 Category 对象列表
    :param product_count: 需要生成的商品总数
    :return: Product 对象列表（尚未提交，需由调用方 add_all 后 flush）
    """
    # 第一步：每个品类保底 1 个商品
    quota_map = {category.category_id: 1 for category in categories}

    # 第二步：剩余名额按幂律权重随机分配，体现品类之间的商品数量差异
    rest_count = product_count - len(categories)
    if rest_count > 0:
        weights = build_weighted_pool(categories, power=1.5, base=0.25)
        chosen = random.choices(categories, weights=weights, k=rest_count)
        for category in chosen:
            quota_map[category.category_id] += 1

    # 第三步：按配额逐个生成商品
    products = []
    used_names = set()

    for category in categories:
        # 取该品类对应的价格区间与商品关键词
        price_low, price_high = CATEGORY_PRICE_RANGE[category.category_name]
        keywords = PRODUCT_KEYWORDS[category.category_name]

        for _ in range(quota_map[category.category_id]):
            products.append(
                Product(
                    product_name=build_product_name(keywords, used_names),
                    category_id=category.category_id,
                    price=round(random.uniform(price_low, price_high), 2),
                )
            )

    return products


def generate_orders(products, order_count, end_date, window_days):
    """
    批量创建订单数据

    :param products: 已创建的 Product 对象列表
    :param order_count: 需要生成的订单总数
    :param end_date: 日期窗口的结束日（通常为今天）
    :param window_days: 日期窗口天数（最近 N 天）
    :return: SalesOrder 对象列表（尚未提交，需由调用方 add_all 后 commit）
    """
    # 商品热度权重：幂律分布，形成爆款与滞销商品的明显区分
    product_weights = build_weighted_pool(products, power=2.5, base=0.03)

    # 省份热度权重：幂律分布，形成明显的区域销量差异
    provinces = list(PROVINCE_CITIES.keys())
    province_weights = build_weighted_pool(provinces, power=2.0, base=0.05)

    # 日期权重：整体缓慢增长 + 周末订单量上浮，使趋势图更贴近真实业务
    start_date = end_date - timedelta(days=window_days - 1)
    date_list = []
    date_weights = []
    for offset in range(window_days):
        current_date = start_date + timedelta(days=offset)

        # 时间越靠后，权重越高，形成整体缓慢增长的趋势
        weight = 1.0 + 0.6 * (offset / max(window_days - 1, 1))

        # 周六、周日订单量上浮 35%
        if current_date.weekday() >= 5:
            weight *= 1.35

        date_list.append(current_date)
        date_weights.append(weight)

    # 逐条生成订单
    orders = []
    for _ in range(order_count):
        product = random.choices(products, weights=product_weights, k=1)[0]
        province = random.choices(provinces, weights=province_weights, k=1)[0]
        city = random.choice(PROVINCE_CITIES[province])
        quantity = random.choices(
            QUANTITY_CHOICES, weights=QUANTITY_WEIGHTS, k=1
        )[0]
        order_date = random.choices(date_list, weights=date_weights, k=1)[0]

        orders.append(
            SalesOrder(
                product_id=product.product_id,
                quantity=quantity,
                # 订单金额 = 商品单价 × 购买数量，保留 2 位小数
                total_amount=round(product.price * quantity, 2),
                province=province,
                city=city,
                order_date=order_date,
            )
        )

    return orders


def clear_existing_data():
    """
    清空三张表中的已有数据

    说明：
        必须按照「外键依赖的逆序」删除：先删订单（依赖商品），
        再删商品（依赖品类），最后删品类，否则会触发外键约束错误。

    :return: None
    """
    SalesOrder.query.delete()
    Product.query.delete()
    Category.query.delete()
    db.session.commit()


def print_summary(orders):
    """
    在控制台输出本次生成结果的统计摘要，便于人工核对数据分布

    说明：
        此处仅为「数据生成结果的校验输出」，
        项目中的业务统计一律在 services 层使用 Pandas 完成。

    :param orders: 已生成的 SalesOrder 对象列表
    :return: None
    """
    # 使用字典累加统计各省份销售额
    province_sales = {}
    total_amount = 0.0
    date_set = set()

    for order in orders:
        province_sales[order.province] = (
            province_sales.get(order.province, 0.0) + order.total_amount
        )
        total_amount += order.total_amount
        date_set.add(order.order_date)

    # 按销售额降序排列
    top_provinces = sorted(
        province_sales.items(), key=lambda item: item[1], reverse=True
    )

    print("\n" + "=" * 56)
    print("模拟数据生成完成")
    print("=" * 56)
    print("订单数量    : {} 条".format(len(orders)))
    print("覆盖省份    : {} 个".format(len(province_sales)))
    print("覆盖日期    : {} 天（{} ~ {}）".format(
        len(date_set), min(date_set), max(date_set)
    ))
    print("销售总额    : {:,.2f} 元".format(total_amount))
    print("-" * 56)
    print("省份销售额 TOP5：")
    for name, amount in top_provinces[:5]:
        print("    {:<12} {:>12,.2f} 元".format(name, amount))
    print("省份销售额 后5位：")
    for name, amount in top_provinces[-5:]:
        print("    {:<12} {:>12,.2f} 元".format(name, amount))
    print("=" * 56 + "\n")


# ==================== 命令行与入口 ====================

def parse_args():
    """
    解析命令行参数，支持灵活调整生成规模与随机种子

    :return: 解析后的参数对象
    """
    parser = argparse.ArgumentParser(
        description="生成电商销售平台的模拟测试数据"
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help="随机种子，默认为 {}，固定种子可复现生成结果".format(
            DEFAULT_SEED
        ),
    )
    parser.add_argument(
        "--categories",
        type=int,
        default=CATEGORY_COUNT,
        help="品类数量，默认为 {}".format(CATEGORY_COUNT),
    )
    parser.add_argument(
        "--products",
        type=int,
        default=PRODUCT_COUNT,
        help="商品数量，默认为 {}".format(PRODUCT_COUNT),
    )
    parser.add_argument(
        "--orders",
        type=int,
        default=ORDER_COUNT,
        help="订单数量，默认为 {}".format(ORDER_COUNT),
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help="保留已有数据（默认会先清空三张表再生成）",
    )
    return parser.parse_args()


def main():
    """
    脚本主流程：建表 → 清空旧数据 → 生成品类 → 生成商品 → 生成订单 → 输出摘要

    :return: None
    """
    args = parse_args()

    # 校验品类数量：不能超过预置品类名称的数量
    if not 1 <= args.categories <= len(CATEGORY_NAMES):
        print("错误：品类数量取值范围为 1 ~ {}".format(len(CATEGORY_NAMES)))
        return

    # 固定随机种子，保证生成结果可复现
    random.seed(args.seed)

    # 创建应用（内部会自动完成建表），并进入应用上下文操作数据库
    app = create_app()

    with app.app_context():
        try:
            # 默认先清空历史数据，避免重复生成导致数据叠加
            if not args.keep:
                clear_existing_data()

            # 1. 生成品类
            categories = generate_categories(CATEGORY_NAMES[:args.categories])

            # 2. 生成商品：add_all 后 flush，以便订单能拿到自增 product_id
            products = generate_products(categories, args.products)
            db.session.add_all(products)
            db.session.flush()

            # 3. 生成订单
            orders = generate_orders(
                products=products,
                order_count=args.orders,
                end_date=date.today(),
                window_days=DATE_WINDOW_DAYS,
            )
            db.session.add_all(orders)

            # 4. 统一提交事务
            db.session.commit()
        except Exception as exc:  # NOQA: BLE001
            # 发生异常时回滚事务，避免脏数据残留，并给出明确的排查指引
            db.session.rollback()
            print("数据生成失败，事务已回滚。错误信息：{}".format(exc))
            print("请依次检查：")
            print("    1) MySQL 服务是否已启动；")
            print("    2) .env 中的 DB_USER / DB_PASSWORD 是否正确；")
            print("    3) ecommerce_db 数据库是否已创建。")
            return

        print(
            "品类 {} 条、商品 {} 条、订单 {} 条已写入数据库".format(
                len(categories), len(products), len(orders)
            )
        )

        # 5. 输出生成结果的统计摘要
        print_summary(orders)


if __name__ == "__main__":
    main()
