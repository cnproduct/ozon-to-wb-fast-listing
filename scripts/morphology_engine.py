# -*- coding: utf-8 -*-
"""
==============================================================================
Physical Morphology & Packaging Deduction Engine (v3.0)
==============================================================================
三层精准推导体系：
1. 第一层：Ozon 真实数据穿透优先 (Размер упаковки / Габариты / Вес с упаковкой / Вес)
2. 第二层：实物物理形态分类精准推导 (PPE防护、美妆护肤、清洁拖把、运动健身、水具净水、工具五金)
3. 第三层：合规约束与自然公差 (Math.floor 纯整数尺寸, weightBrutto KG 浮点数, isValid: True)
==============================================================================
"""

import re
import hashlib
from typing import Dict, Any, Tuple

class PhysicalMorphologyEngine:
    @staticmethod
    def deduce_dimensions_and_weight(
        title: str,
        raw_props: Dict[str, Any] = None,
        html_content: str = "",
        sku: str = ""
    ) -> Dict[str, Any]:
        """
        Deduce realistic package length, width, height (cm) and gross weight (g / kg)
        """
        raw_props = raw_props or {}
        t_lower = (title or "").lower()
        
        length_cm = None
        width_cm = None
        height_cm = None
        weight_g = None
        tnved = raw_props.get('ТН ВЭД') or raw_props.get('ТНВЭД') or ""

        # 1. 第一层：优先从 Ozon 官方结构化属性提取真实外包装尺寸与毛重
        for k, v in raw_props.items():
            k_lower = k.lower()
            v_str = str(v)
            if 'размер упаковки' in k_lower or 'габариты упаковки' in k_lower or 'габариты' in k_lower:
                nums = re.findall(r'\d+(?:\.\d+)?', v_str.replace(',', '.'))
                if len(nums) >= 3:
                    try:
                        length_cm = int(float(nums[0]))
                        width_cm = int(float(nums[1]))
                        height_cm = int(float(nums[2]))
                    except Exception:
                        pass
            elif 'вес с упаковкой' in k_lower or 'вес упаковки' in k_lower:
                nums = re.findall(r'\d+(?:\.\d+)?', v_str.replace(',', '.'))
                if nums:
                    try:
                        val = float(nums[0])
                        weight_g = int(val * 1000) if 'кг' in v_str.lower() else int(val)
                    except Exception:
                        pass
            elif 'вес' in k_lower and weight_g is None:
                nums = re.findall(r'\d+(?:\.\d+)?', v_str.replace(',', '.'))
                if nums:
                    try:
                        val = float(nums[0])
                        weight_g = int(val * 1000) if 'кг' in v_str.lower() else int(val)
                    except Exception:
                        pass

        # 2. 从 HTML 源码中正则穿透兜底
        if html_content and (length_cm is None or weight_g is None):
            if length_cm is None:
                dim_m = re.search(r'(?:Размер упаковки|Габариты упаковки|Габариты)[^:]*:\s*([\d\.,\s/xх*]+)\s*см', html_content, re.IGNORECASE)
                if dim_m:
                    nums = re.findall(r'\d+(?:\.\d+)?', dim_m.group(1).replace(',', '.'))
                    if len(nums) >= 3:
                        try:
                            length_cm = int(float(nums[0]))
                            width_cm = int(float(nums[1]))
                            height_cm = int(float(nums[2]))
                        except Exception:
                            pass
            if weight_g is None:
                wt_m = re.search(r'(?:Вес с упаковкой|Вес упаковки|Вес товара|Вес)[^:]*:\s*([\d\.,\s]+)\s*(г|кг)', html_content, re.IGNORECASE)
                if wt_m:
                    try:
                        val = float(wt_m.group(1).replace(',', '.').strip())
                        unit = wt_m.group(2).lower()
                        weight_g = int(val * 1000) if 'кг' in unit else int(val)
                    except Exception:
                        pass

        # 3. 第二层：实物物理形态分类精准推导 (当 Ozon 缺失字段时严禁单一假模板)
        pack_count = 1
        pack_match = re.search(r'(?:комплект|набор|упаковка)?\s*(\d+)\s*(?:шт|штук|пар)\b', t_lower)
        if pack_match:
            try:
                cnt = int(pack_match.group(1))
                if 1 < cnt <= 100:
                    pack_count = cnt
            except Exception:
                pass

        seed = int(hashlib.md5((sku or title).encode('utf-8')).hexdigest()[:6], 16)
        var_dim = (seed % 3) - 1
        var_wt = (seed % 9) * 2 - 8

        if length_cm is None or width_cm is None or height_cm is None or weight_g is None:
            # A. PPE 个人防护装备 (面罩/盾/护目镜)
            if any(kw in t_lower for kw in ['щиток', 'маска защитная', 'щит для лица', 'сварочная маска', 'шлем', 'экран защитный']):
                base_l, base_w, base_h = 28, 22, 16
                base_wt = 330
                if pack_count > 1:
                    base_h += (pack_count - 1) * 3
                    base_wt += (pack_count - 1) * 160

            elif any(kw in t_lower for kw in ['закрытого типа', 'ultravision', 'панорамные', 'обтюратор', 'с резинкой', 'закрытые', 'герметичные']):
                base_l, base_w, base_h = 19, 10, 8
                base_wt = 135
                if pack_count > 1:
                    base_h += (pack_count - 1) * 4
                    base_wt += (pack_count - 1) * 90

            elif any(kw in t_lower for kw in ['лазерн', 'сварки', 'сварщика', 'хамелеон', 'с футляром', 'в чехле', 'с кейсом']):
                base_l, base_w, base_h = 18, 8, 7
                base_wt = 145
                if pack_count > 1:
                    base_h += (pack_count - 1) * 3
                    base_wt += (pack_count - 1) * 95

            elif any(kw in t_lower for kw in ['2 в 1', '2в1', 'откидные', 'двойные', 'зебра']):
                base_l, base_w, base_h = 17, 7, 5
                base_wt = 75
                if pack_count > 1:
                    base_h += (pack_count - 1) * 2
                    base_wt += (pack_count - 1) * 50

            elif any(kw in t_lower for kw in ['очки защитные', 'защитные очки', 'очки слесарные', 'очки строительные']):
                if pack_count >= 5:
                    base_l, base_w, base_h = 22, 16, 10
                    base_wt = 55 * pack_count + 40
                elif pack_count >= 2:
                    base_l, base_w, base_h = 18, 12, 6
                    base_wt = 55 * pack_count + 25
                else:
                    base_l, base_w, base_h = 16, 6, 5
                    base_wt = 55

            # B. 美妆护肤品 (眼贴膜/精华/面霜/面膜)
            elif any(kw in t_lower for kw in ['патчи', 'патч']):
                base_l, base_w, base_h = 10, 10, 6
                base_wt = 180 + (pack_count - 1) * 120

            elif any(kw in t_lower for kw in ['сыворотк', 'serum', 'эссенци', 'концентрат']):
                base_l, base_w, base_h = 12, 5, 5
                base_wt = 110 + (pack_count - 1) * 80

            elif any(kw in t_lower for kw in ['крем', 'cream', 'флюид', 'бальзам']):
                base_l, base_w, base_h = 9, 8, 7
                base_wt = 160 + (pack_count - 1) * 120

            elif any(kw in t_lower for kw in ['маск', 'mask']):
                base_l, base_w, base_h = 16, 12, 3
                base_wt = 45 * pack_count + 20

            # C. 家居清洁 (拖把/拖把桶/清洁配件)
            elif any(kw in t_lower for kw in ['швабр', 'полотер', 'флаундер']):
                if any(k in t_lower for k in ['ведр', 'отжим', 'комплект', 'набор', 'ведро']):
                    base_l, base_w, base_h = 38, 24, 22
                    base_wt = 1850
                else:
                    base_l, base_w, base_h = 65, 14, 8
                    base_wt = 850

            elif any(kw in t_lower for kw in ['насадка для швабры', 'сменный моп', 'тряпка для швабры']):
                base_l, base_w, base_h = 28, 14, 4
                base_wt = 100 + (pack_count * 40)

            elif any(kw in t_lower for kw in ['ведро']):
                base_l, base_w, base_h = 30, 30, 26
                base_wt = 650

            # D. 运动健身 (弹力带/握力器/拉索手柄)
            elif any(kw in t_lower for kw in ['эспандер', 'жгут', 'резинка для фитнеса']):
                if any(k in t_lower for k in ['борцовск', 'трос', 'кабел', 'трубчат', 'силов']):
                    base_l, base_w, base_h = 26, 18, 8
                    base_wt = 850
                else:
                    base_l, base_w, base_h = 22, 12, 5
                    base_wt = 120 * pack_count + 30

            elif any(kw in t_lower for kw in ['динамометр']):
                base_l, base_w, base_h = 20, 14, 5
                base_wt = 420

            elif any(kw in t_lower for kw in ['рукоятк', 'ручки для тяги']):
                base_l, base_w, base_h = 22, 15, 6
                base_wt = 650

            # E. 水具与净水 (水杯/保温杯/滤芯)
            elif any(kw in t_lower for kw in ['термокружк', 'термостакан']):
                base_l, base_w, base_h = 19, 9, 9
                base_wt = 350

            elif 'термос' in t_lower and 'термостойк' not in t_lower:
                base_l, base_w, base_h = 24, 8, 8
                base_wt = 420

            elif any(kw in t_lower for kw in ['бутылк', 'шейкер', 'фляг']):
                base_l, base_w, base_h = 24, 8, 8
                base_wt = 220

            elif any(kw in t_lower for kw in ['картридж', 'кассет', 'модуль сменный']):
                base_l, base_w, base_h = 22, 16, 10
                base_wt = 350 + (pack_count * 120)

            # F. 通用基准
            else:
                base_l, base_w, base_h = 18, 12, 6
                base_wt = 200

            if length_cm is None:
                length_cm = max(8, base_l + var_dim)
            if width_cm is None:
                width_cm = max(5, base_w + (var_dim if base_w > 8 else 0))
            if height_cm is None:
                height_cm = max(2, base_h)
            if weight_g is None:
                weight_g = max(30, base_wt + var_wt)

        # 3. 第三层：合规约束与自然公差
        length_cm = int(max(5, length_cm))
        width_cm = int(max(5, width_cm))
        height_cm = int(max(2, height_cm))
        weight_g = int(max(20, weight_g))
        weight_kg = round(weight_g / 1000.0, 2)
        if weight_kg <= 0:
            weight_kg = 0.05

        return {
            'length_cm': length_cm,
            'width_cm': width_cm,
            'height_cm': height_cm,
            'weight_g': weight_g,
            'weightBrutto': weight_kg,
            'tnved': tnved,
            'is_inferred': True
        }
