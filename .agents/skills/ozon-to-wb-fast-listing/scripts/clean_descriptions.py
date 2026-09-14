# -*- coding: utf-8 -*-
"""
俄文描述双重编码乱码纠偏与敏感品牌脱敏清洗工具 (v3.0 动态词表配置化版)
精准支持纯乱码、正常西里尔字符以及两者混排的逐段字节级修复，
并支持从 references/sensitive_brands.txt 与 config.json 动态加载脱敏词表，
同时支持针对具体商品动态传入源品牌名彻底脱敏。
"""
import os
import re
import sys
import json
from typing import List, Optional

# 常见 Windows-1252 / CP1251 乱码字符到原始 UTF-8 字节的逆向映射字典
MOJIBAKE_BYTE_MAP = {
    0x20AC: 0x80, # € -> 0x80
    0x0403: 0x81, # Ѓ -> 0x81
    0x201A: 0x82, # ‚ -> 0x82
    0x0192: 0x83, # ƒ -> 0x83
    0x201E: 0x84, # „ -> 0x84
    0x2026: 0x85, # … -> 0x85
    0x2020: 0x86, # † -> 0x86
    0x2021: 0x87, # ‡ -> 0x87
    0x02C6: 0x88, # ˆ -> 0x88
    0x2030: 0x89, # ‰ -> 0x89
    0x0160: 0x8A, # Š -> 0x8A
    0x2039: 0x8B, # ‹ -> 0x8B
    0x0152: 0x8C, # Œ -> 0x8C
    0x017D: 0x8E, # Ž -> 0x8E
    0x2018: 0x91, # ‘ -> 0x91
    0x2019: 0x92, # ’ -> 0x92
    0x201C: 0x93, # “ -> 0x93
    0x201D: 0x94, # ” -> 0x94
    0x2022: 0x95, # • -> 0x95
    0x2013: 0x96, # – -> 0x96
    0x2014: 0x97, # — -> 0x97
    0x02DC: 0x98, # ˜ -> 0x98
    0x2122: 0x99, # ™ -> 0x99
    0x0161: 0x9A, # š -> 0x9A
    0x203A: 0x9B, # › -> 0x9B
    0x0153: 0x9C, # œ -> 0x9C
    0x017E: 0x9E, # ž -> 0x9E
    0x0178: 0x9F  # Ÿ -> 0x9F
}

# 内置兜底核心知名品牌词
DEFAULT_CORE_BRANDS = [
    'Tide', 'SHIK', 'Tuvio', 'Pragma', 'Marble Moscow', 'POWERSTREAM', 'GOAR',
    'Apple', 'Nike', 'Adidas', 'Sony', 'Samsung', 'Xiaomi', 'Mijia', 'Dyson', 'Philips'
]

def load_sensitive_brands() -> List[str]:
    """从外部配置文件动态加载敏感品牌列表 (优先 sensitive_brands.txt 与 config.json)"""
    brands = list(DEFAULT_CORE_BRANDS)
    
    # 1. 尝试从 references/sensitive_brands.txt 加载
    ref_paths = [
        os.path.join(os.path.dirname(__file__), '..', 'references', 'sensitive_brands.txt'),
        os.path.join(os.getcwd(), 'references', 'sensitive_brands.txt')
    ]
    for rp in ref_paths:
        if os.path.exists(rp):
            try:
                with open(rp, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and line not in brands:
                            brands.append(line)
            except Exception:
                pass
            break

    # 2. 尝试从 config.json 加载 sensitive_brands
    cfg_paths = [
        os.path.join(os.getcwd(), 'config.json'),
        os.path.join(os.path.dirname(__file__), '..', 'config.json')
    ]
    for cp in cfg_paths:
        if os.path.exists(cp):
            try:
                with open(cp, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
                    for b in cfg.get('sensitive_brands', []):
                        if b and b not in brands:
                            brands.append(b)
            except Exception:
                pass
            break
            
    return brands

def clean_and_decode_russian(text: str, extra_brands: Optional[List[str]] = None) -> str:
    """
    精准纠正 Latin-1/Windows-1252 双重编码乱码，并剔除未授权敏感品牌词
    - text: 待清洗俄文文本
    - extra_brands: 针对当前商品动态指定的品牌名称 (如 Ozon 源数据中的 brand 字段)
    """
    if not text:
        return ""

    # 1. 逐词/逐段智能匹配典型的以 Ð 或 Ñ 开头的乱码序列并按字节修复
    def fix_mojibake_chunk(match):
        word = match.group(0)
        ba = bytearray([MOJIBAKE_BYTE_MAP.get(ord(c), ord(c) if ord(c) < 256 else 0) for c in word])
        try:
            decoded = ba.decode('utf-8')
            if any('\u0400' <= c <= '\u04ff' for c in decoded):
                return decoded
        except Exception:
            pass
        return word

    mojibake_pattern = re.compile(r'[ÐÑ][^\s,.:;!?()]+')
    text = mojibake_pattern.sub(fix_mojibake_chunk, text)

    # 2. 动态聚合全部敏感品牌词
    active_brands = load_sensitive_brands()
    if extra_brands:
        for eb in extra_brands:
            if eb and str(eb).strip() and str(eb).strip() not in active_brands:
                active_brands.append(str(eb).strip())

    # 3. 按长度倒序剥离品牌词 (优先匹配长词，如 Marble Moscow 优先于 Moscow)
    active_brands.sort(key=lambda x: len(x), reverse=True)
    for b in active_brands:
        # 使用单词边界或精准匹配
        text = re.sub(r'\b' + re.escape(b) + r'\b', '', text, flags=re.IGNORECASE)
        # 兼容不带边界的极端情况
        text = re.sub(re.escape(b), '', text, flags=re.IGNORECASE)

    # 4. 彻底清除所有 Emoji 表情符、杂质字符与特殊图标
    emoji_pattern = re.compile(
        r'[\U00010000-\U0010ffff]'  # 4-byte Emojis (🍓, 🚀, 👍, etc.)
        r'|[\u2600-\u27BF]'          # Misc symbols & dingbats (✔, ★, ⚡, ✈, etc.)
        r'|[\u2300-\u23FF]'          # Misc technical
        r'|[\u2B50-\u2B55]'          # Stars and circles
        r'|[\u200B-\u200D\uFEFF]'    # Zero-width spaces
        r'|[©®™▪►◄★☆✓✦✧✨💥🔥【】·•✔]'
    )
    text = emoji_pattern.sub(' ', text)

    # 5. 铁律：100% 彻底剥离 Ozon 编码、SKU 货号及平台痕迹 (严禁暴露给 WB 买家)
    # 匹配各类俄文/英文提及 Ozon 编码、商品编码、SKU 的整行或片段
    ozon_patterns = [
        r'(?i)[-\s*•]*Код\s+товара\s*(?:Ozon)?\s*[:：]?\s*\d+\s*',
        r'(?i)[-\s*•]*Артикул\s*(?:Ozon|товара)?\s*[:：]?\s*\d+\s*',
        r'(?i)[-\s*•]*Ozon\s*(?:SKU|ID|код)?\s*[:：]?\s*\d+\s*',
        r'(?i)\bOzon\b'
    ]
    for op in ozon_patterns:
        text = re.sub(op, '', text)

    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

if __name__ == '__main__':
    sample = "Ð¿Ñ‹Ð»ÐµÑЃÐ¾ÑЃ для дома Tide"
    cleaned = clean_and_decode_russian(sample, extra_brands=["CustomUnknownBrand"])
    print("[SUCCESS] clean_and_decode_russian 运行成功，清洗后长度:", len(cleaned))
