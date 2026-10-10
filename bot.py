import asyncio
import os
import time
import aiohttp
from playwright.async_api import async_playwright

token = "8777299013:AAH8-gTT-_CTw2Ht0RRXW55jsPEGFh0_OuU"
user_id = "865364645"

def log(mensaje):
    print(f"[{time.strftime('%H:%M:%S')}] {mensaje}", flush=True)

async def enviar_telegram(session, mensaje, ruta_imagen=None):
    if ruta_imagen and os.path.exists(ruta_imagen):
        url = f"https://api.telegram.org/bot{token}/sendPhoto"
        data = aiohttp.FormData()
        data.add_field('chat_id', user_id)
        data.add_field('caption', mensaje)
        data.add_field('photo', open(ruta_imagen, 'rb'), filename='debug.png')
        try:
            async with session.post(url, data=data, timeout=aiohttp.ClientTimeout(total=10)):
                pass
            log("  ✅ Foto enviada a Telegram con éxito.")
            return
        except Exception as e:
            log(f"  ❌ Error enviando foto: {e}")

async def test_betfair():
    async with aiohttp.ClientSession() as session:
        async with async_playwright() as p:
            log("🚀 Lanzando navegador directo a Betfair...")
            browser = await p.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox']
            )
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
                viewport={'width': 1280, 'height': 800}
            )

            page = await context.new_page()

            # Bloquear recursos pesados para que cargue al instante
            await page.route("**/*.{png,jpg,jpeg,svg,gif,webp,ttf,woff,woff2}", lambda route: route.abort())

            try:
                log("🔍 Navegando a https://www.betfair.es/sport/...")
                # Cargar solo el HTML inicial sin esperar a la red
                await page.goto("https://www.betfair.es/sport/", timeout=15000, wait_until="domcontentloaded")
                await page.wait_for_timeout(3000)

                # Intentar cerrar banner de cookies si existe
                try:
                    cookie_btn = await page.query_selector('button:has-text("Aceptar"), #onetrust-accept-btn-handler')
                    if cookie_btn:
                        await cookie_btn.click()
                        await page.wait_for_timeout(1000)
                except Exception:
                    pass

                debug_img = "debug_betfair.png"
                await page.screenshot(path=debug_img, full_page=False)
                log("📸 Captura de Betfair guardada.")

                await enviar_telegram(session, "📸 **DIAGNÓSTICO BETFAIR DIRECTO**\nEsto es lo que ve el servidor:", debug_img)

            except Exception as e:
                log(f"❌ Error al cargar Betfair: {e}")
            finally:
                await browser.close()
                log("🏁 Fin de la prueba.")

if __name__ == "__main__":
    asyncio.run(test_betfair())
