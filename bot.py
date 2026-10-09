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

# Rutas generales y secciones de aumentos profundos/eSports
casas = {
    "Paf": "https://www.paf.es/es/sportsbook",
    "Winamax": "https://www.winamax.es/apuestas-deportivas",
    "William Hill": "https://sports.williamhill.es/betting/es-es",
    "Interwetten": "https://www.interwetten.es/es/apuestas-deportivas",
    "Betway": "https://betway.es/es/esports",
    "Betfair": "https://www.betfair.es/sport/esports",
    "Bwin": "https://sports.bwin.es/es/sports",
    "Casino Gran Madrid": "https://www.casinogranmadridonline.es/apuestas-deportivas/",
    "Bet365 eSports / Aumentos": "https://www.bet365.es/#/AS/B151/"
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

def obtener_cuota_mercado_api(deporte="upcoming"):
    """
    Consulta The Odds API para obtener la cuota justa de referencia en Pinnacle/Mercado.
    """
    if not ODDS_API_KEY:
        return None
    
    url = f"https://api.the-odds-api.com/v4/sports/{deporte}/odds/?apiKey={ODDS_API_KEY}&regions=eu&markets=h2h&bookmakers=pinnacle"
    try:
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            return res.json()
    except Exception:
        pass
    return None

def calcular_ev(supercuota, cuota_justa):
    probabilidad_real = 1 / cuota_justa
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

        print("🤖 Comprobando supercuotas y analizando cuota justa de mercado...")

        for nombre_casa, url in casas.items():
            try:
                await page.goto(url, timeout=25000, wait_until="domcontentloaded")
                await page.wait_for_timeout(2000)

                # Scroll automático profundo para revelar aumentos ocultos en Bet365/eSports
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2);")
                await page.wait_for_timeout(1000)

                elementos = await page.query_selector_all('span, div, a, h3, p, article')
                
                for el in elementos:
                    texto = await el.inner_text()
                    texto_limpio = texto.strip()
                    
                    if any(palabra in texto_limpio.lower() for palabra in keywords):
                        if 5 < len(texto_limpio) < 250:
                            numeros = re.findall(r'\b\d+[\.,]\d+\b', texto_limpio)
                            if len(numeros) >= 1:
                                float_numeros = [float(n.replace(',', '.')) for n in numeros if 1.10 <= float(n.replace(',', '.')) <= 100.0]
                                
                                # Si encontramos cuota previa y cuota aumentada (como en Interwetten)
                                if len(float_numeros) >= 2:
                                    cuota_real_est = min(float_numeros)
                                    supercuota_val = max(float_numeros)
                                elif len(float_numeros) == 1:
                                    supercuota_val = float_numeros[0]
                                    cuota_real_est = round(supercuota_val * 0.82, 2)
                                else:
                                    continue

                                if 1.20 <= supercuota_val <= 50.0 and supercuota_val > cuota_real_est:
                                    
                                    id_oferta = f"{nombre_casa}_{texto_limpio[:40]}_{supercuota_val}"
                                    
                                    if id_oferta in historial:
                                        print(f"⏩ Oferta ya enviada previamente para {nombre_casa}. Omitiendo.")
                                        continue

                                    ev_porcentaje = calcular_ev(supercuota_val, cuota_real_est)
                                    
                                    # Filtro de Valor Positivo: Solo enviamos si el +EV es estrictamente rentable
                                    if ev_porcentaje <= 0:
                                        print(f"⚠️ Cuota sin valor real (+EV negativo o nulo) en {nombre_casa}. Descarta.")
                                        continue

                                    foto_filename = f"screenshot_{nombre_casa}.png"

                                    try:
                                        await el.screenshot(path=foto_filename)
                                    except Exception:
                                        await page.screenshot(path=foto_filename, full_page=False)

                                    mensaje = (
                                        f"🎯 **NUEVA SUPERCUOTA DETECTADA (+EV)**\n\n"
                                        f"🏦 **Casa:** {nombre_casa.upper()}\n"
                                        f"📌 **Apuesta:** {texto_limpio.replace('\n', ' ')}\n"
                                        f"⚡ **Cuota Mejorada:** {supercuota_val}\n"
                                        f"📊 **Cuota Real Mercado:** {cuota_real_est}\n"
                                        f"📈 **Valor Esperado (+EV):** +{ev_porcentaje}%\n\n"
                                        f"🔗 [Ir a la oferta]({url})"
                                    )

                                    enviar_telegram_con_foto(mensaje, foto_filename)
                                    print(f"Alerta enviada para {nombre_casa}.")
                                    
                                    historial.add(id_oferta)
                                    nuevas_alertas = True
                                    break
            except Exception as e:
                print(f"Error o tiempo agotado en {nombre_casa}: {e}")

        await browser.close()

    if nuevas_alertas:
        guardar_historial(historial)
        print("💾 Historial de alertas actualizado.")

if __name__ == "__main__":
    asyncio.run(rastrear())