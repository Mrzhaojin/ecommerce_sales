# -*- coding: utf-8 -*-
"""
认证与权限控制模块。

功能说明：
    1. 初始化 Flask-Login，提供会话登录能力；
    2. 定义角色常量与默认账号（项目不提供注册功能）；
    3. 提供 admin_required 装饰器，用于保护管理类页面与接口；
    4. 统一处理「未登录」场景：API 返回 401 JSON，页面跳转登录页；
    5. 提供按角色动态渲染的侧边栏导航配置。

安全约定：
    1. 密码一律通过 werkzeug.security 做加盐哈希，禁止明文存储；
    2. 登录成功后跳转的 next 参数必须校验为站内相对路径，
       防止开放重定向（Open Redirect）攻击；
    3. 所有页面与接口默认要求登录，权限不足统一返回 403。

分层约定（rule.md 铁则 6）：
    本层属于工具层，只负责认证与鉴权的通用能力，
    不包含任何业务统计逻辑。

创建日期：2026-10-17
"""

from functools import wraps
from urllib.parse import urlparse

from flask import redirect, request, url_for
from flask_login import LoginManager, current_user

from models import db
from models.db_models import User
from utils.response import fail

# 全局登录管理器单例：在 create_app() 中通过 init_login_manager() 完成初始化
login_manager = LoginManager()

# ---------------- 角色常量 ----------------
# 管理员：可访问管理类页面与接口
ROLE_ADMIN = "admin"
# 普通用户：仅可访问查询类页面与接口
ROLE_USER = "user"

# ---------------- 默认账号 ----------------
# 项目不提供注册功能，首次启动时由 app.py 自动写入这两个固定账号。
# 注意：密码在此处以明文形式配置仅用于初始化，
#       写入数据库前会立即通过 set_password() 转换为哈希值。
DEFAULT_ACCOUNTS = [
    {
        "username": "admin",
        "password": "admin123",
        "role": ROLE_ADMIN,
        "remark": "管理员",
    },
    {
        "username": "user",
        "password": "user123",
        "role": ROLE_USER,
        "remark": "普通用户",
    },
]

# ---------------- 侧边栏导航配置 ----------------
# roles 字段声明「哪些角色可以看到该菜单项」，
# 模板中通过 Jinja2 的 {% for %} + {% if %} 组合实现动态渲染。

# 导航图标的 SVG 路径数据（Heroicons 风格 24x24 描边图标）。
# 只保存 path 的 d 属性值，由模板拼接成完整 SVG，
# 既避免在模板中使用 |safe 输出整段 HTML，也符合「不用 emoji 当图标」的规范。
ICON_OVERVIEW = (
    "M3.75 6A2.25 2.25 0 016 3.75h2.25A2.25 2.25 0 0110.5 6v2.25"
    "a2.25 2.25 0 01-2.25 2.25H6a2.25 2.25 0 01-2.25-2.25V6z"
    "M3.75 15.75A2.25 2.25 0 016 13.5h2.25a2.25 2.25 0 012.25 2.25V18"
    "a2.25 2.25 0 01-2.25 2.25H6A2.25 2.25 0 013.75 18v-2.25z"
    "M13.5 6a2.25 2.25 0 012.25-2.25H18A2.25 2.25 0 0120.25 6v2.25"
    "A2.25 2.25 0 0118 10.5h-2.25a2.25 2.25 0 01-2.25-2.25V6z"
    "M13.5 15.75a2.25 2.25 0 012.25-2.25H18a2.25 2.25 0 012.25 2.25V18"
    "A2.25 2.25 0 0118 20.25h-2.25A2.25 2.25 0 0113.5 18v-2.25z"
)

ICON_DATABASE = (
    "M20.25 6.375c0 2.278-3.694 4.125-8.25 4.125S3.75 8.653 3.75 6.375"
    "s3.694-4.125 8.25-4.125 8.25 1.847 8.25 4.125z"
    "M3.75 12c0 2.278 3.694 4.125 8.25 4.125s8.25-1.847 8.25-4.125"
    "M3.75 17.625c0 2.278 3.694 4.125 8.25 4.125s8.25-1.847 8.25-4.125"
)

# 导航项清单：按顺序渲染，roles 决定可见性
NAV_ITEMS = [
    {
        "name": "数据总览",
        "url": "/",
        "icon": ICON_OVERVIEW,
        # 管理员与普通用户均可访问
        "roles": [ROLE_ADMIN, ROLE_USER],
    },
    {
        "name": "数据管理",
        "url": "/admin/data",
        "icon": ICON_DATABASE,
        # 仅管理员可见
        "roles": [ROLE_ADMIN],
    },
]


def build_unauthorized_response():
    """
    构造「未登录访问」的统一响应

    分流规则：
        - 接口路径（/api/ 开头）：返回 401 JSON。
          原因：若返回 302 跳转，前端 fetch 会拿到登录页的 HTML，
          JSON.parse 直接失败，图表区只会显示「数据加载失败」，
          无法区分是「未登录」还是「接口报错」；
        - 页面路径：重定向到登录页，并带上 next 参数以便登录后跳回原页面。

    :return: Flask 响应对象
    """
    if request.path.startswith("/api/"):
        return fail(msg="登录已失效，请重新登录", code=401)

    return redirect(url_for("page.login", next=request.path))


def is_safe_next_url(target):
    """
    校验登录跳转目标地址是否为安全的站内相对路径

    说明：若直接使用用户传入的 next 参数跳转，
    攻击者可构造 http://evil.com 这样的外链实施开放重定向攻击。
    因此必须校验：既不能有网络地址（netloc），又必须以单个 / 开头。

    :param target: 待跳转的地址
    :return: bool，安全返回 True，否则返回 False
    """
    if not target:
        return False

    # 排除 //evil.com 这类协议相对地址，以及任何带域名的绝对地址
    if target.startswith("//") or urlparse(target).netloc:
        return False

    return target.startswith("/")


def init_login_manager(app):
    """
    初始化 Flask-Login 登录管理器并注册相关回调

    注册内容：
        1. user_loader     ：根据会话中的用户ID加载用户对象；
        2. unauthorized_handler：统一处理未登录访问（见 build_unauthorized_response）；
        3. context_processor   ：向所有模板注入侧边栏导航配置 nav_items。

    :param app: Flask 应用实例
    :return: None
    """
    login_manager.init_app(app)
    # 未登录时跳转的目标端点（页面场景）
    login_manager.login_view = "page.login"
    login_manager.login_message = "请先登录后再访问该页面"
    login_manager.login_message_category = "warning"
    # basic 级别：会话标识不一致时标记为非新鲜登录，兼顾安全与体验
    login_manager.session_protection = "basic"

    @login_manager.user_loader
    def load_user(user_id):
        """
        根据会话中保存的用户ID加载用户对象

        :param user_id: 会话中保存的用户ID（字符串）
        :return: User 对象；ID 非法或用户不存在时返回 None
        """
        try:
            uid = int(user_id)
        except (TypeError, ValueError):
            # user_id 被篡改或格式非法时直接判定为未登录
            return None

        try:
            # 使用 SQLAlchemy 2.0 推荐的 session.get() 按主键查询
            return db.session.get(User, uid)
        except Exception as exc:  # NOQA: BLE001
            # 数据库不可用时（MySQL 未启动、连接被断开等）不能让整个请求 500，
            # 否则已登录用户会看到一个无解释的错误页。
            # 返回 None 会让 Flask-Login 将其视为未登录，
            # 进而走正常的「跳转登录页」流程，是更安全的降级方式。
            login_manager.logger.warning("加载用户失败：%s", exc)
            return None

    @login_manager.unauthorized_handler
    def handle_unauthorized():
        """
        未登录访问的统一处理入口

        :return: API 返回 401 JSON，页面重定向到登录页
        """
        return build_unauthorized_response()

    @app.context_processor
    def inject_nav_items():
        """
        向所有模板注入导航配置，使 base.html 可统一渲染侧边栏

        :return: 包含 nav_items 的字典
        """
        return {"nav_items": NAV_ITEMS}


def admin_required(view_func):
    """
    管理员权限装饰器：要求调用方已登录且角色为 admin

    使用方式（必须放在 @login_required 之下、视图函数之上）：

        @bp.route("/admin/xxx")
        @login_required
        @admin_required
        def some_view():
            ...

    处理逻辑：
        1. 未登录     → 交给 build_unauthorized_response() 处理
                        （API 返回 401，页面跳转登录页）；
        2. 已登录但非管理员 → 返回 403 JSON，提示权限不足。

    :param view_func: 被装饰的视图函数
    :return: 包装后的视图函数
    """

    @wraps(view_func)
    def decorated_view(*args, **kwargs):
        """
        权限校验包装函数：先校验登录态，再校验管理员角色

        :param args: 原视图函数的位置参数
        :param kwargs: 原视图函数的关键字参数
        :return: 校验通过时返回原视图函数的执行结果，
                 否则返回 401 或 403 响应
        """
        # 1. 未登录：与 login_required 保持一致的响应行为
        if not current_user.is_authenticated:
            return build_unauthorized_response()

        # 2. 已登录但角色不是管理员：返回 403
        if not getattr(current_user, "is_admin", False):
            return fail(msg="权限不足，仅管理员可执行该操作", code=403)

        return view_func(*args, **kwargs)

    return decorated_view
