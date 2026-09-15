# Antigravity Workspace Instruction & Rules: Ozon to Wildberries Fast Listing

> **核心技能激活宣告**：
> 本工作区所有后续对话及跨境搬家上架任务，必须始终优先并严格激活并遵循 **`ozon-to-wb-fast-listing`** 技能规范（来源：`https://github.com/cnproduct/ozon-to-wb-fast-listing`）。

## 核心执行铁律

1. **【先问后干】第一响应铁律**：
   - 收到用户提供的 SKU（直接粘贴或 `.txt` 文档）后，第一步必须立即向用户呈报已识别的有效数字 SKU 列表，并询问上架的【售价策略】与【库存设置】（提供默认推荐方案：Ozon 绿标价 6 倍实售，划线价 12 倍，50% 官方大促折扣，莫斯科1仓现货库存 5 件；或根据用户最新指定倍数/库存执行）。
   - 严禁在用户未确认前擅自开始耗时的抓取或建卡工作。

2. **【跨境店铺人民币统一价格核算法则（CNY 6倍实售 / 12倍划线 / 50%官方大促与整型约束）】**：
   - **结算货币基准**：跨境卖家在 Wildberries 开立的店铺账户货币为 **人民币（CNY）**（`currencyIsoCode4217: "CNY"`），卖家后台、卡片创建与价格中心均直接下发人民币数值。
   - **基准价格源**：严格提取 Ozon 真实的**绿标卡价对应的人民币价格 $P_{\text{ozon\_CNY}}$**（若为卢布价则按换算汇率统一转为人民币）。
   - **核心定价计算公式**：
     $$P_{\text{sell\_CNY}} = P_{\text{ozon\_CNY}} \times 6$$
     $$P_{\text{strike\_CNY}} = P_{\text{sell\_CNY}} \times 2 = P_{\text{ozon\_CNY}} \times 12$$
     $$\text{官方大促折扣} = 50\%$$
   - **API 整型约束化（WB 平台强制标价为整型数字）**：
     $$P_{\text{strike\_int}} = \text{round}(P_{\text{ozon\_CNY}} \times 12)$$
     $$P_{\text{sell\_int}} = \text{round}(P_{\text{strike\_int}} \times (1 - 50\%))$$
     *（例如 68.13 元：下发划线标价 818 元，50% 折扣后实售 409 元，对应 408.78 元）*
   - **买家端前台呈现与平台补贴**：WB 平台按跨境汇率自动折算为卢布展示并标注 `-50%`；若买家享有平台补贴（SPP），实付进一步降低，平台依然按人民币实售价全额向卖家结算。

3. **【真实物理形态包装尺寸与毛重推导铁律】**：
   - 严禁全店统一死板使用 `18×10×6 cm / 0.3 kg` 假模板。
   - 优先提取 Ozon `/features/` 真实外包装尺寸与毛重；缺失时按实物形态（带箱电钻 32×28×10cm/2.2kg、盒装电钻 24×20×8cm/1.4kg、50ml面霜 8×8×6cm/0.16kg 等）动态推导。
   - 尺寸纯整数向下取整；提交卡片时 `dimensions` 必须显式携带 `"weightBrutto": round(weight_g / 1000.0, 2)`（KG 浮点数）与 `"isValid": True`，彻底杜绝 `weightBrutto: 0` 和 `isValid: False`。

4. **【详情页 100% 剥离 Ozon 编码与竞对平台痕迹】**：
   - 描述（`description`）中严禁出现任何 `- Код товара: ...`、`Код товара Ozon:`、`Артикул:` 等竞对标识与商品编号。

5. **【无授权白牌 100% 脱敏】**：
   - 无官方授权商标的商品，品牌（`brand`）强制置空，严防《要约》第 9.2.3 条第 7 款下架封禁红线。

6. **【10倍极速引擎与现货秒级注入】**：
   - 官方 EAN-13 条形码批量申请；
   - 云端异步直拉相册多图（`POST /content/v3/media/save`）；
   - 莫斯科1仓现货库存秒级注入。

7. **【平台封禁卡片 (Забаненные артикулы WB) 自动隔离容错铁律】**：
   - 在调用 `cards/update` 批量更新时，遇 400 提示封禁条目，系统必须自动解析并隔离被平台封禁的 nmID，自动剔除后重新下发正常卡片，并支持单件降级容错，确保 100% 正常卡片顺利完成更新，绝不因个别历史违规卡片导致整批阻塞。

8. **【微服务异步价格预填与 50% 官方大促折扣闭环】**：
   - 建卡时在 `sizes` 数组中原生预填 `"price": wb_strike_price`；
   - 提交建卡后通过 `POST /api/v2/upload/task` 异步下发 50% 大促折扣与划线价，并通过 `history/tasks` 轮询断言 `status: 3` 与 `successGoodsNumber`；
   - 穿透调用 `GET /api/v2/quarantine/goods` 实时监测，确保价格隔离区报警数为 0。

9. **【一键全量自动化上架指令 (`scripts/fast_list.py`)】**：
   - 收到 SKU 列表或文本路径后，直接调用统一极速上架引擎：`python scripts/fast_list.py --skus <sku_list_or_txt_file>`，全自动执行“去重 -> 抓取 -> 条码 -> 建卡 -> 相册 -> 现货库存 -> 50%大促价格 -> 归档”完整闭环。

