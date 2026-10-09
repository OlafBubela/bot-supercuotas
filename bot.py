import asyncio
import json
import os
import re
import requests
from playwright.async_api import async_playwright

token = "8777299013:AAH8-gTT-_CTw2Ht0RRXW55jsPEGFh0_OuU"
user_id = "865364645"

HISTORIAL_FILE = "alertas_enviadas.json"

casas = {
    "Paf": "https://www.paf.es/es/sportsbook",
    "Winamax": "https://www.winamax.es/apuestas-deportivas",
    "William Hill": "https://sports.williamhill.es/betting/es-es",
    "Interwetten": "https://www.interwetten.es/es/apuestas-deportivas",
    "Betway": "https://betway.es/es/sports",
    "Betfair": "https://www.betfair.es/sport/football",
    "Bwin": "https://sports.bwin.es/es/sports",
    "Casino Gran Madrid": "https://www.casinogranmadridonline.es/apuestas-deportivas/"
}

keywords = [
    'supercuota', 'cuota mejorada', 'boost', 'super cuota', 
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

        # Intercepta y bloquea multimedia pesada para acelerar la carga
        await page.route("**/*.{png,jpg,jpeg,svg,webp,mp4,woff,woff2}", lambda route: route.abort())

        print("🤖 Comprobando supercuotas y generando capturas de pantalla...")

        for nombre_casa, url in casas.items():
            try:
                await page.goto(url, timeout=20000, wait_until="domcontentloaded")
                await page.wait_for_timeout(2000)

                elementos = await page.query_selector_all('span, div, a, h3, p')
                
                for el in elementos:
                    texto = await el.inner_text()
                    texto_limpio = texto.strip()
                    
                    if any(palabra in texto_limpio.lower() for palabra in keywords):
                        if 5 < len(texto_limpio) < 180:
                            numeros = re.findall(r'\b\d+[\.,]\d+\b', texto_limpio)
                            if len(numeros) >= 1:
                                supercuota_val = float(numeros[-1].replace(',', '.'))
                                cuota_real_est = round(supercuota_val * 0.75, 2) if len(numeros) < 2 else float(numeros[0].replace(',', '.'))
                                
                                # PUNTO 4: Filtro inteligente para validar cuotas dentro de un rango realista
                                if 1.20 <= supercuota_val <= 50.0:
                                    
                                    # Identificador único para evitar duplicados
                                    id_oferta = f"{nombre_casa}_{texto_limpio}_{supercuota_val}"
                                    
                                    if id_oferta in historial:
                                        print(f"⏩ Oferta ya enviada previamente para {nombre_casa}. Omitiendo.")
                                        continue

                                    ev_porcentaje = calcular_ev(supercuota_val, cuota_real_est)
                                    foto_filename = f"screenshot_{nombre_casa}.png"

                                    # PUNTO 2: Intenta recortar solo el cuadro/elemento de la oferta
                                    try:
                                        await el.screenshot(path=foto_filename)
                                    except Exception:
                                        # Fallback en caso de que el elemento no sea directamente recortable
                                        await page.screenshot(path=foto_filename, full_page=False)

                                    mensaje = (
                                        f"🎯 **NUEVA SUPERCUOTA DETECTADA**\n\n"
                                        f"🏦 **Casa:** {nombre_casa.upper()}\n"
                                        f"📌 **Apuesta:** {texto_limpio}\n"
                                        f"⚡ **Cuota Mejorada:** {supercuota_val}\n"
                                        f"📊 **Cuota Real Estimada:** {cuota_real_est}\n"
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