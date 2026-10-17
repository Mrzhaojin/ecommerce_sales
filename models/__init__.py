# -*- coding: utf-8 -*-
"""
数据模型层包。

功能说明：
    1. 对外暴露全局唯一的 SQLAlchemy 实例 `db`，供模型文件与 app.py 共用。
       这样设计是为了避免「app.py 导入 models」与「models 导入 app.py」
       相互依赖而产生的循环导入问题；
    2. 统一导出本包下的全部模型类，供 services 层与脚本按需引用。

分层约定（rule.md 铁则 6）：
    本层只负责「表结构定义」与「行数据序列化（to_dict）」，
    禁止编写任何业务流程与统计聚合逻辑；
    统计计算统一交给 services 层使用 Pandas 完成。

导入顺序说明（重要）：
    下方 `from .db_models import ...` 必须写在 `db = SQLAlchemy()` 之后。
    这样 db_models 模块内部执行 `from . import db` 时，
    models 包的命名空间中已存在 db 对象，不会触发循环导入错误。

    同时，这一行导入还承担着一个关键职责：
    使全部表定义自动注册到 db.metadata 中。
    否则任何「直接 import models 后调用 db.create_all()」的代码
    都不会创建出任何表（SQLAlchemy 不知道有哪些表需要创建）。
    这是一个极为隐蔽的坑：create_all() 不会报错，
    但数据库中一张表都不会生成。

    因此新增模型时，**必须**在此处同步补充导入，
    否则该表不会被自动创建。

创建日期：2026-10-17
"""

from flask_sqlalchemy import SQLAlchemy

# 全局数据库实例：
# 在 create_app() 中通过 db.init_app(app) 与具体应用完成绑定
db = SQLAlchemy()

# 必须在 db 定义之后再导入模型，原因见上方「导入顺序说明」。
# （NOQA: E402 用于抑制「模块级导入不在文件顶部」的静态检查告警）
from .db_models import Category  # NOQA: E402,F401
from .db_models import Product  # NOQA: E402,F401
from .db_models import SalesOrder  # NOQA: E402,F401
from .db_models import User  # NOQA: E402,F401

# 对外暴露的对象清单
# 说明：User 是登录认证模型，与三张业务表无外键关联，
#       同样需要导出并在上方导入，以保证 user 表能被自动创建。
__all__ = ["db", "Category", "Product", "SalesOrder", "User"]
