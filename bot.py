import asyncio
import json
import os
import re
import aiohttp
from playwright.async_api import async_playwright

token = "8777299013:AAH8-gTT-_CTw2Ht0RRXW55jsPEGFh0_OuU"
user_id = "865364645"
ODDS_API_KEY = "23fbe34384f88b2bf502bc977f1bb24f" 

HISTORIAL_FILE = "alertas_enviadas.json"

casas = {
    "Paf": "https://www.paf.es/es/sportsbook",
    "Winamax": "https://www.winamax.es/apuestas-deportivas",
    "William Hill": "https://sports.williamhill.es/betting/es-es",
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

TERMINOS_BUSQUEDA_WH = ['Cuota Épica', 'Insuperable']

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

async def obtener_max_cuota_mercado(session, deporte="upcoming"):
    if not ODDS_API_KEY:
        return None
    url = f"https://api.the-odds-api.com/v4/sports/{deporte}/odds/?apiKey={ODDS_API_KEY}&regions=eu&markets=h2h"
    try:
        async with session.get(url, timeout=3) as res:
            if res.status == 200:
                datos = await res.json()
                cuotas = []
                for evento in datos:
                    for bm in evento.get('bookmakers', []):
                        for mk in bm.get('markets', []):
                            for outcome in mk.get('outcomes', []):
                                cuotas.append(outcome.get('price', 0))
                if cuotas:
                    return max(cuotas)
    except Exception:
        pass
    return None

def calcular_ev(supercuota, cuota_referencia_mercado):
    probabilidad_real = 1 / cuota_referencia_mercado
    ev = (probabilidad_real * supercuota) - 1
    return round(ev * 100, 2)

async def enviar_telegram(session, mensaje):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {'chat_id': user_id, 'text': mensaje, 'parse_mode': 'Markdown'}
    try:
        async with session.post(url, json=payload, timeout=5) as resp:
            pass
    except Exception as e:
        print(f"Error enviando mensaje a Telegram: {e}", flush=True)

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

async def escaneo_elementos_pagina(page, session, nombre_casa, url_actual, historial):
    nuevas = False
    elementos = await page.query_selector_all('div, article, button, a, li, section')
    
    for el in elementos:
        try:
            texto = await el.inner_text()
            texto_limpio = texto.strip()
            
            if any(palabra in texto_limpio.lower() for palabra in keywords):
                if 5 < len(texto_limpio) < 300:
                    cuotas = extraer_cuotas_limpias(texto_limpio)
                    if len(cuotas) >= 1:
                        supercuota_val = max(cuotas)
                        cuota_casa_previa = min(cuotas) if len(cuotas) > 1 else round(supercuota_val * 0.8, 2)

                        texto_resumen = texto_limpio[:50].replace('\n', ' ')
                        print(f"  📌 Detectado en {nombre_casa}: '{texto_resumen}...' | Cuota: {supercuota_val}", flush=True)

                        id_oferta = f"{nombre_casa}_{texto_limpio[:25]}_{supercuota_val}"
                        
                        if id_oferta in historial:
                            print(f"  ⏩ Omitida: Ya registrada en el historial.", flush=True)
                            continue

                        cuota_mercado_max = await obtener_max_cuota_mercado(session)
                        cuota_referencia = cuota_mercado_max if cuota_mercado_max else cuota_casa_previa

                        ev_porcentaje = calcular_ev(supercuota_val, cuota_referencia)
                        
                        if ev_porcentaje <= 0:
                            print(f"  ⚠️ Omitida: +EV no rentable ({ev_porcentaje}% vs Ref {cuota_referencia}).", flush=True)
                            continue

                        mensaje = (
                            f"🎯 **NUEVA SUPERCUOTA DETECTADA (+EV REAL)**\n\n"
                            f"🏦 **Casa:** {nombre_casa.upper()}\n"
                            f"📌 **Apuesta:** {texto_limpio.replace(chr(10), ' ')}\n"
                            f"⚡ **Cuota Mejorada:** {supercuota_val}\n"
                            f"📊 **Cuota Mercado / Ref:** {cuota_referencia}\n"
                            f"📈 **Valor Esperado Real (+EV):** +{ev_porcentaje}%\n\n"
                            f"🔗 [Ir a la oferta]({url_actual})"
                        )

                        await enviar_telegram(session, mensaje)
                        print(f"  ✅ ¡ALERTA ENVIADA A TELEGRAM! (+EV: +{ev_porcentaje}%).", flush=True)
                        historial.add(id_oferta)
                        nuevas = True
        except Exception:
            continue
            
    return nuevas

async def rastrear():
    historial = cargar_historial()
    nuevas_alertas = False

    async with aiohttp.ClientSession() as session:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=['--disable-blink-features=AutomationControlled', '--no-sandbox']
            )
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                viewport={'width': 1280, 'height': 800}
            )

            page = await context.new_page()

            print("🤖 Iniciando rastreo con secuencia de cookies + buscador en William Hill...", flush=True)

            for nombre_casa, url in casas.items():
                print(f"🔍 Escaneando {nombre_casa}...", flush=True)
                try:
                    await page.goto(url, timeout=18000, wait_until="domcontentloaded")
                    await page.wait_for_timeout(1500)

                    # 1. Quitar aviso de cookies
                    try:
                        cookie_btn = await page.query_selector('button:has-text("Aceptar y cerrar"), button:has-text("Aceptar")')
                        if cookie_btn:
                            await cookie_btn.click(timeout=1500)
                            await page.wait_for_timeout(1000)
                    except Exception:
                        pass

                    # 2. Si es William Hill, realizar la búsqueda interactiva
                    if nombre_casa == "William Hill":
                        for termino in TERMINOS_BUSQUEDA_WH:
                            try:
                                print(f"  🔎 Abriendo buscador para '{termino}'...", flush=True)
                                search_btn = await page.query_selector('button[aria-label*="Search"], [class*="search"], [id*="search"]')
                                if search_btn:
                                    await search_btn.click(timeout=1500)
                                    await page.wait_for_timeout(1000)

                                search_input = await page.query_selector('input[type="search"], input[type="text"], input[placeholder*="Buscar"]')
                                if search_input:
                                    await search_input.fill("")
                                    await search_input.type(termino, delay=80)
                                    await page.keyboard.press('Enter')
                                    await page.wait_for_timeout(2500)

                                    alerta_wh = await escaneo_elementos_pagina(page, session, nombre_casa, url, historial)
                                    if alerta_wh:
                                        nuevas_alertas = True
                            except Exception as e_search:
                                print(f"  ⚠️ Error durante la búsqueda de {termino}: {e_search}", flush=True)

                    alerta_general = await escaneo_elementos_pagina(page, session, nombre_casa, url, historial)
                    if alerta_general:
                        nuevas_alertas = True

                except Exception as e:
                    print(f"  ⚡ Salto por tiempo agotado en {nombre_casa}", flush=True)

            await browser.close()

    if nuevas_alertas:
        guardar_historial(historial)
        print("💾 Historial de alertas actualizado.", flush=True)

if __name__ == "__main__":
    asyncio.run(rastrear())