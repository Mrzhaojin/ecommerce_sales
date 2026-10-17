# -*- coding: utf-8 -*-
"""
数据模型模块：定义电商销售平台的核心数据表。

表结构清单：
    Category    品类表 category      存储商品品类信息
    Product     商品表 product       存储商品信息
    SalesOrder  订单表 sales_order   存储销售订单信息
    User        用户表 user          存储登录账号与角色信息

关联关系（支持多表关联查询）：
    Category (1) ──< (N) Product (1) ──< (N) SalesOrder

    一个品类包含多个商品：category.category_id = product.category_id
    一个商品对应多笔订单：product.product_id   = sales_order.product_id

    借助上述链式关联，可一次查询出「订单 → 商品 → 品类」的完整链路，
    为品类销售额占比统计（需三表关联）提供数据基础。

分层约定（rule.md 铁则 6）：
    本模块只负责「表结构定义」与「行数据序列化（to_dict）」，
    禁止编写任何业务流程与统计聚合逻辑；
    所有统计计算统一交给 services 层使用 Pandas 完成。

创建日期：2026-10-17
"""

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from . import db


class Category(db.Model):
    """
    品类表模型：存储商品品类信息（如手机、电脑、服装、食品、家居）。
    """

    # 数据库表名
    __tablename__ = "category"

    # 表级参数：显式指定存储引擎与字符集，保证中文正常存储
    __table_args__ = {
        "mysql_engine": "InnoDB",
        "mysql_charset": "utf8mb4",
    }

    # ---------------- 字段定义 ----------------
    # 品类ID：主键，整数自增
    category_id = db.Column(
        db.Integer,
        primary_key=True,
        autoincrement=True,
        comment="品类ID，主键，自增",
    )

    # 品类名称：非空且唯一，避免出现重复品类
    category_name = db.Column(
        db.String(50),
        nullable=False,
        unique=True,
        comment="品类名称，非空且唯一",
    )

    # ---------------- 关联关系 ----------------
    # 一对多：一个品类下可以包含多个商品。
    # backref="category" 会在 Product 实例上自动生成反向引用属性，
    # 即通过 product.category 可直接访问该商品所属的品类对象。
    # lazy="select" 表示访问该属性时才发起查询，避免不必要的数据加载。
    products = db.relationship(
        "Product",
        backref="category",
        lazy="select",
        cascade="all, delete-orphan",
    )

    def to_dict(self):
        """
        将品类对象转换为字典，便于后续交给 Pandas 构造 DataFrame

        :return: 包含品类各字段的字典
        """
        return {
            "category_id": self.category_id,
            "category_name": self.category_name,
        }

    def __repr__(self):
        """
        返回对象的可读字符串，便于调试与日志输出

        :return: 形如 <Category 1:手机> 的字符串
        """
        return "<Category {}:{}>".format(
            self.category_id,
            self.category_name,
        )


class Product(db.Model):
    """
    商品表模型：存储商品信息，通过外键关联所属品类。
    """

    # 数据库表名
    __tablename__ = "product"

    # 表级参数：显式指定存储引擎与字符集，保证中文正常存储
    __table_args__ = {
        "mysql_engine": "InnoDB",
        "mysql_charset": "utf8mb4",
    }

    # ---------------- 字段定义 ----------------
    # 商品ID：主键，整数自增
    product_id = db.Column(
        db.Integer,
        primary_key=True,
        autoincrement=True,
        comment="商品ID，主键，自增",
    )

    # 商品名称：非空
    product_name = db.Column(
        db.String(100),
        nullable=False,
        comment="商品名称，非空",
    )

    # 品类ID：外键，关联 category.category_id
    category_id = db.Column(
        db.Integer,
        db.ForeignKey("category.category_id"),
        nullable=False,
        comment="品类ID，外键，关联 category.category_id",
    )

    # 商品单价：非空（浮点类型，保留 2 位小数）
    price = db.Column(
        db.Float,
        nullable=False,
        comment="商品单价，非空",
    )

    # ---------------- 关联关系 ----------------
    # 一对多：一个商品可以对应多笔订单。
    # backref="product" 会在 SalesOrder 实例上自动生成反向引用属性，
    # 即通过 order.product 可直接访问该订单对应的商品对象。
    orders = db.relationship(
        "SalesOrder",
        backref="product",
        lazy="select",
        cascade="all, delete-orphan",
    )

    def to_dict(self):
        """
        将商品对象转换为字典，便于后续交给 Pandas 构造 DataFrame

        :return: 包含商品各字段的字典
        """
        return {
            "product_id": self.product_id,
            "product_name": self.product_name,
            "category_id": self.category_id,
            "price": float(self.price) if self.price is not None else 0.0,
        }

    def __repr__(self):
        """
        返回对象的可读字符串，便于调试与日志输出

        :return: 形如 <Product 1:星辰智能手机> 的字符串
        """
        return "<Product {}:{}>".format(
            self.product_id,
            self.product_name,
        )


class SalesOrder(db.Model):
    """
    订单表模型：存储每一笔销售订单的核心信息，通过外键关联商品。
    """

    # 数据库表名
    __tablename__ = "sales_order"

    # 表级参数：显式指定存储引擎与字符集，保证中文正常存储
    __table_args__ = {
        "mysql_engine": "InnoDB",
        "mysql_charset": "utf8mb4",
    }

    # ---------------- 字段定义 ----------------
    # 订单ID：主键，整数自增
    order_id = db.Column(
        db.Integer,
        primary_key=True,
        autoincrement=True,
        comment="订单ID，主键，自增",
    )

    # 商品ID：外键，关联 product.product_id
    product_id = db.Column(
        db.Integer,
        db.ForeignKey("product.product_id"),
        nullable=False,
        comment="商品ID，外键，关联 product.product_id",
    )

    # 购买数量：非空整数
    quantity = db.Column(
        db.Integer,
        nullable=False,
        comment="购买数量，非空",
    )

    # 订单总金额：非空（浮点类型，保留 2 位小数）
    total_amount = db.Column(
        db.Float,
        nullable=False,
        comment="订单总金额，非空",
    )

    # 省份：非空，用于省份维度统计
    province = db.Column(
        db.String(50),
        nullable=False,
        comment="省份，非空",
    )

    # 城市：可为空
    city = db.Column(
        db.String(50),
        nullable=True,
        comment="城市",
    )

    # 下单日期：非空，建立了普通索引以加速按日期的趋势统计查询
    order_date = db.Column(
        db.Date,
        nullable=False,
        index=True,
        comment="下单日期，非空",
    )

    def to_dict(self):
        """
        将订单对象转换为字典，便于后续交给 Pandas 构造 DataFrame

        说明：
            日期统一转换为 "YYYY-MM-DD" 格式的字符串，
            金额统一转换为 float，避免 DataFrame 中出现混合类型。

        :return: 包含订单各字段的字典
        """
        return {
            "order_id": self.order_id,
            "product_id": self.product_id,
            "quantity": self.quantity,
            "total_amount": (
                float(self.total_amount) if self.total_amount else 0.0
            ),
            "province": self.province,
            "city": self.city,
            "order_date": (
                self.order_date.strftime("%Y-%m-%d")
                if self.order_date
                else None
            ),
        }

    def __repr__(self):
        """
        返回对象的可读字符串，便于调试与日志输出

        :return: 形如 <SalesOrder 1:广东省-3件> 的字符串
        """
        return "<SalesOrder {}:{}-{}件>".format(
            self.order_id,
            self.province,
            self.quantity,
        )


class User(UserMixin, db.Model):
    """
    用户表模型：存储登录账号信息，用于身份认证与角色权限控制。

    设计说明：
        1. 密码字段只存哈希值（password_hash），任何情况下都不保存明文；
        2. 本项目不提供注册功能，账号由系统在首次启动时自动初始化；
        3. 继承 UserMixin 以接入 Flask-Login，
           由于主键名为 user_id 而非默认的 id，需重写 get_id() 方法。
    """

    # 数据库表名
    __tablename__ = "user"

    # 表级参数：显式指定存储引擎与字符集，保证中文正常存储
    __table_args__ = {
        "mysql_engine": "InnoDB",
        "mysql_charset": "utf8mb4",
    }

    # ---------------- 角色枚举常量 ----------------
    # 管理员：可访问管理类页面与接口
    ROLE_ADMIN = "admin"
    # 普通用户：仅可访问查询类页面与接口
    ROLE_USER = "user"

    # ---------------- 字段定义 ----------------
    # 用户ID：主键，整数自增
    user_id = db.Column(
        db.Integer,
        primary_key=True,
        autoincrement=True,
        comment="用户ID，主键，自增",
    )

    # 用户名：非空且唯一，作为登录账号
    username = db.Column(
        db.String(50),
        nullable=False,
        unique=True,
        comment="用户名，非空且唯一",
    )

    # 密码哈希：非空，由 werkzeug.security 生成，禁止存储明文密码
    password_hash = db.Column(
        db.String(255),
        nullable=False,
        comment="密码哈希值，非空，禁止明文存储",
    )

    # 角色：非空，取值限定为 admin / user
    role = db.Column(
        db.String(20),
        nullable=False,
        default=ROLE_USER,
        comment="角色，枚举值 admin/user",
    )

    # ---------------- 密码处理方法 ----------------

    def set_password(self, raw_password):
        """
        将明文密码加密后写入 password_hash 字段

        说明：使用 werkzeug.security.generate_password_hash 生成带盐哈希，
              默认使用 pbkdf2 算法，同一明文每次生成的哈希值不同，
              因此无法从哈希值反推原始密码。

        :param raw_password: 用户输入的明文密码
        :return: None
        """
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password):
        """
        校验明文密码是否与存储的哈希值匹配

        :param raw_password: 用户输入的明文密码
        :return: bool，匹配返回 True，否则返回 False
        """
        # 哈希值缺失时直接返回 False，避免 check_password_hash 抛异常
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, raw_password)

    # ---------------- Flask-Login 接口 ----------------

    def get_id(self):
        """
        返回用户唯一标识，供 Flask-Login 写入会话

        说明：Flask-Login 默认读取 self.id 属性，
              而本模型主键名为 user_id，因此必须重写本方法，
              否则会话无法正确识别当前登录用户。

        :return: 字符串形式的用户ID
        """
        return str(self.user_id)

    @property
    def is_admin(self):
        """
        判断当前用户是否为管理员

        :return: bool，角色为 admin 时返回 True
        """
        return self.role == self.ROLE_ADMIN

    def to_dict(self):
        """
        将用户对象转换为字典

        安全说明：本方法**不包含** password_hash 字段，
        避免密码哈希在接口响应或日志中泄露。

        :return: 包含用户公开字段的字典
        """
        return {
            "user_id": self.user_id,
            "username": self.username,
            "role": self.role,
        }

    def __repr__(self):
        """
        返回对象的可读字符串，便于调试与日志输出

        :return: 形如 <User 1:admin(admin)> 的字符串
        """
        return "<User {}:{}({})>".format(
            self.user_id,
            self.username,
            self.role,
        )
