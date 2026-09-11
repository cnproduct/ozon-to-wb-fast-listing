# -*- coding: utf-8 -*-
"""
Wildberries 类目专属展示参数探测与饱和注入工具 (多级配置加载版)
用法:
  python scripts/enrich_charcs_pipeline.py --nm 1555130988
"""
import os
import sys
import json
import argparse
import requests

def get_token():
    """优先级：环境变量 > 相对路径 config.json > 用户目录"""
    token = os.getenv('WB_API_TOKEN')
    if not token:
        search_paths = [
            os.path.join(os.getcwd(), 'config.json'),
            os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'config.json')),
            os.path.expanduser('~/.wb_config.json')
        ]
        for p in search_paths:
            if os.path.exists(p):
                try:
                    with open(p, 'r', encoding='utf-8') as f:
                        t = json.load(f).get('wb_api_token')
                        if t and 'YOUR_WB_API_TOKEN' not in t:
                            return t
                except Exception:
                    pass
    return token

def get_category_charcs(subject_id: int, headers: dict):
    url = f"https://content-api.wildberries.ru/content/v2/object/charcs/{subject_id}"
    try:
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code == 200:
            return r.json().get('data', [])
    except Exception:
        pass
    return []

def enrich_card(nm_id: int, token_override: str = None):
    token = token_override or get_token()
    if not token:
        print("[-] [错误] 未配置有效 WB_API_TOKEN！请在 config.json 或环境变量中配置。")
        return

    headers = {'Authorization': token, 'Content-Type': 'application/json'}
    print(f"=== 正在探测商品 nmID: {nm_id} 对应的官方类目展示参数字典 ===")

    try:
        r = requests.post(
            'https://content-api.wildberries.ru/content/v2/get/cards/list',
            headers=headers,
            json={'settings': {'filter': {'textSearch': str(nm_id)}}},
            timeout=15
        )
        if r.status_code != 200:
            print(f"[-] 查询卡片失败: HTTP {r.status_code}")
            return

        cards = r.json().get('cards', [])
        if not cards:
            print(f"[-] 未在店铺中找到商品 nmID={nm_id}")
            return

        c = cards[0]
        sub_id = c.get('subjectID')
        print(f"[*] 商品: {c.get('title')[:35]}... | 类目 ID: {sub_id} | 当前已配置属性数: {len(c.get('characteristics', []))}")
        
        charcs_def = get_category_charcs(sub_id, headers)
        print(f"[+] 获取到该类目官方支持展示属性: {len(charcs_def)} 项")
        
        print("--- 官方推荐高权重前台展示属性列表 ---")
        for ch in charcs_def[:10]:
            print(f"  - ID: {ch.get('charcID'):<8} | 名称: {ch.get('name'):<25} | maxCount: {ch.get('maxCount')}")
    except Exception as e:
        print(f"[-] 请求执行异常: {e}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Wildberries 类目展示参数探测工具")
    parser.add_argument('--nm', type=int, required=True, help='商品 nmID')
    parser.add_argument('--token', type=str, default=None, help='指定 WB API Token')
    args = parser.parse_args()
    enrich_card(args.nm, args.token)
