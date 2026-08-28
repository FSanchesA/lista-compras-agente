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
# NORMALIZAÇÃO DE TEXTO
# =========================================================

def normalizar_texto(texto):

    if texto is None:
        return ""

    texto = str(texto).lower()

    substituicoes = {
        "á": "a",
        "à": "a",
        "ã": "a",
        "â": "a",
        "é": "e",
        "ê": "e",
        "í": "i",
        "ó": "o",
        "ô": "o",
        "õ": "o",
        "ú": "u",
        "ç": "c"
    }

    for origem, destino in substituicoes.items():
        texto = texto.replace(
            origem,
            destino
        )

    texto = re.sub(
        r"[^a-z0-9\s]",
        " ",
        texto
    )

    texto = re.sub(
        r"\s+",
        " ",
        texto
    )

    return texto.strip()


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

    for indice, parte in enumerate(
        partes,
        start=1
    ):

        limite = None

        match_preco = re.search(
            r"at[eé]\s+R?\$?\s*([\d,.]+)",
            parte,
            re.IGNORECASE
        )

        if match_preco:

            valor = (
                match_preco
                .group(1)
                .replace(".", "")
                .replace(",", ".")
            )

            try:
                limite = float(valor)

            except Exception:
                limite = None


            descricao = re.sub(
                r"\s*at[eé]\s+R?\$?\s*[\d,.]+",
                "",
                parte,
                flags=re.IGNORECASE
            ).strip()

        else:

            descricao = parte.strip()


        preferencias.append(
            {
                "prioridade":
                    indice,

                "descricao":
                    descricao,

                "limite":
                    limite
            }
        )

    return preferencias


# =========================================================
# EXTRAIR TAMANHO
# =========================================================

def extrair_tamanho(texto):

    if not texto:
        return None

    texto_norm = normalizar_texto(
        texto
    )


    padroes = [

        (
            r"(\d+(?:[.,]\d+)?)\s*kg",
            "KG"
        ),

        (
            r"(\d+(?:[.,]\d+)?)\s*g",
            "G"
        ),

        (
            r"(\d+(?:[.,]\d+)?)\s*l",
            "L"
        ),

        (
            r"(\d+(?:[.,]\d+)?)\s*ml",
            "ML"
        )

    ]


    for padrao, tipo in padroes:

        match = re.search(
            padrao,
            texto_norm
        )

        if match:

            valor = (
                match
                .group(1)
                .replace(",", ".")
            )

            try:

                return {
                    "valor":
                        float(valor),

                    "tipo":
                        tipo
                }

            except Exception:

                return None

    return None


# =========================================================
# REMOVER TAMANHO DO TEXTO
# =========================================================

def remover_tamanho(texto):

    if not texto:
        return ""

    texto = re.sub(
        r"\b\d+(?:[.,]\d+)?\s*(kg|g|l|ml)\b",
        " ",
        texto,
        flags=re.IGNORECASE
    )

    texto = re.sub(
        r"\s+",
        " ",
        texto
    )

    return texto.strip()


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
    limite=30,
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
# TAMANHO COMPATÍVEL
# =========================================================

def tamanho_compativel(
    produto,
    tamanho
):

    if not tamanho:
        return True


    medida_produto = produto.get(
        "medida"
    )

    tipo_produto = produto.get(
        "tipo_medida"
    )


    if (
        medida_produto is None
        or tipo_produto is None
    ):

        return False


    try:

        medida_produto = float(
            medida_produto
        )

    except Exception:

        return False


    valor_preferencia = float(
        tamanho[
            "valor"
        ]
    )

    tipo_preferencia = tamanho[
        "tipo"
    ]


    if tipo_produto == tipo_preferencia:

        return abs(
            medida_produto -
            valor_preferencia
        ) < 0.01


    if (
        tipo_produto == "G"
        and tipo_preferencia == "KG"
    ):

        return abs(
            medida_produto -
            (
                valor_preferencia *
                1000
            )
        ) < 1


    if (
        tipo_produto == "KG"
        and tipo_preferencia == "G"
    ):

        return abs(
            (
                medida_produto *
                1000
            ) -
            valor_preferencia
        ) < 1


    if (
        tipo_produto == "ML"
        and tipo_preferencia == "L"
    ):

        return abs(
            medida_produto -
            (
                valor_preferencia *
                1000
            )
        ) < 1


    if (
        tipo_produto == "L"
        and tipo_preferencia == "ML"
    ):

        return abs(
            (
                medida_produto *
                1000
            ) -
            valor_preferencia
        ) < 1


    return False


# =========================================================
# EXTRAIR PALAVRAS DA PREFERÊNCIA
# =========================================================

def palavras_preferencia(
    descricao
):

    descricao_sem_tamanho = remover_tamanho(
        descricao
    )

    texto = normalizar_texto(
        descricao_sem_tamanho
    )

    palavras = [
        p
        for p in texto.split()
        if len(p) >= 2
    ]

    return palavras


# =========================================================
# SCORE DE COMPATIBILIDADE
# =========================================================

def score_compatibilidade(
    produto,
    descricao
):

    palavras = palavras_preferencia(
        descricao
    )

    if not palavras:
        return 0


    marca = normalizar_texto(
        produto.get(
            "marca",
            ""
        )
    )

    nome = normalizar_texto(
        produto.get(
            "nome",
            ""
        )
    )

    texto_produto = (
        marca +
        " " +
        nome
    )


    acertos = 0


    for palavra in palavras:

        if palavra in texto_produto:

            acertos += 1


    return (
        acertos /
        len(
            palavras
        )
    )


# =========================================================
# ESCOLHER PRODUTO PELA PREFERÊNCIA
# =========================================================

def escolher_por_preferencia(
    item,
    preferencias,
    produtos
):

    for preferencia in preferencias:

        descricao = preferencia.get(
            "descricao",
            ""
        )

        limite = preferencia.get(
            "limite"
        )

        prioridade = preferencia.get(
            "prioridade"
        )


        tamanho = extrair_tamanho(
            descricao
        )


        candidatos = []


        for produto in produtos:

            if not produto.get(
                "for_sale",
                True
            ):

                continue


            estoque = produto.get(
                "estoque"
            )


            if (
                estoque is not None
                and estoque <= 0
            ):

                continue


            if not tamanho_compativel(
                produto,
                tamanho
            ):

                continue


            preco = produto.get(
                "preco_efetivo"
            )


            if preco is None:

                continue


            if (
                limite is not None
                and preco > limite
            ):

                continue


            score = score_compatibilidade(
                produto,
                descricao
            )


            if score <= 0:

                continue


            candidatos.append(
                {
                    "produto":
                        produto,

                    "score":
                        score
                }
            )


        if candidatos:

            melhor_score = max(
                candidato[
                    "score"
                ]
                for candidato in candidatos
            )


            candidatos_melhor_score = [

                candidato

                for candidato
                in candidatos

                if abs(
                    candidato[
                        "score"
                    ] -
                    melhor_score
                ) < 0.0001

            ]


            candidatos_melhor_score.sort(
                key=lambda x: (
                    x[
                        "produto"
                    ].get(
                        "preco_efetivo"
                    )
                    or 999999
                )
            )


            escolhido = (
                candidatos_melhor_score[
                    0
                ][
                    "produto"
                ]
            )


            return {

                "status":
                    "PREFERENCIA_ATENDIDA",

                "item":
                    item,

                "preferencia_atendida":
                    prioridade,

                "descricao_preferencia":
                    descricao,

                "limite_preco":
                    limite,

                "escolhido":
                    escolhido,

                "motivo":
                    (
                        f"Preferência nº {prioridade} "
                        "atendida."
                    )
            }


    return None


# =========================================================
# SUGERIR ALTERNATIVA
# =========================================================

def sugerir_alternativa(
    item,
    produtos
):

    disponiveis = [
        p
        for p in produtos
        if (
            p.get(
                "for_sale",
                True
            )
            and (
                p.get(
                    "estoque"
                ) is None
                or p.get(
                    "estoque"
                ) > 0
            )
            and p.get(
                "preco_efetivo"
            ) is not None
        )
    ]


    if not disponiveis:

        return None


    disponiveis.sort(
        key=lambda p: (
            p.get(
                "preco_por_medida"
            )
            if p.get(
                "preco_por_medida"
            ) is not None
            else 999999,

            p.get(
                "preco_efetivo"
            )
            or 999999
        )
    )


    return disponiveis[
        0
    ]


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

                "/testar-escolha?item=cafe&preferencias=Santa Clara 250g ate 13",

                "/executar-compra"

            ]

        }
    )


# =========================================================
# TESTE CHROMIUM
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
# API BUSCAR
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
# TESTAR ESCOLHA
# =========================================================

@app.route(
    "/testar-escolha",
    methods=["GET"]
)
def testar_escolha():

    item = request.args.get(
        "item",
        ""
    ).strip()


    preferencias_texto = (
        request.args.get(
            "preferencias",
            ""
        )
        .strip()
    )


    if not item:

        return jsonify(
            {

                "status":
                    "erro",

                "mensagem":
                    "Informe o item."

            }
        ), 400


    try:

        preferencias = parse_preferencias(
            preferencias_texto
        )


        busca = buscar_produtos_api(
            item,
            limite=50
        )


        produtos = busca.get(
            "produtos",
            []
        )


        escolha = None


        if preferencias:

            escolha = escolher_por_preferencia(
                item,
                preferencias,
                produtos
            )


        if escolha:

            return jsonify(
                {

                    "status":
                        "ok",

                    "resultado":
                        escolha

                }
            )


        alternativa = sugerir_alternativa(
            item,
            produtos
        )


        if alternativa:

            return jsonify(
                {

                    "status":
                        "ok",

                    "resultado":
                        {

                            "status":
                                "PREFERENCIA_NAO_ATENDIDA",

                            "item":
                                item,

                            "preferencias":
                                preferencias,

                            "sugestao":
                                alternativa,

                            "motivo":
                                (
                                    "Nenhuma preferência "
                                    "foi atendida. "
                                    "Alternativa sugerida."
                                )

                        }

                }
            )


        return jsonify(
            {

                "status":
                    "ok",

                "resultado":
                    {

                        "status":
                            "NAO_ENCONTRADO",

                        "item":
                            item,

                        "preferencias":
                            preferencias

                    }

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
                    limite=50
                )


                produtos = busca.get(
                    "produtos",
                    []
                )


                escolha = None


                if preferencias:

                    escolha = escolher_por_preferencia(
                        nome,
                        preferencias,
                        produtos
                    )


                if escolha:

                    escolha[
                        "quantidade"
                    ] = quantidade


                    resultados.append(
                        escolha
                    )


                else:

                    sugestao = sugerir_alternativa(
                        nome,
                        produtos
                    )


                    resultados.append(
                        {

                            "status":
                                (
                                    "PREFERENCIA_NAO_ATENDIDA"
                                    if preferencias
                                    else "SUGESTAO"
                                ),

                            "item":
                                nome,

                            "quantidade":
                                quantidade,

                            "preferencias":
                                preferencias,

                            "sugestao":
                                sugestao

                        }
                    )


            except Exception as e:

                resultados.append(
                    {

                        "status":
                            "erro",

                        "item":
                            nome,

                        "quantidade":
                            quantidade,

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
