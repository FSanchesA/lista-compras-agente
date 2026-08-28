from flask import Flask, request, jsonify
from playwright.sync_api import sync_playwright

import os
import re
import json
import traceback
import requests

from urllib.parse import urlencode


app = Flask(__name__)


# =========================================================
# CONFIGURAÇÕES
# =========================================================

MATEUS_URL = (
    "https://mateusmais.com.br/"
    "loja/supermercado-mateus-cohama"
)

MATEUS_API = (
    "https://app.mateusmais.com.br/"
    "api/products/internal/v1/service/"
)

MARKET_ID = (
    "2857c51e-ffc9-4365-b39a-0156cfc032b9"
)

INDEX_PRODUTOS = (
    "SHOWCASE_catalog_product_api_index_PROD"
)


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
# PREÇO EFETIVO
# =========================================================

def preco_efetivo(produto):

    candidatos = [

        produto.get(
            "sale_price"
        ),

        produto.get(
            "low_price"
        ),

        produto.get(
            "bulk_price"
        ),

        produto.get(
            "price"
        )

    ]

    for valor in candidatos:

        if (
            isinstance(
                valor,
                (int, float)
            )
            and valor > 0
        ):

            return float(
                valor
            )

    return None


# =========================================================
# NORMALIZAÇÃO DO PRODUTO
# =========================================================

def normalizar_produto(produto):

    preco = preco_efetivo(
        produto
    )

    medida = produto.get(
        "measure"
    )

    tipo_medida = produto.get(
        "measure_type"
    )

    preco_por_medida = None


    try:

        if (
            preco
            and medida
            and float(medida) > 0
        ):

            medida_float = float(
                medida
            )


            if tipo_medida == "KG":

                preco_por_medida = (
                    preco /
                    medida_float
                )


            elif tipo_medida == "L":

                preco_por_medida = (
                    preco /
                    medida_float
                )


            elif tipo_medida == "G":

                preco_por_medida = (
                    preco /
                    (
                        medida_float /
                        1000
                    )
                )


            elif tipo_medida == "ML":

                preco_por_medida = (
                    preco /
                    (
                        medida_float /
                        1000
                    )
                )

    except Exception:

        preco_por_medida = None


    return {

        "id":
            produto.get(
                "id"
            ),

        "sku":
            produto.get(
                "sku"
            ),

        "barcode":
            produto.get(
                "barcode"
            ),

        "nome":
            produto.get(
                "name"
            ),

        "marca":
            produto.get(
                "brand"
            ),

        "categoria":
            produto.get(
                "category"
            ),

        "departamento":
            produto.get(
                "departament_name"
            ),

        "secao":
            produto.get(
                "section_name"
            ),

        "preco_normal":
            produto.get(
                "price"
            ),

        "preco_promocional":
            produto.get(
                "sale_price"
            ),

        "preco_baixo":
            produto.get(
                "low_price"
            ),

        "preco_efetivo":
            preco,

        "estoque":
            produto.get(
                "amount_in_stock"
            ),

        "medida":
            medida,

        "tipo_medida":
            tipo_medida,

        "preco_por_medida":
            (
                round(
                    preco_por_medida,
                    2
                )
                if preco_por_medida
                else None
            ),

        "for_sale":
            produto.get(
                "for_sale"
            ),

        "imagem":
            produto.get(
                "small_image"
            ) or produto.get(
                "image"
            )

    }


# =========================================================
# BUSCA DIRETA NA API DO MATEUS
# =========================================================

def buscar_produtos_api(
    termo,
    limite=20,
    pagina=0
):

    facet_filters = [

        [
            f"market_id:{MARKET_ID}"
        ],

        [
            "for_sale:true"
        ]

    ]


    params_busca = urlencode(
        {
            "page":
                pagina,

            "hitsPerPage":
                limite,

            "clickAnalytics":
                "true",

            "facetFilters":
                json.dumps(
                    facet_filters,
                    separators=(
                        ",",
                        ":"
                    )
                ),

            "query":
                termo
        }
    )


    payload = {

        "facets": [
            "specification.*",
            "brand",
            "nodes"
        ],

        "params":
            params_busca,

        "index":
            INDEX_PRODUTOS,

        "service":
            "meilisearch"

    }


    headers = {

        "Accept":
            "application/json, text/plain, */*",

        "Content-Type":
            "application/json",

        "Referer":
            "https://mateusmais.com.br/",

        "User-Agent":
            (
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/151 Safari/537.36"
            )

    }


    resposta = requests.post(
        MATEUS_API,
        json=payload,
        headers=headers,
        timeout=30
    )


    resposta.raise_for_status()


    dados = resposta.json()


    hits = dados.get(
        "hits",
        []
    )


    produtos = [
        normalizar_produto(
            produto
        )
        for produto in hits
    ]


    return {

        "termo":
            termo,

        "quantidade":
            len(
                produtos
            ),

        "produtos":
            produtos

    }


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


def abrir_mateus(page):

    page.goto(
        MATEUS_URL,
        wait_until="domcontentloaded",
        timeout=60000
    )

    page.wait_for_timeout(
        3000
    )

    return {

        "titulo":
            page.title(),

        "url":
            page.url

    }


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

            "status":
                "online",

            "servico":
                "Agente Lista de Compras",

            "mercado":
                "Mateus Cohama",

            "market_id":
                MARKET_ID,

            "rotas": [

                "/",

                "/teste",

                "/api-buscar?q=arroz",

                "/api-buscar?q=cafe&limite=20",

                "/executar-compra"

            ]

        }
    )


# =========================================================
# TESTE DO CHROMIUM
# =========================================================

@app.route(
    "/teste",
    methods=["GET"]
)
def teste():

    try:

        with sync_playwright() as p:

            browser = criar_browser(
                p
            )

            page = criar_pagina(
                browser
            )

            dados = abrir_mateus(
                page
            )

            browser.close()


        return jsonify(
            {

                "status":
                    "ok",

                "titulo":
                    dados[
                        "titulo"
                    ],

                "url":
                    dados[
                        "url"
                    ]

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
# TESTE DA API DIRETA
# =========================================================

@app.route(
    "/api-buscar",
    methods=["GET"]
)
def api_buscar():

    termo = request.args.get(
        "q",
        "arroz"
    ).strip()


    try:

        limite = int(
            request.args.get(
                "limite",
                20
            )
        )

    except Exception:

        limite = 20


    limite = max(
        1,
        min(
            limite,
            50
        )
    )


    if not termo:

        return jsonify(
            {

                "status":
                    "erro",

                "mensagem":
                    "Informe um termo de busca."

            }
        ), 400


    try:

        resultado = buscar_produtos_api(
            termo,
            limite=limite
        )


        return jsonify(
            {

                "status":
                    "ok",

                "mercado":
                    "Supermercado Mateus Cohama",

                "resultado":
                    resultado

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


        for item in itens:

            nome = (
                item
                .get(
                    "item",
                    ""
                )
                .strip()
            )


            preferencias_texto = (
                item.get(
                    "preferencias",
                    ""
                )
            )


            preferencias = (
                parse_preferencias(
                    preferencias_texto
                )
            )


            quantidade = (
                item.get(
                    "quantidade",
                    "1"
                )
            )


            try:

                busca = buscar_produtos_api(
                    nome,
                    limite=20
                )


                resultados.append(
                    {

                        "item":
                            nome,

                        "quantidade":
                            quantidade,

                        "preferencias":
                            preferencias,

                        "status":
                            "pesquisado",

                        "opcoes":
                            busca[
                                "produtos"
                            ]

                    }
                )


            except Exception as e:

                resultados.append(
                    {

                        "item":
                            nome,

                        "quantidade":
                            quantidade,

                        "preferencias":
                            preferencias,

                        "status":
                            "erro",

                        "mensagem":
                            str(e)

                    }
                )


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
