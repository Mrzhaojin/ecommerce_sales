# -*- coding: utf-8 -*-
"""
配置模块。

功能说明：
    从根目录的 `.env` 文件中读取环境变量，并将其封装成 Flask 应用
    可直接通过 `app.config.from_object()` 加载的配置类。

    所有敏感信息（数据库账号、密码、SECRET_KEY 等）一律通过环境变量注入，
    严禁在源码中硬编码，以符合 rule.md 铁则 2 的配置管理要求。

配置类说明：
    Config            基础配置类，存放各环境共用的配置项
    DevelopmentConfig 开发环境配置（开启 DEBUG 与 SQL 回显）
    ProductionConfig  生产环境配置（关闭 DEBUG）

创建日期：2026-10-17
"""

import os
from urllib.parse import quote

from dotenv import load_dotenv

# 项目根目录（即 config.py 所在的 ecommerce_sales 目录）
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# 加载 .env 文件中的环境变量；若 .env 不存在则静默跳过，
# 此时自动退化为使用下方 os.getenv() 提供的默认值。
load_dotenv(os.path.join(BASE_DIR, ".env"))


def _get_bool(env_key, default=False):
    """
    将环境变量中的字符串转换为布尔值

    :param env_key: 环境变量名称，如 "FLASK_DEBUG"
    :param default: 当环境变量缺失或为空时返回的默认值
    :return: bool 类型的配置值
    """
    value = os.getenv(env_key)
    if value is None or value == "":
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _get_int(env_key, default=0):
    """
    将环境变量中的字符串转换为整数

    :param env_key: 环境变量名称，如 "DB_PORT"
    :param default: 当环境变量缺失或非法时返回的默认值
    :return: int 类型的配置值
    """
    try:
        return int(os.getenv(env_key, str(default)))
    except (TypeError, ValueError):
        return default


class Config(object):
    """
    基础配置类：存放所有运行环境共用的配置项。
    开发环境与生产环境均继承自本类，避免配置重复。
    """

    # ---------------- Flask 基础配置 ----------------
    # 会话签名密钥；生产环境必须通过 .env 覆盖为高强度随机值
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev-secret-key")

    # ---------------- MySQL 数据库配置 ----------------
    DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
    DB_PORT = _get_int("DB_PORT", 3306)
    DB_USER = os.getenv("DB_USER", "root")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")
    DB_NAME = os.getenv("DB_NAME", "ecommerce_db")

    # SQLAlchemy 连接串：mysql+pymysql 驱动，字符集统一 utf8mb4。
    # 用户名、密码、库名统一做 URL 编码：
    # 若密码中包含 @ / : # 等字符，不编码会导致连接串被错误解析而连接失败。
    SQLALCHEMY_DATABASE_URI = (
        "mysql+pymysql://{user}:{password}@{host}:{port}/{db}"
        "?charset=utf8mb4".format(
            user=quote(str(DB_USER), safe=""),
            password=quote(str(DB_PASSWORD), safe=""),
            host=DB_HOST,
            port=DB_PORT,
            db=quote(str(DB_NAME), safe=""),
        )
    )

    # 关闭 Flask-SQLAlchemy 3.x 的事件追踪系统（已废弃，关闭可节省开销）
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # 连接池配置：预检连接有效性，避免 MySQL 长时间空闲断连
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_size": 10,          # 连接池保持的连接数
        "pool_recycle": 3600,     # 连接回收时间（秒）
        "pool_pre_ping": True,    # 每次取用连接前先探测可用性
    }


class DevelopmentConfig(Config):
    """
    开发环境配置：开启调试模式与 SQL 语句回显，便于实验阶段排错。
    """

    DEBUG = True

    # 是否回显 ORM 生成的 SQL：
    # 默认关闭，避免批量写入时（如生成 1500 条订单）产生海量日志；
    # 需要验证「ORM 只取行、不做分组聚合」时，
    # 在 .env 中添加 SQLALCHEMY_ECHO=true 即可临时开启。
    SQLALCHEMY_ECHO = _get_bool("SQLALCHEMY_ECHO", False)


class ProductionConfig(Config):
    """
    生产环境配置：关闭调试模式与 SQL 回显，避免敏感信息外泄。
    """

    DEBUG = False
    SQLALCHEMY_ECHO = False


# 环境名称与配置类的映射表
CONFIG_MAP = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
}


def get_config(config_name=None):
    """
    根据环境名称获取对应的配置类

    :param config_name: 环境名称，取值为 development / production；
                        传入 None 时自动读取 .env 中的 FLASK_ENV
    :return: 配置类对象（未实例化的类），交给 app.config.from_object() 使用
    """
    # 未显式指定时，优先使用环境变量 FLASK_ENV，默认为开发环境
    if not config_name:
        config_name = os.getenv("FLASK_ENV", "development")

    # 小写归一后查表；查不到时安全回退到开发环境配置
    return CONFIG_MAP.get(str(config_name).strip().lower(), DevelopmentConfig)
