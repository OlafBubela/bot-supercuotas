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
        async with session.get(url, timeout=4) as res:
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
        print(f"Error enviando foto a Telegram: {e}", flush=True)

def extraer_cuotas_limpias(texto):
    """Filtra y extrae solo las cuotas reales ignorando ganancias en euros (€)."""
    # Eliminar patrones de ganancias en euros tipo '66.50€' o '10€'
    texto_sin_euros = re.sub(r'\b\d+[\.,]?\d*\s*€', '', texto)
    
    numeros = re.findall(r'\b\d+[\.,]\d+\b', texto_sin_euros)
    cuotas_validas = []
    
    for n in numeros:
        try:
            val = float(n.replace(',', '.'))
            # Cuotas normales de supercuota (entre 1.20 y 15.00)
            if 1.20 <= val <= 15.00:
                cuotas_validas.append(val)
        except ValueError:
            continue
            
    return cuotas_validas

async def escaneo_elementos_pagina(page, session, nombre_casa, url_actual, historial):
    nuevas = False
    elementos = await page.query_selector_all('article, div[class*="event"], div[class*="selection"], div[class*="market"], li, section, div, span')
    coincidencias = 0
    
    for el in elementos:
        try:
            texto = await el.inner_text()
            texto_limpio = texto.strip()
            
            if any(palabra in texto_limpio.lower() for palabra in keywords):
                if 5 < len(texto_limpio) < 400:
                    cuotas_encontradas = extraer_cuotas_limpias(texto_limpio)
                    
                    if len(cuotas_encontradas) >= 1:
                        if len(cuotas_encontradas) >= 2:
                            cuota_casa_previa = min(cuotas_encontradas)
                            supercuota_val = max(cuotas_encontradas)
                        else:
                            supercuota_val = cuotas_encontradas[0]
                            cuota_casa_previa = round(supercuota_val * 0.80, 2)

                        coincidencias += 1
                        texto_resumen = texto_limpio[:60].replace('\n', ' ')
                        print(f"  📌 Detectado en {nombre_casa}: '{texto_resumen}...' | Cuota Limpia: {supercuota_val}", flush=True)

                        id_oferta = f"{nombre_casa}_{texto_limpio[:30]}_{supercuota_val}"
                        
                        if id_oferta in historial:
                            print(f"  ⏩ Omitida: Oferta ya en historial.", flush=True)
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
        print(f"  ℹ️ Sin bloques válidos extraídos en esta vista.", flush=True)
        
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

            # No bloqueamos CSS/JS para permitir el renderizado exacto de William Hill y Bet365
            print("🤖 Iniciando rastreo con filtrado de cuotas puras (sin €)...", flush=True)

            for nombre_casa, url in casas.items():
                print(f"🔍 Escaneando {nombre_casa}...", flush=True)
                try:
                    await page.goto(url, timeout=15000, wait_until="domcontentloaded")
                    await page.wait_for_timeout(2000)

                    if nombre_casa == "William Hill":
                        for termino in TERMINOS_BUSQUEDA:
                            try:
                                print(f"  🔎 Búsqueda URL para '{termino}'...", flush=True)
                                search_url = f"https://sports.williamhill.es/betting/es-es/search?term={termino.replace(' ', '%20')}"
                                await page.goto(search_url, timeout=15000, wait_until="domcontentloaded")
                                await page.wait_for_timeout(3000)

                                alerta_busqueda = await escaneo_elementos_pagina(page, session, nombre_casa, search_url, historial)
                                if alerta_busqueda:
                                    nuevas_alertas = True
                            except Exception as e_search:
                                print(f"  ⚠️ Error buscando {termino}: {e_search}", flush=True)

                    hubo_alerta = await escaneo_elementos_pagina(page, session, nombre_casa, url, historial)
                    if hubo_alerta:
                        nuevas_alertas = True

                except Exception as e:
                    print(f"⚠️ Tiempo agotado cargando {nombre_casa}: {e}", flush=True)

            await browser.close()

    if nuevas_alertas:
        guardar_historial(historial)
        print("💾 Historial de alertas actualizado.", flush=True)

if __name__ == "__main__":
    asyncio.run(rastrear())