import asyncio
import json
import os
import re
import time
import aiohttp
from playwright.async_api import async_playwright

# Configuración de Telegram
token = "8777299013:AAH8-gTT-_CTw2Ht0RRXW55jsPEGFh0_OuU"
user_id = "865364645"

HISTORIAL_FILE = "alertas_enviadas.json"
SCREENSHOT_PATH = "oferta_detectada.png"

CONFIG_CASAS = {
    "Bet365 Deportes": {
        "url": "https://www.bet365.es/#/HO/",
        "keywords": ["superaumento"],
        "blacklist": ["parlay", "combinada", "crea tu apuesta", "aumento de parlay"],
        "wh_search": False
    },
    "William Hill": {
        "url": "https://sports.williamhill.es/betting/es-es",
        "keywords": ["épica", "insuperable", "cuota épica", "cuotas épicas"],
        "blacklist": ["crea tu apuesta", "combinada", "3 o más"],
        "wh_search": True,
        "search_terms": ["épica", "insuperable"]
    },
    "Winamax": {
        "url": "https://www.winamax.es/apuestas-deportivas",
        "keywords": ["gran supercuota", "supercuota"],
        "blacklist": ["mymatch", "combinada"],
        "wh_search": False
    },
    "Casino Gran Madrid": {
        "url": "https://www.casinogranmadridonline.es/apuestas-deportivas/",
        "keywords": ["apuesta del día", "apuestas del día"],
        "blacklist": ["combinada"],
        "wh_search": False
    },
    "Betfair": {
        "url": "https://www.betfair.es/sport/football",
        "keywords": ["supercuota"],
        "blacklist": ["combipartido", "combinada"],
        "wh_search": False
    },
    "Paf": {
        "url": "https://www.paf.es/es/sportsbook",
        "keywords": ["cuotas mejoradas", "cuota mejorada"],
        "blacklist": ["combinada", "crea tu apuesta"],
        "wh_search": False
    },
    "Betway": {
        "url": "https://betway.es/es/esports",
        "keywords": ["mega cuota", "megacuota"],
        "blacklist": ["combinada"],
        "wh_search": False
    },
    "Interwetten": {
        "url": "https://www.interwetten.es/es/apuestas-deportivas",
        "keywords": ["supercuota", "megacuota"],
        "blacklist": ["combinada"],
        "wh_search": False
    },
    "Bwin": {
        "url": "https://sports.bwin.es/es/sports",
        "keywords": ["supercuota", "precio mejorado"],
        "blacklist": ["build a bet", "combinada"],
        "wh_search": False
    }
}

def log(mensaje):
    timestamp = time.strftime("%H:%M:%S")
    print(f"[{timestamp}] {mensaje}", flush=True)

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

def calcular_ev(supercuota, cuota_referencia_base):
    if cuota_referencia_base <= 1.0:
        return 0.0
    probabilidad_real = 1 / cuota_referencia_base
    ev = (probabilidad_real * supercuota) - 1
    return round(ev * 100, 2)

async def enviar_telegram_con_foto(session, mensaje, ruta_imagen=None):
    if ruta_imagen and os.path.exists(ruta_imagen):
        url = f"https://api.telegram.org/bot{token}/sendPhoto"
        data = aiohttp.FormData()
        data.add_field('chat_id', user_id)
        data.add_field('caption', mensaje)
        data.add_field('parse_mode', 'Markdown')
        data.add_field('photo', open(ruta_imagen, 'rb'), filename='oferta.png')
        try:
            async with session.post(url, data=data, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                pass
            os.remove(ruta_imagen)
            return
        except Exception as e:
            log(f"Error enviando foto a Telegram: {e}")

    url_text = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {'chat_id': user_id, 'text': mensaje, 'parse_mode': 'Markdown'}
    try:
        async with session.post(url_text, json=payload, timeout=aiohttp.ClientTimeout(total=5)) as resp:
            pass
    except Exception as e:
        log(f"Error enviando mensaje a Telegram: {e}")

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

async def escaneo_elementos_pagina(page, session, nombre_casa, config, historial):
    nuevas = False
    keywords = config["keywords"]
    blacklist = config["blacklist"]

    try:
        if "bet365" in nombre_casa.lower():
            try:
                await page.wait_for_selector('div, article, section', timeout=4000)
                await page.evaluate("window.scrollBy(0, 250);")
                await page.wait_for_timeout(1500)
            except Exception:
                pass

        elementos = await page.query_selector_all('article, section, div[class*="boost"], div[class*="promo"], div[class*="offer"], div')
        
        for el in elementos:
            try:
                texto = await el.inner_text()
                texto_limpio = texto.strip()
                texto_lower = texto_limpio.lower()
                
                # 1. Filtro estricto por nombres reales de la casa
                if any(kw in texto_lower for kw in keywords):
                    # 2. Descartar si incluye términos de combinadas/creador de apuestas
                    if any(bl in texto_lower for bl in blacklist):
                        continue

                    if 5 < len(texto_limpio) < 200:
                        cuotas = extraer_cuotas_limpias(texto_limpio)

                        if len(cuotas) >= 1:
                            supercuota_val = max(cuotas)
                            cuota_referencia = min(cuotas) if len(cuotas) > 1 else round(supercuota_val * 0.8, 2)

                            texto_resumen = texto_limpio[:50].replace('\n', ' ')
                            log(f"  📌 Oferta real detectada en {nombre_casa}: '{texto_resumen}...' | Cuota: {supercuota_val}")

                            id_oferta = f"{nombre_casa}_{texto_limpio[:20]}_{supercuota_val}"
                            
                            if id_oferta in historial:
                                log(f"