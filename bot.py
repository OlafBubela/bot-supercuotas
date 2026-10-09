import asyncio
import re
import requests
from playwright.async_api import async_playwright

token = "8777299013:AAH8-gTT-_CTw2Ht0RRXW55jsPEGFh0_OuU"
user_id = "865364645"

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
    'superaumento', 'mejorada', 'especiales', 'superprecio'
]

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
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        print("🤖 Comprobando supercuotas y generando capturas de pantalla...")

        for nombre_casa, url in casas.items():
            try:
                await page.goto(url, timeout=25000, wait_until="domcontentloaded")
                await page.wait_for_timeout(3000)  # Esperar a que carguen las cuotas dinámicas

                # Extraer texto de la página
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
                                
                                if supercuota_val > 1.0:
                                    ev_porcentaje = calcular_ev(supercuota_val, cuota_real_est)
                                    
                                    # Tomar captura de pantalla de la casa
                                    foto_filename = f"screenshot_{nombre_casa}.png"
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
                                    print(f"Alerta con foto enviada para {nombre_casa}.")
                                    break
            except Exception as e:
                print(f"Error procesando {nombre_casa}: {e}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(rastrear())