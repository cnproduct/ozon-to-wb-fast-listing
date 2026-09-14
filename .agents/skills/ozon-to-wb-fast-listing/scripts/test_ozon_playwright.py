from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.launch(
        channel='chrome',
        headless=True,
        args=['--disable-blink-features=AutomationControlled']
    )
    context = browser.new_context(
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36',
        locale='ru-RU'
    )
    page = context.new_page()
    page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    
    sku = '695177496'
    url = f'https://www.ozon.ru/product/{sku}/'
    print(f'Navigating to {url}...')
    resp = page.goto(url, wait_until='domcontentloaded', timeout=30000)
    time.sleep(2)
    print('Status:', resp.status, 'Title:', page.title())
    content = page.content()
    print('Length:', len(content))
    browser.close()
