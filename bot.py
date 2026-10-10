import asyncio
import json
import os
import re
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
    'megacuota', 'aumento de cuota', 'aumento de apuesta', 
    'superaumento', 'aumento', 'mejorada', 'especiales', 
    'superprecio', 'cuota aumentada', 'aumento de ganancias',
    'cuota épica', 'cuotas insuperables', 'épica', 'insuperable', 'cuota epica'
]

TERMINOS_BUSQUEDA = ['Insuperable', 'Cuota Épica']

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
        async with session.get(url, timeout=5) as res:
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

async def enviar_telegram_con_foto(session, mensaje, foto_path):
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    data = aiohttp.FormData()
    data.add_field('chat_id', user_id)
    data.add_field('caption', mensaje)
    data.add_field('parse_mode', 'Markdown')
    data.add_field('photo', open(foto_path, 'rb'))
    
    try:
        async with session.post(url, data=data) as resp:
            pass
    except Exception as e:
        print(f"Error al enviar foto a Telegram: {e}", flush=True)

async def escaneo_elementos_pagina(page, session, nombre_casa, url_actual, historial):
    nuevas = False
    elementos = await page.query_selector_all('span, div, a, h3, p, article')
    coincidencias = 0
    
    for el in elementos:
        try:
            texto = await el.inner_text()
            texto_limpio = texto.strip()
            
            if any(palabra in texto_limpio.lower() for palabra in keywords):
                if 5 < len(texto_limpio) < 300:
                    numeros = re.findall(r'\b\d+[\.,]\d+\b', texto_limpio)
                    if len(numeros) >= 1:
                        float_numeros = [float(n.replace(',', '.')) for n in numeros if 1.10 <= float(n.replace(',', '.')) <= 100.0]
                        
                        if len(float_numeros) >= 2:
                            cuota_casa_previa = min(float_numeros)
                            supercuota_val = max(float_numeros)
                        elif len(float_numeros) == 1:
                            supercuota_val = float_numeros[0]
                            cuota_casa_previa = round(supercuota_val * 0.75, 2)
                        else:
                            continue

                        coincidencias += 1
                        print(f"  📌 Texto detectado en {nombre_casa}: '{texto_limpio[:50]}...' | Cuota: {supercuota_val}", flush=True)

                        if 1.20 <= supercuota_val <= 50.0 and supercuota_val > cuota_casa_previa:
                            id_oferta = f"{nombre_casa}_{texto_limpio[:40]}_{supercuota_val}"
                            
                            if id_oferta in historial:
                                print(f"  ⏩ Omitida: Oferta ya estaba registrada en el historial.", flush=True)
                                continue

                            cuota_mercado_max = await obtener_max_cuota_mercado(session)
                            cuota_referencia = cuota_mercado_max if cuota_mercado_max else cuota_casa_previa

                            ev_porcentaje = calcular_ev(supercuota_val, cuota_referencia)
                            
                            if ev_porcentaje <= 0:
                                print(f"  ⚠️ Omitida: +EV no rentable ({ev_porcentaje}% vs Ref {cuota_referencia}).", flush=True)
                                continue

                            foto_filename = f"screenshot_{nombre_casa}.png"

                            try:
                                await el.screenshot(path=foto_filename)
                            except Exception:
                                await page.screenshot(path=foto_filename, full_page=False)

                            texto_formateado = texto_limpio.replace('\n', ' ')

                            mensaje = (
                                f"🎯 **NUEVA SUPERCUOTA DETECTADA (+EV REAL)**\n\n"
                                f"🏦 **Casa:** {nombre_casa.upper()}\n"
                                f"📌 **Apuesta:** {texto_formateado}\n"
                                f"⚡ **Cuota Mejorada:** {supercuota_val}\n"
                                f"📊 **Cuota Mercado / Ref:** {cuota_referencia}\n"
                                f"📈 **Valor Esperado Real (+EV):** +{ev_porcentaje}%\n\n"
                                f"🔗 [Ir a la oferta]({url_actual})"
                            )

                            await enviar_telegram_con_foto(session, mensaje, foto_filename)
                            print(f"  ✅ ¡ALERTA ENVIADA A TELEGRAM! (+EV: +{ev_porcentaje}%).", flush=True)
                            
                            historial.add(id_oferta)
                            nuevas = True
                            break
        except Exception:
            continue
            
    if coincidencias == 0:
        print(f"  ℹ️ No se extrajo ningún bloque con texto + cuota válido en la vista actual.", flush=True)
        
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
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={'width': 1280, 'height': 800}
            )
            page = await context.new_page()

            await page.route("**/*.{png,jpg,jpeg,svg,webp,mp4,woff,woff2}", lambda route: route.abort())

            print("🤖 Iniciando rastreo con diagnóstico ampliado...", flush=True)

            for nombre_casa, url in casas.items():
                print(f"🔍 Escaneando {nombre_casa}...", flush=True)
                try:
                    await page.goto(url, timeout=20000, wait_until="domcontentloaded")
                    await page.wait_for_timeout(1500)

                    try:
                        cookie_btn = await page.query_selector('button:has-text("Aceptar"), button:has-text("Accept"), #accept-cookies')
                        if cookie_btn:
                            await cookie_btn.click(timeout=1000)
                    except Exception:
                        pass

                    if nombre_casa == "William Hill":
                        for termino in TERMINOS_BUSQUEDA:
                            try:
                                print(f"  🔎 Buscando '{termino}' en {nombre_casa}...", flush=True)
                                search_btn = await page.query_selector('button[aria-label*="Search"], .search-trigger, .header__search, [data-test-id*="search"]')
                                if search_btn:
                                    await search_btn.click(timeout=1000)
                                    await page.wait_for_timeout(500)
                                
                                search_input = await page.query_selector('input[type="search"], input[placeholder*="Buscar"], input[name*="search"]')
                                if search_input:
                                    await search_input.fill(termino)
                                    await page.keyboard.press('Enter')
                                    await page.wait_for_timeout(2500)

                                    alerta_busqueda = await escaneo_elementos_pagina(page, session, nombre_casa, url, historial)
                                    if alerta_busqueda:
                                        nuevas_alertas = True
                                else:
                                    print("  ⚠️ No se encontró el campo de texto del buscador.", flush=True)
                            except Exception as e_search:
                                print(f"  ⚠️ Error buscando {termino}: {e_search}", flush=True)

                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 3);")
                    await page.wait_for_timeout(1000)

                    hubo_alerta = await escaneo_elementos_pagina(page, session, nombre_casa, url, historial)
                    if hubo_alerta:
                        nuevas_alertas = True

                except Exception as e:
                    print(f"❌ Tiempo agotado o error en {nombre_casa}: {e}", flush=True)

            await browser.close()

    if nuevas_alertas:
        guardar_historial(historial)
        print("💾 Historial de alertas actualizado.", flush=True)

if __name__ == "__main__":
    asyncio.run(rastrear())