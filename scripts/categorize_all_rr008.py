# -*- coding: utf-8 -*-
import json, os, sys, re

try:
    sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
except:
    pass

archive_path = r'c:\Users\Administrator\Documents\google drive\ozon-to-wb-fast-listing\rr008_listed_products.json'
with open(archive_path, 'r', encoding='utf-8') as f:
    products = json.load(f)

ref_path = r'c:\Users\Administrator\Documents\google drive\ozon-to-wb-fast-listing\references\wb_all_subjects.json'
with open(ref_path, 'r', encoding='utf-8') as f:
    all_subjects = json.load(f)

# Build a subject dictionary by ID
subj_by_id = {s['subjectID']: s for s in all_subjects}

def determine_correct_subject(title: str, category_path: str = "") -> dict:
    t = title.lower()
    
    # 1. 拖把类 / 擦窗器 / 拖把桶 / 喷水拖把 (Швабры, 1594)
    # Exclude mop refills/heads
    if any(k in t for k in ['насадка для швабры', 'насадки для швабр', 'сменная насадка для швабры', 'тряпка для швабры', 'сменные насадки для швабр', 'насадка на швабру', 'насадки на швабру', 'сменная насадка на швабру', 'тряпки для швабры', 'моп для швабры', 'сменный моп', 'насадки моп']):
        return {"subjectID": 2257, "subjectName": "Насадки для швабр", "category": "Mop Heads"}
    
    if any(k in t for k in ['швабр', 'флаундер', 'полотер', 'окномойк', 'стеклоочистител', 'склиз для окон', 'водосгон']):
        return {"subjectID": 1594, "subjectName": "Швабры", "category": "Mops"}
        
    if any(k in t for k in ['ведро хозяйственн', 'ведро для мусора', 'ведро строительн', 'ведро складн', 'ведро с отжимом', 'ведро']):
        # If bucket with mop -> usually Швабры 1594 or Ведра хозяйственные 1436
        if 'швабр' in t:
            return {"subjectID": 1594, "subjectName": "Швабры", "category": "Mops & Buckets"}
        return {"subjectID": 1436, "subjectName": "Ведра хозяйственные", "category": "Buckets"}

    if any(k in t for k in ['набор для уборки', 'комплект для уборки']):
        return {"subjectID": 1594, "subjectName": "Швабры", "category": "Cleaning Sets"}

    # 2. 运动健身 / 弹力带 / 阻力带 / 扩胸器 / 健身绳 / 握力计 / 力量拉索 (Эспандеры 249, Динамометры 3659, Рукоятки для тренажеров 5251, Тренажеры 475)
    if any(k in t for k in ['динамометр']):
        return {"subjectID": 3659, "subjectName": "Динамометры", "category": "Dynamometers"}
    
    if any(k in t for k in ['рукоятки для тренажера', 'рукоятка для тренажера', 'рукоятки для тренажеров', 'рукоятка для тяги', 'рукоятки для тяги', 'ручки для тяги', 'ручка для армлифтинга', 'рукоятка для кроссовера', 'ручки мягкая тяга']):
        return {"subjectID": 5251, "subjectName": "Рукоятки для тренажеров", "category": "Gym Handles"}
        
    if any(k in t for k in [
        'эспандер', 'резинка для фитнеса', 'резинки для фитнеса', 'фитнес резинк', 'фитнес-резинк',
        'борцовская резина', 'борцовский жгут', 'резина для дзюдо', 'резина для борьбы', 'резина для плавания',
        'резина для тренировки', 'жгут спортивный', 'жгут резиновый спортивный', 'петли резиновые', 'петля резиновая',
        'лента силовая', 'лента для фитнеса', 'лента латексная', 'эспандер ленточный', 'эспандер кистевой',
        'эспандер трубчатый', 'эспандер пружинный', 'эспандер плечевой', 'эспандер-бабочка', 'эспандер для пальцев',
        'эспандер лыжника', 'эспандер боксера', 'эспандер гироскопический', 'жгут атлетический', 'резина с захватами',
        'набор резинок для подтягивания', 'резинка для подтягивания', 'фитнес лента', 'силовой трос', 'силовых кабелей',
        'кабель силовой спортивный', 'жгут медицинский', 'эспандер-петля'
    ]):
        return {"subjectID": 249, "subjectName": "Эспандеры", "category": "Expanders & Bands"}

    if any(k in t for k in ['тренажер', 'тренажёр']):
        return {"subjectID": 475, "subjectName": "Тренажеры", "category": "Trainers"}

    # 3. 净水 / 水过滤 / 滤水壶 / 滤芯 / 滤料 / 渗透膜 (Кассеты 3741, Фильтры-кувшины 940, Фильтры под мойку 7688/1435)
    # Let's see: Pitchers vs Cartridges vs RO Systems
    if any(k in t for k in ['фильтр-кувшин', 'фильтр кувшин', 'кувшин для очистки воды', 'кувшин водоочиститель']):
        return {"subjectID": 940, "subjectName": "Фильтры-кувшины для воды", "category": "Filter Pitchers"}
        
    if any(k in t for k in [
        'кассета для фильтра', 'кассеты для фильтра', 'кассета фильтра', 'кассеты сменные', 'картридж для фильтра-кувшина',
        'сменный картридж для фильтра-кувшина', 'модуль для кувшина'
    ]):
        return {"subjectID": 3741, "subjectName": "Кассеты для фильтров-кувшинов", "category": "Pitcher Cartridges"}

    if any(k in t for k in [
        'картридж', 'кассет', 'сменный модуль', 'модуль сменный', 'набор сменных фильтров', 'комплект сменных модулей',
        'мембрана', 'обратного осмоса', 'минерализатор', 'постфильтр', 'предфильтр', 'префильтр', 'аквафор', 'гейзер', 'барьер',
        'смола', 'шунгит', 'кварц зернистый', 'засыпка', 'ионообменная', 'фильтр под мойку', 'колба для фильтра',
        'очистки воды', 'фильтрации воды', 'умягчения воды', 'фильтр магистральный', 'brita', 'maxtra', 'фильтр для воды',
        'фильтр для жесткой воды', 'фильтрующих', 'наполнитель фильтра', 'сорбент', 'самопромывной фильтр'
    ]):
        return {"subjectID": 3741, "subjectName": "Кассеты для фильтров-кувшинов", "category": "Filter Cartridges"}

    if any(k in t for k in ['силовой', 'трос', 'кабель']):
        return {"subjectID": 249, "subjectName": "Эспандеры", "category": "Expanders"}

    # 4. 保温杯 / 保温瓶 / 随行杯 / 运动水壶 / 水杯
    if any(k in t for k in ['термокружк', 'термостакан', 'автокружк']):
        return {"subjectID": 1274, "subjectName": "Термокружки", "category": "Thermal Mugs"}
        
    if 'термос' in t and 'термостойк' not in t and 'термопаст' not in t:
        return {"subjectID": 511, "subjectName": "Термосы", "category": "Thermoses"}

    if any(k in t for k in ['бутылк', 'фляг', 'шейкер', 'bottle']):
        return {"subjectID": 384, "subjectName": "Бутылки для воды", "category": "Water Bottles"}

    if any(k in t for k in ['кружк', 'стакан', 'чашк', 'бокал']):
        return {"subjectID": 812, "subjectName": "Кружки", "category": "Mugs / Cups"}

    if any(k in t for k in ['крышка', 'пробка']):
        return {"subjectID": 819, "subjectName": "Крышки", "category": "Lids / Caps"}

    # 5. 其他特殊商品
    if any(k in t for k in ['массажные шары', 'массажер']):
        return {"subjectID": 983, "subjectName": "Массажеры механические", "category": "Massagers"}

    if any(k in t for k in ['маска для сипап', 'маска']):
        return {"subjectID": 249, "subjectName": "Спортивный товар / Маски", "category": "Masks"}

    if any(k in t for k in ['black afgano', 'парфюм', 'духи']):
        return {"subjectID": 1952, "subjectName": "Парфюмерная вода", "category": "Perfume"}

    return {"subjectID": None, "subjectName": "UNKNOWN", "category": "Unknown"}

# Test all 591 products
unmatched = []
categorized = {}

for p in products:
    title = p.get('title', '')
    res = determine_correct_subject(title)
    sid = res.get('subjectID')
    sname = res.get('subjectName')
    
    if not sid:
        unmatched.append(p)
    else:
        categorized.setdefault(f"{sid}: {sname}", []).append(p)

print(f"Total products: {len(products)}")
print(f"Successfully matched: {len(products) - len(unmatched)}")
print(f"Unmatched: {len(unmatched)}")

print("\n--- Breakdown of All 591 Products by Correct Subject ---")
for cat, items in sorted(categorized.items(), key=lambda x: len(x[1]), reverse=True):
    print(f"  • {cat}: {len(items)} items")

if unmatched:
    print("\n--- Unmatched Items ---")
    for u in unmatched[:10]:
        print(f"  SKU {u.get('sku')}: {u.get('title')}")
