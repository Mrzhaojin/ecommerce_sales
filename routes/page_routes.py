# -*- coding: utf-8 -*-
"""
页面路由模块。

功能说明：
    定义返回 HTML 页面的路由，包含登录、登出、数据看板首页与数据管理页。

    本文件负责「接收请求 → 调用 services 层 → 渲染模板」，
    具体的指标计算统一交给 services 层完成，禁止在此编写业务逻辑。

权限说明：
    1. /login          公开访问（登录入口）；
    2. /               需登录（@login_required），未登录自动跳转登录页；
    3. /admin/data     需登录且角色为管理员（@login_required + @admin_required），
                       普通用户访问返回 403；
    4. /logout         需登录，退出后回到登录页。

    三个受保护页面的装饰器叠加顺序均为：
        @page_bp.route(...) → @login_required → @admin_required（管理页才有）
    顺序不可颠倒，否则 admin_required 会在未登录时拿到匿名用户对象。

    侧边栏导航配置 nav_items 由 utils/auth.py 中的上下文处理器统一注入，
    无需各视图函数逐个传递；模板通过 Jinja2 的 for + if 组合按角色渲染。

数据管理页说明：
    /admin/data 支持通过 URL 查询参数切换页签、搜索、排序与分页，
    页签与表格列的定义集中在 TAB_CONFIG 中，
    模板只需循环渲染即可，新增一张表的浏览页无需改动模板结构。

创建日期：2026-10-17
"""

from flask import (
    Blueprint,
    current_app,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user

from models.db_models import User
from services import admin_service, data_service
from utils.auth import admin_required, is_safe_next_url

# 创建页面蓝图：不设置 url_prefix，首页路径即为 /
page_bp = Blueprint("page", __name__)

# ==================== 数据管理页的页签配置 ====================
# 说明：本配置把「页签 → 查询函数 → 表格列定义」集中管理，
#       路由层只负责把当前页签对应的配置取出并传给模板，
#       模板通过 {% for %} 循环渲染表头与数据行，
#       后续若要新增一张表的浏览页，只需在此追加一项配置即可。
#
# 字段说明：
#   name          页签显示名称
#   query         对应的 services 查询函数（由路由层调用）
#   default_sort  默认排序列
#   empty_text    数据为空时的提示文案
#   search_hint   搜索框的占位提示文案
#   columns       表格列定义，field 为数据字段名，label 为表头文字，
#                 format 指定单元格格式化方式（money/int/percent/text）
TAB_CONFIG = {
    "category": {
        "name": "品类数据",
        "query": admin_service.get_category_rows,
        "default_sort": "category_id",
        "empty_text": "暂无品类数据，请先运行 generate_data.py 生成模拟数据",
        "search_hint": "按品类名称搜索",
        "columns": [
            {"field": "category_id", "label": "品类ID", "format": "int"},
            {"field": "category_name", "label": "品类名称", "format": "text"},
            {"field": "product_count", "label": "商品数", "format": "int"},
            {"field": "order_count", "label": "订单数", "format": "int"},
            {"field": "total_amount", "label": "销售额", "format": "money"},
            {"field": "amount_ratio", "label": "销售占比", "format": "percent"},
        ],
    },
    "product": {
        "name": "商品数据",
        "query": admin_service.get_product_rows,
        "default_sort": "product_id",
        "empty_text": "暂无商品数据，请先运行 generate_data.py 生成模拟数据",
        "search_hint": "按商品名称或品类搜索",
        "columns": [
            {"field": "product_id", "label": "商品ID", "format": "int"},
            {"field": "product_name", "label": "商品名称", "format": "text"},
            {"field": "category_name", "label": "所属品类", "format": "text"},
            {"field": "price", "label": "单价", "format": "money"},
            {"field": "total_quantity", "label": "累计销量", "format": "int"},
            {"field": "total_amount", "label": "累计销售额", "format": "money"},
        ],
    },
    "order": {
        "name": "订单数据",
        "query": admin_service.get_order_rows,
        "default_sort": "order_id",
        "empty_text": "暂无订单数据，请先运行 generate_data.py 生成模拟数据",
        "search_hint": "按商品、品类、省份或城市搜索",
        "columns": [
            {"field": "order_id", "label": "订单ID", "format": "int"},
            {"field": "product_name", "label": "商品名称", "format": "text"},
            {"field": "category_name", "label": "所属品类", "format": "text"},
            {"field": "quantity", "label": "数量", "format": "int"},
            {"field": "total_amount", "label": "订单金额", "format": "money"},
            {"field": "province", "label": "省份", "format": "text"},
            {"field": "city", "label": "城市", "format": "text"},
            {"field": "order_date", "label": "下单日期", "format": "text"},
        ],
    },
}


@page_bp.route("/login", methods=["GET", "POST"])
def login():
    """
    登录页面与登录提交

    接口路径：GET|POST /login
    请求参数：
        GET   next（可选）登录成功后跳转的目标地址，必须是站内相对路径
        POST  username 用户名、password 密码
    返回内容：
        GET   渲染 templates/login.html
        POST  校验通过跳转目标页（默认首页）；校验失败重新渲染登录页并带错误提示

    安全说明：
        1. 登录失败时不区分「用户不存在」与「密码错误」，
           统一提示「用户名或密码错误」，避免账号枚举；
        2. next 参数必须经 is_safe_next_url() 校验，
           防止开放重定向攻击。

    :return: 渲染后的 HTML 页面或重定向响应
    """
    # 已登录用户直接回到首页，避免重复登录
    if current_user.is_authenticated:
        return redirect(url_for("page.index"))

    error_msg = None

    if request.method == "POST":
        # 去除首尾空格，避免用户误输入空格导致登录失败
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""

        # 查询用户：数据库不可用时捕获异常并给出针对性提示。
        # 若不捕获，MySQL 未启动会导致登录页直接 500，
        # 用户会误以为是程序本身有问题，而不是数据库没连上。
        try:
            user = User.query.filter_by(username=username).first()
        except Exception as exc:  # NOQA: BLE001
            current_app.logger.error("[登录] 查询用户失败：%s", exc, exc_info=True)
            return render_template(
                "login.html",
                page_title="登录",
                error_msg="数据库服务不可用，请检查 MySQL 是否已启动",
                db_error=True,
            )

        if user is None or not user.check_password(password):
            # 统一错误提示，不泄露账号是否存在
            error_msg = "用户名或密码错误"
        else:
            # 校验通过：写入会话，Flask-Login 自动维护登录状态
            login_user(user)

            # 处理跳转目标：优先使用 next 参数，非法则回退到首页
            next_url = request.args.get("next") or ""
            if not is_safe_next_url(next_url):
                next_url = url_for("page.index")

            return redirect(next_url)

    return render_template(
        "login.html",
        page_title="登录",
        error_msg=error_msg,
    )


@page_bp.route("/logout")
@login_required
def logout():
    """
    退出登录：清除会话中的登录状态并回到登录页

    接口路径：GET /logout
    权限要求：需已登录

    :return: 重定向到登录页
    """
    logout_user()
    return redirect(url_for("page.login"))


@page_bp.route("/")
@login_required
def index():
    """
    数据看板首页：渲染销售数据可视化页面

    接口路径：GET /
    权限要求：需登录，未登录自动跳转登录页
    请求参数：无
    返回内容：渲染后的 templates/index.html 页面

    传递的模板变量：
        page_title  页面标题（体现 Jinja2 变量传递）
        cards       顶部 4 个数据卡片数据（模板中使用 for 循环渲染）

    :return: 渲染后的 HTML 页面
    """
    try:
        # 调用 services 层计算卡片指标，路由层不做任何计算
        cards = data_service.get_overview_cards()
    except Exception as exc:  # NOQA: BLE001
        # 卡片数据加载失败时降级为空列表并降级渲染，
        # 避免个别指标异常导致整个页面无法打开
        current_app.logger.error(
            "[数据总览卡片] 加载失败：%s", exc, exc_info=True
        )
        cards = []

    # 通过 render_template 向模板传递变量（Jinja2 变量传递特性）
    return render_template(
        "index.html",
        page_title="数据总览",
        cards=cards,
    )


@page_bp.route("/admin/data")
@login_required
@admin_required
def admin_data():
    """
    数据管理页：仅管理员可访问的三表数据浏览与统计页面

    接口路径：GET /admin/data
    权限要求：需登录且角色为 admin；普通用户访问返回 403
    请求参数（全部为可选，缺省时使用默认值）：
        tab       数据表页签，取值 category / product / order，默认 category
        keyword   搜索关键字，按各表的名称字段做模糊匹配
        page      当前页码，从 1 开始，默认 1
        per_page  每页条数，默认 10，上限 100
        sort_by   排序列名，非法列名会自动回退到该表默认排序列
        order     排序方向，desc（降序，默认）或 asc（升序）
    返回内容：渲染后的 templates/admin_data.html 页面

    实现说明：
        本视图只负责「读取查询参数 → 调用 services 层 → 传递模板变量」，
        所有统计与分页计算均由 services/admin_service.py 用 Pandas 完成。
        数据获取失败时捕获异常并降级为空列表，
        保证管理员仍能看到页面结构与错误提示，而不是一个 500 错误页。

    :return: 渲染后的 HTML 页面
    """
    # 1. 读取并归一化页签参数：非法页签回退到品类页，避免后续查询分支出错
    tab = (request.args.get("tab") or "category").strip().lower()
    if tab not in TAB_CONFIG:
        tab = "category"

    # 2. 读取搜索与分页参数（均由 services 层做类型收敛与范围校验）
    keyword = (request.args.get("keyword") or "").strip()
    page = request.args.get("page", 1)
    per_page = request.args.get("per_page", 10)

    # 3. 读取排序参数：desc 为降序，其余一律按升序处理
    sort_by = (request.args.get("sort_by") or "").strip()
    descending = (request.args.get("order") or "desc").strip().lower() != "asc"

    # 4. 调用 services 层获取当前页签的数据行与分页信息
    rows = []
    pagination = None
    overview = {}
    error_msg = None

    try:
        # 概览指标三个页签共用，单独调用一次
        overview = admin_service.get_admin_overview()

        # 按页签分发到对应的 service 查询函数
        query_function = TAB_CONFIG[tab]["query"]
        rows, pagination = query_function(
            keyword=keyword,
            page=page,
            per_page=per_page,
            sort_by=sort_by if sort_by else TAB_CONFIG[tab]["default_sort"],
            descending=descending,
        )
    except Exception as exc:  # NOQA: BLE001
        # 数据库不可用或统计异常时降级为空数据，页面仍展示错误提示
        current_app.logger.error(
            "[数据管理-%s] 数据加载失败：%s", tab, exc, exc_info=True
        )
        error_msg = "数据加载失败，请检查数据库连接后重试"
        rows = []
        pagination = admin_service.build_empty_pagination(page, per_page)
        overview = {}

    return render_template(
        "admin_data.html",
        page_title="数据管理",
        current_role=current_user.role,
        # 页签配置供模板循环渲染页签按钮（体现 Jinja2 循环渲染）
        tabs=TAB_CONFIG,
        active_tab=tab,
        active_config=TAB_CONFIG[tab],
        keyword=keyword,
        sort_by=sort_by if sort_by else TAB_CONFIG[tab]["default_sort"],
        order="asc" if not descending else "desc",
        rows=rows,
        pagination=pagination,
        overview=overview,
        error_msg=error_msg,
    )
