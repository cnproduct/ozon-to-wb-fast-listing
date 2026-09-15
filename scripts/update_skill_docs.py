# -*- coding: utf-8 -*-
"""
Script to update SKILL.md and documentation across all skill locations
"""

import os
import re

def update_skills():
    p2 = 'c:/Users/Administrator/Documents/google drive/ozon-to-wb-fast-listing/SKILL.md'
    p1 = 'c:/Users/Administrator/Documents/google drive/.agents/skills/ozon-to-wb-fast-listing/SKILL.md'

    with open(p2, 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. Update Rule 0.5 in content
    new_rule_05 = """> 0.5. **【真实物理包装尺寸与 weightBrutto 智能推导铁律（三层推导体系，杜绝假模板与 isValid=False）】**：
>    - **第一层（Ozon 真实数据穿透优先）**：穿透解析 Ozon `/features/` 与主页结构树中的 `Размер упаковки`、`Габариты упаковки`、`Вес с упаковкой`、`Вес товара`、`Вес` 等真实外包装毫米尺寸与克重。
>    - **第二层（实物物理形态分类精准推导）**：当 Ozon 卖家缺失外包装字段时，**严禁全店统一死板套用单一假模板**！必须基于商品标题、品类、件数倍数（Multi-pack）与配件结构（如拉链硬盒、面罩、全景镜框、翻盖结构等）进行真实物理形态精准推导（面罩 `28×22×16cm/320g`、全景密闭镜 `19×10×8cm/135g`、硬盒焊接镜 `18×8×7cm/145g`、2合1翻盖镜 `17×7×5cm/75g`、开放式平光镜 `16×6×5cm/55g`、多件装自动扩算）。
>    - **第三层（合规约束与自然公差）**：尺寸纯整数向下取整（`Math.floor`），`dimensions` 必须显式携带 `"weightBrutto": round(weight_g / 1000.0, 2)`（公斤浮点数）与 `"isValid": True`，彻底杜绝 `weightBrutto: 0` 和 `isValid: False` 严重损伤店铺评分与转化率。"""

    content = re.sub(r'> 0\.5\.\s*\*\*【真实物理包装尺寸与 weightBrutto.*?严重损伤店铺物流履约评分与前台转化。', new_rule_05, content, flags=re.DOTALL)

    # 2. Update Section 4 in content
    old_sec_4_pat = r'### 4\. 包装尺寸与精确小数点 KG 重量.*?(?=### 5\.)'

    new_sec_4 = """### 4. 包装尺寸与精确小数点 KG 重量 (尺寸严格向下取整 + 智能物理形态推导体系 SOP)

> [!IMPORTANT]
> **拒绝千篇一律假模板，100% 还原商品真实物理外包装尺寸与毛重**：
> 过去很多卖家搬家上架时全店统一写 `18×10×6 cm / 0.3 kg` 或 `15×15×10 cm / 0.5 kg`，不仅导致买家端参数失真，更会因体积重计算虚高而多付昂贵物流履约运费，或因超差被买家投诉。必须严格执行以下 **三层智能物理形态推导规范**：

1. **第一层：Ozon /features/ 页面真实毫米级外包装与毛重穿透提取**：
   - 优先联动抓取 Ozon `/features/` 完整规格页与主页结构树；
   - 深度扫描 `Размер упаковки (Длина х Ширина х Высота)`、`Габариты упаковки`、`Вес с упаковкой`、`Вес товара`、`Вес` 等字段；
   - 命中真实包装数据时，100% 优先采信 Ozon 官方数据。

2. **第二层：基于商品物理形态 (Physical Morphology) 与件数倍数的精准分类推导**：
   - 当 Ozon 卖家未填写外包装参数时，系统自动调用 `PhysicalMorphologyEngine`（`scripts/morphology_engine.py`），根据商品标题、品类词、配件与实物形态进行真实物理规格还原：
     - **大号全脸防护面罩/弧形面屏/焊工头盔 (`щиток`, `маска`, `шлем`)** ➔ `28×22×16 cm`，毛重 `0.32 ~ 0.45 kg`；
     - **全景密闭式防尘/防风护目镜 (`ultravision`, `закрытого типа`, `с обтюратором`)** ➔ `19~20×10~11×8 cm`，毛重 `0.13 ~ 0.16 kg`；
     - **激光焊接专用镜/EVA拉链硬盒套装 (`лазерная сварка`, `в чехле`, `с футляром`)** ➔ `17~18×8×7 cm`，毛重 `0.14 ~ 0.18 kg`；
     - **双色翻盖/2合1可调节工装镜 (`2 в 1`, `зебра`, `откидные`)** ➔ `17×7×5 cm`，毛重 `0.07 ~ 0.09 kg`；
     - **开放式轻量聚碳酸酯防护眼镜 (`очки защитные`, `для болгарки`)** ➔ `15~17×6×5 cm`，毛重 `0.05 ~ 0.07 kg`；
     - **多件套装 (`2 шт`, `5 шт`, `10 шт` 等)** ➔ 自动按件数扩算外包装箱体积与总毛重（如 5件装 `22×16×10 cm / 280g`，10件装 `25×20×12 cm / 550g`）。
   - **自然测量公差 (Deterministic Micro-Variance)**：结合 SKU 扰动因子产生自然的物理测量微差（±1cm, ±5~8g），彻底杜绝全店千篇一律完全相同数值。

3. **第三层：WB API 严格整型约束、weightBrutto 浮点下发与描述底部同步**：
   - **尺寸严格向下取整 (Math.floor)**：WB 官方 API 接口的 `dimensions.length / width / height` 强制要求为**整数 (Integer)**，必须严格向下取整（如 `24.9 cm` ➔ **`24`**，`9.6 cm` ➔ **`9`**，`7.3 cm` ➔ **`7`**）；
   - **长宽高顺序绝对不颠倒**：严格按照 `length`（长） × `width`（宽） × `height`（高）下发；
   - **毛重必须显式下发并标记合规**：`dimensions` 必须携带 `"weightBrutto": round(weight_g / 1000.0, 2)`（公斤浮点数，如 0.14, 0.32, 0.06 等）与 `"isValid": True`，彻底杜绝 `weightBrutto: 0` 和 `isValid: False`；
   - **描述区结构化参数同步**：在商品详情描述（`description`）底部的【Основные характеристики】中，同步列出与 `dimensions` 严格一致的毛重与包装尺寸，实现前后台 100% 数据闭环。

"""

    content = re.sub(old_sec_4_pat, new_sec_4, content, flags=re.DOTALL)

    # 3. Copy morphology_engine.py into .agents/skills/ozon-to-wb-fast-listing/scripts/
    target_morph = 'c:/Users/Administrator/Documents/google drive/.agents/skills/ozon-to-wb-fast-listing/scripts/morphology_engine.py'
    src_morph = 'c:/Users/Administrator/Documents/google drive/ozon-to-wb-fast-listing/scripts/morphology_engine.py'
    if os.path.exists(src_morph):
        os.makedirs(os.path.dirname(target_morph), exist_ok=True)
        with open(src_morph, 'r', encoding='utf-8') as f:
            m_code = f.read()
        with open(target_morph, 'w', encoding='utf-8') as f:
            f.write(m_code)
        print('Copied morphology_engine.py to .agents skill scripts dir')

    # 4. Copy ozon_crawler.py and batch_processor.py into .agents skill scripts
    for s_name in ['ozon_crawler.py', 'batch_processor.py']:
        s_src = os.path.join('c:/Users/Administrator/Documents/google drive/ozon-to-wb-fast-listing/scripts', s_name)
        s_dst = os.path.join('c:/Users/Administrator/Documents/google drive/.agents/skills/ozon-to-wb-fast-listing/scripts', s_name)
        if os.path.exists(s_src):
            with open(s_src, 'r', encoding='utf-8') as f:
                s_data = f.read()
            with open(s_dst, 'w', encoding='utf-8') as f:
                f.write(s_data)
            print(f'Synced {s_name} to .agents skill scripts')

    # 5. Write updated SKILL.md
    with open(p2, 'w', encoding='utf-8') as f:
        f.write(content)
    with open(p1, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f'Successfully updated SKILL.md in {p1} and {p2}!')

if __name__ == '__main__':
    update_skills()
