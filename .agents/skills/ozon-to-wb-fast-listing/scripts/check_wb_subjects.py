import sys
sys.path.insert(0, 'scripts')
from wb_uploader import WildberriesAPIClient
client = WildberriesAPIClient()
sys.stdout.reconfigure(encoding='utf-8')

r = client.session.get('https://content-api.wildberries.ru/content/v2/object/all', params={'name': 'крем'})
print("Status:", r.status_code)
data = r.json().get('data', [])
print(f"Found {len(data)} items:")
for it in data[:8]:
    print(f"  ID: {it.get('subjectID')} | Name: {it.get('subjectName')} | Parent: {it.get('parentName')}")
