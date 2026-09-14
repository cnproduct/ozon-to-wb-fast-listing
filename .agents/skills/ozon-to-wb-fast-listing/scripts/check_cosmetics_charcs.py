import sys
sys.path.insert(0, 'scripts')
from wb_uploader import WildberriesAPIClient
client = WildberriesAPIClient()
sys.stdout.reconfigure(encoding='utf-8')

for sid in [372, 1566, 357, 377]:
    r = client.session.get(f'https://content-api.wildberries.ru/content/v2/object/charcs/{sid}')
    data = r.json().get('data', [])
    req = [c.get('name') for c in data if c.get('required')]
    print(f"Subject {sid}: {len(data)} charcs, Required: {req}")
