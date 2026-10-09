import requests 
from bs4 import BeautifulSoup

token = "8777299013:AAH8-gTT-_CTw2Ht0RRXW55jsPEGFh0_OuU" 
user_id = "865364645" 
headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

casas = { 
    "Winamax": "https://www.winamax.es/apuestas-deportivas", 
    "Paf": "https://www.paf.es/en/sportsbook", 
    "William Hill": "https://sports.williamhill.es/betting/es-es", 
    "Interwetten": "https://www.interwetten.es/es/apuestas-deportivas" 
}
keywords = ['supercuota', 'cuota mejorada', 'boost', 'super cuota', 'megacuota', 'aumento de cuota']

print("🤖 Comprobando supercuotas...")

for nombre_casa, url in casas.items(): 
    try: 
        res = requests.get(url, headers=headers, timeout=10) 
        soup = BeautifulSoup(res.text, 'html.parser')

        promociones = []
        for elemento in soup.find_all(['span', 'div', 'a', 'h3']):
            texto = elemento.get_text(strip=True)
            if any(palabra in texto.lower() for palabra in keywords):
                if texto not in promociones and len(texto) < 150:
                    promociones.append(texto)

        if promociones:
            mensaje = f"🔥 **SUPERCUOTAS DETECTADAS EN {nombre_casa.upper()}** 🔥\n\n" + "\n---\n".join(promociones[:5])
            url_tg = f"https://api.telegram.org/bot{token}/sendMessage"
            requests.post(url_tg, json={"chat_id": user_id, "text": mensaje, "parse_mode": "Markdown"})
            print(f"Alerta enviada para {nombre_casa}.")
        else:
            print(f"{nombre_casa}: sin supercuotas activas.")

    except Exception as e:
        print(f"Error en {nombre_casa}: {e}")
