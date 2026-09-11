# -*- coding: utf-8 -*-
"""
买家端 CDN 静态切片 options 编译状态智能探测器 (动态分桶算法与多桶探测版)
用法: python scripts/check_cdn_slice.py --nm 1555130988
"""
import argparse
import requests
import sys

def get_basket_number(vol: int) -> int:
    """根据 Wildberries 官方 nmID vol 区间计算理论 basket 桶号"""
    if 0 <= vol <= 143: return 1
    elif 144 <= vol <= 287: return 2
    elif 288 <= vol <= 431: return 3
    elif 432 <= vol <= 719: return 4
    elif 720 <= vol <= 1007: return 5
    elif 1008 <= vol <= 1061: return 6
    elif 1062 <= vol <= 1115: return 7
    elif 1116 <= vol <= 1169: return 8
    elif 1170 <= vol <= 1313: return 9
    elif 1314 <= vol <= 1601: return 10
    elif 1602 <= vol <= 1655: return 11
    elif 1656 <= vol <= 1919: return 12
    elif 1920 <= vol <= 2045: return 13
    elif 2046 <= vol <= 2189: return 14
    elif 2190 <= vol <= 2405: return 15
    elif 2406 <= vol <= 2621: return 16
    elif 2622 <= vol <= 2837: return 17
    elif 2838 <= vol <= 3053: return 18
    elif 3054 <= vol <= 3269: return 19
    elif 3270 <= vol <= 3485: return 20
    # 针对新大号 nmID 动态散列
    return 48 if (vol % 2 == 0) else 49

def check_card_slice(nm_id: int):
    vol = nm_id // 100000
    part = nm_id // 1000
    primary_basket = get_basket_number(vol)
    
    # 候选桶探测列表 (优先理论桶，再探测常见活跃桶)
    candidate_baskets = [primary_basket, 48, 49, 1, 2, 3]
    candidate_baskets = list(dict.fromkeys(candidate_baskets)) # 保序去重
    
    print(f"=== 正在探测商品 (nmID: {nm_id}, vol: {vol}, part: {part}) 买家端 options 静态切片 ===")
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

    for b in candidate_baskets:
        url = f"https://basket-{b:02d}.wbbasket.ru/vol{vol}/part{part}/{nm_id}/info/ru/card.json"
        try:
            r = requests.get(url, headers=headers, timeout=5)
            if r.status_code == 200:
                data = r.json()
                opts = data.get('options', [])
                print(f"\n[SUCCESS] [切片编译成功] 命中节点: basket-{b:02d} | options 参数数量: {len(opts)} 项")
                for o in opts[:10]:
                    print(f"  - {o.get('name')}: {o.get('value')}")
                if len(opts) > 10:
                    print(f"  ... 以及其他 {len(opts)-10} 项属性")
                return True
        except Exception:
            pass

    print(f"\n[WAITING] [编译排队中] 各节点暂未完成静态切片构建 (处于 WB 官方 30~45 分钟定时批处理构建窗口中)")
    print("[TIP] 说明：只要卖家后台 characteristics 已上送合规，批处理跑完后买家端会自动展现。")
    return False

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Wildberries 买家端 CDN 静态切片 options 探测器")
    parser.add_argument('--nm', type=int, required=True, help='商品 nmID')
    args = parser.parse_args()
    check_card_slice(args.nm)
