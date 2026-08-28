from flask import Flask, request, jsonify
from playwright.sync_api import sync_playwright
import os
import re
import traceback


app = Flask(__name__)


MATEUS_URL = "https://mateusmais.com.br/loja/supermercado-mateus-cohama"


# =========================================================
# PREFERÊNCIAS
# =========================================================

def parse_preferencias(texto):

    if not texto:
        return []

    partes = [
        p.strip()
        for p in texto.split(";")
        if p.strip()
    ]

    preferencias = []

    for parte in partes:

        match = re.search(
            r"(.+?)\s+at[eé]\s+R?\$?\s*([\d,.]+)",
            parte,
            re.IGNORECASE
        )

        if match:

            termo = match.group(1).strip()

            limite = (
                match
                .group(2)
                .replace(".", "")
                .replace(",", ".")
            )

            try:
                limite = float(limite)
            except Exception:
                limite = None

            preferencias.append(
                {
                    "termo": termo,
                    "limite": limite
                }
            )

        else:

            preferencias.append(
                {
                    "termo": parte,
                    "limite": None
                }
            )

    return preferencias


# =========================================================
# PREÇO
# =========================================================

def extrair_preco(texto):

    if not texto:
        return None

    match = re.search(
        r"R\$\s*([\d.]+,\d{2})",
        texto
    )

    if not match:
        return None

    valor = (
        match
        .group(1)
        .replace(".", "")
        .replace(",", ".")
    )

    try:
        return float(valor)
    except Exception:
        return None


# =========================================================
# NAVEGADOR
# =========================================================

def criar_browser(playwright):

    return playwright.chromium.launch(
        headless=True,
        args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-setuid-sandbox"
        ]
    )


def criar_pagina(browser):

    return browser.new_page(
        viewport={
            "width": 1440,
            "height": 900
        },
        locale="pt-BR"
    )


# =========================================================
# ABRIR MATEUS
# =========================================================

def abrir_mateus(page):

    page.goto(
        MATEUS_URL,
        wait_until="domcontentloaded",
        timeout=60000
    )

    page.wait_for_timeout(
        3500
    )

    return {
        "titulo": page.title(),
        "url": page.url
    }


# =========================================================
# PESQUISA VISUAL
# =========================================================

def executar_busca(
    page,
    termo
):

    abrir_mateus(
        page
    )

    campo_busca = page.locator(
        "#search-autocomplete-input"
    )

    campo_busca.wait_for(
        state="visible",
        timeout=30000
    )

    campo_busca.fill(
        termo
    )

    page.wait_for_timeout(
        700
    )

    campo_busca.press(
        "Enter"
    )

    page.wait_for_timeout(
        4000
    )

    return {
        "termo": termo,
        "titulo": page.title(),
        "url": page.url
    }


# =========================================================
# COLETAR PRODUTOS DA PÁGINA
# =========================================================

def coletar_produtos(page):

    produtos = []

    links = page.locator(
        'a[href*="/produtos/"]'
    )

    total = min(
        links.count(),
        30
    )

    vistos = set()

    for i in range(total):

        link = links.nth(i)

        try:

            href = (
                link.get_attribute(
                    "href"
                ) or ""
            )

            if not href:
                continue

            if href in vistos:
                continue

            if "/cliente-mateus-mais/" in href:
                continue

            vistos.add(href)

            texto_link = ""

            try:
                texto_link = (
                    link.inner_text(
                        timeout=1500
                    ) or ""
                ).strip()
            except Exception:
                pass

            pai_texto = ""

            try:
                pai_texto = (
                    link
                    .locator("xpath=..")
                    .inner_text(
                        timeout=1500
                    ) or ""
                ).strip()
            except Exception:
                pass

            avo_texto = ""

            try:
                avo_texto = (
                    link
                    .locator("xpath=../..")
                    .inner_text(
                        timeout=1500
                    ) or ""
                ).strip()
            except Exception:
                pass

            contexto = "\n".join(
                [
                    texto_link,
                    pai_texto,
                    avo_texto
                ]
            ).strip()

            linhas = [
                linha.strip()
                for linha in contexto.split("\n")
                if linha.strip()
            ]

            nome = ""

            for linha in linhas:

                linha_lower = linha.lower()

                if (
                    not linha.startswith("R$")
                    and "adicionar" not in linha_lower
                    and "comprar" not in linha_lower
                    and len(linha) > 3
                ):
                    nome = linha
                    break

            preco = extrair_preco(
                contexto
            )

            produtos.append(
                {
                    "nome": nome,
                    "preco": preco,
                    "texto_bruto": contexto[:800],
                    "href": href
                }
            )

        except Exception:
            pass

    return produtos


# =========================================================
# HOME
# =========================================================

@app.route(
    "/",
    methods=["GET"]
)
def home():

    return jsonify(
        {
            "status": "online",
            "servico": "Agente Lista de Compras",
            "mercado": "Mateus Cohama",
            "rotas": [
                "/",
                "/teste",
                "/diagnostico",
                "/buscar?q=arroz",
                "/capturar-api?q=arroz",
                "/descobrir-busca?q=arroz",
                "/executar-compra"
            ]
        }
    )


# =========================================================
# TESTE
# =========================================================

@app.route(
    "/teste",
    methods=["GET"]
)
def teste():

    try:

        with sync_playwright() as p:

            browser = criar_browser(p)

            page = criar_pagina(
                browser
            )

            dados_site = abrir_mateus(
                page
            )

            browser.close()

        return jsonify(
            {
                "status": "ok",
                "titulo": dados_site["titulo"],
                "url": dados_site["url"]
            }
        )

    except Exception as e:

        return jsonify(
            {
                "status": "erro",
                "erro": str(e),
                "trace": traceback.format_exc()
            }
        ), 500


# =========================================================
# DIAGNÓSTICO LEVE
# =========================================================

@app.route(
    "/diagnostico",
    methods=["GET"]
)
def diagnostico():

    try:

        with sync_playwright() as p:

            browser = criar_browser(p)

            page = criar_pagina(
                browser
            )

            abrir_mateus(
                page
            )

            page.wait_for_timeout(
                1500
            )

            candidatos = []

            inputs = page.locator(
                "input"
            )

            total = inputs.count()

            for i in range(
                min(total, 20)
            ):

                el = inputs.nth(i)

                candidatos.append(
                    {
                        "indice":
                            i,

                        "placeholder":
                            el.get_attribute(
                                "placeholder"
                            ) or "",

                        "name":
                            el.get_attribute(
                                "name"
                            ) or "",

                        "type":
                            el.get_attribute(
                                "type"
                            ) or "",

                        "id":
                            el.get_attribute(
                                "id"
                            ) or "",

                        "aria_label":
                            el.get_attribute(
                                "aria-label"
                            ) or ""
                    }
                )

            titulo = page.title()

            url = page.url

            browser.close()

        return jsonify(
            {
                "status": "ok",
                "titulo": titulo,
                "url": url,
                "quantidade_inputs": total,
                "inputs": candidatos
            }
        )

    except Exception as e:

        return jsonify(
            {
                "status": "erro",
                "erro": str(e),
                "trace": traceback.format_exc()
            }
        ), 500


# =========================================================
# BUSCA REAL
# =========================================================

@app.route(
    "/buscar",
    methods=["GET"]
)
def buscar():

    termo = request.args.get(
        "q",
        "arroz"
    ).strip()

    if not termo:

        return jsonify(
            {
                "status": "erro",
                "mensagem":
                    "Informe um produto para pesquisar."
            }
        ), 400

    try:

        with sync_playwright() as p:

            browser = criar_browser(p)

            page = criar_pagina(
                browser
            )

            resultado = executar_busca(
                page,
                termo
            )

            produtos = coletar_produtos(
                page
            )

            resultado[
                "quantidade_produtos_detectados"
            ] = len(produtos)

            resultado[
                "produtos"
            ] = produtos[:20]

            browser.close()

        return jsonify(
            {
                "status": "ok",
                "resultado": resultado
            }
        )

    except Exception as e:

        return jsonify(
            {
                "status": "erro",
                "erro": str(e),
                "trace": traceback.format_exc()
            }
        ), 500


# =========================================================
# CAPTURAR API
# =========================================================

@app.route(
    "/capturar-api",
    methods=["GET"]
)
def capturar_api():

    termo = request.args.get(
        "q",
        "arroz"
    ).strip()

    try:

        chamadas = []

        respostas = []

        with sync_playwright() as p:

            browser = criar_browser(p)

            page = criar_pagina(
                browser
            )

            def registrar_request(req):

                try:

                    if req.resource_type in [
                        "xhr",
                        "fetch"
                    ]:

                        chamadas.append(
                            {
                                "tipo":
                                    req.resource_type,

                                "metodo":
                                    req.method,

                                "url":
                                    req.url
                            }
                        )

                except Exception:
                    pass


            def registrar_response(resp):

                try:

                    req = resp.request

                    if req.resource_type not in [
                        "xhr",
                        "fetch"
                    ]:
                        return

                    content_type = (
                        resp.headers.get(
                            "content-type",
                            ""
                        )
                    )

                    registro = {
                        "status":
                            resp.status,

                        "url":
                            resp.url,

                        "content_type":
                            content_type
                    }

                    if (
                        "application/json"
                        in content_type
                    ):

                        try:

                            dados = resp.json()

                            registro[
                                "amostra"
                            ] = str(
                                dados
                            )[:2000]

                        except Exception:
                            pass

                    respostas.append(
                        registro
                    )

                except Exception:
                    pass


            page.on(
                "request",
                registrar_request
            )

            page.on(
                "response",
                registrar_response
            )

            abrir_mateus(
                page
            )

            chamadas.clear()
            respostas.clear()

            campo = page.locator(
                "#search-autocomplete-input"
            )

            campo.wait_for(
                state="visible",
                timeout=30000
            )

            campo.fill(
                termo
            )

            page.wait_for_timeout(
                500
            )

            campo.press(
                "Enter"
            )

            page.wait_for_timeout(
                5000
            )

            browser.close()

        palavras = [
            "product",
            "produto",
            "search",
            "busca",
            "catalog",
            "catalogo",
            "graphql",
            "sku",
            "offer",
            "price",
            "pricing",
            "market"
        ]

        candidatos = []

        for resposta in respostas:

            url_lower = (
                resposta
                .get(
                    "url",
                    ""
                )
                .lower()
            )

            if any(
                palavra in url_lower
                for palavra in palavras
            ):

                candidatos.append(
                    resposta
                )

        return jsonify(
            {
                "status": "ok",
                "termo": termo,
                "total_chamadas": len(
                    chamadas
                ),
                "total_respostas": len(
                    respostas
                ),
                "candidatos":
                    candidatos[:30],
                "todas_respostas":
                    respostas[:50]
            }
        )

    except Exception as e:

        return jsonify(
            {
                "status": "erro",
                "erro": str(e),
                "trace": traceback.format_exc()
            }
        ), 500


# =========================================================
# DESCOBRIR FORMATO DA BUSCA
# =========================================================

@app.route(
    "/descobrir-busca",
    methods=["GET"]
)
def descobrir_busca():

    termo = request.args.get(
        "q",
        "arroz"
    ).strip()

    try:

        requests_capturados = []

        with sync_playwright() as p:

            browser = criar_browser(p)

            page = criar_pagina(
                browser
            )

            def registrar_request(req):

                try:

                    url = req.url.lower()

                    if (
                        "api/products/internal/v1/service"
                        not in url
                    ):
                        return

                    headers = req.headers

                    registro = {
                        "url":
                            req.url,

                        "metodo":
                            req.method,

                        "resource_type":
                            req.resource_type,

                        "post_data":
                            req.post_data,

                        "content_type":
                            headers.get(
                                "content-type",
                                ""
                            ),

                        "accept":
                            headers.get(
                                "accept",
                                ""
                            ),

                        "referer":
                            headers.get(
                                "referer",
                                ""
                            ),

                        "origin":
                            headers.get(
                                "origin",
                                ""
                            )
                    }

                    requests_capturados.append(
                        registro
                    )

                except Exception:
                    pass


            page.on(
                "request",
                registrar_request
            )

            abrir_mateus(
                page
            )

            requests_capturados.clear()

            campo = page.locator(
                "#search-autocomplete-input"
            )

            campo.wait_for(
                state="visible",
                timeout=30000
            )

            campo.fill(
                termo
            )

            page.wait_for_timeout(
                500
            )

            campo.press(
                "Enter"
            )

            page.wait_for_timeout(
                5000
            )

            browser.close()

        return jsonify(
            {
                "status":
                    "ok",

                "termo":
                    termo,

                "quantidade":
                    len(
                        requests_capturados
                    ),

                "requests":
                    requests_capturados
            }
        )

    except Exception as e:

        return jsonify(
            {
                "status":
                    "erro",

                "erro":
                    str(e),

                "trace":
                    traceback.format_exc()
            }
        ), 500


# =========================================================
# PESQUISAR PRODUTO
# =========================================================

def pesquisar_produto(
    page,
    nome,
    preferencias
):

    resultado = {
        "item":
            nome,

        "status":
            "pendente",

        "produto_encontrado":
            None,

        "preco":
            None,

        "preferencias_interpretadas":
            preferencias
    }

    try:

        executar_busca(
            page,
            nome
        )

        produtos = coletar_produtos(
            page
        )

        resultado[
            "status"
        ] = "busca_executada"

        resultado[
            "produtos"
        ] = produtos[:10]

        return resultado

    except Exception as e:

        resultado[
            "status"
        ] = "erro"

        resultado[
            "mensagem"
        ] = str(e)

        return resultado


# =========================================================
# EXECUTAR COMPRA
# =========================================================

@app.route(
    "/executar-compra",
    methods=["POST"]
)
def executar_compra():

    try:

        dados = request.get_json(
            force=True
        )

        itens = dados.get(
            "itens",
            []
        )

        if not itens:

            return jsonify(
                {
                    "status":
                        "erro",

                    "mensagem":
                        "Nenhum item recebido."
                }
            ), 400

        resultados = []

        with sync_playwright() as p:

            browser = criar_browser(p)

            page = criar_pagina(
                browser
            )

            for item in itens:

                nome = (
                    item
                    .get(
                        "item",
                        ""
                    )
                    .strip()
                )

                preferencias = (
                    parse_preferencias(
                        item.get(
                            "preferencias",
                            ""
                        )
                    )
                )

                resultado = pesquisar_produto(
                    page,
                    nome,
                    preferencias
                )

                resultado[
                    "quantidade"
                ] = item.get(
                    "quantidade",
                    "1"
                )

                resultados.append(
                    resultado
                )

            browser.close()

        return jsonify(
            {
                "status":
                    "ok",

                "mercado":
                    "Supermercado Mateus Cohama",

                "quantidade_itens":
                    len(
                        resultados
                    ),

                "resultados":
                    resultados
            }
        )

    except Exception as e:

        return jsonify(
            {
                "status":
                    "erro",

                "erro":
                    str(e),

                "trace":
                    traceback.format_exc()
            }
        ), 500


# =========================================================
# INICIAR
# =========================================================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            5000
        )
    )

    app.run(
        host="0.0.0.0",
        port=port
    )
