import sys, re
with open(r'C:\Users\Administrator\.gemini\antigravity\brain\447cf62a-9867-403a-8499-06df6a3e67fe\.system_generated\steps\487\content.md', 'r', encoding='utf-8') as f:
    html = f.read()
bcs = re.findall(r'<a[^>]+href=["\']/category/[^"\']+["\'][^>]*>(.*?)</a>', html)
clean_bcs = [re.sub(r'<[^>]+>', '', b).strip() for b in bcs if re.sub(r'<[^>]+>', '', b).strip()]
sys.stdout.reconfigure(encoding='utf-8')
print('Breadcrumbs:', ' > '.join(clean_bcs[:5]))
