import asyncio
import json
import os
import re
import time
import aiohttp
from playwright.async_api import async_playwright

token = "8777299013:AAH8-gTT-_CTw2Ht0RRXW55jsPEGFh0_OuU"
user_id = "865364645"

HISTORIAL_FILE = "alertas_definitivo.json"
SCREENSHOT_PATH = "oferta_detectada.png"

CONFIG_CASAS = {
    "Bet365 Deportes": {
        "url": "https://www.bet365.es/#/HO/",
        "keywords": ["superaumento"],
        "blacklist": ["parlay", "combinada", "crea tu apuesta"],
        "wh_search": False
    },
    "Winamax": {
        "url": "https://www.winamax.es/apuestas-deportivas",
        "keywords": ["gran supercuota"],
        "blacklist": ["mymatch", "combinada"],
        "wh_search": False
    },
    "William Hill": {
        "url": "https://sports.williamhill.es/betting/es-es",
        "keywords": ["épica", "insuperable"],
        "blacklist": ["crea tu apuesta", "combinada"],
        "wh_search": True,
        "search_terms": ["épica", "insuperable"]
    },
    "Casino Gran Madrid": {
        "url": "https://www.casinogranmadridonline.es/apuestas-deportivas/",
        "keywords": ["apuesta del día"],
        "blacklist": ["combinada"],
        "wh_search": False
    }
}

def log(mensaje):
    print(f"[{time.strftime('%H:%M:%S')}] {mensaje}", flush=True)

def cargar_historial():
    if os.path.exists(HISTORIAL_FILE):
        try:
            with open(HISTORIAL_FILE, 'r', encoding='utf-8') as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()

def guardar_historial(historial):
    with open(HISTORIAL_FILE, 'w', encoding='utf-8') as f:
        json.dump(list(historial), f, ensure_ascii=False, indent=2)

async def enviar_telegram_con_foto(session, mensaje, ruta_imagen=None):
    if ruta_imagen and os.path.exists(ruta_imagen):
        url = f"https://api.telegram.org/bot{token}/sendPhoto"
        data = aiohttp.FormData()
        data.add_field('chat_id', user_id)
        data.add_field('caption', mensaje)
        data.add_field('parse_mode', 'Markdown')
        data.add_field('photo', open(ruta_imagen, 'rb'), filename='oferta.png')
        try:
            async with session.post(url, data=data, timeout=aiohttp.ClientTimeout(total=10)):
                pass
            os.remove(ruta_imagen)
            return
        except Exception as e:
            log(f"Error enviando foto: {e}")

    url_text = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {'chat_id': user_id, 'text': mensaje, 'parse_mode': 'Markdown'}
    try:
        async with session.post(url_text, json=payload, timeout=aiohttp.ClientTimeout(total=5)):
            pass
    except Exception as e:
        log(f"Error enviando mensaje: {e}")

async def escaneo_elementos_pagina(page, session, nombre_casa, config, historial):
    nuevas = False
    keywords = config["keywords"]
    blacklist = config["blacklist"]

    try:
        elementos = await page.query_selector_all('article, section, button, div[class*="boost"], div[class*="promo"], div[class*="offer"], div')
        
        for el in elementos:
            try:
                texto = await el.inner_text()
                texto_limpio = texto.strip()
                texto_lower = texto_limpio.lower()
                
                if any(kw in texto_lower for kw in keywords):
                    if any(bl in texto_lower for bl in blacklist):
                        continue

                    if 5 < len(texto_limpio) < 500:
                        texto_resumen = texto_limpio[:60].replace('\n', ' ')
                        log(f"  🎯 Oferta detectada en {nombre_casa}: '{texto_resumen}'")

                        id_oferta = f"{nombre_casa}_{texto_limpio[:20]}"
                        if id_oferta in historial:
                            log(f"  ⏩ Omitida: Ya en historial.")
                            continue

                        try:
                            await el.screenshot(path=SCREENSHOT_PATH)
                        except Exception:
                            await page.screenshot(path=SCREENSHOT_PATH)

                        mensaje = (
                            f"🎯 **NUEVA SUPERCUOTA DETECTADA**\n\n"
                            f"🏦 **Casa:** {nombre_casa.upper()}\n"
                            f"📌 **Oferta:** {texto_limpio.replace(chr(10), ' ')}\n\n"
                            f"🔗 [Ir a la oferta]({config['url']})"
                        )

                        await enviar_telegram_con_foto(session, mensaje, SCREENSHOT_PATH)
                        log(f"  ✅ ¡ALERTA Y CAPTURA ENVIADAS!")
                        historial.add(id_oferta)
                        nuevas = True
            except Exception:
                continue
    except Exception as e:
        log(f"  ⚠️ Error escaneando {nombre_casa}: {e}")
            
    return nuevas

async def rastrear():
    historial = cargar_historial()
    nuevas_alertas = False

    async with aiohttp.ClientSession() as session:
        async with async_playwright() as p:
            log("🚀 Iniciando rastreo...")
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--no-sandbox',
                    '--disable-setuid-sandbox'
                ]
            )
            # Contexto de navegador completamente camuflado como usuario real
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
                viewport={'width': 1366, 'height': 768},
                locale="es-ES",
                timezone_id="Europe/Madrid"
            )
            page = await context.new_page()

            await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

            for nombre_casa, config in CONFIG_CASAS.items():
                log(f"🔍 Escaneando {nombre_casa}...")
                try:
                    # Timeout rápido de 4 segundos para Winamax
                    timeout_val = 4000 if nombre_casa == "Winamax" else 10000
                    await page.goto(config['url'], timeout=timeout_val, wait_until="commit")
                    
                    # Pausa de renderizado en Bet365 con movimiento de ratón
                    if "bet365" in nombre_casa.lower():
                        await page.wait_for_timeout(3500)
                        await page.mouse.move(200, 200)
                        await page.evaluate("window.scrollBy(0, 300);")
                        await page.wait_for_timeout(1000)

                    if config.get("wh_search"):
                        for termino in config.get("search_terms", []):
                            try:
                                log(f"  🔎 Buscando '{termino}' en William Hill...")
                                search_input = await page.query_selector('input[type="search"], input[type="text"], input[placeholder*="Buscar"]')
                                if search_input:
                                    await search_input.click()
                                    await search_input.fill("")
                                    await search_input.type(termino, delay=100)
                                    await page.keyboard.press("Enter")
                                    await page.wait_for_timeout(2500)
                                    
                                    if await escaneo_elementos_pagina(page, session, nombre_casa, config, historial):
                                        nuevas_alertas = True
                            except Exception as e_wh:
                                log(f"  ⚠️ Error en la búsqueda de {termino}: {e_wh}")

                    if await escaneo_elementos_pagina(page, session, nombre_casa, config, historial):
                        nuevas_alertas = True

                except Exception as e:
                    log(f"  ⚡ Salto en {nombre_casa}: {e}")

            await browser.close()
            log("🏁 Proceso finalizado.")

    if nuevas_alertas:
        guardar_historial(historial)

if __name__ == "__main__":
    asyncio.run(rastrear())
