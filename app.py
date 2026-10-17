# -*- coding: utf-8 -*-
"""
项目入口模块。

功能说明：
    1. 通过应用工厂函数 `create_app()` 创建并配置 Flask 应用实例；
    2. 加载 config.py 中的配置对象；
    3. 注册 Jinja2 模板过滤器，供模板做金额与数量格式化；
    4. 初始化数据库扩展（db.init_app），并在首次运行时自动建表；
    5. 检测数据库连通性，失败时在页面顶部给出醒目提示；
    6. 初始化登录管理器并写入默认账号（项目不提供注册功能）；
    7. 注册页面蓝图与 API 蓝图；
    8. 注册 404 / 500 错误处理器，避免用户看到原始报错堆栈；
    9. 提供本地开发启动入口（python app.py）。

设计说明：
    采用「应用工厂 + 蓝图」模式（rule.md 铁则 6），
    避免在模块顶层直接创建全局 app 实例导致的循环导入与测试困难问题。

    自动建表说明：
    create_app() 内部会调用 init_database() 执行 db.create_all()；
    该方法默认开启 checkfirst，已存在的表会被自动跳过，
    因此可以安全地重复执行，实现「首次运行自动建表、后续启动无副作用」。

    注意：db.create_all() 只能建表，不能创建数据库本身，
    运行前需先手动创建 ecommerce_db 数据库。

创建日期：2026-10-17
"""

import logging
import os

from dotenv import load_dotenv
from flask import Flask

from config import get_config
from models import db
from models.db_models import User
from routes import api_bp, page_bp
from utils.auth import DEFAULT_ACCOUNTS, init_login_manager
from utils.format_filters import register_filters
from utils.response import fail

# 项目根目录（即 app.py 所在的 ecommerce_sales 目录）
BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def create_app(config_name=None):
    """
    Flask 应用工厂函数：创建并完成应用实例的初始化

    :param config_name: 环境名称（development / production）；
                        为 None 时自动读取 .env 中的 FLASK_ENV
    :return: 已完成配置、数据库绑定与蓝图注册的 Flask 应用实例
    """
    # 优先加载 .env，确保后续 from_object 时能读到最新环境变量
    load_dotenv(os.path.join(BASE_DIR, ".env"))

    # 显式声明模板目录与静态资源目录，保持目录结构清晰
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )

    # 1. 加载配置对象（配置值全部来源于 .env，禁止硬编码）
    app.config.from_object(get_config(config_name))

    # 2. 配置 JSON 序列化行为（Flask 2.3 起由 app.json 提供相关属性）
    #    关闭 ASCII 转义，保证接口正常输出中文
    app.json.ensure_ascii = False
    #    关闭键名自动排序，保持响应字段为 {code, msg, data} 的顺序
    app.json.sort_keys = False

    # 3. 注册 Jinja2 模板过滤器（金额 / 数量 / 百分比格式化）
    #    注册后模板中可直接使用 {{ value|cell('money') }} 等写法
    register_filters(app)

    # 4. 初始化数据库扩展：将 db 实例与当前应用绑定
    db.init_app(app)

    # 5. 初始化数据库：首次运行时自动创建所有数据表
    init_database(app)

    # 6. 检测数据库连通性，检测结果会展示在页面顶部
    check_database(app)

    # 7. 初始化登录管理器（Flask-Login），注册 user_loader 与未登录处理逻辑
    init_login_manager(app)

    # 8. 初始化默认账号：项目不提供注册功能，首次启动时写入固定账号
    init_default_users(app)

    # 9. 注册蓝图（页面路由 + API 路由）
    register_blueprints(app)

    # 10. 注册全局错误处理器：让 404 / 500 都返回友好页面而非原始堆栈
    register_error_handlers(app)

    # 11. 注册模板上下文处理器：向所有模板注入全局展示变量
    register_template_context(app)

    return app


def init_database(app):
    """
    初始化数据库：在应用上下文中创建所有数据表

    实现说明：
        1. db.create_all() 默认 checkfirst=True，
           只会创建尚不存在的表，已存在的表会被自动跳过，
           因此可以安全地重复执行，实现「首次运行自动建表」；
        2. db.metadata 中已经注册了全部表定义——
           models/__init__.py 在定义 db 之后会自动导入 db_models，
           因此本函数无需再手动导入模型；
        3. 若 MySQL 未启动或数据库不存在，此处仅记录警告日志而不中断启动，
           避免开发环境因数据库不可用导致整个应用无法运行。

    :param app: Flask 应用实例
    :return: None
    """

    # 建表前先置为 False，由下方成功分支改写为 True，
    # 供 check_database() 判断是否需要跳过连通性探测
    app.config["DB_TABLES_READY"] = False

    with app.app_context():
        try:
            db.create_all()
            app.config["DB_TABLES_READY"] = True
            app.logger.info("数据库表初始化完成（已存在的表自动跳过）")
        except Exception as exc:  # NOQA: BLE001
            # 记录详细错误信息，提示开发者检查 MySQL 状态与数据库是否存在
            app.logger.warning(
                "数据库表初始化失败，请检查 MySQL 是否已启动、"
                "ecommerce_db 数据库是否已创建。错误信息：%s",
                exc,
            )


def check_database(app):
    """
    检测数据库连通性，并将检测结果写入 app.config["DB_AVAILABLE"]

    设计目的：
        当 MySQL 未启动、账号密码错误或数据库不存在时，
        各统计接口会全部失败，页面表现为「图表空白 + 卡片为 0」，
        用户很难判断到底是「没有数据」还是「数据库连不上」。
        因此在启动时主动探测一次，
        由 base.html 在页面顶部渲染醒目的异常提示条。

    实现说明：
        这里执行的 `SELECT 1` 是不含任何用户输入的常量语句，
        不存在 SQL 注入风险，符合 rule.md 铁则 2 的要求
        （铁则禁止的是「字符串拼接 / 参数未绑定」的写法）。

    :param app: Flask 应用实例
    :return: bool，数据库可用返回 True，否则返回 False
    """
    from sqlalchemy import text

    # 建表已经失败时无需再探测，直接判定为不可用
    if not app.config.get("DB_TABLES_READY", True):
        app.config["DB_AVAILABLE"] = False
        return False

    with app.app_context():
        try:
            db.session.execute(text("SELECT 1"))
            db.session.commit()
            app.config["DB_AVAILABLE"] = True
        except Exception as exc:  # NOQA: BLE001
            # 回滚未完成的事务，避免会话处于不可用状态
            db.session.rollback()
            app.config["DB_AVAILABLE"] = False
            app.logger.warning(
                "数据库连接失败，页面数据将无法加载。"
                "请检查 MySQL 是否已启动、.env 中的账号密码与库名是否正确。"
                "错误信息：%s",
                exc,
            )

    return app.config["DB_AVAILABLE"]


def register_template_context(app):
    """
    注册模板上下文处理器，向所有模板注入全局展示变量

    注入的变量：
        db_available  数据库是否可用（由 check_database 检测得出），
                      base.html 依据它在页面顶部渲染异常提示条。

    :param app: Flask 应用实例
    :return: None
    """

    @app.context_processor
    def inject_global_vars():
        """
        向模板上下文注入全局变量

        :return: 包含全局展示变量的字典
        """
        return {
            # 默认 True：未执行检测时不显示告警，避免误报
            "db_available": app.config.get("DB_AVAILABLE", True),
        }


def register_error_handlers(app):
    """
    注册全局错误处理器，统一 404 / 500 的展示形式

    分流规则（与「未登录」的处理保持一致）：
        - /api/ 开头的路径：返回 JSON 信封，便于前端统一处理；
        - 其余页面路径：渲染 templates/error.html 友好错误页。

    设计目的：
        开启 DEBUG 时 Flask 会直接展示带堆栈的调试页，
        关闭 DEBUG 时则展示简陋的默认 404 / 500 页。
        两者对最终用户都不友好，因此统一接管这两个状态码。

    :param app: Flask 应用实例
    :return: None
    """
    from flask import render_template, request

    @app.errorhandler(404)
    def handle_not_found(error):
        """
        处理 404（请求的资源不存在）

        :param error: Flask 传入的错误对象
        :return: JSON 响应（API）或错误页（页面），HTTP 状态码 404
        """
        if request.path.startswith("/api/"):
            return fail(msg="请求的资源不存在：{}".format(request.path), code=404)

        return render_template(
            "error.html",
            page_title="页面不存在",
            error_code=404,
            error_title="页面不存在",
            error_detail="请检查访问地址是否正确，或从左侧菜单重新进入。",
        ), 404

    @app.errorhandler(500)
    def handle_server_error(error):
        """
        处理 500（服务器内部错误）

        说明：多数 500 由数据库不可用或统计过程异常引发，
              因此错误页中给出针对性的排查建议。

        :param error: Flask 传入的错误对象
        :return: JSON 响应（API）或错误页（页面），HTTP 状态码 500
        """
        # 记录完整堆栈到日志，便于排查；页面只展示友好提示
        app.logger.error("服务器内部错误：%s", error, exc_info=True)

        if request.path.startswith("/api/"):
            return fail(msg="服务器内部错误，请稍后重试", code=500)

        return render_template(
            "error.html",
            page_title="服务异常",
            error_code=500,
            error_title="服务暂时不可用",
            error_detail=(
                "数据处理过程中发生异常，常见原因是数据库连接失败。"
                "请检查 MySQL 是否已启动、.env 配置是否正确，然后刷新页面重试。"
            ),
        ), 500


def init_default_users(app):
    """
    初始化默认登录账号（项目不提供注册功能）

    执行逻辑：
        1. 逐个检查默认账号是否已存在（按 username 判重），已存在则跳过，
           因此本函数可安全重复执行，不会覆盖用户已修改的密码；
        2. 不存在的账号才创建，并在写入前立即将明文密码转为哈希值。

    :param app: Flask 应用实例
    :return: None
    """
    with app.app_context():
        created_names = []
        try:
            for account in DEFAULT_ACCOUNTS:
                # 按用户名判重，避免重复初始化
                exists = User.query.filter_by(
                    username=account["username"]
                ).first()
                if exists is not None:
                    continue

                user = User(
                    username=account["username"],
                    role=account["role"],
                )
                # 明文密码仅在此处出现，立即转换为哈希后入库
                user.set_password(account["password"])
                db.session.add(user)
                created_names.append(
                    "{}({})".format(account["username"], account["remark"])
                )

            db.session.commit()

            if created_names:
                app.logger.info(
                    "已初始化默认账号：%s", "、".join(created_names)
                )
        except Exception as exc:  # NOQA: BLE001
            # 建表失败或数据库不可用时回滚，仅记录警告不影响应用启动
            db.session.rollback()
            app.logger.warning("默认账号初始化失败：%s", exc)


def register_blueprints(app):
    """
    将所有蓝图注册到 Flask 应用实例

    :param app: Flask 应用实例
    :return: None
    """
    # 页面蓝图：提供 / 等 HTML 页面
    app.register_blueprint(page_bp)

    # API 蓝图：统一挂载在 /api 前缀下，提供 /api/sales/* 数据接口
    app.register_blueprint(api_bp)


def _get_int(env_key, default):
    """
    安全读取整数型环境变量，避免配置了非法值时直接崩溃

    :param env_key: 环境变量名称
    :param default: 缺失或非法时使用的默认值
    :return: int 类型的配置值
    """
    try:
        return int(os.getenv(env_key, str(default)))
    except (TypeError, ValueError):
        app_logger = logging.getLogger(__name__)
        app_logger.warning(
            "环境变量 %s 取值非法，已回退为默认值 %s", env_key, default
        )
        return default


def main():
    """
    本地开发启动入口：创建应用并以开发服务器方式运行

    安全说明：
        DEBUG=True 时 Werkzeug 会开启交互式调试器，
        该调试器允许在浏览器中执行任意 Python 代码。
        因此本函数会在「开启 DEBUG 且监听非本机地址」时打印严重警告，
        避免把调试器暴露到局域网。

    :return: None
    """
    app = create_app()

    # 监听地址与端口同样支持通过 .env 覆盖
    host = os.getenv("FLASK_HOST", "127.0.0.1")
    port = _get_int("FLASK_PORT", 5000)
    debug = app.config.get("DEBUG", True)

    # 本机回环地址清单：仅在这些地址上监听时启用调试器才是安全的
    loopback_hosts = ("127.0.0.1", "localhost", "::1")
    if debug and host not in loopback_hosts:
        app.logger.warning(
            "安全警告：当前为调试模式且监听地址为 %s，"
            "Werkzeug 交互式调试器将对外暴露，存在远程执行代码的风险。"
            "建议将 FLASK_HOST 改为 127.0.0.1，"
            "或设置 FLASK_ENV=production 关闭调试模式。",
            host,
        )

    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    main()
