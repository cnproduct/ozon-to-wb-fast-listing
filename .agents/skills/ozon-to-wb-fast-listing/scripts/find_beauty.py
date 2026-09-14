import sys
sys.path.insert(0, 'scripts')
from wb_uploader import WildberriesAPIClient
client = WildberriesAPIClient()
sys.stdout.reconfigure(encoding='utf-8')

# Get all subjects from content-api
r = client.session.get('https://content-api.wildberries.ru/content/v2/object/all', params={'limit': 1000})
data = r.json().get('data', [])
beauty_subs = [it for it in data if it.get('parentName') in ['Красота', 'Здоровье', 'Аптека']]
print(f"Total beauty subjects found: {len(beauty_subs)}")
for it in beauty_subs[:30]:
    print(f"  {it.get('subjectID')}: {it.get('subjectName')} ({it.get('parentName')})")
