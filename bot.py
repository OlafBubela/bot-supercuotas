import os
import asyncio
import aiohttp
from playwright.async_api import async_playwright

# Configuración de Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "TU_TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "TU_TELEGRAM_CHAT_ID")

# Nombres exactos y exclusivos de los aumentos en cada casa para evitar falsos positivos
EXACT_AUMENTO_NAMES = {
    "Betfair": ["supercuota", "combi del día"],
    "Winamax": ["supercuota", "momo boost", "cuota mejorada"],
    "Casino Gran Madrid": ["supercuota cgm", "mega cuota"],
    "Paf": ["paf boost", "supertabla"],
    "Betway": ["betway boost"],
    "Interwetten": ["supercuota interwetten", "cuota top"],
    "Bwin": ["price boost", "supercuota bwin"]
}

# URLs directas de las secciones donde publican los aumentos
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
    """Envía la alerta a Telegram adjuntando la captura de pantalla del aumento."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    
    if screenshot_path and os.path.exists(screenshot_path):
        async with aiohttp.ClientSession() as session:
            with open(screenshot_path, 'rb') as photo:
                data = aiohttp.FormData()
                data.add_field('chat_id', TELEGRAM_CHAT_ID)
                data.add_field('caption', text)
                data.add_field('photo', photo)
                
                async with session.post(url, data=data) as resp:
                    if resp.status == 200:
                        print(f"OK: Foto enviada a Telegram para: {text[:40]}...")
                    else:
                        print(f"Error en Telegram API: {resp.status}")
    else:
        text_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        async with aiohttp.ClientSession() as session:
            payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
            await session.post(text_url, json=payload)

async def check_bookmaker(page, name, url):
    """Inspecciona la casa de apuestas filtrando únicamente por la denominación oficial de sus aumentos."""
    print(f"Escaneando {name}...")
    exact_names = EXACT_AUMENTO_NAMES.get(name, [])
    
    try:
        await page.goto(url, timeout=35000, wait_until="networkidle")
        await asyncio.sleep(3)
        
        content = await page.content()
        content_lower = content.lower()
        
        # Filtra únicamente coincidencias exactas del nombre del aumento
        found_matches = [term for term in exact_names if term in content_lower]
        
        if found_matches:
            print(f"AUMENTO REAL DETECTADO en {name}! Coincidencia: {found_matches}")
            
            # Toma la captura de pantalla del aumento
            filename = f"aumento_{name.lower().replace(' ', '_')}.png"
            await page.screenshot(path=filename, full_page=False)
            
            caption = (
                f"🔥 **¡Aumento Detectado en {name}!**\n\n"
                f"🏷️ **Sección:** {', '.join(found_matches).upper()}\n"
                f"🔗 [Ir al aumento en {name}]({url})"
            )
            
            await send_telegram_alert(caption, filename)
            
            if os.path.exists(filename):
                os.remove(filename)
        else:
            print(f"No hay aumentos oficiales activos en {name}.")
            
    except Exception as e:
        print(f"Error al revisar {name}: {e}")

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 800},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = await context.new_page()

        for name, url in BOOKMAKER_URLS.items():
            await check_bookmaker(page, name, url)

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
