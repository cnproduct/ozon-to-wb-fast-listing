# -*- coding: utf-8 -*-
"""
Smart Category Matcher for Wildberries
Implements 3-Tier Category Semantic Alignment SOP
1. High-Priority Curated Domain Mapping
2. Deep Semantic Token Matching against all 6,925 official WB subjects
3. Strict Quality Gate (Zero Dummy Fallback)
"""
import os, sys, re, json

class SmartCategoryMatcher:
    def __init__(self, subjects_json_path=None):
        if not subjects_json_path:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            subjects_json_path = os.path.join(base_dir, 'references', 'wb_all_subjects.json')
            
        with open(subjects_json_path, 'r', encoding='utf-8') as f:
            self.wb_subjects = json.load(f)
            
        self.wb_by_id = {s['subjectID']: s for s in self.wb_subjects}
        self.wb_by_name = {s['subjectName'].lower(): s for s in self.wb_subjects}

    def match(self, title, category_path=""):
        tl = (title or "").lower()
        cl = (category_path or "").lower()
        
        # 1. Mops, Buckets, Cleaning Tools
        if 'швабр' in tl or 'mop' in tl:
            if 'паров' in tl: return 2584, 'Паровые швабры'
            if any(k in tl for k in ['насадк', 'сменн', 'тряпк', 'насадо', 'моп']): return 2257, 'Насадки для швабр'
            return 1594, 'Швабры'
        if 'ведро' in tl or 'ведром' in tl or 'ведра' in tl:
            if 'мусор' in tl: return 1593, 'Ведра для мусора'
            return 1436, 'Ведра хозяйственные'
        if 'окномойк' in tl or 'стеклоочистител' in tl or 'мойщик окон' in tl:
            return 2011, 'Стеклоочистители'

        # 2. Bicycle Accessories & Lighting (Priority)
        if any(k in tl for k in ['фонар', 'фара', 'светильник', 'подсветк', 'мигалк', 'габарит', 'велофонар', 'knog', 'blinder', 'ravemen', 'rockbros']):
            if any(k in tl for k in ['вело', 'самокат', 'руль', 'подседельн', 'велосипед', 'rhl', 'blinder', 'knog', 'ravemen', 'rockbros', 'передний', 'задний', 'габарит']):
                return 4512, 'Фонари велосипедные'
        if any(k in tl for k in ['велосипед', 'вело', 'самокат', 'электровелосипед']):
            if any(k in tl for k in ['фонар', 'фара', 'светильник', 'подсветк', 'мигалк', 'габарит', 'свет']):
                return 4512, 'Фонари велосипедные'
            if 'грипс' in tl or 'рукоятк' in tl or 'ручки на руль' in tl:
                return 6487, 'Грипсы велозапястья'
            if 'педал' in tl:
                return 1050, 'Педали велосипедные'
            if 'крыл' in tl:
                return 4412, 'Крылья велосипедные'
            if 'зеркал' in tl:
                return 1401, 'Зеркала велосипедные'
            if 'звонок' in tl or 'сигнал' in tl:
                return 562, 'Звонки велосипедные'
            if 'насос' in tl:
                return 4588, 'Насосы велосипедные'
            if 'держател' in tl or 'креплен' in tl:
                return 6464, 'Аксессуары для велосипеда'
            if 'защит' in tl or 'замок' in tl:
                return 1399, 'Защита велосипеда'
            if 'седл' in tl or 'сидень' in tl:
                return 2153, 'Седла велосипедные'
            if 'сумк' in tl or 'чехол' in tl:
                return 1376, 'Сумки велосипедные'
            if 'цепь' in tl:
                return 4414, 'Цепи велосипедные'
            return 6464, 'Аксессуары для велосипеда'

        # 3. Depilation & Cosmetics
        if any(k in tl for k in ['воск', 'italwax', 'kapous']) and any(k in tl for k in ['депил', 'эпил', 'гранул', 'картридж', 'italwax', 'kapous', 'пленочн', 'горяч']):
            return 1934, 'Воски для депиляции'
        if 'воск' in tl and ('депил' in cl or 'эпил' in cl):
            return 1934, 'Воски для депиляции'
        if 'крем' in tl and any(k in tl for k in ['депил', 'эпил', 'veet']):
            return 357, 'Кремы'
        if 'воскоплав' in tl:
            return 1935, 'Воскоплавы'
        if 'полоск' in tl and 'депил' in tl:
            return 1933, 'Полоски для депиляции'
        if 'шпател' in tl and 'депил' in tl:
            return 1932, 'Шпатели для депиляции'
        if 'сыворотк' in tl or 'serum' in tl or 'эссенци' in tl:
            return 372, 'Сыворотки'
        if 'лосьон' in tl:
            return 359, 'Лосьоны'
        if 'эмульси' in tl:
            return 1566, 'Эмульсии'
        if 'маск' in tl and ('лиц' in tl or 'тканев' in tl or 'гидрогел' in tl):
            return 360, 'Маски косметические'
        if 'крем' in tl:
            return 357, 'Кремы'
        if 'скраб' in tl:
            return 362, 'Скрабы'
        if 'пилинг' in tl:
            return 363, 'Пилинги'
        if 'тоник' in tl:
            return 365, 'Тоники'
        if 'пенк' in tl or 'гель для умыван' in tl:
            return 367, 'Пенки для умывания'

        # 4. Vacuum Cleaners
        if 'пылесос' in tl or 'пелесос' in tl:
            if any(k in tl for k in ['автомобильн', 'для авто', 'для машин', 'в машину', 'авто ']):
                return 2012, 'Пылесосы автомобильные'
            if 'робот' in tl: return 2043, 'Роботы-пылесосы'
            if 'вертикальн' in tl: return 2010, 'Вертикальные пылесосы'
            return 2012, 'Пылесосы автомобильные'

        # 5. Power Tools
        if any(k in tl for k in ['шуруповерт', 'дрель', 'перфоратор', 'гайковерт', 'винтоверт']):
            return 2197, 'Шуруповерты'
        if 'болгарк' in tl or 'ушм' in tl:
            return 2198, 'Углошлифовальные машины'
        if 'лобзик' in tl:
            return 2199, 'Лобзики'
        if 'паяльник' in tl:
            return 3004, 'Паяльники'

        # 6. Board Games, Cards, Mats, Drinkware
        if any(k in tl for k in ['игральные карты', 'колода карт', 'карты для покера', 'карты покер', 'покер', 'настольн', '365 вопрос', 'метафорическ']):
            return 2918, 'Аксессуары для настольных игр'
        if 'таро' in tl:
            return 4146, 'Карты Таро'
        if 'придверн' in tl or ('коврик' in tl and 'ванн' not in tl and 'мышь' not in tl and 'авто' not in tl):
            return 2317, 'Коврики придверные'
        if 'автоковрик' in tl or ('коврик' in tl and 'авто' in tl):
            return 2153, 'Коврики автомобильные'
        if 'термос' in tl:
            return 511, 'Термосы'
        if 'термокружк' in tl or 'термостакан' in tl:
            return 1274, 'Термокружки'
        if 'бутылк' in tl and any(k in tl for k in ['вод', 'спорт', 'питье']):
            return 384, 'Бутылки для воды'

        # 7. Auto chemicals & Accessories
        if 'ароматизатор' in tl and 'авто' in tl:
            return 2157, 'Ароматизаторы автомобильные'
        if 'автошампун' in tl:
            return 2041, 'Автошампуни'
        if 'очистител' in tl and 'авто' in tl:
            return 3540, 'Очистители автомобильные'

        # Tier 2: Token Matching
        tokens = re.findall(r'[а-яА-Яa-zA-Z]{3,}', tl)
        best_match = None
        best_score = 0
        for sub in self.wb_subjects:
            s_name = sub['subjectName'].lower()
            score = sum(1 for tok in tokens if tok in s_name)
            if score > best_score:
                best_score = score
                best_match = sub
                
        if best_match and best_score >= 1:
            return best_match['subjectID'], best_match['subjectName']

        return None, 'UNMATCHED'
