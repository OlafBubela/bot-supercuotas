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
        "card_selector": "div[class*='SuperCuota'], div[class*='boost'], div[class*='card'], article"
    },
    "Betfair": {
        "url": "https://www.betfair.es/sport/promotions",
        "keywords": ["supercuota", "combi del día"],
        "card_selector": ".promotion-tile, .avb-col"
    },
    "Casino Gran Madrid": {
        "url": "https://www.casinogranmadridonline.es/apuestas-deportivas",
        "keywords": ["supercuota cgm", "mega cuota"],
        "card_selector": "[class*='boost'], [class*='promo']"
    },
    "Paf": {
        "url": "https://www.paf.es/bets",
        "keywords": ["paf boost", "supertabla"],
        "card_selector": "[class*='boost']"
    },
    "Betway": {
        "url": "https://betway.es/es/sports",
        "keywords": ["betway boost"],
        "card_selector": ".boostCard, [class*='boost']"
    },
    "Interwetten": {
        "url": "https://www.interwetten.es/es/apuestas-deportivas",
        "keywords": ["supercuota interwetten", "cuota top"],
        "card_selector": "[class*='boost']"
    },
    "Bwin": {
        "url": "https://sports.bwin.es/es/sports",
        "keywords": ["price boost", "supercuota bwin"],
        "card_selector": "[class*='price-boost']"
    }
}

async def send_telegram_alert(text, image_path=None):
    """Envía la alerta a Telegram con el formato exacto."""
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

def parse_card_info(text_content):
    """Extrae evento, hora, mercado, cuotas y porcentaje exactos."""
    lines = [line.strip() for line in text_content.split('\n') if len(line.strip()) > 2]
    
    # Extraer horas (ej: 20:45, 18:00, etc.)
    time_match = re.search(r'\b\d{1,2}:\d{2}\b', text_content)
    time_str = f" (Hoy {time_match.group(0)})" if time_match else ""
    
    match_title = lines[0] if lines else "Evento"
    market_description = lines[1] if len(lines) > 1 else "Apuesta especial"
    
    # Buscar números decimales (cuotas)
    numbers = re.findall(r'\b\d+[\.,]\d+\b', text_content)
    numbers = [float(n.replace(',', '.')) for n in numbers if float(n.replace(',', '.')) > 1.01]
    
    odds_str = ""
    if len(numbers) >= 2:
        cuota_old = min(numbers[:2])
        cuota_new = max(numbers[:2])
        if cuota_old < cuota_new:
            val_pct = ((cuota_new - cuota_old) / cuota_old) * 100
            odds_str = f"*{cuota_old:.2f}* ➡️ *{cuota_new:.2f}* (*{val_pct:.2f}%*)"
            
    return match_title, time_str, market_description, odds_str

async def check_bookmaker(page, name, config):
    print(f"Escaneando {name}...")
    url = config["url"]
    keywords = config["keywords"]
    
    try:
        await page.goto(url, timeout=45000, wait_until="networkidle")
        await asyncio.sleep(3)
        
        # Ocultar cookies
        try:
            cookie_btn = await page.query_selector("button:has-text('Aceptar'), #onetrust-accept-btn-handler")
            if cookie_btn:
                await cookie_btn.click()
                await asyncio.sleep(1)
        except Exception:
            pass

        content = await page.content()
        content_lower = content.lower()
        found = any(kw in content_lower for kw in keywords)
        
        if found:
            print(f"AUMENTO DETECTADO en {name}")
            
            card_el = await page.query_selector(config["card_selector"])
            card_text = await card_el.inner_text() if card_el else await page.inner_text("body")
            
            match_title, time_str, market_desc, odds_str = parse_card_info(card_text)
            
            filename = f"aumento_{name.lower()}.png"
            
            # Recorte exacto a la tarjeta del banner
            if card_el:
                await card_el.screenshot(path=filename)
            else:
                body = await page.query_selector("main") or await page.query_selector("body")
                await body.screenshot(path=filename, clip={"x": 250, "y": 150, "width": 780, "height": 450})

            # FORMATO EXACTO A LA IMAGEN DE EJEMPLO
            caption = (
                f"⚽ *{match_title}*{time_str}\n"
                f"{market_desc}\n"
                f"{odds_str}"
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
