# Antigravity Workspace Instruction & Rules: Ozon to Wildberries Fast Listing

> **核心技能激活宣告**：
> 本工作区所有后续对话及跨境搬家上架任务，必须始终优先并严格激活并遵循 **`ozon-to-wb-fast-listing`** 技能规范（来源：`https://github.com/cnproduct/ozon-to-wb-fast-listing`）。

## 核心执行铁律

1. **【先问后干】第一响应铁律**：
   - 收到用户提供的 SKU（直接粘贴或 `.txt` 文档）后，第一步必须立即向用户呈报已识别的有效数字 SKU 列表，并询问上架的【售价策略】与【库存设置】（提供默认推荐方案：Ozon 原价 5 倍实售，划线价 10 倍，50% 官方大促折扣，莫斯科1仓现货库存 200 件；或根据用户最新指定倍数/库存执行）。
   - 严禁在用户未确认前擅自开始耗时的抓取或建卡工作。

2. **【多币种汇率自适应定价法则】**：
   - 店铺结算币种检测：中国跨境卖家店铺（如 007 店铺）结算币种为人民币（CNY）。
   - 严格按汇率公式换算：
     $$P_{\text{target\_buyer\_RUB}} = \text{round}(P_{\text{ozon\_RUB}} \times M)$$
     $$P_{\text{sell\_CNY}} = \max\left(1, \text{round}\left(\frac{P_{\text{target\_buyer\_RUB}}}{\text{wb\_rub\_rate}}\right)\right)$$
     $$P_{\text{strike\_CNY}} = \max\left(2, \text{ceil}\left(\frac{P_{\text{sell\_CNY}}}{1 - D / 100.0}\right)\right)$$
   - 严禁将卢布数字直接当成人民币下发，杜绝“2万变27万”的币种混淆事故。
   - 大幅度降价需采用 0.70x 阶梯平滑调价防价格隔离 (Карантин цен)。

3. **【真实物理形态包装尺寸与毛重推导铁律】**：
   - 严禁全店统一死板使用 `18×10×6 cm / 0.3 kg` 假模板。
   - 优先提取 Ozon `/features/` 真实外包装尺寸与毛重；缺失时按实物形态（带箱电钻 32×28×10cm/2.2kg、盒装电钻 24×20×8cm/1.4kg、50ml面霜 8×8×6cm/0.16kg 等）动态推导。
   - 尺寸纯整数向下取整，毛重为 KG 浮点数。

4. **【详情页 100% 剥离 Ozon 编码与竞对平台痕迹】**：
   - 描述（`description`）中严禁出现任何 `- Код товара: ...`、`Код товара Ozon:`、`Артикул:` 等竞对标识与商品编号。

5. **【无授权白牌 100% 脱敏】**：
   - 无官方授权商标的商品，品牌（`brand`）强制置空，严防《要约》第 9.2.3 条第 7 款下架封禁红线。

6. **【10倍极速引擎与现货秒级注入】**：
   - 官方 EAN-13 条形码批量申请；
   - 云端异步直拉相册多图（`POST /content/v3/media/save`）；
   - 莫斯科1仓现货库存秒级注入。
