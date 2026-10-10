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

async def enviar_telegram_con_foto(session, mensaje, foto_path=None):
    url = f"https://api.telegram.org/bot{token}/sendMessage" if not foto_path else f"https://api.telegram.org/bot{token}/sendPhoto"
    
    if foto_path and os.path.exists(foto_path):
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
    else:
        payload = {'chat_id': user_id, 'text': mensaje, 'parse_mode': 'Markdown'}
        try:
            async with session.post(url, json=payload) as resp:
                pass
        except Exception as e:
            print(f"Error enviando texto a Telegram: {e}", flush=True)

def extraer_cuotas_limpias(texto):
    texto_sin_euros = re.sub(r'\b\d+[\.,]?\d*\s*€', '', texto)
    numeros = re.findall(r'\b\d+[\.,]\d+\b', texto_sin_euros)
    cuotas_validas = []
    for n in numeros:
        try:
            val = float(n.replace(',', '.'))
            if 1.15 <= val <= 20.00:
                cuotas_validas.append(val)
        except ValueError:
            continue
    return cuotas_validas

async def procesar_oferta(session, nombre_casa, texto_oferta, supercuota_val, cuota_previa, url_actual, historial, page=None):
    id_oferta = f"{nombre_casa}_{texto_oferta[:25]}_{supercuota_val}"
    
    if id_oferta in historial:
        print(f"  ⏩ Omitida: Ya está en el historial.", flush=True)
        return False

    cuota_mercado_max = await obtener_max_cuota_mercado(session)
    cuota_referencia = cuota_mercado_max if cuota_mercado_max else cuota_previa

    ev_porcentaje = calcular_ev(supercuota_val, cuota_referencia)
    
    if ev_porcentaje <= 0:
        print(f"  ⚠️ Omitida: +EV no rentable ({ev_porcentaje}% vs Ref {cuota_referencia}).", flush=True)
        return False

    foto_filename = f"screenshot_{nombre_casa}.png" if page else None
    if page:
        try:
            await page.screenshot(path=foto_filename, full_page=False)
        except Exception:
            foto_filename = None

    mensaje = (
        f"🎯 **NUEVA SUPERCUOTA DETECTADA (+EV REAL)**\n\n"
        f"🏦 **Casa:** {nombre_casa.upper()}\n"
        f"📌 **Apuesta:** {texto_oferta}\n"
        f"⚡ **Cuota Mejorada:** {supercuota_val}\n"
        f"📊 **Cuota Mercado / Ref:** {cuota_referencia}\n"
        f"📈 **Valor Esperado Real (+EV):** +{ev_porcentaje}%\n\n"
        f"🔗 [Ir a la oferta]({url_actual})"
    )

    await enviar_telegram_con_foto(session, mensaje, foto_filename)
    print(f"  ✅ ¡ALERTA ENVIADA A TELEGRAM! (+EV: +{ev_porcentaje}%).", flush=True)
    historial.add(id_oferta)
    return True

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

            # Interceptador de red para la API interna
            async def manejar_respuesta(response):
                nonlocal nuevas_alertas
                try:
                    url = response.url
                    # Detectar respuestas JSON de William Hill / Bet365 / Paf
                    if "application/json" in response.headers.get("content-type", ""):
                        if any(term in url for term in ["offering", "sports", "priceboost", "bets", "search"]):
                            data = await response.json()
                            str_data = json.dumps(data).lower()
                            
                            if any(k in str_data for k in ['boost', 'insuperable', 'aumento', 'cuota epica']):
                                print(f"  🌐 Datos JSON promocionales interceptados en la red ({url[:60]}...)", flush=True)
                except Exception:
                    pass

            page.on("response", manejar_respuesta)

            print("🤖 Iniciando rastreo técnico por interceptación de red y DOM...", flush=True)

            for nombre_casa, url in casas.items():
                print(f"🔍 Escaneando {nombre_casa}...", flush=True)
                try:
                    await page.goto(url, timeout=20000, wait_until="domcontentloaded")
                    await page.wait_for_timeout(2500)

                    # Escaneo DOM secundario por si acaso
                    elementos = await page.query_selector_all('div, article, button, a')
                    for el in elementos:
                        try:
                            texto = await el.inner_text()
                            texto_limpio = texto.strip()
                            if any(palabra in texto_limpio.lower() for palabra in keywords):
                                if 5 < len(texto_limpio) < 300:
                                    cuotas = extraer_cuotas_limpias(texto_limpio)
                                    if len(cuotas) >= 1:
                                        sq = max(cuotas)
                                        cp = min(cuotas) if len(cuotas) > 1 else round(sq * 0.8, 2)
                                        print(f"  📌 Detectado en DOM {nombre_casa}: '{texto_limpio[:40].replace(chr(10), ' ')}...' | Cuota: {sq}", flush=True)
                                        enviado = await procesar_oferta(session, nombre_casa, texto_limpio.replace('\n', ' '), sq, cp, url, historial, page)
                                        if enviado:
                                            nuevas_alertas = True
                        except Exception:
                            continue

                except Exception as e:
                    print(f"⚠️ Error/Timeout en {nombre_casa}: {e}", flush=True)

            await browser.close()

    if nuevas_alertas:
        guardar_historial(historial)
        print("💾 Historial de alertas actualizado.", flush=True)

if __name__ == "__main__":
    asyncio.run(rastrear())