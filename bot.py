import asyncio
import json
import os
import re
import time
import aiohttp
from playwright.async_api import async_playwright

# Configuración de Telegram
token = "8777299013:AAH8-gTT-_CTw2Ht0RRXW55jsPEGFh0_OuU"
user_id = "865364645"

HISTORIAL_FILE = "alertas_v3.json"
SCREENSHOT_PATH = "oferta_detectada.png"

CONFIG_CASAS = {
    "Bet365 Deportes": {
        "url": "https://www.bet365.es/#/HO/",
        "keywords": ["superaumento"],
        "blacklist": ["parlay", "combinada", "crea tu apuesta"],
    },
    "Winamax": {
        "url": "https://www.winamax.es/apuestas-deportivas",
        "keywords": ["gran supercuota"],
        "blacklist": ["mymatch", "combinada"],
    },
    "William Hill": {
        "url": "https://sports.williamhill.es/betting/es-es",
        "keywords": ["épica", "insuperable"],
        "blacklist": ["crea tu apuesta", "combinada"],
    },
    "Casino Gran Madrid": {
        "url": "https://www.casinogranmadridonline.es/apuestas-deportivas/",
        "keywords": ["apuesta del día"],
        "blacklist": ["combinada"],
    },
    "Betfair": {
        "url": "https://www.betfair.es/sport/football",
        "keywords": ["supercuota"],
        "blacklist": ["combipartido", "combinada"],
    },
    "Paf": {
        "url": "https://www.paf.es/es/sportsbook",
        "keywords": ["cuotas mejoradas"],
        "blacklist": ["combinada"],
    },
    "Betway": {
        "url": "https://betway.es/es/esports",
        "keywords": ["mega cuota"],
        "blacklist": ["combinada"],
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
            log(f"Error enviando foto a Telegram: {e}")

    url_text = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {'chat_id': user_id, 'text': mensaje, 'parse_mode': 'Markdown'}
    try:
        async with session.post(url_text, json=payload, timeout=aiohttp.ClientTimeout(total=5)):
            pass
    except Exception as e:
        log(f"Error enviando mensaje a Telegram: {e}")

async def rastrear():
    historial = cargar_historial()
    nuevas_alertas = False

    async with aiohttp.ClientSession() as session:
        async with async_playwright() as p:
            log("🚀 Iniciando comprobación directa...")
            browser = await p.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox']
            )
            context = await browser.new_context(
                viewport={'width': 1280, 'height': 800},
                locale="es-ES"
            )
            page = await context.new_page()

            for nombre_casa, config in CONFIG_CASAS.items():
                log(f"🔍 Escaneando {nombre_casa}...")
                try:
                    # Carga simple sin bloquear la red
                    await page.goto(config['url'], timeout=8000, wait_until="domcontentloaded")
                    await page.wait_for_timeout(2000)

                    # Hacer un scroll rápido para cargar imágenes/tarjetas
                    await page.evaluate("window.scrollBy(0, 400);")
                    await page.wait_for_timeout(1000)

                    # Obtener TODO el texto visible de la página en 1 sola llamada
                    texto_pagina = await page.evaluate("document.body.innerText")
                    texto_lower = texto_pagina.lower()

                    # Comprobar palabra clave
                    kw_encontrada = None
                    for kw in config["keywords"]:
                        if kw in texto_lower:
                            kw_encontrada = kw
                            break

                    if kw_encontrada:
                        # Descartar si hay palabras de la blacklist muy cerca
                        if any(bl in texto_lower for bl in config["blacklist"]):
                            log(f"  ⏩ Omitida en {nombre_casa}: detectada combinación/parlay.")
                            continue

                        # Extraer un fragmento representativo
                         lineas = [l.strip() for l in texto_pagina.split('\n') if kw_encontrada in l.lower()]
                         resumen_oferta = lineas[0] if lineas else f"Oferta {kw_encontrada}"
                         
                        id_oferta = f"{nombre_casa}_{resumen_oferta[:30]}"
                        if id_oferta in historial:
                            log(f"  ⏩ Omitida: Ya notificada anteriormente.")
                            continue

                        log(f"  🎯 ¡OFERTA ENCONTRADA EN {nombre_casa.upper()}!")

                        # Tomar captura completa de la vista
                        await page.screenshot(path=SCREENSHOT_PATH)

                        mensaje = (
                            f"🎯 **SUPERCUOTA DETECTADA**\n\n"
                            f"🏦 **Casa:** {nombre_casa.upper()}\n"
                            f"📌 **Detalle:** {resumen_oferta[:150]}\n\n"
                            f"🔗 [Ir a la oferta]({config['url']})"
                        )

                        await enviar_telegram_con_foto(session, mensaje, SCREENSHOT_PATH)
                        log(f"  ✅ Notificación y captura enviadas a Telegram.")
                        historial.add(id_oferta)
                        nuevas_alertas = True

                except Exception as e:
                    log(f"  ⚡ Salto seguro en {nombre_casa}: {e}")

            await browser.close()
            log("🏁 Proceso finalizado.")

    if nuevas_alertas:
        guardar_historial(historial)

if __name__ == "__main__":
    asyncio.run(rastrear())