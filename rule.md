# 电商销售数据可视化平台 · 开发规则文档（rule.md）

> **文档性质**：本文件是本项目的**唯一开发契约**，对项目中的人类开发者与 AI Agent 均具有强制约束力。
> **适用项目**：`three_project`（电商销售数据可视化平台）
> **创建日期**：2026-10-17
> **执行原则**：任何与本文件冲突的实现，一律视为**缺陷（Defect）**，必须回退并按本文件重写。

---

## 0. 阅读与执行约定

1. Agent 在开始任何编码任务前，必须**先完整读取本文件**，并在实现过程中持续对照。
2. 本文件中：
   - **【必须】** 表示强制要求，违反即判定任务失败；
   - **【禁止】** 表示绝对不允许出现的代码写法或结构；
   - **【建议】** 表示推荐做法，非强制。
3. 当需求与本文件冲突、或本文件存在未覆盖的场景时，Agent **必须先以问答方式向用户确认**，得到明确答复后方可继续，**禁止自行臆断**。
4. 版本兼容性问题优先按第 2 章的"版本锁定清单"执行；若仍无法解决，**必须以问答方式询问用户确认后再操作**。

---

## 1. 项目硬性规范清单（铁则）

> 以下 7 条为**最高优先级约束**。当本文件其他章节与其冲突时，以本章为准。

### 铁则 1：后端框架与模板引擎

| 项目 | 规定 |
|---|---|
| Web 框架 | **【必须】** Flask |
| 模板引擎 | **【必须】** Jinja2（Flask 内置，禁止替换为其他模板引擎） |

**【必须】** 模板部分必须完整体现 Jinja2 三大核心特性，缺一不可：

| 核心特性 | 落地要求 | 判定标准 |
|---|---|---|
| **模板继承** | 定义 `templates/base.html` 作为父模板，使用 `{% block %}` 挖槽；业务页面（`index.html`）使用 `{% extends "base.html" %}` 继承并覆写 block | 项目中至少存在 1 处 `{% extends %}`、父模板中至少 3 个 `{% block %}` |
| **变量传递** | 路由函数通过 `render_template('index.html', **ctx)` 向模板传参，模板中使用 `{{ var }}` 取值 | 首页至少传递 `page_title`、`total_sales`、`total_orders`、`product_count`、`province_count` 等变量并在模板中渲染 |
| **循环渲染** | 使用 `{% for %}...{% endfor %}` 渲染侧边栏导航菜单、数据卡片列表等可迭代数据 | 至少存在 1 处 `{% for %}` 用于渲染导航菜单，1 处用于渲染数据卡片 |

**【禁止】**
- 禁止使用 `render_template_string()` 拼接整页 HTML；
- 禁止在模板中编写复杂业务逻辑（循环嵌套超过 2 层、多层条件判断），业务逻辑必须留在 Python 侧；
- 禁止把 `{% extends %}` 写成非首行语句。

---

### 铁则 2：数据库与 ORM

| 项目 | 规定 |
|---|---|
| 数据库 | **【必须】** MySQL（5.7 / 8.0） |
| 驱动 | **【必须】** PyMySQL |
| ORM | **【必须】** Flask-SQLAlchemy |
| 连接串格式 | `mysql+pymysql://<user>:<password>@<host>:<port>/<dbname>?charset=utf8mb4` |

**【禁止】**
- **【禁止】原生 SQL 硬编码拼接**，包括但不限于：
  - 字符串拼接式 SQL：`"SELECT * FROM product WHERE name = '" + name + "'"`；
  - f-string 注入式 SQL：`f"... WHERE category_id = {cid}"`；
  - 无参数化占位符的 `db.session.execute(text(...))` 拼接。
- 禁止使用 `sqlite` 或其他数据库替代 MySQL；
- 禁止在模型层之外散布 `create_engine` / 裸连接代码。

**【必须】**
- 所有表结构通过 **Model 类**定义（继承 `db.Model`）；
- 若确有必要执行原生 SQL（如建库、批量导入），**必须**使用 SQLAlchemy 的 `text()` + **绑定参数** `text("... WHERE id = :id")` 并通过 `params={"id": val}` 传值；
- 数据库连接信息统一走 `.env` + `python-dotenv` 读取，**禁止硬编码账号密码到源码**。

---

### 铁则 3：接口风格与响应格式

**【必须】** 数据接口严格遵循 **RESTful** 设计规范：

- 资源名使用**复数名词**（`/api/sales/...`），禁止出现动词（如 `/api/getSales`）；
- 语义与 HTTP 方法对应：GET 查询、POST 新增、PUT 全量更新、DELETE 删除；本项目以 GET 为主；
- 使用**语义化 HTTP 状态码**（200 成功、400 参数错误、404 资源不存在、500 服务端异常）。

**【必须】** 所有 JSON 接口返回统一响应信封（Envelope）：

```json
{
  "code": 200,
  "msg": "success",
  "data": []
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `code` | int | 业务状态码，与 HTTP 状态码保持一致 |
| `msg` | str | 提示信息，成功固定为 `"success"` |
| `data` | any | 业务数据，可为数组、对象或 null |

**【必须】** 统一封装响应工具函数，禁止在每个路由里手写字典：

```python
# app/utils/response.py
def ok(data=None, msg="success", code=200):
    """成功响应统一封装"""
    return jsonify({"code": code, "msg": msg, "data": data}), code

def fail(msg="error", code=400, data=None):
    """失败响应统一封装"""
    return jsonify({"code": code, "msg": msg, "data": data}), code
```

**【必须】** 每个 API 路由必须包含 `try...except` 兜底异常捕获，异常时返回 `code=500` 并记录日志。

---

### 铁则 4：数据处理层必须使用 Pandas

**【必须】** 所有统计、清洗、聚合、计算逻辑**必须**在 `service` 层使用 **Pandas** 完成。

**标准数据流（唯一允许的实现路径）**：

```
Model 查询（ORM，只做行级筛选，不做聚合）
   ↓
rows = query.all()
   ↓
df = pd.DataFrame([r.to_dict() for r in rows])   # 转 DataFrame
   ↓
【Pandas 完成】清洗 → 分组 → 聚合 → 排序 → 计算派生指标
   ↓
df.to_dict(orient="records")                      # 转标准 JSON 结构
   ↓
统一响应封装 → 返回
```

**【禁止】**
- **【禁止】直接用 SQL 分组聚合后返回**结果，包括但不限于：
  - `db.session.query(func.sum(...)).group_by(...)`；
  - `SELECT SUM(...), province FROM ... GROUP BY province` 形式的原生/半原生聚合；
  - 在 SQL 层做 `ORDER BY ... LIMIT 10` 得到 TOP10 再直接返回。
- 禁止用纯 Python `for` 循环 + 字典累加代替 Pandas 聚合（失去使用 Pandas 的意义）。

**【允许】** ORM 仅负责"取原始数据行"。`TOP10`、`求和`、`排序`、`去重计数`等**必须在 Pandas 中完成**。

**【必须】** 数据清洗约定统一在 Pandas 中处理：
- 缺失值：`df.dropna(subset=[...])` 或 `fillna(0)`，需注明原因；
- 类型修正：`pd.to_datetime(df["order_date"])`、`astype({"quantity": "int"})`；
- 金额精度：统一 `round(x, 2)`。

---

### 铁则 5：前端可视化必须使用 ECharts

| 项目 | 规定 |
|---|---|
| 图表库 | **【必须】** ECharts 5.4.3（**CDN 引入**，禁止 npm/本地打包） |
| UI 框架 | **【必须】** Bootstrap 5.3.0（**CDN 引入**，**仅用于栅格与基础布局**，禁止覆盖图表主题） |

**【必须】** 所有图表必须启用交互能力：
- **悬浮提示**：`tooltip: { trigger: 'axis' }`（直角坐标系）/ `{ trigger: 'item' }`（饼图），显示具体数值；
- **缩放**：
  - 折线/柱状图配置 `dataZoom: [{ type: 'inside' }, { type: 'slider' }]`；
  - 支持 `toolbox: { feature: { dataZoom: {}, restore: {}, saveAsImage: {} } }`；
- **自适应**：监听 `window.addEventListener('resize', () => chart.resize())`，容器宽度使用百分比。

**【禁止】** 使用 Chart.js、Highcharts、AntV G2 等其他图表库替代 ECharts。

**【建议】** 图表初始化封装为独立 JS 文件 `static/js/charts.js`，通过 `fetch` 调用 API，避免模板内嵌大量 JS。

---

### 铁则 6：模块化分层架构

**【必须】** 代码按 **路由层 / 业务逻辑层 / 数据模型层** 三层严格分离，禁止跨层混写。

| 分层 | 职责 | 禁止事项 |
|---|---|---|
| **路由层** `app/routes/` | 接收请求、校验参数、调用 Service、封装响应 | 禁止写 SQL、禁止写 Pandas、禁止写业务判断 |
| **业务逻辑层** `app/services/` | 编排数据获取、Pandas 清洗聚合、业务规则计算 | 禁止直接操作 `request` / `jsonify` |
| **数据模型层** `app/models/` | 定义表结构、字段、关系、`to_dict()` 序列化 | 禁止写业务流程、禁止调用 Service |
| **工具层** `app/utils/` | 响应封装、数据库连接、日志、通用工具 | 禁止包含业务逻辑 |

**【必须】** 使用 **Flask 蓝图（Blueprint）** 组织路由，禁止把所有路由堆在 `app.py` 里。

**【必须】** 使用 **应用工厂模式** `create_app()`，禁止在模块顶层直接 `app = Flask(__name__)` 后全局散用。

详细目录结构见第 3 章。

---

### 铁则 7：注释与命名规范（高校实验项目标准）

**【必须】** 所有代码添加**详细中文注释**，注释覆盖率要求：

| 位置 | 要求 |
|---|---|
| 文件头部 | 文件说明（功能、作者、创建日期），使用 `"""..."""` 文档字符串 |
| 类 | 类文档字符串，说明用途 |
| 函数 / 方法 | **必须**包含：功能说明、`:param xxx:` 参数说明、`:return:` 返回值说明 |
| 关键逻辑块 | 行内 `#` 注释，解释"为什么这么做"而非"做了什么" |
| 复杂 SQL / Pandas 链式操作 | 每一步链式操作配一行注释 |

**【必须】** 命名规范统一：

| 对象 | 规范 | 正例 | 反例 |
|---|---|---|---|
| 包名 / 模块名 | 小写下划线 `snake_case` | `sales_service.py` | `SalesService.py` |
| 类名 | 大驼峰 `PascalCase` | `SalesOrder` | `sales_order` |
| 函数 / 变量 | 小写下划线 `snake_case` | `get_province_sales` | `getProvinceSales` |
| 常量 | 全大写下划线 | `DEFAULT_PAGE_SIZE` | `defaultPageSize` |
| 数据库表名 / 字段 | 小写下划线，与第 4 章一致 | `sales_order.order_date` | `SalesOrder.OrderDate` |
| 蓝图名 | 小写下划线 | `sales_bp` | `SalesBP` |
| 模板文件 | 小写下划线 `.html` | `index.html` | `Index.html` |
| 静态资源文件 | 小写下划线 | `charts.js` | `Charts.js` |

**【必须】** 前端资源的命名约定（v1.5 明确）：

| 对象 | 规范 | 正例 | 反例 |
|---|---|---|---|
| JS 文件名 | 小写下划线 | `charts.js` | `charts.js` ✓ |
| JS 变量 / 函数名 | **小写下划线 snake_case** | `get_chart_instance` | `getChartInstance` |
| JS 常量 | 全大写下划线 | `API_ENDPOINTS` | `apiEndpoints` |
| DOM `id` | 小写下划线 | `province_chart` | `provinceChart` |
| CSS 类名 | 小写连字符 kebab-case | `chart-box` | `chartBox` |
| CSS 自定义属性 | 小写连字符 | `--color-primary` | `--colorPrimary` |

> 说明：CSS 类名沿用 kebab-case 是前端样式领域的通行写法（BEM / Bootstrap 均如此），
> 与 Python 侧的 snake_case 不冲突；**JS 标识符则统一为 snake_case，与后端保持一致**。

**【例外】** 以下大小写形式不属于违规：
- 模块级单例对象（`db`、`login_manager`、`page_bp`、`api_bp`）：小写，非常量；
- 浏览器原生 API（`matchMedia`、`toLocaleString`、`setAttribute`）：必须保持原样。

**【必须】** 单个函数长度控制在 **50 行以内**，超出必须拆分。

---

### 铁则 8：登录认证与双角色权限控制

> **v1.4 新增（2026-10-17，按用户第 8 轮需求）**

**【必须】** 本项目的**所有页面与所有 API 接口默认要求登录**，不存在匿名可访问的资源。

#### 8.1 用户模型 `User`（表 `user`）

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `user_id` | INT | 主键，自增 | 用户唯一标识 |
| `username` | VARCHAR(50) | NOT NULL，UNIQUE | 用户名 |
| `password_hash` | VARCHAR(255) | NOT NULL | 密码哈希值，**禁止明文存储** |
| `role` | VARCHAR(20) | NOT NULL，默认 `user` | 角色枚举：`admin` / `user` |

**【必须】** `User` 模型须满足：

1. 继承 `UserMixin`（提供 `is_authenticated` 等 Flask-Login 必需属性）；
2. **重写 `get_id()`** 返回 `str(self.user_id)` —— 主键名为 `user_id` 而非 Flask-Login 默认的 `id`，不重写会导致会话无法回查用户；
3. 提供 `set_password()` / `check_password()`，内部调用 `werkzeug.security.generate_password_hash` / `check_password_hash`（pbkdf2 加盐）；
4. 提供 `is_admin` 属性（`role == "admin"`）；
5. `to_dict()` **禁止包含 `password_hash`**，避免哈希外泄到接口或模板。

#### 8.2 认证实现约定

| 项目 | 规定 |
|---|---|
| 会话管理 | **【必须】** Flask-Login 0.6.3 |
| 密码哈希 | **【必须】** `werkzeug.security`（禁止 MD5 / SHA1 裸摘要 / 明文） |
| 注册功能 | **【禁止】** 不提供任何注册入口 |
| 默认账号 | **【必须】** 首次启动时由 `app.py` 自动初始化，已存在则跳过（幂等） |

默认账号（明文密码**仅**出现在 `utils/auth.py` 的 `DEFAULT_ACCOUNTS` 常量中，写入数据库前立即转为哈希）：

| 用户名 | 密码 | 角色 | 可见菜单 |
|---|---|---|---|
| `admin` | `admin123` | `admin` | 数据总览、数据管理 |
| `user` | `user123` | `user` | 数据总览 |

#### 8.3 权限控制约定

**【必须】** 装饰器叠加顺序固定为 `@bp.route` → `@login_required` → `@admin_required`（`@admin_required` 紧贴视图函数）。

| 资源类型 | 未登录 | 已登录但角色不足 |
|---|---|---|
| 页面（`GET /`、`/admin/data` 等） | **302** 重定向到 `/login?next=<原路径>` | **403** JSON `{"code":403,...}` |
| 接口（`/api/**`） | **401** JSON `{"code":401,"msg":"登录已失效，请重新登录"}` | **403** JSON |

> **401 而非 302 的原因**：若接口返回 302，前端 `fetch` 会拿到登录页 HTML，`JSON.parse` 直接失败，
> 图表区只会显示"数据加载失败"，无法区分"未登录"与"接口报错"。

**【必须】** 查询类 API（`/api/sales/*`）仅需 `@login_required`，**不加** `@admin_required`；
管理类接口（后续扩展）叠加 `@admin_required`。

#### 8.4 安全约定（强制执行）

1. **开放重定向防护【必须】**：登录后的 `next` 跳转地址须经 `is_safe_next_url()` 校验 ——
   排除带 `netloc` 的绝对地址与 `//` 开头的协议相对地址，且必须以单个 `/` 开头；校验失败回退首页。
2. **账号枚举防护【必须】**：用户名不存在与密码错误须返回**同一句**提示（"用户名或密码错误"）。
3. **密钥管理【必须】**：`FLASK_SECRET_KEY` 存于 `.env`，禁止硬编码；`.env` 已在 `.gitignore` 中。
4. **【禁止】** 在任何日志、`to_dict()`、接口响应中出现 `password_hash` 或明文密码。

#### 8.5 前端渲染约定（Jinja2 条件判断）

**【必须】** 侧边栏菜单与顶部用户栏由 `{% if current_user.is_authenticated %}` / `{% if current_user.role in item.roles %}` 驱动：

| 位置 | 要求 |
|---|---|
| `templates/base.html` | 侧边栏用 `{% for item in nav_items %}` + `{% if current_user.role in item.roles %}` 动态渲染 |
| `templates/base.html` | 顶部显示用户名首字母头像、用户名、角色徽章、退出登录按钮；未登录时整块不渲染 |
| `templates/login.html` | **【必须】** `{% extends "base.html" %}`；`{% if error_msg %}` 渲染错误提示；表单 action 携带 `next` |
| 导航数据来源 | 由 `utils/auth.py` 的 `NAV_ITEMS` 经 `context_processor` 注入，路由层不再单独传参 |

---

### 铁则 9：异常处理与降级提示

> **v1.5 新增（2026-10-17，按用户「最终优化」要求）**

**【必须】** 任何异常都不得让用户面对「空白页面」或「原始报错堆栈」。三类场景的强制约定如下。

#### 9.1 数据库连接失败

| 环节 | 强制做法 |
|---|---|
| 启动检测 | **【必须】** `create_app()` 内调用 `check_database(app)` 执行一次连通性探测，结果写入 `app.config["DB_AVAILABLE"]` |
| 页面提示 | **【必须】** `base.html` 依据 `db_available` 在页面顶部渲染红色「数据库连接异常」提示条，并给出排查步骤 |
| 登录降级 | **【必须】** 登录接口捕获数据库异常，返回「数据库服务不可用，请检查 MySQL 是否已启动」而非 500 |
| 会话降级 | **【必须】** `user_loader` 捕获数据库异常后返回 `None`（视为未登录），避免已登录用户被 500 中断 |
| 建表失败 | **【必须】** `init_database()` 只记录告警不中断启动，并写入 `app.config["DB_TABLES_READY"]` |

#### 9.2 API 调用失败

| 环节 | 强制做法 |
|---|---|
| 后端 | **【必须】** 每个 API 路由 `try...except` 兜底，记录日志并返回 `code=500` 与精简错误描述 |
| 前端通用失败 | **【必须】** `show_empty()` 在图表容器内展示失败标题与原因，禁止留白 |
| 前端 401 | **【必须】** 识别 `error.code === 401`，提示「登录已失效」并在 1.5 秒后自动跳转 `/login?next=<当前路径>`；**4 个图表只跳转一次** |
| 前端 404 / 500 | **【必须】** 后端对 `/api/` 路径返回 JSON 信封，对页面路径渲染 `error.html` |

#### 9.3 数据为空

| 位置 | 强制做法 |
|---|---|
| 图表 | **【必须】** 展示「暂无 XX 数据」空态提示，而不是空容器 |
| 首页卡片 | **【必须】** `{% for %}...{% else %}` 分支提示「数据卡片加载失败」 |
| 数据管理表格 | **【必须】** 跨列居中显示空态文案；有关键字时提示「未找到与「XX」匹配的数据」 |
| 分页 | **【必须】** 无数据时仍返回结构完整的分页信息（由 `build_empty_pagination()` 提供） |

#### 9.4 全局错误处理器

**【必须】** `create_app()` 内调用 `register_error_handlers(app)` 注册 404 与 500 处理器，
按路径分流：`/api/**` 返回 JSON；其余渲染 `templates/error.html`。

---

## 2. 精准技术栈与版本清单

### 2.1 版本锁定清单（Pin 版本，禁止随意升降）

| 组件 | 版本 | 说明 |
|---|---|---|
| Python | **3.9** | 基础运行时（建议 3.9.x 最新补丁版） |
| Flask | **2.3.3** | Web 框架 |
| Flask-SQLAlchemy | **3.1.1** | ORM 扩展 |
| PyMySQL | **1.1.0** | MySQL 驱动 |
| pandas | **2.0.3** | 数据处理 |
| python-dotenv | **1.0.0** | 环境变量管理 |
| Flask-Login | **0.6.3** | 会话登录与角色权限（v1.4 新增） |
| ECharts | **5.4.3** | 前端图表（CDN） |
| Bootstrap | **5.3.0** | 前端布局（CDN） |

### 2.2 传递依赖约束（已知兼容性风险，必须同时锁定）

| 包 | 约束 | 原因 |
|---|---|---|
| `SQLAlchemy` | `>=2.0,<2.1` | Flask-SQLAlchemy 3.1.1 要求 SQLAlchemy 2.x |
| `numpy` | **`<2.0`** | ⚠️ pandas 2.0.3 编译于 NumPy 1.x ABI，pip 默认装 NumPy 2.x 会导致 `ImportError: numpy.dtype size changed` |
| `Werkzeug` | `>=2.3,<2.4` | Flask 2.3.3 官方配套约束 |
| `Jinja2` | `>=3.1,<3.2` | Flask 2.3.3 官方配套约束 |

### 2.3 requirements.txt 标准内容

```txt
# ===== 电商销售数据可视化平台 · 依赖清单 =====
# Web 框架
Flask==2.3.3
Werkzeug==2.3.7
Jinja2==3.1.2

# 登录认证（v1.4 新增）
Flask-Login==0.6.3

# 数据库 ORM
Flask-SQLAlchemy==3.1.1
SQLAlchemy==2.0.21
PyMySQL==1.1.0
cryptography==41.0.4

# 数据处理
pandas==2.0.3
numpy==1.26.4

# 配置管理
python-dotenv==1.0.0
```

> **【必须】** 安装时使用 `python -m pip install -r requirements.txt`，安装后执行 `python -c "import flask, pandas, sqlalchemy; print(flask.__version__, pandas.__version__)"` 验证。

### 2.4 CDN 引入地址（固定写法）

```html
<!-- Bootstrap 5.3.0：仅做栅格与基础布局 -->
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">

<!-- ECharts 5.4.3：图表库 -->
<script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
```

> **【v1.3：本地兜底已实现】** `templates/base.html` 采用「CDN 优先 + 本地回退」策略：
> 先加载 CDN 的 `echarts@5.4.3`，随后用一行内联脚本判断 `window.echarts` 是否存在，
> 不存在则同步插入本地副本 `static/vendor/echarts.min.js`（该文件已实际下载入库）。
> **该策略无需任何开关，离线环境下自动生效，且不牺牲在线时的 CDN 加载速度。**
>
> 采用 `document.write` 同步插入的原因：必须保证 ECharts 在 `charts.js` 执行前就绪，
> 异步插入会破坏脚本执行顺序。插入路径由 `url_for` 生成，不含用户输入，无注入风险。

### 2.5 版本兼容问题处理策略

**【必须】** 遇到版本兼容问题时，按以下顺序处理：
1. 先尝试通过**锁定传递依赖版本**解决（见 2.2）；
2. 若需**变更主版本清单**（第 2.1 节），**必须停止操作，以问答方式询问用户确认**；
3. 得到用户明确确认后，同步更新本文件对应章节，再执行安装。

---

## 3. 目录结构与模块划分

> **v1.1 变更（2026-10-17，经用户确认）**：采用「平铺式目录」替代原 `app/` 包结构。
> 三层分离（models / services / routes）、应用工厂 `create_app()`、蓝图注册**全部保留**，
> 与铁则 6 完全兼容：`create_app()` 位于 `app.py` 内，数据库单例 `db` 位于 `models/__init__.py`。

```
three_project/
├── rule.md                         # 【本文档】开发规则
└── ecommerce_sales/                # 项目根目录
    ├── app.py                      # 入口：应用工厂 create_app() + 自动建表 + 蓝图注册 + 启动入口
    ├── config.py                   # 配置类：从 .env 读取，禁止硬编码
    ├── generate_data.py            # 模拟数据生成脚本（命令行参数化）
    ├── requirements.txt            # 依赖清单（版本锁定）
    ├── .env                        # 环境变量（真实配置，加入 .gitignore）
    ├── .env.example                # 环境变量示例（不含真实密码，可提交）
    ├── .gitignore
    │
    ├── models/                     # 【数据模型层】
    │   ├── __init__.py             # 数据库单例 db = SQLAlchemy() + 模型统一导出（含 User）
    │   └── db_models.py            # 四张表的模型定义：User / Category / Product / SalesOrder
    │
    ├── services/                   # 【业务逻辑层】Pandas 聚合核心
    │   ├── __init__.py
    │   ├── data_service.py         # 总览卡片 + 省份/趋势/品类/TOP10 统计
    │   └── admin_service.py        # 【v1.5】管理员数据管理：概览指标 +
    │                               #  品类/商品/订单明细（搜索+排序+分页，全走 Pandas）
    │
    ├── routes/                     # 【路由层】
    │   ├── __init__.py             # 蓝图统一导出（page_bp / api_bp）
    │   ├── page_routes.py          # 页面路由：/ /login /logout /admin/data
    │   └── api_routes.py           # API 路由：/api/sales/*（均需登录）
    │
    ├── utils/                      # 【工具层】
    │   ├── __init__.py
    │   ├── response.py             # 统一 JSON 响应封装 ok() / fail()
    │   ├── auth.py                 # 【v1.4】登录管理器、角色常量、默认账号、
    │   │                           #          NAV_ITEMS、admin_required 装饰器
    │   └── format_filters.py       # 【v1.5】Jinja2 过滤器：money/int/percent/cell
    │
    ├── templates/                  # Jinja2 模板
    │   ├── base.html               # 父模板：布局骨架 + 角色动态侧边栏 + 顶部用户栏
    │   │                           #          + 数据库异常提示条
    │   ├── index.html              # 子模板：extends base.html，数据看板
    │   ├── login.html              # 【v1.4】登录页：extends base.html
    │   ├── admin_data.html         # 【v1.5】管理员「数据管理」页：三表明细浏览
    │   └── error.html              # 【v1.5】404 / 500 友好错误页
    │
    ├── static/
    │   ├── css/
    │   │   └── style.css           # 自定义样式（侧边栏、卡片、顶部栏、登录页）
    │   ├── js/
    │   │   └── charts.js           # ECharts 图表初始化与交互（4 个 init 函数）
    │   └── vendor/
    │       └── echarts.min.js      # ECharts 本地副本（CDN 不可用时自动回退）
    │
    └── design-system/              # UI UX Pro Max 设计系统令牌
        └── ecommercedashboard/MASTER.md
    └── data/                       # 数据脚本
        └── init_db.py              # 建库（CREATE DATABASE）+ 建表脚本
```

### 3.1 关键设计说明

| 关注点 | 约定 |
|---|---|
| `db` 单例位置 | 定义在 `models/__init__.py`，供模型文件与 `app.py` 共用，避免循环导入 |
| 应用工厂 | `create_app(config_name=None)` 定义在 `app.py`，返回配置完成的 Flask 实例 |
| 蓝图注册 | `register_blueprints(app)` 定义在 `app.py`，集中注册 `page_bp` 与 `api_bp` |
| 建表时机 | `create_app()` 内只做 `db.init_app(app)` 绑定，**建表由 `data/init_db.py` 独立脚本执行** |
| 中文与字段序 | `app.json.ensure_ascii = False`、`app.json.sort_keys = False`（Flask 2.3 起由 `app.json` 配置） |
| 登录管理器初始化 | **【v1.4】** `create_app()` 内调用 `init_login_manager(app)`，注册 `user_loader` / `unauthorized_handler` / `context_processor` |
| 默认账号初始化 | **【v1.4】** `create_app()` 内调用 `init_default_users(app)`，幂等写入 `admin` / `user`，失败仅告警不阻塞启动 |
| 过滤器注册 | **【v1.5】** `create_app()` 内调用 `register_filters(app)`，注册 `money` / `int_comma` / `percent` / `cell` 四个 Jinja2 过滤器 |
| 数据库连通性 | **【v1.5】** `check_database(app)` 启动时探测一次，结果注入模板变量 `db_available`（见铁则 9.1） |
| 错误处理器 | **【v1.5】** `register_error_handlers(app)` 接管 404 / 500，按路径分流 JSON 与错误页（见铁则 9.4） |
| 模板上下文 | **【v1.5】** `register_template_context(app)` 向所有模板注入 `db_available` |

---

## 4. 数据库设计说明书

### 4.1 数据库基本要求

| 项目 | 规定 |
|---|---|
| 数据库名 | `ecommerce_db` |
| 字符集 | `utf8mb4` |
| 排序规则 | `utf8mb4_unicode_ci` |
| 表数量 | **4 张**（v1.4 新增 `user`；原 3 张业务表 category / product / sales_order） |
| 表引擎 | InnoDB |
| 关联关系 | 支持多表关联查询：`category ← product ← sales_order` |

**【必须】** 表结构通过 Flask-SQLAlchemy Model 定义，脚本仅负责 `db.create_all()`。

### 4.2 表结构定义

#### 表 1：品类表 `category`

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `category_id` | INT | 主键，自增 | 品类唯一标识 |
| `category_name` | VARCHAR(50) | NOT NULL | 品类名称（手机、电脑、服装、食品、家居） |

> 注：题目给出的字段清单中未包含状态/时间字段，**严格按题面实现，禁止擅自增加字段**。如需扩展须先询问用户。

#### 表 2：商品表 `product`

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `product_id` | INT | 主键，自增 | 商品唯一标识 |
| `product_name` | VARCHAR(100) | NOT NULL | 商品名称 |
| `category_id` | INT | 外键 → `category.category_id`，NOT NULL | 所属品类 |
| `price` | FLOAT | NOT NULL | 商品单价 |

> **浮点字段映射约定（v1.2 调整）**：用户明确要求金额字段使用 `Float`，
> 因此 SQLAlchemy 侧统一使用 `db.Float`（MySQL 侧映射为 `FLOAT`）。
> 已知影响：`FLOAT` 为近似数值类型，大批量求和时与精确值存在微小误差
> （实测 1500 条订单总额误差约 0.17 元）。
> 补偿措施：生成数据时统一 `round(2)`，统计时在 Pandas 层再次 `round(2)` 后输出。

#### 表 3：订单表 `sales_order`

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `order_id` | INT | 主键，自增 | 订单唯一标识 |
| `product_id` | INT | 外键 → `product.product_id`，NOT NULL | 关联商品 |
| `quantity` | INT | NOT NULL | 购买数量 |
| `total_amount` | FLOAT | NOT NULL | 订单总金额 |
| `province` | VARCHAR(50) | NOT NULL | 省份（全国 31 个省份随机分布） |
| `city` | VARCHAR(50) | NOT NULL | 城市 |
| `order_date` | DATE | NOT NULL，建索引 | 下单日期 |

> **【建议】** 为高频查询字段建立索引：`product_id`、`order_date`、`province`。

#### 表 4：用户表 `user`（v1.4 新增，详见铁则 8）

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `user_id` | INT | 主键，自增 | 用户唯一标识 |
| `username` | VARCHAR(50) | NOT NULL，UNIQUE | 用户名 |
| `password_hash` | VARCHAR(255) | NOT NULL | 密码哈希（werkzeug pbkdf2 加盐） |
| `role` | VARCHAR(20) | NOT NULL，默认 `user` | 角色枚举 `admin` / `user` |

> 该表为认证专用，**不与三张业务表建立外键关联**。

### 4.3 ER 关系说明

```
category (1) ──< (N) product (1) ──< (N) sales_order

user（独立，无外键关联）
```

- 一个品类包含多个商品（`category.category_id = product.category_id`）；
- 一个商品对应多笔订单（`product.product_id = sales_order.product_id`）；
- 省份统计、品类统计、TOP10 商品统计均需通过 **JOIN 多表关联** 取数后再交给 Pandas 聚合。

### 4.4 Model 实现约定

```python
# app/models/sales_order.py
class SalesOrder(db.Model):
    """订单表模型：记录每一笔销售订单的核心信息"""
    __tablename__ = "sales_order"

    order_id = db.Column(db.Integer, primary_key=True, autoincrement=True, comment="订单ID，主键自增")
    product_id = db.Column(db.Integer, db.ForeignKey("product.product_id"), nullable=False, comment="商品ID，外键")
    quantity = db.Column(db.Integer, nullable=False, comment="购买数量")
    total_amount = db.Column(db.Numeric(12, 2), nullable=False, comment="订单总金额")
    province = db.Column(db.String(50), nullable=False, comment="省份")
    city = db.Column(db.String(50), nullable=False, comment="城市")
    order_date = db.Column(db.Date, nullable=False, index=True, comment="下单日期")

    def to_dict(self) -> dict:
        """将模型对象转换为字典，便于 Pandas 构造 DataFrame"""
        return {
            "order_id": self.order_id,
            "product_id": self.product_id,
            "quantity": self.quantity,
            "total_amount": float(self.total_amount) if self.total_amount else 0.0,
            "province": self.province,
            "city": self.city,
            "order_date": self.order_date.strftime("%Y-%m-%d") if self.order_date else None,
        }
```

**【必须】** 每个 Model 都必须实现 `to_dict()` 方法，作为 ORM → Pandas 的标准转换入口。

### 4.5 模拟数据要求

| 表 | 数据量建议 |
|---|---|
| `category` | 5 条（手机、电脑、服装、食品、家居） |
| `product` | **20 条**（v1.2 调整，原为 40~60 条），随机分布于 5 个品类，各品类数量不平均 |
| `sales_order` | **1500 条**（v1.2 调整，原为 3000~5000 条） |

- **省份**：覆盖全国 **31 个省份**（不含港澳台，按中国行政区划规范表述），按幂律权重抽样，区域销量高低差异明显；
- **日期**：`order_date` 覆盖**最近 3 个月（90 天）**，叠加「缓慢增长 + 周末上浮」权重；
- **金额一致性**：`total_amount = price × quantity`，生成时须保证数据自洽并 `round(2)`；
- **随机可复现**：生成脚本使用固定随机种子（默认 `random.seed(42)`），可通过 `--seed` 覆盖；
- **分布要求**：数据**不得平均分配**，须通过 `random.random() ** power + base` 的幂律权重形成明显的高低区分。

---

## 5. API 接口定义清单

### 5.1 接口总览

| 接口路径 | 请求方式 | 功能描述 | 访问权限 | 响应数据结构 |
|---|---|---|---|---|
| `/login` | GET / POST | 登录页 / 提交登录 | 匿名可访问 | 页面 / 302 |
| `/logout` | GET | 退出登录 | 需登录 | 302 → `/login` |
| `/` | GET | 看板首页，渲染 HTML | **需登录** | 页面（`index.html`） |
| `/admin/data` | GET | 数据管理（占位页） | **需登录 + 管理员** | 页面（`admin_data.html`） |
| `/api/sales/province` | GET | 按省份统计销售额 | **需登录** | `[{name: 省份, value: 销售额}]` |
| `/api/sales/trend` | GET | 按日期统计每日销量趋势 | **需登录** | `[{date: 日期, sales: 销售额}]` |
| `/api/sales/category` | GET | 按品类统计销售额占比 | **需登录** | `[{name: 品类, value: 销售额}]` |
| `/api/sales/top` | GET | 销量 TOP10 商品 | **需登录** | `[{name: 商品名, value: 销量}]` |

### 5.2 统一响应格式

```json
{
  "code": 200,
  "msg": "success",
  "data": []
}
```

### 5.3 接口详细说明

#### 5.3.1 `GET /` — 看板首页

- **功能**：渲染数据可视化看板 HTML 页面
- **返回**：HTML 页面（`templates/index.html`）
- **传递变量（体现 Jinja2 变量传递）**：

| 变量名 | 类型 | 说明 |
|---|---|---|
| `page_title` | str | 页面标题 |
| `nav_items` | list[dict] | 侧边栏导航菜单（配合 `{% for %}` 循环渲染） |
| `cards` | list[dict] | 顶部 4 个数据卡片（配合 `{% for %}` 循环渲染） |

**卡片数据定义**：

| 卡片 | 字段 | 计算口径 |
|---|---|---|
| 总销售额 | `total_sales` | `df["total_amount"].sum()` |
| 总订单量 | `total_orders` | `len(df)`（订单行数） |
| 商品总数 | `product_count` | `product` 表记录数 |
| 覆盖省份数 | `province_count` | `df["province"].nunique()` |

#### 5.3.2 `GET /api/sales/province` — 省份销售额统计

- **处理流程**：`sales_order` 全量取数 → Pandas `groupby("province")["total_amount"].sum()` → 降序排序
- **响应示例**：

```json
{"code": 200, "msg": "success", "data": [{"name": "广东省", "value": 128345.5}, {"name": "江苏省", "value": 110234.0}]}
```

- **字段**：`name`(str) 省份名称、`value`(float) 销售额，保留 2 位小数

#### 5.3.3 `GET /api/sales/trend` — 每日销售趋势

- **处理流程**：`order_date` 转 datetime → `groupby("order_date")["total_amount"].sum()` → 按日期升序
- **响应示例**：

```json
{"code": 200, "msg": "success", "data": [{"date": "2026-01-01", "sales": 8934.0}]}
```

- **字段**：`date`(str, `YYYY-MM-DD`)、`sales`(float) 当日销售额

#### 5.3.4 `GET /api/sales/category` — 品类销售占比

- **处理流程**：`sales_order JOIN product JOIN category`（**多表关联**）→ Pandas `groupby("category_name")["total_amount"].sum()`
- **响应示例**：

```json
{"code": 200, "msg": "success", "data": [{"name": "手机", "value": 234567.0}]}
```

- **字段**：`name`(str) 品类名称、`value`(float) 销售额；饼图自动换算百分比

#### 5.3.5 `GET /api/sales/top` — 商品销量 TOP10

- **处理流程**：`sales_order JOIN product` → Pandas `groupby("product_name")["quantity"].sum()` → `sort_values(descending=True).head(10)`
- **响应示例**：

```json
{"code": 200, "msg": "success", "data": [{"name": "iPhone 15", "value": 328}]}
```

- **字段**：`name`(str) 商品名称、`value`(int) 累计销量

### 5.4 业务状态码约定

| code | 含义 | 使用场景 |
|---|---|---|
| 200 | 成功 | 正常返回 |
| 400 | 请求参数错误 | 参数缺失或格式非法 |
| 401 | **未登录**（v1.4） | 接口未携带有效会话 |
| 403 | **权限不足**（v1.4） | 已登录但角色非 admin |
| 404 | 资源不存在 | 路径错误 |
| 500 | 服务端异常 | 数据库异常 / Pandas 处理异常 |

> **【必须】** 401 / 403 与 HTTP 状态码保持一致（响应信封的 `code` 与 HTTP status 相同）。
> 页面场景的 401 表现为 302 跳转登录页，403 仍返回 JSON（管理页为普通 GET 访问，直接展示 JSON 提示即可）。

---

## 6. 页面功能与布局说明

### 6.1 整体布局

采用 **左侧侧边栏 + 右侧主内容区** 的后台管理布局。

```
```
┌──────────────┬──────────────────────────────────────────┐
│              │ 顶栏：[头像 用户名 角色徽章] [退出登录]   │
│  系统标题     ├──────────────────────────────────────────┤
│              │  顶部：4 个数据卡片                      │
│  导航菜单     ├──────────────────────────────────────────┤
│  - 数据总览   │  第一行：[省份柱状图 60%] [品类饼图 40%]  │
│  - 数据管理   ├──────────────────────────────────────────┤
│   （仅管理员）│  第二行：[每日销售趋势折线图 100%]        │
│              ├──────────────────────────────────────────┤
│              │  第三行：[商品销量 TOP10 横向柱状图 100%] │
└──────────────┴──────────────────────────────────────────┘
```

#### 侧边栏（Sidebar）

- **系统标题**：`电商销售数据可视化平台`
- **导航菜单**：使用 `{% for %}` 循环渲染，当前项高亮
- **【必须】** 菜单项通过 `{% if current_user.role in item.roles %}` 按角色过滤：
  - 管理员（`admin`）：数据总览、数据管理
  - 普通用户（`user`）：仅数据总览
- **【必须】** 未登录时整个侧边栏不渲染（`{% if current_user.is_authenticated %}`）

#### 顶部用户栏（v1.4 新增）

- **【必须】** 显示用户名首字母头像、`{{ current_user.username }}`、角色徽章（管理员 / 普通用户）、退出登录按钮
- **【必须】** 使用 Jinja2 条件判断区分角色样式：`{% if current_user.is_admin %}管理员{% else %}普通用户{% endif %}`

#### 主内容区（Main Content）

| 区域 | 内容 | 宽度 | 图表类型 |
|---|---|---|---|
| 顶部卡片区 | 总销售额、总订单量、商品总数、覆盖省份数 | 4 × 25%（`col-md-3`） | 纯数据卡片 |
| 第一行 | 省份销售柱状图 + 品类占比饼图 | 60% / 40%（`col-md-7` / `col-md-5`） | 柱状图 / 饼图 |
| 第二行 | 每日销售趋势折线图 | 100%（`col-12`） | 折线图 |
| 第三行 | 商品销量 TOP10 排行榜 | 100%（`col-12`） | 横向柱状图 |

### 6.2 图表配置要求

| 图表 | ECharts 配置要点 |
|---|---|
| **省份柱状图** | `xAxis` 省份（45° 倾斜），`yAxis` 销售额，`tooltip: {trigger:'axis'}` |
| **品类饼图** | 环形 `radius: ['40%','70%']`，`tooltip: {trigger:'item', formatter:'{b}: {c} ({d}%)'}`，含图例 |
| **趋势折线图** | `smooth: true`，`areaStyle` 渐变填充，`dataZoom: [{type:'inside'},{type:'slider'}]` |
| **TOP10 横向柱状图** | `yAxis.type='category'`（inverse），`xAxis.type='value'`，`itemStyle` 渐变色 |

**【必须】** 全部图表：
1. 悬浮显示具体数值（`tooltip`）；
2. 自适应页面宽度（`resize` 监听 + 百分比容器）。

### 6.3 Jinja2 三大特性落地位置（对照铁则 1）

| 特性 | 落地文件 | 具体写法 |
|---|---|---|
| 模板继承 | `templates/base.html` / `index.html` | `{% extends "base.html" %}`；父模板定义 `{% block title %}`、`{% block content %}`、`{% block scripts %}`、`{% block sidebar %}` |
| 变量传递 | `routes/page_routes.py` → `index.html` | `render_template("index.html", page_title=..., cards=...)`；模板中 `{{ page_title }}` |
| 循环渲染 | `templates/base.html` / `index.html` | 侧边栏 `{% for item in nav_items %}`；卡片区 `{% for card in cards %}` |
| **条件渲染**（v1.4） | `templates/base.html` | 侧边栏可见性 `{% if current_user.role in item.roles %}`；登录态 `{% if current_user.is_authenticated %}`；角色徽章 `{% if current_user.is_admin %}` |
| **条件渲染**（v1.4） | `templates/login.html` | `{% if error_msg %}` 渲染登录失败提示 |

> **【说明】** `nav_items` 改由 `utils/auth.py` 的 `NAV_ITEMS` 经 `context_processor` 全局注入，
> 路由层不再单独传参，保证所有继承 `base.html` 的页面侧边栏一致。

### 6.4 数据管理页布局（v1.5）

仅管理员可见，`GET /admin/data`，支持 `tab` / `keyword` / `page` / `per_page` / `sort_by` / `order` 六个查询参数。

```
┌──────────────┬──────────────────────────────────────────┐
│              │ 顶栏：[头像 用户名 角色徽章] [退出登录]   │
│  系统标题     ├──────────────────────────────────────────┤
│              │ 概览卡片区：7 个指标（品类/商品/订单数、  │
│  导航菜单     │   销售额、客单价、省份数、日期跨度）      │
│  - 数据总览   ├──────────────────────────────────────────┤
│  - 数据管理   │ 页签：[品类数据][商品数据][订单数据]      │
│   （仅管理员）│       + 搜索框（按各表名称字段模糊匹配）   │
│              ├──────────────────────────────────────────┤
│              │ 数据表格（表头点击排序，支持升降序切换）   │
│              ├──────────────────────────────────────────┤
│              │ 分页器：共 N 条 · 第 x/y 页 [上一页][下一页]│
└──────────────┴──────────────────────────────────────────┘
```

**【必须】** 实现约定：

1. 页签与表格列的定义集中在 `routes/page_routes.py` 的 `TAB_CONFIG` 中，
   模板只做 `{% for %}` 渲染，新增一张表的浏览页无需改动模板结构；
2. **统计、搜索、排序、分页全部在 `services/admin_service.py` 用 Pandas 完成**
   （排序用 `sort_values`，分页用 `iloc` 切片），符合铁则 4；
3. 排序列名必须经白名单校验（`_sort_dataframe`），防止传入非法列名导致 500；
4. 分页参数必须做类型收敛（`_safe_int`），`per_page` 上限 `MAX_PER_PAGE = 100`，
   超出总页数的页码自动收敛到最后一页；
5. 单元格格式化统一交给 `cell` 过滤器，禁止在模板中写格式化逻辑。

---

## 7. 编码规范补充

### 7.1 导入顺序（PEP 8）

```python
# 1. 标准库
import os
from datetime import datetime

# 2. 第三方库
import pandas as pd
from flask import Blueprint, jsonify, render_template

# 3. 本地应用
from app.extensions import db
from app.models import SalesOrder
from app.services import sales_service
```

### 7.2 异常处理

**【必须】** 每个路由函数：

```python
@sales_bp.route("/api/sales/province", methods=["GET"])
def get_province_sales():
    """获取各省份销售额统计（接口：GET /api/sales/province）"""
    try:
        data = sales_service.get_sales_by_province()
        return ok(data)
    except Exception as e:
        # 记录异常日志，返回统一错误响应，避免堆栈外泄
        current_app.logger.error(f"[省份统计] 接口异常: {e}", exc_info=True)
        return fail(msg=f"服务器内部错误: {str(e)}", code=500)
```

### 7.3 配置管理（.env）

```ini
# .env.example（提交到仓库，不含真实值）
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=root
DB_PASSWORD=
DB_NAME=ecommerce_db
FLASK_ENV=development
SECRET_KEY=please-change-me
```

**【禁止】** 将 `.env` 提交到版本库；`.gitignore` 必须包含 `.env`、`__pycache__/`、`*.pyc`、`.venv/`。

### 7.4 Service 层标准实现范式（Pandas 聚合示例）

```python
def get_sales_by_province() -> list:
    """
    按省份统计销售额（使用 Pandas 完成聚合计算）

    :return: [{"name": 省份, "value": 销售额}, ...]
    """
    # 1. ORM 取原始行数据（不做任何分组聚合）
    rows = SalesOrder.query.all()
    if not rows:
        return []

    # 2. 转换为 DataFrame
    df = pd.DataFrame([r.to_dict() for r in rows])

    # 3. 数据清洗：金额转数值，缺失值补 0
    df["total_amount"] = pd.to_numeric(df["total_amount"], errors="coerce").fillna(0.0)

    # 4. Pandas 聚合：按省份分组求和
    result = df.groupby("province", as_index=False)["total_amount"].sum()

    # 5. 排序 + 精度处理
    result = result.sort_values("total_amount", ascending=False)
    result["total_amount"] = result["total_amount"].round(2)

    # 6. 统一字段命名后返回
    result = result.rename(columns={"province": "name", "total_amount": "value"})
    return result.to_dict(orient="records")
```

---

## 8. 交付物与验收自检清单（Definition of Done）

任务完成前，Agent 必须逐项自检，**全部通过后方可交付**：

### 铁则符合性

- [ ] 后端为 Flask，模板为 Jinja2，且**同时**体现继承 / 变量传递 / 循环渲染
- [ ] 使用 MySQL + Flask-SQLAlchemy，代码中**无任何原生 SQL 拼接**
- [ ] 接口为 RESTful 风格，所有 JSON 接口返回 `{code, msg, data}`
- [ ] 统计逻辑**全部经 Pandas** 完成，无 `func.sum` / `GROUP BY` 聚合
- [ ] 图表全部使用 ECharts 5.4.3 CDN，均含 `tooltip` 与自适应
- [ ] 代码按 routes / services / models / utils 分层，使用蓝图与应用工厂
- [ ] 全部注释为中文，命名统一 `snake_case` / `PascalCase`
- [ ] **【v1.4】** 所有页面与接口默认要求登录；密码为哈希存储，无明文
- [ ] **【v1.4】** 接口未登录返回 401 JSON，页面未登录 302 跳登录页
- [ ] **【v1.4】** 普通用户访问管理资源返回 403；`next` 参数通过安全校验

### 数据与服务

- [ ] 4 张表结构符合第 4 章定义（含 `user` 表），业务表含外键与多表 JOIN
- [ ] 模拟数据覆盖 31 个省份，订单量 1500（v1.2 调整）
- [ ] 4 个查询接口登录后均可正常访问并返回预期结构

### 页面

- [ ] 侧边栏 + 主内容区布局正确
- [ ] 4 个数据卡片数值正确
- [ ] 4 个图表（柱 / 饼 / 折线 / 横向柱）全部渲染且可交互
- [ ] **【v1.4】** 登录页可正常登录；顶部显示用户名与退出按钮
- [ ] **【v1.4】** 管理员可见「数据管理」，普通用户不可见
- [ ] **【v1.5】** 数据管理页三个页签均可浏览，搜索 / 排序 / 分页正常
- [ ] **【v1.5】** 数据库不可用时页面顶部显示异常提示条，登录页给出友好提示
- [ ] **【v1.5】** 404 / 500 渲染友好错误页，接口路径返回 JSON
- [ ] **【v1.5】** 全部 Python 文件含模块 / 类 / 函数文档字符串与 `:param:` `:return:`
- [ ] **【v1.5】** 文件名、Python 标识符、JS 标识符、DOM id 统一 snake_case；CSS 类名 kebab-case

### 文档

- [ ] `README.md` 含环境准备、启动步骤、功能说明、截图位
- [ ] `requirements.txt` 版本锁定无误

---

## 9. 变更控制

1. **【必须】** 任何对本文档的修改，需经用户确认后执行，并在文末"修订记录"中登记。
2. 若实现过程中发现规范存在技术性缺陷，应**先提出问题与建议方案，等用户确认后再改规则、再改代码**。

---

## 10. 修订记录

| 日期 | 版本 | 修订内容 | 修订人 |
|---|---|---|---|
| 2026-10-17 | v1.0 | 初始版本：依据用户需求整理 7 条硬性规范、技术栈版本、数据库设计、API 清单、页面布局 | — |
| 2026-10-17 | v1.1 | 第 3 章目录结构改为平铺式（项目根 `ecommerce_sales/`，入口 `app.py`），保留三层分离、应用工厂与蓝图；新增 3.1 节关键设计说明。经用户确认后执行 | 用户确认 |
| 2026-10-17 | v1.2 | ① 金额字段由 DECIMAL 改为 `db.Float`（按用户明确要求，已记录 FLOAT 精度影响与补偿措施）；② 模拟数据量由「商品 40~60 / 订单 3000~5000」调整为「商品 20 / 订单 1500」；③ 目录结构同步 `db_models.py` 与 `generate_data.py` 的实际位置 | 用户确认 |
| 2026-10-17 | v1.3 | 前端可视化落地：① 引入 UI UX Pro Max 设计系统（Data-Dense Dashboard，density 8 / variance 5 / motion 3），令牌持久化于 `design-system/ecommercedashboard/MASTER.md`；② 新增 `static/js/charts.js`（4 个图表各一个 init 函数 + fetch 联调）、重写 `style.css` / `base.html` / `index.html`；③ ECharts 实现 CDN + 本地 `static/vendor/` 自动回退 | 用户指定 |
| 2026-10-17 | v1.4 | 登录认证与双角色权限控制：① 新增**铁则 8**（User 模型、Flask-Login 0.6.3、werkzeug 哈希、默认账号 admin/user、装饰器叠加顺序、401/403 分流、Open Redirect 与账号枚举防护、Jinja2 条件渲染约定）；② 新增 `utils/auth.py`（login_manager / NAV_ITEMS / `admin_required` / `is_safe_next_url`）；③ 新增 `templates/login.html` 与 `templates/admin_data.html`，`base.html` 改为按角色动态渲染侧边栏 + 顶部用户栏；④ 4 个查询接口加 `@login_required`；⑤ 依赖新增 `Flask-Login==0.6.3`；⑥ 第 4 章表数量 3→4（新增 `user` 表）；⑦ 第 5 章接口表增加「访问权限」列，状态码新增 401/403 | 用户指定 |
| 2026-10-17 | v1.5 | 最终优化（高校实验评分标准对齐）：① 新增**铁则 9**（数据库连接失败 / API 调用失败 / 数据为空三类场景的强制降级约定，含全局 404·500 错误处理器）；② 管理员功能建设：`services/admin_service.py`（概览指标 + 品类/商品/订单明细，搜索·排序·分页全走 Pandas）与重写 `templates/admin_data.html`（页签 + 概览卡片 + 表格 + 分页器）；③ 新增 `utils/format_filters.py`（Jinja2 `cell` 过滤器，模板零格式化逻辑）与 `templates/error.html`；④ `app.py` 新增 `check_database` / `register_error_handlers` / `register_template_context` / `register_filters`，登录与 `user_loader` 增加数据库异常降级；⑤ 前端 `charts.js` 增加 401 自动跳转登录页；⑥ 铁则 7 补充前端命名约定（JS 与 DOM id 用 snake_case，CSS 类名保留 kebab-case，模块级单例对象为例外）；⑦ 第 3 章目录结构与 3.1 设计说明同步；⑧ 新增 6.4 节数据管理页布局；⑨ 项目根目录新增 `启动说明.md` | 用户指定 |
