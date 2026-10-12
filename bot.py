"""
Bot de aumentos de cuota -> Telegram  (versión ligera: sin navegador y sin IA)

Qué hace, cada pocos minutos:
  - Descarga la página de aumentos de Paf, Interwetten y Winamax y lee los aumentos directamente.
  - Te avisa por Telegram SOLO de los nuevos (casa, competición, partido, selección,
    cuota anterior -> cuota aumentada y cuánto sube realmente la ganancia).
  - Opcional: vigila otras páginas (p. ej. Gran Casino Madrid) y avisa cuando cambian.

Instalación (móvil con Termux, servidor o PC):
    pip install requests beautifulsoup4

Variables de entorno:
    TELEGRAM_TOKEN      "8777299013:AAH8-gTT-_CTw2Ht0RRXW55jsPEGFh0_OuU"
    TELEGRAM_CHAT_ID    865364645
    AVISAR_EXISTENTES   (opcional) pon 1 para recibir también los aumentos que ya hay al arrancar

Probar un parser con un archivo guardado, sin enviar nada:
    python bot_aumentos_v3.py --probar paf archivo.html
    python bot_aumentos_v3.py --probar interwetten archivo.html
    python bot_aumentos_v3.py --probar winamax archivo.html
"""
import os
import re
import sys
import json
import time
import html as htmllib
import hashlib
import datetime as dt
from dataclasses import dataclass
from pathlib import Path

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9",
}
ESTADO_FILE = Path("estado.json")
ALERTA_ERROR_CADA_SEG = 6 * 3600


@dataclass
class Aumento:
    casa: str
    id: str
    competicion: str
    evento: str
    mercado: str
    seleccion: str
    cuota_original: float
    cuota_aumentada: float
    url: str
    inicio: str = ""          # hora de inicio del partido (si la web la da)
    apuesta_max: str = ""     # límite de apuesta (si la web lo indica)

    @property
    def pct_ganancia(self) -> float:
        """Cuánto sube la GANANCIA (no la cuota): (aumentada-1)/(original-1) - 1."""
        if self.cuota_original <= 1:
            return 0.0
        return ((self.cuota_aumentada - 1) / (self.cuota_original - 1) - 1) * 100

    @property
    def clave(self) -> str:
        return f"{self.casa}|{self.id}|{self.cuota_aumentada}"


# ----------------------------------------------------------------------------
# PARSERS (uno por casa)
# ----------------------------------------------------------------------------
def parse_paf(html: str, url: str) -> list[Aumento]:
    soup = BeautifulSoup(html, "html.parser")
    tag = soup.find("script", id="__RELAY_STORE__")
    if not tag or not tag.string:
        raise ValueError("No encuentro los datos de Paf (¿web cambiada o página de bloqueo?)")
    store = json.loads(tag.string)
    salida = []
    for nodo in store.values():
        if not isinstance(nodo, dict):
            continue
        if nodo.get("__typename") not in ("PrepackOutcomeBoostCard", "PrepackBetBoostCard"):
            continue
        if nodo.get("isSuspended"):
            continue
        try:
            antes, ahora = float(nodo["odds"]), float(nodo["boostedOdds"])
        except (KeyError, TypeError, ValueError):
            continue

        refs = (nodo.get("selections") or {}).get("__refs", [])
        textos = []
        for r in refs:
            s = store.get(r, {})
            crit = (s.get("criterion") or "").strip()
            adic = (s.get("addendum") or "").strip()
            textos.append(f"{crit} – {adic}" if adic else crit)

        def nombre(clave):
            ref = (nodo.get(clave) or {}).get("__ref")
            return (store.get(ref, {}) or {}).get("name", "") if ref else ""

        evento = nodo.get("eventName") or " - ".join(x for x in (nombre("homeParticipant"), nombre("awayParticipant")) if x)
        ids = "-".join(str(x) for x in nodo.get("outcomeIds", []))
        salida.append(Aumento(
            casa="Paf",
            id=f"{nodo.get('eventId')}:{ids}",
            competicion=nodo.get("sportIconLabel") or "",
            evento=evento or "Partido no indicado",
            mercado=f"Combinada de {len(textos)} selecciones" if len(textos) > 1 else "",
            seleccion=" + ".join(textos),
            cuota_original=antes,
            cuota_aumentada=ahora,
            url=url,
        ))
    return salida


def _num(txt: str) -> float:
    return float(txt.strip().replace(",", "."))


def parse_interwetten(html: str, url: str) -> list[Aumento]:
    soup = BeautifulSoup(html, "html.parser")
    tarjetas = soup.select("li.s-oddsboost-bet")
    salida = []
    for li in tarjetas:
        m = re.search(r"js-oddsboost-bet-(\d+)", " ".join(li.get("class", [])))
        ident = m.group(1) if m else hashlib.md5(li.get_text().encode()).hexdigest()[:10]
        cab = li.select_one(".s-oddsboost-bet-header")
        evento = (cab.get("title") or cab.get_text(" ", strip=True)) if cab else ""
        cuerpo = li.select_one(".s-oddsboost-bet-body > div")
        mercado, seleccion = "", ""
        if cuerpo:
            mercado = next((t.strip() for t in cuerpo.find_all(string=True, recursive=False) if t.strip()), "")
            pron = cuerpo.find("div")
            seleccion = re.sub(r"^Pronóstico:\s*", "", pron.get_text(" ", strip=True)) if pron else ""
        odd = li.select_one(".s-oddsboost-bet-footer-odd")
        if not odd:
            continue
        try:
            antes = _num(odd.find("span").get_text())
            ahora = _num(odd.find("strong").get_text())
        except (AttributeError, ValueError):
            continue
        salida.append(Aumento("Interwetten", ident, "", evento, mercado, seleccion, antes, ahora, url))
    if not tarjetas and "Odds Boost" not in html:
        raise ValueError("No encuentro la sección Odds Boost de Interwetten (¿web cambiada o bloqueo?)")
    return salida


def parse_winamax(html: str, url: str) -> list[Aumento]:
    pos = html.find("var PRELOADED_STATE = ")
    if pos < 0:
        raise ValueError("No encuentro los datos de Winamax (¿web cambiada o página de bloqueo?)")
    inicio = html.index("{", pos)
    st, _ = json.JSONDecoder().raw_decode(html[inicio:])

    # La sección "Supercuotas" es un deporte más dentro de los datos de la página
    deporte = next((v for v in st.get("sports", {}).values() if v.get("sportName") == "Supercuotas"), None)
    if deporte is None:
        raise ValueError("No encuentro la sección Supercuotas de Winamax (¿URL equivocada?)")

    try:
        from zoneinfo import ZoneInfo
        zona = ZoneInfo("Europe/Madrid")
    except Exception:
        zona = None

    salida = []
    for mid in deporte.get("matches", []):
        partido = st["matches"].get(str(mid))
        if not partido or not partido.get("available"):
            continue
        apuesta = st["bets"].get(str(partido.get("mainBetId")))
        if not apuesta or not apuesta.get("outcomes"):
            continue
        oid = str(apuesta["outcomes"][0])
        ahora = st["odds"].get(oid)
        antes = apuesta.get("previousOdd")
        if not ahora or not antes:
            continue
        etiqueta = (st["outcomes"].get(oid) or {}).get("label", "")
        m = re.search(r"apuesta máxima\s*([\d.,]+)\s*€", apuesta.get("betTitle", ""))
        hora = ""
        if partido.get("matchStart"):
            t = dt.datetime.fromtimestamp(partido["matchStart"], tz=zona) if zona else dt.datetime.fromtimestamp(partido["matchStart"])
            hora = t.strftime("%d/%m %H:%M")
        categoria = (st.get("categories", {}).get(str(partido.get("categoryId"))) or {}).get("categoryName", "")
        salida.append(Aumento(
            casa="Winamax",
            id=str(mid),
            competicion=categoria,
            evento=re.sub(r"^La Supercuota:\s*", "", partido.get("title", "")),
            mercado="Supercuota",
            seleccion=etiqueta,
            cuota_original=float(antes),
            cuota_aumentada=float(ahora),
            url=url,
            inicio=hora,
            apuesta_max=f"{m.group(1)} €" if m else "",
        ))
    return salida


# ----------------------------------------------------------------------------
# CONFIGURACIÓN DE FUENTES
# ----------------------------------------------------------------------------
FUENTES = [
    {"nombre": "Paf", "url": "https://www.paf.es", "parser": parse_paf, "cada": 300},
    {"nombre": "Interwetten", "url": "https://www.interwetten.es/es/apuestas-deportivas",
     "parser": parse_interwetten, "cada": 300},
    # Dirección de la sección Supercuotas de Winamax (pendiente de confirmar con la barra de direcciones)
    {"nombre": "Winamax", "url": "https://www.winamax.es/apuestas-deportivas/sports/100000",
     "parser": parse_winamax, "cada": 300},
]

# Páginas que solo se vigilan: avisan cuando el contenido cambia (sin entender el contenido).
VIGILAR = [
    # Página de "Super Cuota" del menú de promociones de apuestas (confirmar que es donde se publican)
    {"nombre": "Gran Casino Madrid", "url": "https://www.casinogranmadridonline.es/promociones/apuestas-deportivas-bonos/super-cuota", "cada": 120},
]


# ----------------------------------------------------------------------------
# TELEGRAM
# ----------------------------------------------------------------------------
def tg_enviar(texto: str) -> None:
    token, chat = os.environ["TELEGRAM_TOKEN"], os.environ["TELEGRAM_CHAT_ID"]
    r = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data={"chat_id": chat, "text": texto[:4000], "parse_mode": "HTML", "disable_web_page_preview": True},
        timeout=30,
    )
    if r.status_code != 200:
        print("Telegram error:", r.status_code, r.text[:200])


def n2(x: float) -> str:
    return f"{x:.2f}".replace(".", ",")


def formatear(a: Aumento, corto: bool = False) -> str:
    esc = htmllib.escape
    estrella = "⭐ " if a.pct_ganancia >= 25 else ""
    if corto:
        return f"• {esc(a.evento)}: {esc(a.seleccion or a.mercado)} — {n2(a.cuota_original)} → <b>{n2(a.cuota_aumentada)}</b> ({a.pct_ganancia:+.0f}%)"
    cab = f"🏦 <b>{esc(a.casa)}</b>" + (f" · {esc(a.competicion)}" if a.competicion else "")
    lineas = [cab, f"⚽ {esc(a.evento)}"]
    if a.mercado:
        lineas.append(f"📌 {esc(a.mercado)}")
    if a.seleccion:
        lineas.append(f"🎯 {esc(a.seleccion)}")
    if a.inicio:
        lineas.append(f"⏰ {esc(a.inicio)}")
    lineas.append(f"💸 {n2(a.cuota_original)} → <b>{n2(a.cuota_aumentada)}</b>")
    if a.apuesta_max:
        lineas.append(f"🔒 Apuesta máxima: {esc(a.apuesta_max)}")
    lineas.append(f"{estrella}📈 La ganancia sube un <b>{a.pct_ganancia:+.0f}%</b>")
    lineas.append(f'🔗 <a href="{esc(a.url)}">Abrir {esc(a.casa)}</a>')
    return "\n".join(lineas)


def avisar(nuevos: list[Aumento]) -> None:
    if len(nuevos) <= 5:
        for a in nuevos:
            tg_enviar(formatear(a))
        return
    # Muchos de golpe: un resumen compacto por casa para no inundar el chat
    casa = nuevos[0].casa
    for i in range(0, len(nuevos), 12):
        bloque = nuevos[i:i + 12]
        tg_enviar(f"🏦 <b>{htmllib.escape(casa)}</b>: {len(nuevos)} aumentos nuevos\n\n" + "\n".join(formatear(a, True) for a in bloque))


# ----------------------------------------------------------------------------
# ESTADO
# ----------------------------------------------------------------------------
def cargar() -> dict:
    if ESTADO_FILE.exists():
        return json.loads(ESTADO_FILE.read_text())
    return {"vistos": [], "iniciadas": [], "hashes": {}, "ultima_alerta": {}}


def guardar(est: dict) -> None:
    est["vistos"] = est["vistos"][-5000:]
    ESTADO_FILE.write_text(json.dumps(est))


def alerta_error(est: dict, nombre: str, msg: str) -> None:
    print(f"[{nombre}] {msg}")
    if time.time() - est["ultima_alerta"].get(nombre, 0) > ALERTA_ERROR_CADA_SEG:
        est["ultima_alerta"][nombre] = time.time()
        tg_enviar(f"⚠️ No puedo leer <b>{htmllib.escape(nombre)}</b>: {htmllib.escape(msg)}")


# ----------------------------------------------------------------------------
# BUCLE PRINCIPAL
# ----------------------------------------------------------------------------
def descargar(url: str) -> str:
    r = requests.get(url, headers=HEADERS, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"la web respondió con el código {r.status_code}")
    return r.text


def revisar_fuente(f: dict, est: dict) -> None:
    html = descargar(f["url"])
    aumentos = f["parser"](html, f["url"])
    vistos = set(est["vistos"])
    nuevos = [a for a in aumentos if a.clave not in vistos]
    primera_vez = f["nombre"] not in est["iniciadas"]

    est["vistos"].extend(a.clave for a in nuevos)
    if primera_vez:
        est["iniciadas"].append(f["nombre"])
        if os.environ.get("AVISAR_EXISTENTES") == "1":
            avisar(nuevos)
        else:
            tg_enviar(f"✅ <b>{htmllib.escape(f['nombre'])}</b> conectado: ahora mismo hay {len(aumentos)} aumentos. "
                      f"Te avisaré solo de los nuevos.")
    elif nuevos:
        avisar(nuevos)


def revisar_vigilada(v: dict, est: dict) -> None:
    html = descargar(v["url"])
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "svg", "noscript"]):
        t.decompose()
    texto = re.sub(r"\s+", " ", soup.get_text(" ")).strip()
    h = hashlib.md5(texto.encode()).hexdigest()
    anterior = est["hashes"].get(v["nombre"])
    est["hashes"][v["nombre"]] = h
    if anterior and anterior != h:
        tg_enviar(f"👀 <b>{htmllib.escape(v['nombre'])}</b>: la página ha cambiado, puede haber un aumento nuevo.\n"
                  f'🔗 <a href="{htmllib.escape(v["url"])}">Abrir</a>')


def main() -> None:
    est = cargar()
    tareas = [(f, revisar_fuente) for f in FUENTES] + [
        (v, revisar_vigilada) for v in VIGILAR if v["url"] != "PEGA_AQUI"
    ]
    proxima = {t[0]["nombre"]: 0.0 for t in tareas}
    print("Bot en marcha. Fuentes:", ", ".join(proxima))
    while True:
        ahora = time.time()
        for cfg, fn in tareas:
            if ahora < proxima[cfg["nombre"]]:
                continue
            proxima[cfg["nombre"]] = ahora + cfg["cada"]
            try:
                fn(cfg, est)
            except Exception as e:
                alerta_error(est, cfg["nombre"], str(e))
            guardar(est)
        time.sleep(15)


def probar(casa: str, archivo: str) -> None:
    parsers = {"paf": parse_paf, "interwetten": parse_interwetten, "winamax": parse_winamax}
    html = Path(archivo).read_text(encoding="utf-8", errors="ignore")
    lista = parsers[casa.lower()](html, "https://ejemplo")
    print(f"{len(lista)} aumentos encontrados\n")
    for a in lista:
        print(f"[{a.competicion or '-'}] {a.evento} | {a.mercado or '-'} | {a.seleccion} | "
              f"{a.cuota_original} -> {a.cuota_aumentada} ({a.pct_ganancia:+.0f}%) {a.inicio} {a.apuesta_max}")


if __name__ == "__main__":
    if len(sys.argv) >= 4 and sys.argv[1] == "--probar":
        probar(sys.argv[2], sys.argv[3])
    else:
        main()
