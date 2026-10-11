import os
import re
import asyncio
import aiohttp
from playwright.async_api import async_playwright

TELEGRAM_BOT_TOKEN = "8777299013:AAH8-gTT-_CTw2Ht0RRXW55jsPEGFh0_OuU"
TELEGRAM_CHAT_ID = "865364645"

BOOKMAKER_CONFIG = {
    "Winamax": {
        "url": "https://www.winamax.es/supercuotas",
        "keywords": ["supercuota", "momo boost", "cuota mejorada"],
        "card_selector": "div[class*='SuperCuota'], div[class*='boost'], .slider-item, article",
        "img_selector": "img[src*='supercuotas'], img[src*='boost'], div[class*='SuperCuota'] img"
    },
    "Betfair": {
        "url": "https://www.betfair.es/sport/promotions",
        "keywords": ["supercuota", "combi del día"],
        "card_selector": ".promotion-tile, .avb-col",
        "img_selector": ".promotion-tile img"
    },
    "Casino Gran Madrid": {
        "url": "https://www.casinogranmadridonline.es/apuestas-deportivas",
        "keywords": ["supercuota cgm", "mega cuota"],
        "card_selector": "[class*='boost'], [class*='promo']",
        "img_selector": "[class*='boost'] img"
    },
    "Paf": {
        "url": "https://www.paf.es/bets",
        "keywords": ["paf boost", "supertabla"],
        "card_selector": "[class*='boost']",
        "img_selector": "[class*='boost'] img"
    },
    "Betway": {
        "url": "https://betway.es/es/sports",
        "keywords": ["betway boost"],
        "card_selector": ".boostCard, [class*='boost']",
        "img_selector": ".boostCard img"
    },
    "Interwetten": {
        "url": "https://www.interwetten.es/es/apuestas-deportivas",
        "keywords": ["supercuota interwetten", "cuota top"],
        "card_selector": "[class*='boost']",
        "img_selector": "[class*='boost'] img"
    },
    "Bwin": {
        "url": "https://sports.bwin.es/es/sports",
        "keywords": ["price boost", "supercuota bwin"],
        "card_selector": "[class*='price-boost']",
        "img_selector": "[class*='price-boost'] img"
    }
}

async def send_telegram_alert(text, image_path=None):
    """Envía la alerta con la imagen exacta a Telegram."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    
    if image_path and os.path.exists(image_path):
        async with aiohttp.ClientSession() as session:
            with open(image_path, 'rb') as photo:
                data = aiohttp.FormData()
                data.add_field('chat_id', TELEGRAM_CHAT_ID)
                data.add_field('caption', text)
                data.add_field('parse_mode', 'Markdown')
                data.add_field('photo', photo)
                
                async with session.post(url, data=data) as resp:
                    if resp.status != 200:
                        print(f"Error Telegram API: {resp.status}")
    else:
        text_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        async with aiohttp.ClientSession() as session:
            payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}
            await session.post(text_url, json=payload)

def parse_odds_and_value(text_content):
    """Extrae las cuotas y calcula el valor en porcentaje exacto."""
    numbers = re.findall(r'\b\d+[\.,]\d+\b', text_content)
    numbers = [float(n.replace(',', '.')) for n in numbers if float(n.replace(',', '.')) > 1.01]
    
    if len(numbers) >= 2:
        cuota_old = min(numbers[:2])
        cuota_new = max(numbers[:2])
        if cuota_old < cuota_new:
            val_pct = ((cuota_new - cuota_old) / cuota_old) * 100
            return cuota_old, cuota_new, round(val_pct, 2)
            
    return None, None, None

async def check_bookmaker(page, name, config):
    print(f"Escaneando {name}...")
    url = config["url"]
    keywords = config["keywords"]
    
    try:
        await page.goto(url, timeout=45000, wait_until="domcontentloaded")
        await asyncio.sleep(4)
        
        # Cerrar banners de cookies
        try:
            cookie_btn = await page.query_selector("button:has-text('Aceptar'), button:has-text('Accept'), #onetrust-accept-btn-handler")
            if cookie_btn:
                await cookie_btn.click()
                await asyncio.sleep(1)
        except Exception:
            pass

        card_el = await page.query_selector(config["card_selector"])
        
        content = await page.content()
        content_lower = content.lower()
        found_matches = [term for term in keywords if term in content_lower]
        
        if found_matches or card_el:
            print(f"AUMENTO DETECTADO en {name}")
            
            card_text = await card_el.inner_text() if card_el else ""
            lines = [l.strip() for l in card_text.split('\n') if len(l.strip()) > 2]
            
            event_title = lines[0] if lines else "Evento con Supercuota"
            market_detail = lines[1] if len(lines) > 1 else "Supercuota disponible"
            
            cuota_old, cuota_new, val_pct = parse_odds_and_value(card_text)
            
            if cuota_old and cuota_new:
                odds_str = f"`{cuota_old:.2f}` ➡️ `{cuota_new:.2f}` (`{val_pct}%`)"
            else:
                odds_str = "Consulte las cuotas en la plataforma"

            filename = f"aumento_{name.lower()}.png"
            
            # Buscar la imagen/banner directo de la supercuota
            img_element = await page.query_selector(config["img_selector"])
            if img_element:
                await img_element.screenshot(path=filename)
            elif card_el:
                await card_el.screenshot(path=filename)
            else:
                await page.screenshot(path=filename, clip={"x": 200, "y": 150, "width": 880, "height": 500})
            
            # Formato idéntico al de tu ejemplo
            caption = (
                f"⚽ *{event_title}*\n"
                f"*{market_detail}*\n"
                f"{odds_str}\n\n"
                f"🔗 [Ir a la apuesta]({url})"
            )
            
            await send_telegram_alert(caption, filename)
            
            if os.path.exists(filename):
                os.remove(filename)
        else:
            print(f"Sin aumentos en {name}.")
            
    except Exception as e:
        print(f"Error al revisar {name}: {e}")

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 800},
            locale='es-ES',
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
        )
        page = await context.new_page()

        for name, config in BOOKMAKER_CONFIG.items():
            await check_bookmaker(page, name, config)

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
