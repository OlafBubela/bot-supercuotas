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

HISTORIAL_FILE = "alertas_definitivo.json"
SCREENSHOT_PATH = "oferta_detectada.png"

# Casas de apuestas estables (sin Bet365 ni William Hill)
CONFIG_CASAS = {
    "Winamax": {
        "url": "https://www.winamax.es/apuestas-deportivas",
        "keywords": ["gran supercuota"],
        "blacklist": ["mymatch", "combinada"],
    },
    "Casino Gran Madrid": {
        "url": "https://www.casinogranmadridonline.es/apuestas-deportivas/",
        "keywords": ["apuesta del día", "apuestas del día"],
        "blacklist": ["combinada"],
    },
    "Betfair": {
        "url": "https://www.betfair.es/sport/football",
        "keywords": ["supercuota"],
        "blacklist": ["combipartido", "combinada"],
    },
    "Paf": {
        "url": "https://www.paf.es/es/sportsbook",
        "keywords": ["cuotas mejoradas", "cuota mejorada"],
        "blacklist": ["combinada", "crea tu apuesta"],
    },
    "Betway": {
        "url": "https://betway.es/es/esports",
        "keywords": ["mega cuota", "megacuota"],
        "blacklist": ["combinada"],
    },
    "Interwetten": {
        "url": "https://www.interwetten.es/es/apuestas-deportivas",
        "keywords": ["supercuota", "megacuota"],
        "blacklist": ["combinada"],
    },
    "Bwin": {
        "url": "https://sports.bwin.es/es/sports",
        "keywords": ["supercuota", "precio mejorado"],
        "blacklist": ["build a bet", "combinada"],
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

def calcular_ev(supercuota, cuota_referencia_base):
    if cuota_referencia_base <= 1.0:
        return 0.0
    probabilidad_real = 1 / cuota_referencia_base
    ev = (probabilidad_real * supercuota) - 1
    return round(ev * 100, 2)

def extraer_cuotas_limpias(texto):
    texto_sin_euros = re.sub(r'\b\d+[\.,]?\d*\s*€', '', texto)
    numeros = re.findall(r'\b\d+[\.,]\d+\b', texto_sin_euros)
    cuotas_validas = []
    for n in numeros:
        try:
            val = float(n.replace(',', '.'))
            if 1.15 <= val <= 15.00:
                cuotas_validas.append(val)
        except ValueError:
            continue
    return cuotas_validas

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

                    if 5 < len(texto_limpio) < 400:
                        cuotas = extraer_cuotas_limpias(texto_limpio)

                        if len(cuotas) >= 1:
                            supercuota_val = max(cuotas)
                            cuota_referencia = min(cuotas) if len(cuotas) > 1 else round(supercuota_val * 0.8, 2)

                            texto_resumen = texto_limpio[:50].replace('\n', ' ')
                            log(f"  🎯 Oferta detectada en {nombre_casa}: '{texto_resumen}...' | Cuota: {supercuota_val}")

                            id_oferta = f"{nombre_casa}_{texto_limpio[:20]}_{supercuota_val}"
                            
                            if id_oferta in historial:
                                log(f"  ⏩ Omitida: Ya en historial.")
                                continue

                            ev_porcentaje = calcular_ev(supercuota_val, cuota_referencia)
                            
                            try:
                                await el.screenshot(path=SCREENSHOT_PATH)
                            except Exception:
                                await page.screenshot(path=SCREENSHOT_PATH)

                            mensaje = (
                                f"🎯 **NUEVA SUPERCUOTA DETECTADA**\n\n"
                                f"🏦 **Casa:** {nombre_casa.upper()}\n"
                                f"📌 **Apuesta:** {texto_limpio.replace(chr(10), ' ')}\n"
                                f"⚡ **Supercuota:** {supercuota_val}\n"
                                f"📊 **Cuota Base Ref:** {cuota_referencia}\n"
                                f"📈 **Valor Esperado (+EV):** +{ev_porcentaje}%\n\n"
                                f"🔗 [Ir a la oferta]({config['url']})"
                            )

                            await enviar_telegram_con_foto(session, mensaje, SCREENSHOT_PATH)
                            log(f"  ✅ ¡ALERTA Y CAPTURA ENVIADAS A TELEGRAM!")
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
            log("🚀 Iniciando rastreo limpio...")
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--no-sandbox',
                    '--disable-setuid-sandbox'
                ]
            )
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
                viewport={'width': 1280, 'height': 800},
                locale="es-ES",
                timezone_id="Europe/Madrid"
            )

            page = await context.new_page()

            await page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            """)

            for nombre_casa, config in CONFIG_CASAS.items():
                log(f"🔍 Escaneando {nombre_casa}...")
                try:
                    await page.goto(config['url'], timeout=6000, wait_until="domcontentloaded")
                    await page.wait_for_timeout(1500)

                    # Aceptar cookies rápido si sale botón
                    try:
                        cookie_btn = await page.query_selector('button:has-text("Aceptar"), button:has-text("Aceptar y cerrar")')
                        if cookie_btn:
                            await cookie_btn.click(timeout=800)
                    except Exception:
                        pass

                    if await escaneo_elementos_pagina(page, session, nombre_casa, config, historial):
                        nuevas_alertas = True

                except Exception as e:
                    log(f"  ⚡ Salto seguro en {nombre_casa}: {e}")

            await browser.close()
            log("🏁 Proceso finalizado.")

    if nuevas_alertas:
        guardar_historial(historial)

if __name__ == "__main__":
    asyncio.run(rastrear())