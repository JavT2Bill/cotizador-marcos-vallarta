#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Descarga imágenes de molduras desde marcosymarcos.mx y genera data/molduras_scraped.json
- Guarda imágenes en: img/molduras/<SKU>.jpg
- Si no hay SKU, usa el slug de la URL como id
- Intenta detectar ancho en cm del título (p. ej. "3.0 cm")
- color/style heurísticos por palabras clave (sirven como fallback)
"""

import os, re, json, time
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup as BS

BASE = "https://www.marcosymarcos.mx/"
CATEGORIAS = [
    "https://www.marcosymarcos.mx/categoria/molduras/poliestireno/",
    # Agrega más categorías si quieres cubrir todo
    # "https://www.marcosymarcos.mx/categoria/molduras/",
]

OUT_DIR = "img/molduras"
DATA_DIR = "data"
OUT_JSON = os.path.join(DATA_DIR, "molduras_scraped.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
}

os.makedirs(OUT_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

def get_soup(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return BS(r.text, "lxml")

def slug_from_url(url):
    path = urlparse(url).path.strip("/").split("/")
    return (path[-1] or "producto").upper().replace("-", "_")

def clean_id(text):
    text = (text or "").strip().upper()
    # Deja letras, números y guiones/guiones bajos
    text = re.sub(r"[^A-Z0-9_-]+", "", text)
    return text or None

def parse_width_cm(text):
    if not text: return None
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*cm", text, re.I)
    if not m: return None
    v = m.group(1).replace(",", ".")
    try:
        return float(v)
    except:
        return None

def guess_style_and_color(name):
    """Heurística simple para fallback de textura/color."""
    t = (name or "").lower()
    style = "grain"
    color = "#555555"
    mapc = {
        "negro": "#111111",
        "blanco": "#f5f5f5",
        "nogal": "#6b3f21",
        "caoba": "#7a3b1f",
        "chocolate": "#4b2b1a",
        "natural": "#c9b18c",
        "maple": "#e0b977",
        "wengue": "#3a2a1a",
        "roble": "#916c44",
        "azul": "#1f3a5a",
        "gris": "#777777",
        "plata": "#c0c0c0",
        "dorado": "#c7a446",
        "oro": "#c7a446",
        "bronce": "#8c6b3f",
        "marfil": "#f0eee6",
    }
    for k, v in mapc.items():
        if k in t:
            color = v
            break
    if any(k in t for k in ["plata", "dorado", "oro", "bronce", "metal"]):
        style = "metal"
    return style, color

def find_product_links(cat_url):
    seen = set()
    url = cat_url
    while url:
        soup = get_soup(url)
        # WooCommerce típico
        for a in soup.select("ul.products li.product a.woocommerce-LoopProduct-link"):
            href = urljoin(BASE, a.get("href"))
            seen.add(href)
        # fallback general
        for a in soup.select('a[href*="/producto/"]'):
            href = urljoin(BASE, a.get("href"))
            seen.add(href)
        # paginación
        nxt = soup.select_one('a.next, a[rel="next"]')
        url = urljoin(BASE, nxt.get("href")) if nxt else None
        time.sleep(0.6)  # amable con el servidor
    return sorted(seen)

def extract_product(url):
    soup = get_soup(url)
    title_el = soup.select_one("h1.product_title, h1.entry-title")
    title = title_el.get_text(" ", strip=True) if title_el else slug_from_url(url)

    sku_el = soup.select_one("span.sku, .sku, .product_meta .sku")
    sku = clean_id(sku_el.get_text(strip=True) if sku_el else None)
    if not sku:
        sku = clean_id(slug_from_url(url))

    # imagen principal
    img_url = None
    og = soup.select_one('meta[property="og:image"]')
    if og and og.get("content"):
        img_url = urljoin(BASE, og["content"])
    if not img_url:
        g = soup.select_one(".woocommerce-product-gallery__image img")
        if g and (g.get("data-large_image") or g.get("src")):
            img_url = urljoin(BASE, g.get("data-large_image") or g.get("src"))
    if not img_url:
        wpi = soup.select_one("img.wp-post-image")
        if wpi and wpi.get("src"):
            img_url = urljoin(BASE, wpi["src"])

    width_cm = parse_width_cm(title)
    style, color = guess_style_and_color(title)

    return {
        "id": sku,
        "name": title,
        "width_cm": width_cm,
        "color": color,
        "style": style,
        "img_url": img_url
    }

def download_image(url, path):
    if not url:
        return False
    try:
        r = requests.get(url, headers=HEADERS, timeout=40)
        r.raise_for_status()
        with open(path, "wb") as f:
            f.write(r.content)
        return True
    except Exception as e:
        print("No se pudo bajar", url, e)
        return False

def main():
    products = {}
    for cat in CATEGORIAS:
        print("Categoría:", cat)
        for purl in find_product_links(cat):
            try:
                data = extract_product(purl)
                pid = data["id"]
                if not pid:
                    continue
                if pid in products:
                    continue
                print(" -", pid, data["name"])
                # guarda imagen
                img_path = os.path.join(OUT_DIR, f"{pid}.jpg")
                ok = download_image(data["img_url"], img_path)
                # arma registro
                rec = {
                    "id": pid,
                    "name": data["name"],
                    "width_cm": data["width_cm"],
                    "color": data["color"],
                    "style": data["style"],
                    "img": img_path.replace("\\", "/") if ok else None
                }
                products[pid] = rec
                time.sleep(0.6)
            except Exception as e:
                print("Error en", purl, e)

    out = list(products.values())
    # genera JSON (no pisa data/molduras.json existente)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("Listo:", OUT_JSON, "=>", len(out), "molduras")

if __name__ == "__main__":
    main()
