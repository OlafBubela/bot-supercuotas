import os
import asyncio
import aiohttp
from playwright.async_api import async_playwright

TELEGRAM_BOT_TOKEN = "8777299013:AAH8-gTT-_CTw2Ht0RRXW55jsPEGFh0_OuU"
TELEGRAM_CHAT_ID = "865364645"

# Palabras clave y URLs
EXACT_AUMENTO_NAMES = {
    "Betfair": ["supercuota", "combi del día"],
    "Winamax": ["supercuota", "momo boost", "cuota mejorada"],
    "Casino Gran Madrid": ["supercuota cgm", "mega cuota"],
    "Paf": ["paf boost", "supertabla"],
    "Betway": ["betway boost"],
    "Interwetten": ["supercuota interwetten", "cuota top"],
    "Bwin": ["price boost", "supercuota bwin"]
}

BOOKMAKER_URLS = {
    "Betfair": "https://www.betfair.es/sport/promotions",
    "Winamax": "https://www.winamax.es/supercuotas",
    "Casino Gran Madrid": "https://www.casinogranmadridonline.es/apuestas-deportivas",
    "Paf": "https://www.paf.es/bets",
    "Betway": "https://betway.es/es/sports",
    "Interwetten": "https://www.interwetten.es/es/apuestas-deportivas",
    "Bwin": "https://sports.bwin.es/es/sports"
}

async def send_telegram_alert(text, screenshot_path=None):
    """Envía la alerta adjuntando la captura de pantalla con Markdown habilitado."""
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

async def check_bookmaker(page, name, url):
    print(f"Escaneando {name}...")
    exact_names = EXACT_AUMENTO_NAMES.get(name, [])
    
    try:
        await page.goto(url, timeout=40000, wait_until="domcontentloaded")
        await asyncio.sleep(4)
        
        # Aceptar cookies de forma genérica para limpiar la pantalla
        try:
            cookie_btn = await page.query_selector("button:has-text('Aceptar'), button:has-text('Accept'), #onetrust-accept-btn-handler")
            if cookie_btn:
                await cookie_btn.click()
                await asyncio.sleep(1)
        except Exception:
            pass

        content = await page.content()
        content_lower = content.lower()
        
        found_matches = [term for term in exact_names if term in content_lower]
        
        if found_matches:
            print(f"AUMENTO DETECTADO en {name}: {found_matches}")
            
            # Extraer textos visibles de tarjetas o secciones de la oferta
            extracted_info = []
            cards = await page.query_selector_all(".boost-item, .supercuota, [class*='boost'], [class*='supercuota'], article")
            
            for card in cards[:3]:  # Toma las primeras 3 ofertas encontradas
                text = await card.inner_text()
                lines = [line.strip() for line in text.split("\n") if line.strip()]
                if lines:
                    extracted_info.append(" - " + " | ".join(lines[:4]))
            
            info_text = "\n".join(extracted_info) if extracted_info else "Detalles disponibles en el enlace."
            
            filename = f"aumento_{name.lower().replace(' ', '_')}.png"
            
            # Intenta hacer captura del contenedor del aumento o de toda la pantalla si falla
            target_element = await page.query_selector(".boost-item, .supercuota, [class*='boost'], main, body")
            if target_element:
                await target_element.screenshot(path=filename)
            else:
                await page.screenshot(path=filename, full_page=False)
            
            caption = (
                f"🔥 *¡Aumento Detectado en {name}!*\n\n"
                f"📌 *Detalles del evento y cuota:*\n{info_text}\n\n"
                f"🏷️ *Categoría:* {', '.join(found_matches).upper()}\n"
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
        # Configurar navegador simulando ubicación en España e idioma español
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 800},
            locale='es-ES',
            geolocation={'latitude': 40.416775, 'longitude': -3.703790}, # Madrid
            permissions=['geolocation'],
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
        )
        page = await context.new_page()

        for name, url in BOOKMAKER_URLS.items():
            await check_bookmaker(page, name, url)

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
