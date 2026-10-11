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
        "card_selectors": [
            "[data-testid*='boost']", 
            ".supercuota-item", 
            "div[class*='SuperCuota']",
            "div[class*='boost']",
            "article"
        ]
    },
    "Betfair": {
        "url": "https://www.betfair.es/sport/promotions",
        "keywords": ["supercuota", "combi del día"],
        "card_selectors": [".promotion-tile", ".avb-col", "[class*='promo']"]
    },
    "Casino Gran Madrid": {
        "url": "https://www.casinogranmadridonline.es/apuestas-deportivas",
        "keywords": ["supercuota cgm", "mega cuota"],
        "card_selectors": ["[class*='boost']", "[class*='promo']"]
    },
    "Paf": {
        "url": "https://www.paf.es/bets",
        "keywords": ["paf boost", "supertabla"],
        "card_selectors": ["[class*='boost']", "[class*='offer']"]
    },
    "Betway": {
        "url": "https://betway.es/es/sports",
        "keywords": ["betway boost"],
        "card_selectors": [".boostCard", "[class*='boost']"]
    },
    "Interwetten": {
        "url": "https://www.interwetten.es/es/apuestas-deportivas",
        "keywords": ["supercuota interwetten", "cuota top"],
        "card_selectors": ["[class*='boost']", "[class*='top-offer']"]
    },
    "Bwin": {
        "url": "https://sports.bwin.es/es/sports",
        "keywords": ["price boost", "supercuota bwin"],
        "card_selectors": ["[class*='price-boost']", "[class*='boost']"]
    }
}

async def send_telegram_alert(text, screenshot_path=None):
    """Envía mensaje y captura en HD a Telegram."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    
    if screenshot_path and os.path.exists(screenshot_path):
        async with aiohttp.ClientSession() as session:
            with open(screenshot_path, 'rb') as photo:
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
    """Extrae las cuotas del texto y calcula el incremento porcentual de valor."""
    # Busca números decimales (ej: 2.10, 3.50, 4,5)
    numbers = re.findall(r'\b\d+[\.,]\d+\b', text_content)
    numbers = [float(n.replace(',', '.')) for n in numbers if float(n.replace(',', '.')) > 1.01]
    
    if len(numbers) >= 2:
        cuota_antigua = min(numbers[:2])
        cuota_nueva = max(numbers[:2])
        if cuota_antigua < cuota_nueva:
            incremento = ((cuota_nueva - cuota_antigua) / cuota_antigua) * 100
            return cuota_antigua, cuota_nueva, round(incremento, 1)
            
    return None, None, None

async def check_bookmaker(page, name, config):
    print(f"Escaneando {name}...")
    url = config["url"]
    keywords = config["keywords"]
    selectors = config["card_selectors"]
    
    try:
        await page.goto(url, timeout=45000, wait_until="domcontentloaded")
        await asyncio.sleep(4)
        
        # Ocultar o aceptar modales y avisos de cookies
        try:
            cookie_btn = await page.query_selector("button:has-text('Aceptar'), button:has-text('Accept'), #onetrust-accept-btn-handler")
            if cookie_btn:
                await cookie_btn.click()
                await asyncio.sleep(1)
        except Exception:
            pass

        # Buscar elementos/tarjetas concretos de la apuesta
        target_element = None
        for sel in selectors:
            elements = await page.query_selector_all(sel)
            for el in elements:
                text = (await el.inner_text()).lower()
                if any(kw in text for kw in keywords):
                    target_element = el
                    break
            if target_element:
                break
                
        content = await page.content()
        content_lower = content.lower()
        found_matches = [term for term in keywords if term in content_lower]
        
        if found_matches or target_element:
            print(f"AUMENTO DETECTADO en {name}")
            
            card_text = ""
            if target_element:
                card_text = await target_element.inner_text()
            else:
                # Si no aísla elemento, coge el cuerpo principal
                body = await page.query_selector("main") or await page.query_selector("body")
                card_text = await body.inner_text() if body else ""

            # Limpiar líneas de texto de la oferta
            lines = [l.strip() for l in card_text.split('\n') if len(l.strip()) > 3]
            match_name = lines[0] if lines else "Evento con supercuota"
            bet_detail = " | ".join(lines[1:4]) if len(lines) > 1 else "Consulta el enlace para más detalles."
            
            # Extraer cuotas y calcular valor
            cuota_old, cuota_new, valor_pct = parse_odds_and_value(card_text)
            
            odds_info = ""
            if cuota_old and cuota_new:
                odds_info = (
                    f"📉 *Cuota Antigua:* `{cuota_old:.2f}`\n"
                    f"🚀 *Cuota Aumentada:* `{cuota_new:.2f}`\n"
                    f"📊 *Aumento de Valor:* `+{valor_pct}%`"
                )
            else:
                odds_info = "⚡ *Aumento detectado en la plataforma.*"

            filename = f"aumento_{name.lower().replace(' ', '_')}.png"
            
            # Tomar captura recortada EXACTA de la tarjeta o área central
            if target_element:
                await target_element.screenshot(path=filename)
            else:
                # Recorte horizontal centrado si captura la página
                await page.set_viewport_size({"width": 1280, "height": 720})
                await page.screenshot(path=filename, clip={"x": 100, "y": 100, "width": 1080, "height": 600})
            
            caption = (
                f"🔥 *¡Aumento Detectado en {name}!*\n\n"
                f"⚽ *Partido/Evento:* {match_name}\n"
                f"🎯 *Apuesta:* {bet_detail}\n\n"
                f"{odds_info}\n\n"
                f"🔗 [Ir a la Supercuota]({url})"
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
