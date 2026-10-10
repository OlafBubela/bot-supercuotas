import asyncio
import aiohttp
from playwright.async_api import async_playwright

token = "8777299013:AAH8-gTT-_CTw2Ht0RRXW55jsPEGFh0_OuU"
user_id = "865364645"

async def test_vista():
    async with aiohttp.ClientSession() as session:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            
            print("Entrando a Bet365 para tomar foto de control...")
            await page.goto("https://www.bet365.es/#/HO/", timeout=15000)
            await page.wait_for_timeout(4000)
            await page.screenshot(path="vista_bet365.png")
            
            url = f"https://api.telegram.org/bot{token}/sendPhoto"
            data = aiohttp.FormData()
            data.add_field('chat_id', user_id)
            data.add_field('caption', 'Foto de control: Esto es lo que ve el bot en GitHub')
            data.add_field('photo', open('vista_bet365.png', 'rb'))
            await session.post(url, data=data)
            await browser.close()

if __name__ == "__main__":
    asyncio.run(test_vista())
