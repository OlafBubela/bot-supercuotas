async def rastrear():
    historial = cargar_historial()

    async with aiohttp.ClientSession() as session:
        async with async_playwright() as p:
            log("🚀 Iniciando rastreo de Betfair vía Proxy Español...")
            
            # USO DE PROXY ESPAÑOL PARA EVITAR EL BLOQUEO 'RESTRICTED'
            # Puedes usar un servicio de proxies residenciales o un proxy público de España
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--no-sandbox',
                    '--disable-setuid-sandbox'
                ],
                # Si tienes un proxy propio (ej. BrightData, Webshare, Oxylabs, etc.), ponlo aquí:
                # proxy={"server": "http://IP_O_HOST_PROXIES:PUERTO", "username": "USUARIO", "password": "PASSWORD"}
            )

            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
                viewport={'width': 1280, 'height': 800},
                locale="es-ES",
                timezone_id="Europe/Madrid"
            )

            page = await context.new_page()

            await page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            """)

            log("🔍 Entrando a Betfair...")
            try:
                await page.goto(CONFIG_BETFAIR['url'], timeout=15000, wait_until="domcontentloaded")
                await page.wait_for_timeout(3000)

                try:
                    cookie_btn = await page.query_selector('button:has-text("Aceptar"), #onetrust-accept-btn-handler')
                    if cookie_btn:
                        await cookie_btn.click(timeout=800)
                except Exception:
                    pass

                debug_img = "debug_betfair.png"
                await page.screenshot(path=debug_img, full_page=False)
                await enviar_telegram_con_foto(session, "📸 **CONTROL BETFAIR:** Verificando acceso", debug_img)

                alerta_enviada = await escaneo_betfair(page, session, historial)
                if alerta_enviada:
                    guardar_historial(historial)

            except Exception as e:
                log(f"  ⚡ Error durante el acceso a Betfair: {e}")

            await browser.close()
            log("🏁 Proceso finalizado.")
