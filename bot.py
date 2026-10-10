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

# Clave de The Odds API
ODDS_API_KEY = "23fbe34384f88b2bf502bc977f1bb24f" 

HISTORIAL_FILE = "alertas_enviadas.json"

casas = {
    "Paf": "https://www.paf.es/es/sportsbook",
    "Winamax": "https://www.winamax.es/apuestas-deportivas",
    "William Hill Promos": "https://sports.williamhill.es/betting/es-es/highlights",
    "Interwetten": "https://www.interwetten.es/es/apuestas-deportivas",
    "Betway": "https://betway.es/es/esports",
    "Betfair": "https://www.betfair.es/sport/football",
    "Bwin": "https://sports.bwin.es/es/sports",
    "Casino Gran Madrid": "https://www.casinogranmadridonline.es/apuestas-deportivas/",
    "Bet365 Deportes": "https://www.bet365.es/#/HO/"
}

keywords = [
    'supercuota', 'cuota mejorada', 'boost', 'odds boost', 'oddsboost', 'super cuota', 
    'megacuota', 'aumento de cuota', 'aumento de apuesta', 'aumento', 'mejorada', 
    'especiales', 'superprecio', 'cuota aumentada', 'aumento de ganancias',
    'cuota épica', 'cuotas insuperables', 'épica', 'insuperable', 'cuota epica'
]

def log(mensaje):
    """Imprime mensajes con marca de tiempo para trazabilidad en tiempo real."""
    timestamp = time.strftime("%H:%M:%S")
    print(f"[{timestamp}] {mensaje}", flush=True)

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

async def enviar_telegram(session, mensaje):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {'chat_id': user_id, 'text': mensaje, 'parse_mode': 'Markdown'}
    try:
        async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=5)) as resp:
            pass
    except Exception as e:
        log(f"Error enviando mensaje a Telegram: {e}")

def extraer_cuotas_limpias(texto):
    """Filtra importes en euros (€) e identificadores secundarios."""
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

async def escaneo_elementos_pagina(page, session, nombre_casa, url_actual, historial):
    nuevas = False
    try:
        # 1. Espera activa para hidratar Custom Elements en Bet365 y casas con SPA
        if "bet365" in url_actual.lower():
            try:
                await page.wait_for_selector('div, article, section', timeout=4000)
                # Scroll para detonar la carga diferida del banner de aumentos
                await page.evaluate("window.scrollBy(0, 200);")
                await page.wait_for_timeout(1500)
            except Exception:
                pass

        # Seleccionar contenedores del DOM
        elementos = await page.query_selector_all('article, section, div[class*="boost"], div[class*="promo"], div[class*="offer"], div')
        
        for el in elementos:
            try:
                texto = await el.inner_text()
                texto_limpio = texto.strip()
                
                if any(palabra in texto_limpio.lower() for palabra in keywords):
                    if 5 < len(texto_limpio) < 300:
                        cuotas = extraer_cuotas_limpias(texto_limpio)

                        if len(cuotas) >= 1:
                            supercuota_val = max(cuotas)
                            
                            # Determinación precisa de la cuota base de referencia
                            if len(cuotas) > 1:
                                cuota_referencia = min(cuotas)
                            else:
                                cuota_referencia = round(supercuota_val * 0.75, 2)

                            texto_resumen = texto_limpio[:60].replace('\n', ' ')
                            log(f"  📌 Detectado en {nombre_casa}: '{texto_resumen}...' | Cuota: {supercuota_val}")

                            id_oferta = f"{nombre_casa}_{texto_limpio[:25]}_{supercuota_val}"
                            
                            if id_oferta in historial:
                                log(f"  ⏩ Omitida: Ya registrada en el historial.")
                                continue

                            ev_porcentaje = calcular_ev(supercuota_val, cuota_referencia)
                            
                            mensaje = (
                                f"🎯 **NUEVA SUPERCUOTA DETECTADA (+EV REAL)**\n\n"
                                f"🏦 **Casa:** {nombre_casa.upper()}\n"
                                f"📌 **Apuesta:** {texto_limpio.replace(chr(10), ' ')}\n"
                                f"⚡ **Cuota Mejorada:** {supercuota_val}\n"
                                f"📊 **Cuota Referencia Base:** {cuota_referencia}\n"
                                f"📈 **Valor Esperado (+EV):** +{ev_porcentaje}%\n\n"
                                f"🔗 [Ir a la oferta]({url_actual})"
                            )

                            await enviar_telegram(session, mensaje)
                            log(f"  ✅ ¡ALERTA ENVIADA A TELEGRAM! (+EV: +{ev_porcentaje}%).")
                            historial.add(id_oferta)
                            nuevas = True
            except Exception:
                continue
    except Exception as e:
        log(f"  ⚠️ Error durante el escaneo del DOM en {nombre_casa}: {e}")
            
    return nuevas

async def rastrear():
    historial = cargar_historial()
    nuevas_alertas = False

    async with aiohttp.ClientSession() as session:
        async with async_playwright() as p:
            log("🚀 Iniciando Chromium con enmascaramiento anti-detección...")
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-infobars',
                    '--window-position=0,0',
                    '--ignore-certificate-errors',
                    '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36'
                ]
            )
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
                viewport={'width': 1280, 'height': 800},
                locale="es-ES",
                timezone_id="Europe/Madrid"
            )

            page = await context.new_page()
            page.set_default_timeout(6000)

            # Inyección para ocultar automatización de Playwright
            await page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            """)

            log("🤖 Comienza el recorrido por las casas de apuestas...")

            for nombre_casa, url in casas.items():
                log(f"🔍 Escaneando {nombre_casa} ({url})...")
                try:
                    await page.goto(url, timeout=8000, wait_until="domcontentloaded")
                    await page.wait_for_timeout(1000)

                    # Intentar cerrar el banner de cookies de forma limpia
                    try:
                        cookie_btn = await page.query_selector('button:has-text("Aceptar y cerrar"), button:has-text("Aceptar")')
                        if cookie_btn:
                            await cookie_btn.click(timeout=1000)
                            await page.wait_for_timeout(500)
                    except Exception:
                        pass

                    alerta = await escaneo_elementos_pagina(page, session, nombre_casa, url, historial)
                    if alerta:
                        nuevas_alertas = True

                except Exception as e:
                    log(f"  ⚡ Salto seguro por timeout en {nombre_casa}: {e}")

            await browser.close()
            log("🏁 Navegador cerrado correctamente.")

    if nuevas_alertas:
        guardar_historial(historial)
        log("💾 Historial de alertas actualizado.")

if __name__ == "__main__":
    asyncio.run(rastrear())