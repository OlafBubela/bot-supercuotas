import asyncio
import json
import os
import re
import requests
from playwright.async_api import async_playwright

# Configuración de Telegram
token = "8777299013:AAH8-gTT-_CTw2Ht0RRXW55jsPEGFh0_OuU"
user_id = "865364645"

# Clave de The Odds API
ODDS_API_KEY = "23fbe34384f88b2bf502bc977f1bb24f" 

HISTORIAL_FILE = "alertas_enviadas.json"

# Rutas optimizadas (portadas y secciones clave)
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
    'cuota épica', 'cuotas insuperables', 'épica', 'insuperable'
]

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

def obtener_max_cuota_mercado(deporte="upcoming"):
    if not ODDS_API_KEY:
        return None
    url = f"https://api.the-odds-api.com/v4/sports/{deporte}/odds/?apiKey={ODDS_API_KEY}&regions=eu&markets=h2h"
    try:
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            datos = res.json()
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

def enviar_telegram_con_foto(mensaje, foto_path):
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    with open(foto_path, 'rb') as photo:
        payload = {
            'chat_id': user_id,
            'caption': mensaje,
            'parse_mode': 'Markdown'
        }
        files = {'photo': photo}
        requests.post(url, data=payload, files=files)

async def escaneo_elementos_pagina(page, nombre_casa, url_actual, historial):
    nuevas = False
    elementos = await page.query_selector_all('span, div, a, h3, p, article')
    
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

                        if 1.20 <= supercuota_val <= 50.0 and supercuota_val > cuota_casa_previa:
                            id_oferta = f"{nombre_casa}_{texto_limpio[:40]}_{supercuota_val}"
                            
                            if id_oferta in historial:
                                continue

                            cuota_mercado_max = obtener_max_cuota_mercado()
                            cuota_referencia = cuota_mercado_max if cuota_mercado_max else cuota_casa_previa

                            ev_porcentaje = calcular_ev(supercuota_val, cuota_referencia)
                            
                            if ev_porcentaje <= 0:
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

                            enviar_telegram_con_foto(mensaje, foto_filename)
                            print(f"Alerta enviada para {nombre_casa} (+EV: +{ev_porcentaje}%).")
                            
                            historial.add(id_oferta)
                            nuevas = True
                            break
        except Exception:
            continue
    return nuevas

async def rastrear():
    historial = cargar_historial()
    nuevas_alertas = False

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 800}
        )
        page = await context.new_page()

        await page.route("**/*.{png,jpg,jpeg,svg,webp,mp4,woff,woff2}", lambda route: route.abort())

        print("🤖 Comprobando portadas y navegando a eventos con aumentos ocultos...")

        for nombre_casa, url in casas.items():
            try:
                await page.goto(url, timeout=25000, wait_until="domcontentloaded")
                await page.wait_for_timeout(2000)

                await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 3);")
                await page.wait_for_timeout(1000)

                # 1. Escaneo de la portada principal
                hubo_alerta = await escaneo_elementos_pagina(page, nombre_casa, url, historial)
                if hubo_alerta:
                    nuevas_alertas = True

                # 2. Navegación a eventos internos para buscar aumentos escondidos
                enlaces_eventos = await page.query_selector_all('a[href*="event"], a[href*="partido"], a[href*="match"], .src-MarketGroup')
                urls_partidos = []
                for link in enlaces_eventos[:3]:  # Analiza los 3 eventos principales para optimizar tiempo
                    href = await link.get_attribute('href')
                    if href and href.startswith('http'):
                        urls_partidos.append(href)

                for url_partido in set(urls_partidos):
                    try:
                        await page.goto(url_partido, timeout=15000, wait_until="domcontentloaded")
                        await page.wait_for_timeout(1500)

                        # Intentar clicar en pestañas de aumentos/especiales si existen
                        pestañas_aumentos = await page.query_selector_all('text="Aumento de apuesta", text="Aumentos", text="Supercuota", text="Especiales"')
                        for tab in pestañas_aumentos[:2]:
                            try:
                                await tab.click(timeout=1000)
                                await page.wait_for_timeout(500)
                            except Exception:
                                pass

                        alerta_interna = await escaneo_elementos_pagina(page, nombre_casa, url_partido, historial)
                        if alerta_interna:
                            nuevas_alertas = True
                    except Exception:
                        continue

            except Exception as e:
                print(f"Error o tiempo agotado en {nombre_casa}: {e}")

        await browser.close()

    if nuevas_alertas:
        guardar_historial(historial)
        print("💾 Historial de alertas actualizado.")

if __name__ == "__main__":
    asyncio.run(rastrear())