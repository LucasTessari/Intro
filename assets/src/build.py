"""Gera os SVGs de assets/ a partir dos modelos em assets/src/.

Imagens SVG exibidas pelo GitHub não podem carregar fontes externas, então
este script baixa as fontes do Google Fonts, recorta só os caracteres usados
e embute tudo (em WOFF2/base64) dentro de cada SVG.

Uso:
    pip install fonttools brotli
    python assets/src/build.py

Para mudar um texto, edite o modelo em assets/src/<nome>.svg e rode de novo.
"""

import base64
import io
import pathlib
import re
import urllib.request

from fontTools import subset
from fontTools.ttLib import TTFont

SRC = pathlib.Path(__file__).resolve().parent
OUT = SRC.parent
CACHE = SRC / ".fonts"

# família usada nos modelos -> (consulta do Google Fonts, peso CSS)
FONTS = {
    "LTG Mono": [("IBM+Plex+Mono:wght@400", 400), ("IBM+Plex+Mono:wght@600", 600)],
    "LTG Cond": [("Archivo:wdth,wght@75,700", 700)],
    "LTG XCond": [("Archivo:wdth,wght@62.5,800", 800)],
}

PLACEHOLDER = "/*FONTS*/"


def fetch_ttf(query):
    CACHE.mkdir(exist_ok=True)
    cached = CACHE / (re.sub(r"[^A-Za-z0-9]+", "_", query) + ".ttf")
    if cached.exists():
        return cached.read_bytes()
    css_url = f"https://fonts.googleapis.com/css2?family={query}"
    # Sem user agent de navegador moderno o Google Fonts devolve TTF.
    req = urllib.request.Request(css_url, headers={"User-Agent": "Mozilla/5.0"})
    css = urllib.request.urlopen(req).read().decode()
    ttf_url = re.search(r"url\((https://[^)]+\.ttf)\)", css).group(1)
    data = urllib.request.urlopen(ttf_url).read()
    cached.write_bytes(data)
    return data


def subset_woff2(ttf_bytes, chars):
    font = TTFont(io.BytesIO(ttf_bytes))
    options = subset.Options()
    options.flavor = "woff2"
    options.hinting = False
    options.layout_features = ["kern", "liga"]
    options.name_IDs = []
    subsetter = subset.Subsetter(options)
    subsetter.populate(text=chars)
    subsetter.subset(font)
    buf = io.BytesIO()
    font.save(buf)
    return base64.b64encode(buf.getvalue()).decode()


def text_of(svg):
    # Conteúdo dos elementos <text>/<tspan>, sem as tags.
    inner = re.findall(r"<text[^>]*>(.*?)</text>", svg, flags=re.S)
    plain = re.sub(r"<[^>]+>", "", "".join(inner))
    for entity, char in (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">")):
        plain = plain.replace(entity, char)
    return plain


def main():
    templates = sorted(SRC.glob("*.svg"))
    chars = "".join(sorted(set("".join(text_of(t.read_text()) for t in templates)) | {" "}))

    faces = {}
    for family, variants in FONTS.items():
        rules = []
        for query, weight in variants:
            data = subset_woff2(fetch_ttf(query), chars)
            rules.append(
                f"@font-face{{font-family:'{family}';font-weight:{weight};"
                f"src:url(data:font/woff2;base64,{data}) format('woff2')}}"
            )
        faces[family] = "".join(rules)

    for template in templates:
        svg = template.read_text()
        used = "".join(css for family, css in faces.items() if f"'{family}'" in svg)
        out = OUT / template.name
        out.write_text(svg.replace(PLACEHOLDER, used))
        print(f"{out.relative_to(OUT.parent)}  {out.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    main()
