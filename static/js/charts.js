/**
 * ============================================================
 * 数据看板图表模块
 * ------------------------------------------------------------
 * 职责：通过 fetch API 调用后端 RESTful 接口获取 JSON 数据，
 *       并使用 ECharts 5.4.3 渲染 4 个交互图表。
 *
 * 设计依据：UI UX Pro Max 生成的 Data-Dense Dashboard 设计系统
 *          （设计令牌见 static/css/style.css 顶部 :root）
 *
 * 核心约定：
 *   1. 所有数据均来自后端接口，前端不得出现任何硬编码的模拟数据；
 *   2. 每个图表对应一个独立的 init 函数，职责单一、便于单独调试；
 *   3. 页面加载完成后按固定顺序依次调用各 init 函数；
 *   4. 每个图表都必须具备悬浮提示（tooltip）与缩放（dataZoom）能力；
 *   5. 窗口尺寸变化时图表自适应重绘；
 *   6. 尊重系统的「减少动效」偏好，开启时关闭图表动画。
 * ============================================================
 */

/* 使用 IIFE 包裹，避免污染全局命名空间 */
(function () {
    'use strict';

    /* ==================== 一、接口与常量配置 ==================== */

    /**
     * 后端接口地址清单
     * 与 routes/api_routes.py 中定义的路由一一对应
     */
    var API_ENDPOINTS = {
        PROVINCE: '/api/sales/province',
        CATEGORY: '/api/sales/category',
        TREND: '/api/sales/trend',
        TOP: '/api/sales/top'
    };

    /**
     * 图表配色：取自设计系统（蓝色数据 + 琥珀色强调）
     * 说明：饼图等多系列图表按顺序取用该色板
     */
    var CHART_PALETTE = [
        '#1E40AF',  /* 主色 primary   */
        '#3B82F6',  /* 次色 secondary */
        '#60A5FA',  /* 浅蓝，用于次级数据 */
        '#D97706',  /* 强调色 accent  */
        '#F59E0B'   /* 琥珀，用于补充系列 */
    ];

    /** 图表通用文字颜色（对应 --color-muted-foreground） */
    var TEXT_COLOR = '#475569';
    /** 图表分割线颜色（对应 --color-border） */
    var SPLIT_LINE_COLOR = '#DBEAFE';

    /** 是否开启了「减少动效」偏好（用于关闭图表动画） */
    var PREFERS_REDUCED_MOTION =
        window.matchMedia &&
        window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    /* ==================== 二、通用工具函数 ==================== */

    /**
     * 调用后端接口并解析统一响应信封
     *
     * 后端统一响应格式：{"code": 200, "msg": "success", "data": [...]}
     * 本函数负责校验 code 字段，非 200 时抛出带 msg 的错误，
     * 使调用方能够以统一的 try/catch 方式处理业务异常与网络异常。
     *
     * @param {string} url 接口地址
     * @returns {Promise<Array>} 响应中的 data 数组
     */
    function fetch_json(url) {
        return fetch(url, {
            method: 'GET',
            headers: { 'Accept': 'application/json' },
            cache: 'no-cache'
        }).then(function (response) {
            if (!response.ok) {
                /* 把 HTTP 状态码挂到错误对象上，供上层判断具体失败原因 */
                throw build_error('HTTP ' + response.status, response.status);
            }
            return response.json();
        }).then(function (payload) {
            if (payload.code !== 200) {
                throw build_error(payload.msg || '接口返回异常', payload.code);
            }
            return payload.data || [];
        });
    }

    /**
     * 构造带业务状态码的错误对象
     *
     * 说明：原生 Error 只能携带 message，
     *       而「登录失效（401）」需要区别于「接口报错（500）」做不同处理，
     *       因此额外挂一个 code 字段，供上层的错误处理函数分派。
     *
     * @param {string} message 错误描述
     * @param {number} code 业务 / HTTP 状态码
     * @returns {Error} 附带 code 字段的错误对象
     */
    function build_error(message, code) {
        var error = new Error(message);
        error.code = code;
        return error;
    }

    /* 登录失效后是否已触发跳转：4 个图表会同时报 401，只需跳转一次 */
    var login_redirecting = false;

    /**
     * 跳转到登录页，并携带当前页面路径以便登录后跳回
     */
    function redirect_to_login() {
        window.location.href = '/login?next=' +
            encodeURIComponent(window.location.pathname);
    }

    /**
     * 统一的图表加载失败处理：按错误类型给出不同的友好提示
     *
     * 分流规则：
     *   401 登录失效 → 提示后自动跳转登录页（避免用户面对一堆空图表不知所措）；
     *   其他错误     → 就地展示失败原因，并保留重试的可能（刷新页面）。
     *
     * @param {HTMLElement} container 图表容器
     * @param {Error} error 错误对象
     * @param {string} title 其他错误时的提示标题
     */
    function handle_fetch_error(container, error, title) {
        hide_loading(container);

        if (error.code === 401) {
            show_empty(container, '登录已失效', '正在跳转到登录页…');
            if (!login_redirecting) {
                login_redirecting = true;
                setTimeout(redirect_to_login, 1500);
            }
            return;
        }

        show_empty(container, title, error.message);
    }

    /**
     * 金额格式化：保留 2 位小数并添加千分位分隔符
     * @param {number} value 数值
     * @returns {string} 形如 ¥1,234.56 的字符串
     */
    function format_currency(value) {
        var num = Number(value) || 0;
        return '¥' + num.toLocaleString('zh-CN', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2
        });
    }

    /**
     * 整数格式化：添加千分位分隔符（用于销量等计数指标）
     * @param {number} value 数值
     * @returns {string} 形如 1,234 的字符串
     */
    function format_int(value) {
        return (Number(value) || 0).toLocaleString('zh-CN');
    }

    /**
     * 在图表容器中显示「加载中」指示
     * @param {HTMLElement} container 图表容器
     */
    function show_loading(container) {
        hide_loading(container);
        var mask = document.createElement('div');
        mask.className = 'chart-loading';
        mask.setAttribute('role', 'status');
        mask.setAttribute('aria-live', 'polite');
        mask.innerHTML =
            '<span class="spinner" aria-hidden="true"></span><span>数据加载中…</span>';
        container.appendChild(mask);
    }

    /**
     * 移除图表容器中的「加载中」指示
     * @param {HTMLElement} container 图表容器
     */
    function hide_loading(container) {
        var mask = container.querySelector('.chart-loading');
        if (mask) {
            mask.remove();
        }
    }

    /**
     * 显示空数据或加载失败的降级提示
     * 设计依据：UX 规范要求避免空白屏幕，应给出有用提示
     *
     * @param {HTMLElement} container 图表容器
     * @param {string} title 提示标题
     * @param {string} [detail] 详细信息（可选）
     */
    function show_empty(container, title, detail) {
        var mask = document.createElement('div');
        mask.className = 'chart-empty';
        mask.setAttribute('role', 'status');
        mask.innerHTML =
            '<span class="chart-empty-title">' + title + '</span>' +
            (detail ? '<span>' + detail + '</span>' : '');
        container.appendChild(mask);
    }

    /**
     * 获取（或首次创建）容器上的 ECharts 实例
     *
     * 实例缓存在容器对象的 __echarts_instance__ 属性上，
     * 保证同一个容器只初始化一次，后续更新直接 setOption 复用实例。
     *
     * @param {HTMLElement} container 图表容器
     * @returns {Object|null} ECharts 实例；ECharts 未加载时返回 null
     */
    function get_chart_instance(container) {
        /* ECharts 资源未就绪时直接返回 null，由调用方降级处理 */
        if (typeof echarts === 'undefined') {
            return null;
        }
        if (!container.__echarts_instance__) {
            container.__echarts_instance__ = echarts.init(container);
        }
        return container.__echarts_instance__;
    }

    /**
     * 图表的统一基础配置
     * 包含动画开关、无障碍声明与通用文字样式
     *
     * @returns {Object} 基础配置对象
     */
    function build_base_option() {
        return {
            /* 开启减少动效偏好时关闭动画 */
            animation: !PREFERS_REDUCED_MOTION,
            animationDuration: 400,
            animationEasing: 'cubicOut',
            /* 无障碍：为图表生成描述文本，供读屏软件使用 */
            aria: {
                enabled: true,
                decal: { show: false }
            },
            textStyle: {
                fontFamily: '"Fira Sans","Microsoft YaHei",sans-serif',
                color: TEXT_COLOR
            }
        };
    }

    /**
     * 合并基础配置与具体图表配置
     * @param {Object} option 具体图表的配置
     * @returns {Object} 合并后的完整配置
     */
    function merge_base(option) {
        var base = build_base_option();
        for (var key in option) {
            if (Object.prototype.hasOwnProperty.call(option, key)) {
                base[key] = option[key];
            }
        }
        return base;
    }

    /* ==================== 三、图表配置构建函数 ==================== */
    /* 每个函数只负责「数据 → ECharts option」的转换，不接触 DOM */

    /**
     * 构建「省份销售额柱状图」配置
     *
     * 实现逻辑：
     *   1. X 轴为类目轴（31 个省份），标签旋转 45° 避免文字重叠；
     *   2. Y 轴为数值轴（销售额），刻度标签格式化为万元，缩短文字长度；
     *   3. 柱体使用主色到次色的线性渐变，视觉上区分于其他图表；
     *   4. tooltip 使用 axis 触发器，悬浮即可查看该省精确金额；
     *   5. dataZoom 同时开启 inside（滚轮/拖拽）与 slider（底部滑块），
     *      满足「图表可缩放」的交互要求。
     *
     * @param {Array} rows 接口返回数据 [{name, value}]
     * @returns {Object} ECharts 配置
     */
    function build_province_option(rows) {
        return merge_base({
            tooltip: {
                trigger: 'axis',
                axisPointer: { type: 'shadow' },
                formatter: function (params) {
                    var item = params[0];
                    return item.name + '<br/>销售额：' +
                        format_currency(item.value);
                }
            },
            grid: {
                left: 12,
                right: 16,
                top: 24,
                bottom: 64,
                containLabel: true
            },
            xAxis: {
                type: 'category',
                data: rows.map(function (item) { return item.name; }),
                axisLabel: {
                    rotate: 45,
                    fontSize: 11,
                    color: TEXT_COLOR
                },
                axisLine: { lineStyle: { color: SPLIT_LINE_COLOR } },
                axisTick: { show: false }
            },
            yAxis: {
                type: 'value',
                name: '销售额',
                nameTextStyle: { fontSize: 11, color: TEXT_COLOR },
                axisLabel: {
                    fontSize: 11,
                    color: TEXT_COLOR,
                    /* 以「万元」为单位显示，避免长数字挤压图表宽度 */
                    formatter: function (value) {
                        return (value / 10000).toFixed(0) + '万';
                    }
                },
                splitLine: { lineStyle: { color: SPLIT_LINE_COLOR } }
            },
            dataZoom: [
                { type: 'inside', start: 0, end: 100 },
                {
                    type: 'slider',
                    height: 16,
                    bottom: 18,
                    borderColor: SPLIT_LINE_COLOR,
                    fillerColor: 'rgba(30,64,175,0.12)'
                }
            ],
            series: [{
                name: '销售额',
                type: 'bar',
                data: rows.map(function (item) { return item.value; }),
                barMaxWidth: 26,
                itemStyle: {
                    borderRadius: [4, 4, 0, 0],
                    /* 主色 → 次色 的垂直渐变 */
                    color: {
                        type: 'linear',
                        x: 0, y: 0, x2: 0, y2: 1,
                        colorStops: [
                            { offset: 0, color: '#3B82F6' },
                            { offset: 1, color: '#1E40AF' }
                        ]
                    }
                },
                emphasis: { focus: 'series' }
            }]
        });
    }

    /**
     * 构建「品类销售额占比环形饼图」配置
     *
     * 实现逻辑：
     *   1. 使用环形（radius 内 45% 外 70%）而非实心饼，中心留白更轻盈；
     *   2. tooltip 使用 item 触发器，展示金额与 ECharts 自动计算的百分比；
     *   3. 配色按顺序取用 CHART_PALETTE，保证与设计系统一致；
     *   4. 图例置于底部，小屏时自动换行，避免遮挡图形；
     *   5. 无障碍：饼图不依赖颜色单独传达含义，图例与提示均带文字。
     *
     * @param {Array} rows 接口返回数据 [{name, value}]
     * @returns {Object} ECharts 配置
     */
    function build_category_option(rows) {
        return merge_base({
            color: CHART_PALETTE,
            tooltip: {
                trigger: 'item',
                /* {d}% 为 ECharts 自动计算的百分比 */
                formatter: function (params) {
                    return params.name + '<br/>销售额：' +
                        format_currency(params.value) +
                        '（' + params.percent + '%）';
                }
            },
            legend: {
                type: 'scroll',
                bottom: 0,
                itemWidth: 10,
                itemHeight: 10,
                textStyle: { fontSize: 12, color: TEXT_COLOR }
            },
            series: [{
                name: '品类销售额',
                type: 'pie',
                radius: ['45%', '70%'],
                center: ['50%', '46%'],
                avoidLabelOverlap: true,
                itemStyle: {
                    borderColor: '#FFFFFF',
                    borderWidth: 2
                },
                label: {
                    fontSize: 11,
                    color: TEXT_COLOR,
                    formatter: '{b}\n{d}%'
                },
                labelLine: { length: 8, length2: 8 },
                data: rows.map(function (item) {
                    return { name: item.name, value: item.value };
                })
            }]
        });
    }

    /**
     * 构建「每日销售趋势折线图」配置
     *
     * 实现逻辑：
     *   1. X 轴为日期类目轴，标签只显示「月-日」以容纳 90 个数据点；
     *   2. 开启 smooth 平滑曲线与 areaStyle 渐变填充，弱化单日波动噪声；
     *   3. 保留 symbol 但默认隐藏，悬浮时才显示数据点，减少视觉干扰；
     *   4. dataZoom 开启缩放，便于聚焦任意时间段（最近 3 个月跨度较大）；
     *   5. 后端已补齐无订单日期为 0，因此曲线不会出现断裂跳变。
     *
     * @param {Array} rows 接口返回数据 [{date, sales}]
     * @returns {Object} ECharts 配置
     */
    function build_trend_option(rows) {
        return merge_base({
            tooltip: {
                trigger: 'axis',
                axisPointer: { type: 'line' },
                formatter: function (params) {
                    var item = params[0];
                    return item.axisValue + '<br/>销售额：' +
                        format_currency(item.value);
                }
            },
            grid: {
                left: 12,
                right: 16,
                top: 24,
                bottom: 64,
                containLabel: true
            },
            xAxis: {
                type: 'category',
                boundaryGap: false,
                data: rows.map(function (item) { return item.date; }),
                axisLabel: {
                    fontSize: 11,
                    color: TEXT_COLOR,
                    /* 2026-07-20 → 07-20，缩短标签长度 */
                    formatter: function (value) {
                        return value.slice(5);
                    }
                },
                axisLine: { lineStyle: { color: SPLIT_LINE_COLOR } },
                axisTick: { show: false }
            },
            yAxis: {
                type: 'value',
                name: '销售额',
                nameTextStyle: { fontSize: 11, color: TEXT_COLOR },
                axisLabel: {
                    fontSize: 11,
                    color: TEXT_COLOR,
                    formatter: function (value) {
                        return (value / 10000).toFixed(1) + '万';
                    }
                },
                splitLine: { lineStyle: { color: SPLIT_LINE_COLOR } }
            },
            dataZoom: [
                { type: 'inside', start: 0, end: 100 },
                {
                    type: 'slider',
                    height: 16,
                    bottom: 18,
                    borderColor: SPLIT_LINE_COLOR,
                    fillerColor: 'rgba(30,64,175,0.12)'
                }
            ],
            series: [{
                name: '销售额',
                type: 'line',
                smooth: true,
                showSymbol: false,
                data: rows.map(function (item) { return item.sales; }),
                lineStyle: { width: 2, color: '#1E40AF' },
                itemStyle: { color: '#1E40AF' },
                /* 面积渐变填充：上方半透明蓝色 → 下方近白色 */
                areaStyle: {
                    color: {
                        type: 'linear',
                        x: 0, y: 0, x2: 0, y2: 1,
                        colorStops: [
                            { offset: 0, color: 'rgba(59,130,246,0.35)' },
                            { offset: 1, color: 'rgba(59,130,246,0.02)' }
                        ]
                    }
                }
            }]
        });
    }

    /**
     * 构建「商品销量 TOP10 横向柱状图」配置
     *
     * 实现逻辑：
     *   1. 交换坐标轴：Y 轴为商品名（类目轴），X 轴为销量（数值轴），
     *      形成横向条形图，商品名再长也能完整显示；
     *   2. 后端返回为降序，而 ECharts 类目轴自下而上绘制，
     *      因此需将数据反转，使销量最高的商品排在最上方；
     *   3. 条形末端显示具体销量数值，不依赖悬浮即可读数；
     *   4. 使用主色到强调色的横向渐变，与其他图表形成层次区分。
     *
     * @param {Array} rows 接口返回数据 [{name, value}]，已按销量降序
     * @returns {Object} ECharts 配置
     */
    function build_top_option(rows) {
        /* 反转数组：让销量第一名显示在图表顶部 */
        var reversed = rows.slice().reverse();

        return merge_base({
            tooltip: {
                trigger: 'axis',
                axisPointer: { type: 'shadow' },
                formatter: function (params) {
                    var item = params[0];
                    return item.name + '<br/>销量：' +
                        format_int(item.value) + ' 件';
                }
            },
            grid: {
                left: 12,
                right: 60,
                top: 12,
                bottom: 12,
                containLabel: true
            },
            xAxis: {
                type: 'value',
                name: '销量（件）',
                nameTextStyle: { fontSize: 11, color: TEXT_COLOR },
                axisLabel: { fontSize: 11, color: TEXT_COLOR },
                splitLine: { lineStyle: { color: SPLIT_LINE_COLOR } }
            },
            yAxis: {
                type: 'category',
                data: reversed.map(function (item) { return item.name; }),
                axisLabel: { fontSize: 11, color: TEXT_COLOR },
                axisLine: { lineStyle: { color: SPLIT_LINE_COLOR } },
                axisTick: { show: false }
            },
            series: [{
                name: '销量',
                type: 'bar',
                data: reversed.map(function (item) { return item.value; }),
                barMaxWidth: 18,
                itemStyle: {
                    borderRadius: [0, 4, 4, 0],
                    /* 主色 → 强调色 的横向渐变 */
                    color: {
                        type: 'linear',
                        x: 0, y: 0, x2: 1, y2: 0,
                        colorStops: [
                            { offset: 0, color: '#1E40AF' },
                            { offset: 1, color: '#D97706' }
                        ]
                    }
                },
                /* 条形末端直接显示数值，降低对悬浮交互的依赖 */
                label: {
                    show: true,
                    position: 'right',
                    fontSize: 11,
                    color: TEXT_COLOR,
                    formatter: function (params) {
                        return format_int(params.value);
                    }
                },
                emphasis: { focus: 'series' }
            }]
        });
    }

    /* ==================== 四、各图表的初始化函数 ==================== */
    /* 每个函数对应一个图表，流程统一为：
       显示 loading → fetch 数据 → 构建 option → setOption → 异常降级提示 */

    /**
     * 初始化「省份销售额柱状图」
     * 对应接口：GET /api/sales/province
     * @returns {Promise<void>}
     */
    function init_province_chart() {
        var container = document.getElementById('province_chart');
        if (!container) {
            return Promise.resolve();
        }

        show_loading(container);
        return fetch_json(API_ENDPOINTS.PROVINCE).then(function (rows) {
            hide_loading(container);
            if (!rows.length) {
                show_empty(container, '暂无省份销售数据');
                return;
            }
            var chart = get_chart_instance(container);
            if (!chart) {
                show_empty(container, '图表库未加载', '请检查 ECharts 资源');
                return;
            }
            chart.setOption(build_province_option(rows), true);
        }).catch(function (error) {
            hide_loading(container);
            handle_fetch_error(container, error, '省份数据加载失败');
        });
    }

    /**
     * 初始化「品类销售额占比环形饼图」
     * 对应接口：GET /api/sales/category
     * @returns {Promise<void>}
     */
    function init_category_chart() {
        var container = document.getElementById('category_chart');
        if (!container) {
            return Promise.resolve();
        }

        show_loading(container);
        return fetch_json(API_ENDPOINTS.CATEGORY).then(function (rows) {
            hide_loading(container);
            if (!rows.length) {
                show_empty(container, '暂无品类销售数据');
                return;
            }
            var chart = get_chart_instance(container);
            if (!chart) {
                show_empty(container, '图表库未加载', '请检查 ECharts 资源');
                return;
            }
            chart.setOption(build_category_option(rows), true);
        }).catch(function (error) {
            hide_loading(container);
            handle_fetch_error(container, error, '品类数据加载失败');
        });
    }

    /**
     * 初始化「每日销售趋势折线图」
     * 对应接口：GET /api/sales/trend
     * @returns {Promise<void>}
     */
    function init_trend_chart() {
        var container = document.getElementById('trend_chart');
        if (!container) {
            return Promise.resolve();
        }

        show_loading(container);
        return fetch_json(API_ENDPOINTS.TREND).then(function (rows) {
            hide_loading(container);
            if (!rows.length) {
                show_empty(container, '暂无销售趋势数据');
                return;
            }
            var chart = get_chart_instance(container);
            if (!chart) {
                show_empty(container, '图表库未加载', '请检查 ECharts 资源');
                return;
            }
            chart.setOption(build_trend_option(rows), true);
        }).catch(function (error) {
            hide_loading(container);
            handle_fetch_error(container, error, '趋势数据加载失败');
        });
    }

    /**
     * 初始化「商品销量 TOP10 横向柱状图」
     * 对应接口：GET /api/sales/top
     * @returns {Promise<void>}
     */
    function init_top_chart() {
        var container = document.getElementById('top_chart');
        if (!container) {
            return Promise.resolve();
        }

        show_loading(container);
        return fetch_json(API_ENDPOINTS.TOP).then(function (rows) {
            hide_loading(container);
            if (!rows.length) {
                show_empty(container, '暂无商品销量数据');
                return;
            }
            var chart = get_chart_instance(container);
            if (!chart) {
                show_empty(container, '图表库未加载', '请检查 ECharts 资源');
                return;
            }
            chart.setOption(build_top_option(rows), true);
        }).catch(function (error) {
            hide_loading(container);
            handle_fetch_error(container, error, '销量数据加载失败');
        });
    }

    /* ==================== 五、自适应与入口 ==================== */

    /**
     * 收集页面上所有已初始化的图表实例
     * @returns {Array} ECharts 实例数组
     */
    function collect_charts() {
        var ids = ['province_chart', 'category_chart', 'trend_chart', 'top_chart'];
        var charts = [];
        ids.forEach(function (id) {
            var container = document.getElementById(id);
            if (container && container.__echarts_instance__) {
                charts.push(container.__echarts_instance__);
            }
        });
        return charts;
    }

    /**
     * 窗口尺寸变化时重绘所有图表
     * 使用 150ms 防抖，避免拖拽窗口时高频重绘造成卡顿
     */
    var resize_timer = null;
    window.addEventListener('resize', function () {
        if (resize_timer) {
            clearTimeout(resize_timer);
        }
        resize_timer = setTimeout(function () {
            collect_charts().forEach(function (chart) {
                chart.resize();
            });
        }, 150);
    });

    /**
     * 按顺序初始化全部图表
     *
     * 说明：这里采用串行 await 的方式依次调用，
     * 便于按顺序定位问题，也符合「页面加载完成后依次调用」的要求。
     * 若后续追求更快的首屏速度，可改为 Promise.all 并发请求。
     *
     * @returns {Promise<void>}
     */
    function bootstrap_charts() {
        return init_province_chart()
            .then(init_category_chart)
            .then(init_trend_chart)
            .then(init_top_chart);
    }

    /* 页面 DOM 就绪后启动图表初始化流程 */
    document.addEventListener('DOMContentLoaded', function () {
        bootstrap_charts();
    });
})();
