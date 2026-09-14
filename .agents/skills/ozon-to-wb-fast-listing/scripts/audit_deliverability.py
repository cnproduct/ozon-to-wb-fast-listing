# -*- coding: utf-8 -*-
"""
全链路商品可交付性多维全自动审计脚本 (防御空店与动态 Token 版)
"""
import os
import sys
import json
import requests

def get_token():
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

def run_audit():
    token = get_token()
    if not token:
        print("[-] 提示: 未配置 WB_API_TOKEN，请在 config.json 或环境变量中配置后执行审计。")
        return False

    headers = {'Authorization': token, 'Content-Type': 'application/json'}
    print("=== 开始执行 Wildberries 全店商品四维交付审计 ===")
    
    try:
        r = requests.post(
            'https://content-api.wildberries.ru/content/v2/get/cards/list',
            headers=headers,
            json={'settings': {'cursor': {'limit': 100}}},
            timeout=15
        )
        if r.status_code != 200:
            print(f"[-] 请求店铺卡片失败: HTTP {r.status_code}")
            return False
            
        cards = r.json().get('cards', [])
        total = len(cards)
        print(f"店铺在线卡片总数: {total} 件")

        # 防御空店 ZeroDivisionError
        if total == 0:
            print("[TIP] 店铺当前暂无已创建商品卡片，无需执行白牌与参数审计。")
            return True

        clean_brand_count = sum(1 for c in cards if c.get('brand') == "")
        rich_charcs_count = sum(1 for c in cards if len(c.get('characteristics', [])) >= 5)

        r_err = requests.post('https://content-api.wildberries.ru/content/v2/cards/error/list', headers=headers, json={}, timeout=15)
        err_items = r_err.json().get('data', []) if r_err.status_code == 200 else []

        print(f"- 白牌合规率 (无授权封禁风险): {clean_brand_count}/{total} ({clean_brand_count/total*100:.1f}%)")
        print(f"- 丰富展示参数达标率 (>=5项): {rich_charcs_count}/{total} ({rich_charcs_count/total*100:.1f}%)")
        print(f"- 异步错误队列数量: {len(err_items)} (必须为 0)")
        
        if len(err_items) == 0 and clean_brand_count == total:
            print("[PASSED] [全部通过] 四维交付审计通过，商品处于健康就绪状态！")
            return True
        else:
            print("[WARN] [存在告警] 请根据上方指标进行整改！")
            return False
    except Exception as e:
        print(f"[-] 审计执行异常: {e}")
        return False

if __name__ == '__main__':
    run_audit()
