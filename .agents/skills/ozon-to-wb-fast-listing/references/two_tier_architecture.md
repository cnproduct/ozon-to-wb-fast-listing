# Wildberries 买家端两级分离渲染架构白皮书 (Two-Tier Architecture)

> **版本**：v3.0.0 架构白皮书  
> **核心受众**：跨境电商技术人员、运营交付质检员、自动化程序设计者。

---

## 一、为什么会有“前台留白”的物理等待期？

许多新手运营与外部开发者常犯的一个严重误判是：
> “我调用官方 API 建卡成功了，为什么立即在买家端 App 或网页上查看，商品的规格参数列表 (Характеристики / О товаре) 依然是一片空白？”

这是由 Wildberries 买家端的底层高并发架构所决定的。

---

## 二、两级分离渲染架构深度剖析

Wildberries 买家端采用 **动态网关层** 与 **静态 CDN 切片层** 两级分离架构：

```mermaid
graph TD
    API[WB 卖家 OpenAPI] --> DB[(官方核心数据库)]
    
    subgraph 动态网关层 (秒级生效: 0 ~ 5分钟)
        DB --> DG[动态网关集群 API]
        DG --> AppTitle[标题 Title]
        DG --> AppPhotos[相册多图 Photos]
        DG --> AppPrice[价格与折扣 Price & Discount]
        DG --> AppStocks[现货库存 Stocks]
        DG --> AppBuyBtn[立即购买/加购 按钮可点亮]
    end
    
    subgraph 静态 CDN 切片层 (批处理编译周期: 约 30 ~ 45分钟)
        DB --> Builder[官方集群批处理编译引擎]
        Builder --> S3[wbbasket 静态存储集群]
        S3 --> Edge[全球 CDN 边缘节点 card.json]
        Edge --> Options[买家端 Характеристики 参数网格]
        Edge --> Desc[买家端折叠长文描述 Description]
    end
```

### 1. 第一级：动态网关层 (Dynamic Gateway Tier)
- **时效性**：API 提交后 **0 ~ 5 分钟内即刻生效**。
- **包含字段**：
  - 商品标题 (`title`)
  - 画廊多图 (`photos`)
  - 划线原价与大促折扣标签 (`price`, `discount`)
  - 仓库现货库存 (`stocks`)
  - 购物车购买按钮状态 (`В корзину`)
- **结论**：只要完成建卡、直拉多图、改价与上库存，买家端已经能够搜索到、浏览多图并立即下单购买！

### 2. 第二级：静态 CDN 切片层 (Static CDN Slice Tier)
- **时效性**：**约 30 ~ 45 分钟定时批量编译更新**。
- **包含字段**：
  - 买家端规格参数网格 (`options`)
  - 折叠展开的长篇商品描述 (`description`)
- **运行机制**：
  官方后台计算集群会定时将卖家的商品参数编译打包成静态 JSON 文件（格式：`https://basket-xx.wbbasket.ru/vol{vol}/part{part}/{nmID}/info/ru/card.json`），分发推送到全球 CDN 节点。
- **结论**：新卡提交后的前 30~45 分钟内，options 静态切片排队编译是平台的**正常物理周期**。只要卖家的卖家库 `characteristics` 属性注入饱和且格式合规，编译跑完后前台参数网格会自动展现，绝非建卡失败！
