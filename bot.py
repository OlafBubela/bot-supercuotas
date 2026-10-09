import requests
from bs4 import BeautifulSoup
import re

token = "8777299013:AAH8-gTT-_CTw2Ht0RRXW55jsPEGFh0_OuU"
user_id = "865364645"
odds_api_key = "23fbe34384f88b2bf502bc977f1bb24f"

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8"
}

casas = {
    "Paf": "https://www.paf.es/es/sportsbook",
    "Winamax": "https://www.winamax.es/apuestas-deportivas",
    "William Hill": "https://sports.williamhill.es/betting/es-es",
    "Interwetten": "https://www.interwetten.es/es/apuestas-deportivas"
}

keywords = ['supercuota', 'cuota mejorada', 'boost', 'super cuota', 'megacuota', 'aumento de cuota', 'mejorada', 'especiales']

def obtener_cuota_pinnacle(deporte="soccer_spain_liga"):
    url = f"https://api.the-odds-api.com/v4/sports/{deporte}/odds/"
    params = {
        'apiKey': odds_api_key,
        'regions': 'eu',
        'markets': 'h2h',
        'bookmakers': 'pinnacle'
    }
    try:
        res = requests.get(url, params=params, timeout=10)
        if res.status_code == 200:
            return res.json()
    except Exception as e:
        print(f"Error consultando Odds API: {e}")
    return None

def calcular_ev(supercuota, cuota_justa):
    probabilidad_real = 1 / cuota_justa
    ev = (probabilidad_real * supercuota) - 1
    return round(ev * 100, 2)

print("🤖 Comprobando supercuotas y analizando promociones...")

for nombre_casa, url in casas.items():
    try:
        res = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')

        promociones = []
        for elemento in soup.find_all(['span', 'div', 'a', 'h3', 'p']):
            texto = elemento.get_text(strip=True)
            if any(palabra in texto.lower() for palabra in keywords):
                if texto not in promociones and 5 < len(texto) < 180:
                    numeros = re.findall(r'\b\d+[\.,]\d+\b', texto)
                    if numeros:
                        try:
                            supercuota_val = float(numeros[-1].replace(',', '.'))
                            if supercuota_val > 1.0:
                                cuota_mercado_estimada = supercuota_val * 0.75
                                ev_porcentaje = calcular_ev(supercuota_val, cuota_mercado_estimada)
                                texto_ev = f"{texto} ⚡ (Cuota: {supercuota_val} | Est. +EV: +{ev_porcentaje}%)"
                                promociones.append(texto_ev)
                            else:
                                promociones.append(texto)
                        except Exception:
                            promociones.append(texto)
                    else:
                        promociones.append(texto)

        if promociones:
            mensaje = f"🔥 **OFERTAS / SUPERCUOTAS EN {nombre_casa.upper()}** 🔥\n\n" + "\n---\n".join(promociones[:5])
            url_tg = f"https://api.telegram.org/bot{token}/sendMessage"
            requests.post(url_tg, json={"chat_id": user_id, "text": mensaje, "parse_mode": "Markdown"})
            print(f"Alerta enviada para {nombre_casa}.")
        else:
            print(f"{nombre_casa}: sin supercuotas detectadas.")

    except Exception as e:
        print(f"Error en {nombre_casa}: {e}")