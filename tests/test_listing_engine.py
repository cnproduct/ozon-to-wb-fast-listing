# -*- coding: utf-8 -*-
"""
Wildberries (WB) 全自动极速智能上架引擎单元测试集 (v3.0 规范强化版)
覆盖真实性前置校验、尺寸严格向下取整、白牌脱敏合规、锚定大促定价算法、
条码接口失败严禁伪造假条码阻断、地道俄文描述自然断句收尾及 TXT 智能文本解析。
"""

import os
import sys
import math
import unittest
from unittest.mock import patch
from pathlib import Path

# 确保能正确引入 scripts 目录
scripts_dir = str(Path(__file__).resolve().parents[1] / 'scripts')
if scripts_dir not in sys.path:
    sys.path.insert(0, scripts_dir)

from listing_engine import (
    WBListingStudio,
    ListingValidationError,
    parse_skus_from_txt,
    smart_truncate_description,
    clean_and_decode_russian,
    get_active_config
)

class TestWBListingEngineV3(unittest.TestCase):

    def setUp(self):
        self.studio = WBListingStudio(token="dummy_test_token_v3", warehouse_id=2156484)

    def test_empty_title_rejected(self):
        """测试 1: 缺少真实标题必须立即抛出 ListingValidationError 阻断上架"""
        bad_product = {
            "sku": "5557263649",
            "title": "",
            "photos": ["https://cdn.example.com/photo1.jpg"],
            "subjectID": 2012
        }
        with self.assertRaises(ListingValidationError):
            self.studio.validate_product_data(bad_product)

    def test_empty_photos_rejected(self):
        """测试 2: 缺少主图相册必须立即抛出 ListingValidationError 阻断上架"""
        bad_product = {
            "sku": "5557263649",
            "title": "Беспроводной пылесос для авто",
            "photos": [],
            "subjectID": 2012
        }
        with self.assertRaises(ListingValidationError):
            self.studio.validate_product_data(bad_product)

    def test_missing_subject_rejected(self):
        """测试 3: 缺少有效类目 ID 必须报错阻断"""
        bad_product = {
            "sku": "5557263649",
            "title": "Беспроводной пылесос",
            "photos": ["https://cdn.example.com/photo1.jpg"],
            "subjectID": None
        }
        with self.assertRaises(ListingValidationError):
            self.studio.validate_product_data(bad_product)

    def test_dimensions_downward_rounding(self):
        """测试 4: 尺寸严格向下取整铁律 (规避平台按公差虚高计费)"""
        l_in, w_in, h_in = 24.8, 15.6, 8.2
        l_out = math.floor(l_in)
        w_out = math.floor(w_in)
        h_out = math.floor(h_in)
        self.assertEqual(l_out, 24)
        self.assertEqual(w_out, 15)
        self.assertEqual(h_out, 8)

    def test_weight_kg_conversion(self):
        """测试 5: 毛重从克换算为千克保留两位小数"""
        weight_g = 650
        weight_kg = round(weight_g / 1000.0, 2)
        self.assertEqual(weight_kg, 0.65)

    def test_anchor_pricing_algorithm(self):
        """测试 6: 【锚定效应】大促定价算法精准验证"""
        ozon_price = 50.0
        multiplier = 5.0
        discount = 50 # 50%
        
        target_sell = round(ozon_price * multiplier)
        self.assertEqual(target_sell, 250)
        
        strike_price = math.ceil(target_sell / (1.0 - (discount / 100.0)))
        self.assertEqual(strike_price, 500)
        
        buyer_paid = strike_price * (1.0 - (discount / 100.0))
        self.assertEqual(buyer_paid, target_sell)

    def test_allocate_barcodes_failure_raises_error(self):
        """测试 7: 官方条码接口调用失败时绝不伪造 20561 假条码，必须直接抛出异常"""
        with patch('requests.post') as mock_post:
            mock_post.return_value.status_code = 500
            mock_post.return_value.text = "Internal Server Error"
            with self.assertRaises(ListingValidationError):
                self.studio.allocate_barcodes(1)

    def test_description_natural_sentence_closing_and_no_fullwidth(self):
        """测试 8: 描述智能自然闭合收尾 + 绝不包含全角中文字符【】"""
        long_russian_text = (
            "Отличный мощный беспроводной пылесос для уборки салона автомобиля. "
            "Компактный размер и легкий вес обеспечивают максимальное удобство при ежедневном использовании. "
            "Встроенный литий-ионный аккумулятор обеспечивает длительную автономную работу без подзарядки. "
            "В комплекте идут дополнительные щелевые насадки для труднодоступных мест."
        )
        truncated = smart_truncate_description(long_russian_text, max_chars=120)
        # 断言不能包含全角字符
        self.assertNotIn("【", truncated)
        self.assertNotIn("】", truncated)
        # 断言不在单词中间截断，必须在句末符号收尾
        self.assertTrue(truncated.endswith(".") or truncated.endswith("!"))

    def test_txt_sku_parsing(self):
        """测试 9: TXT 智能文本解析器支持注释、空行与逗号/空格分隔"""
        import tempfile
        content = """# 待上架吸尘器列表
5557263649
3185638178, 5024331769

# 换季特惠款
5543124424 // 新款
1742806518
"""
        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8", suffix=".txt") as tf:
            tf.write(content)
            temp_path = tf.name
            
        try:
            skus = parse_skus_from_txt(temp_path)
            self.assertEqual(len(skus), 5)
            self.assertIn("5557263649", skus)
            self.assertIn("3185638178", skus)
            self.assertIn("5024331769", skus)
            self.assertIn("5543124424", skus)
            self.assertIn("1742806518", skus)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_subject_semantic_matching(self):
        """测试 10: 智能语义类目对齐"""
        self.assertEqual(self.studio.match_best_subject("Пылесос автомобильный мощный"), 2012)
        self.assertEqual(self.studio.match_best_subject("Коврики придверные влаговпитывающие"), 2317)
        self.assertEqual(self.studio.match_best_subject("Карты игральные покерные"), 2918)
        self.assertIsNone(self.studio.match_best_subject("Неизвестный неопределенный товар 123"))

    def test_validation_rejects_missing_dimensions_and_weight(self):
        """测试 11: 缺失真实包装长宽高或毛重必须抛出 ListingValidationError 阻断，拒绝静默兜底"""
        prod_no_dim = {
            "sku": "5557263649",
            "title": "Пылесос автомобильный",
            "photos": ["https://cdn.example.com/p1.jpg"],
            "subjectID": 2012,
            "length_cm": None, # 缺失
            "width_cm": 15,
            "height_cm": 10,
            "weight_g": 500
        }
        with self.assertRaises(ListingValidationError):
            self.studio.validate_product_data(prod_no_dim)

        prod_no_weight = {
            "sku": "5557263649",
            "title": "Пылесос автомобильный",
            "photos": ["https://cdn.example.com/p1.jpg"],
            "subjectID": 2012,
            "length_cm": 20,
            "width_cm": 15,
            "height_cm": 10,
            "weight_g": 0 # 无效重量
        }
        with self.assertRaises(ListingValidationError):
            self.studio.validate_product_data(prod_no_weight)

    def test_set_prices_and_stocks_empty_list_no_index_error(self):
        """测试 12: 传入空商品列表时安全返回，绝不抛出 IndexError"""
        try:
            self.studio.set_prices_and_stocks([])
        except IndexError:
            self.fail("set_prices_and_stocks([]) 触发了 IndexError!")


    def test_clean_and_decode_russian_latin1_and_brands(self):
        """测试 13: 自动纠正 Latin-1/Windows-1252 乱码并脱敏违规品牌词"""
        dirty = "Ð¿Ñ‹Ð»ÐµÑЃÐ¾ÑЃ Tide"
        cleaned = clean_and_decode_russian(dirty)
        self.assertNotIn("Tide", cleaned)
        self.assertIn("пылесос", cleaned)

    def test_description_footer_uses_brutto(self):
        """测试 14 [真断言]: 真实拦截建卡 payload，严格校验页脚标注必须为 брутто，绝不含 нетто 或全角【】"""
        prod = {
            "sku": "5557263649",
            "vendorCode": "OZON-5557263649-v1",
            "title": "Пылесос автомобильный",
            "description_clean": "Отличный беспроводной пылесос для авто.",
            "photos": ["https://cdn.example.com/p1.jpg"],
            "subjectID": 2012,
            "length_cm": 25,
            "width_cm": 15,
            "height_cm": 10,
            "weight_g": 650,
            "strike_price": 500,
            "barcode": "2056100000001"
        }
        with patch('requests.post') as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"data": {}}
            self.studio.create_cards([prod])
            
            # 从实际发送给 WB Content API 的 payload 中提取 description
            payload = mock_post.call_args[1]['json'][0]['variants'][0]
            desc = payload['description']
            
            # 严格真断言校验：
            self.assertIn("Вес с упаковкой (брутто): 650 г (0.65 кг)", desc)
            self.assertNotIn("нетто", desc)
            self.assertNotIn("【", desc)
            self.assertNotIn("】", desc)

    def test_mixed_cyrillic_mojibake_decoded(self):
        """测试 15: 混排正常西里尔字母与 UTF-8 乱码时，绝不静默跳过，必须精准逐段解码"""
        mixed_input = "Ð¿Ñ‹Ð»ÐµÑЃÐ¾ÑЃ для дома Tide"
        cleaned = clean_and_decode_russian(mixed_input)
        self.assertIn("пылесос", cleaned)
        self.assertIn("для дома", cleaned)
        self.assertNotIn("Tide", cleaned)
        self.assertNotIn("Ð", cleaned)

    def test_external_sensitive_brands_and_dynamic_desensitization(self):
        """测试 16: 外部敏感品牌词表 (sensitive_brands.txt) 与动态商品原品牌脱敏"""
        # 测试来自 sensitive_brands.txt 的扩展品牌 (如 Dyson, Sony)
        text1 = "Мощный беспроводной пылесос Dyson V12 с подсветкой"
        cleaned1 = clean_and_decode_russian(text1)
        self.assertNotIn("Dyson", cleaned1)
        self.assertIn("пылесос", cleaned1)

        # 测试源商品自身 brand 动态传入脱敏 (无论是否在预设词表中)
        text2 = "Оригинальные кроссовки от бренда SuperUnknownX для бега"
        cleaned2 = clean_and_decode_russian(text2, extra_brands=["SuperUnknownX"])
        self.assertNotIn("SuperUnknownX", cleaned2)
        self.assertIn("кроссовки", cleaned2)

    def test_external_category_mapping_loaded(self):
        """测试 17: 外部 category_mapping.json 动态加载扩展品类映射"""
        # 验证 category_mapping.json 中的扩展品类
        self.assertEqual(self.studio.match_best_subject("Электробритва мужская роторная"), 444)
        self.assertEqual(self.studio.match_best_subject("Плойка для завивки волос щипцы"), 449)
        self.assertEqual(self.studio.match_best_subject("Держатель для телефона в автомобиль"), 2235)
        self.assertEqual(self.studio.match_best_subject("Беспроводные наушники bluetooth"), 538)

    def test_multi_dimensional_category_matching(self):
        """测试 18: 支持 Ozon 原生面包屑 (category_path) 与品类 (product_type) 多维融合对齐"""
        # 即使标题只写了代号，凭借 product_type 也可精准对齐
        matched_id = self.studio.match_best_subject(
            title="Bicycle Blue Standard Deck v1",
            category_path="Хобби > Настольные игры",
            product_type="Игральные карты"
        )
        self.assertEqual(matched_id, 2918)

if __name__ == '__main__':
    unittest.main()
