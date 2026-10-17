# -*- coding: utf-8 -*-
"""
数据库初始化脚本：创建数据库与数据表。

功能说明：
    1. 以「不指定数据库」的方式连接 MySQL 服务，
       创建配置文件中声明的数据库（如已存在则跳过）；
    2. 通过 Flask-SQLAlchemy 的 db.create_all() 创建全部数据表
       ——三张业务表（category / product / sales_order）
       与一张认证表（user）
       （已存在的表自动跳过，可安全重复执行）。

为什么需要单独建库：
    SQLAlchemy 的 db.create_all() 只能在「已存在的数据库」中建表，
    无法创建数据库本身，因此必须先执行一步建库操作。

安全性说明：
    1. 数据库账号、密码全部从 .env 读取，代码中不出现任何明文凭据；
    2. CREATE DATABASE 语句的数据库名无法使用参数绑定，
       因此在拼接前先做白名单校验（仅允许字母、数字、下划线），
       不合法则直接抛出异常，从根本上杜绝 SQL 注入风险；
    3. 脚本运行过程中不会输出任何密码信息。

使用方式：
    python data/init_db.py

创建日期：2026-10-17
"""

import os
import re
import sys

import pymysql

# 将项目根目录加入模块搜索路径，保证脚本可以直接以文件方式运行
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from app import create_app  # NOQA: E402
from config import get_config  # NOQA: E402
from models import db  # NOQA: E402

# 数据库名白名单：仅允许字母、数字、下划线
DB_NAME_PATTERN = r"^[A-Za-z0-9_]+$"


def validate_db_name(db_name):
    """
    校验数据库名称的合法性，防止拼接 SQL 时产生注入风险

    :param db_name: 待校验的数据库名称
    :return: 校验通过后的数据库名称
    :raises ValueError: 名称不符合白名单规则时抛出
    """
    if not re.match(DB_NAME_PATTERN, str(db_name)):
        raise ValueError(
            "非法的数据库名称：{!r}，仅允许字母、数字、下划线".format(db_name)
        )
    return db_name


def create_database(cfg):
    """
    连接 MySQL 服务并创建数据库（如已存在则跳过）

    :param cfg: 配置类对象，需提供 DB_HOST / DB_PORT / DB_USER /
                DB_PASSWORD / DB_NAME 等属性
    :return: None
    """
    # 先校验库名，再拼接进 SQL，杜绝注入风险
    db_name = validate_db_name(cfg.DB_NAME)

    # 建库语句：使用反引号包裹标识符，并显式指定字符集与排序规则
    create_sql = (
        "CREATE DATABASE IF NOT EXISTS `{}` "
        "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci".format(db_name)
    )

    # 连接 MySQL 服务（不指定 database，否则库不存在时会连接失败）
    connection = pymysql.connect(
        host=cfg.DB_HOST,
        port=int(cfg.DB_PORT),
        user=cfg.DB_USER,
        password=cfg.DB_PASSWORD,
        charset="utf8mb4",
    )

    try:
        with connection.cursor() as cursor:
            cursor.execute(create_sql)
        connection.commit()
        print("[1/2] 数据库 `{}` 已就绪".format(db_name))
    finally:
        # 无论成功与否都关闭连接，避免连接泄漏
        connection.close()


def create_tables(app):
    """
    在应用上下文中创建所有数据表

    :param app: Flask 应用实例
    :return: None
    """
    # 导入模型模块，确保全部表定义注册到 db.metadata 中。
    # 说明：models/__init__.py 在定义 db 之后会自动导入全部模型，
    #       因此只要「import models」或「import 任意一个模型」，
    #       四张表的定义就已经注册完毕。
    #       此处显式导入是为了让阅读脚本的人一眼看清会创建哪些表。
    # （NOQA: F401 用于抑制「导入未使用」的静态检查告警）
    from models.db_models import Category  # NOQA: F401
    from models.db_models import Product  # NOQA: F401
    from models.db_models import SalesOrder  # NOQA: F401
    from models.db_models import User  # NOQA: F401

    with app.app_context():
        # create_all() 默认 checkfirst=True，已存在的表会被自动跳过
        db.create_all()
        table_names = ", ".join(db.metadata.tables.keys())
        print("[2/2] 数据表已就绪：{}".format(table_names))


def main():
    """
    脚本主流程：建库 → 建表 → 输出初始化结果

    :return: None
    """
    # 第一步只读取配置，不创建 Flask 应用，
    # 避免在数据库尚未创建时触发 app.py 中的自动建表
    cfg = get_config()
    create_database(cfg)

    # 第二步创建应用并建立三张业务表
    app = create_app()
    create_tables(app)

    print("\n数据库初始化完成，可执行 generate_data.py 生成模拟数据。")


if __name__ == "__main__":
    main()
