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

MATEUS_BASE = "https://mateusmais.com.br"

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
# NORMALIZAR TEXTO
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
# REMOVER TAMANHO
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
# NORMALIZAR PRODUTO
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
# BUSCA DIRETA NA API
# =========================================================

def buscar_produtos_api(
    termo,
    limite=50,
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
# SCORE PREFERÊNCIA
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

    return [
        p
        for p in texto.split()
        if len(p) >= 2
    ]


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
# ESCOLHER POR PREFERÊNCIA
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
                for candidato
                in candidatos
            )

            melhores = [
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

            melhores.sort(
                key=lambda x:
                    x[
                        "produto"
                    ].get(
                        "preco_efetivo"
                    )
                    or 999999
            )

            escolhido = melhores[
                0
            ][
                "produto"
            ]

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
# ALTERNATIVA MELHOR CUSTO
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
# DECIDIR ITEM
# =========================================================

def decidir_item(
    nome,
    preferencias_texto
):

    preferencias = parse_preferencias(
        preferencias_texto
    )

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

        return escolha

    sugestao = sugerir_alternativa(
        nome,
        produtos
    )

    return {

        "status":
            (
                "PREFERENCIA_NAO_ATENDIDA"
                if preferencias
                else "SUGESTAO"
            ),

        "item":
            nome,

        "preferencias":
            preferencias,

        "sugestao":
            sugestao
    }


# =========================================================
# PLAYWRIGHT
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


def criar_contexto(browser):

    return browser.new_context(
        viewport={
            "width": 1440,
            "height": 900
        },
        locale="pt-BR"
    )


def criar_pagina(contexto):

    return contexto.new_page()


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
# ABRIR ÁREA DE LOGIN
# =========================================================

def abrir_login(page):

    abrir_mateus(
        page
    )

    textos = [
        "Entrar",
        "Login",
        "Acessar",
        "Minha conta"
    ]

    for texto in textos:

        try:

            botao = page.get_by_text(
                texto,
                exact=False
            ).first

            if botao.is_visible(
                timeout=1500
            ):

                botao.click()

                page.wait_for_timeout(
                    1500
                )

                return True

        except Exception:
            pass


    seletores = [
        'button:has-text("Entrar")',
        'a:has-text("Entrar")',
        '[aria-label*="entrar" i]',
        '[aria-label*="login" i]',
        '[href*="login"]',
        '[href*="auth"]'
    ]

    for seletor in seletores:

        try:

            elemento = page.locator(
                seletor
            ).first

            if elemento.is_visible(
                timeout=1000
            ):

                elemento.click()

                page.wait_for_timeout(
                    1500
                )

                return True

        except Exception:
            pass


    return False


# =========================================================
# LOGIN AUTOMÁTICO
# =========================================================

def login_mateus(page):

    usuario = os.getenv(
        "MATEUS_LOGIN"
    )

    senha = os.getenv(
        "MATEUS_SENHA"
    )

    if not usuario or not senha:

        raise Exception(
            "MATEUS_LOGIN e MATEUS_SENHA "
            "não estão configurados no Render."
        )


    abriu_login = abrir_login(
        page
    )


    page.wait_for_timeout(
        1000
    )


    # -------------------------------------------------
    # PRIMEIRO CAMPO: CPF / TELEFONE / E-MAIL
    # -------------------------------------------------

    candidatos_usuario = [

        'input[type="tel"]',

        'input[type="email"]',

        'input[name*="cpf" i]',

        'input[name*="phone" i]',

        'input[name*="login" i]',

        'input[placeholder*="cpf" i]',

        'input[placeholder*="telefone" i]',

        'input[placeholder*="celular" i]',

        'input[type="text"]'

    ]


    campo_usuario = None


    for seletor in candidatos_usuario:

        try:

            loc = page.locator(
                seletor
            )

            for i in range(
                min(
                    loc.count(),
                    10
                )
            ):

                el = loc.nth(
                    i
                )

                placeholder = (
                    el.get_attribute(
                        "placeholder"
                    ) or ""
                ).lower()


                if (
                    "00000-000"
                    in placeholder
                    or "pesquise"
                    in placeholder
                ):

                    continue


                if el.is_visible():

                    campo_usuario = el

                    break

            if campo_usuario:
                break

        except Exception:
            pass


    if not campo_usuario:

        return {

            "status":
                "CAMPO_USUARIO_NAO_ENCONTRADO",

            "abriu_login":
                abriu_login,

            "url":
                page.url

        }


    campo_usuario.fill(
        usuario
    )


    page.wait_for_timeout(
        500
    )


    # -------------------------------------------------
    # TENTA CONTINUAR CASO LOGIN SEJA EM DUAS ETAPAS
    # -------------------------------------------------

    botoes_continuar = [

        'button:has-text("Continuar")',

        'button:has-text("Avançar")',

        'button:has-text("Entrar")',

        'button:has-text("Acessar")'

    ]


    for seletor in botoes_continuar:

        try:

            botao = page.locator(
                seletor
            ).first

            if botao.is_visible(
                timeout=500
            ):

                botao.click()

                page.wait_for_timeout(
                    1500
                )

                break

        except Exception:
            pass


    # -------------------------------------------------
    # SENHA
    # -------------------------------------------------

    campo_senha = page.locator(
        'input[type="password"]'
    ).first


    try:

        campo_senha.wait_for(
            state="visible",
            timeout=10000
        )

    except Exception:

        return {

            "status":
                "CAMPO_SENHA_NAO_ENCONTRADO",

            "url":
                page.url

        }


    campo_senha.fill(
        senha
    )


    page.wait_for_timeout(
        400
    )


    # -------------------------------------------------
    # ENTRAR
    # -------------------------------------------------

    clicou = False


    for seletor in [

        'button:has-text("Entrar")',

        'button:has-text("Acessar")',

        'button:has-text("Login")',

        'button[type="submit"]'

    ]:

        try:

            botao = page.locator(
                seletor
            ).first

            if botao.is_visible(
                timeout=700
            ):

                botao.click()

                clicou = True

                break

        except Exception:
            pass


    if not clicou:

        campo_senha.press(
            "Enter"
        )


    page.wait_for_timeout(
        4000
    )


    body = normalizar_texto(
        page.locator(
            "body"
        ).inner_text(
            timeout=5000
        )
    )


    sinais_login = [

        "minha conta",

        "meus pedidos",

        "sair",

        "ola",

        "perfil"

    ]


    autenticado = any(
        sinal in body
        for sinal in sinais_login
    )


    return {

        "status":
            (
                "LOGIN_OK"
                if autenticado
                else "LOGIN_EXECUTADO_VALIDAR"
            ),

        "autenticado":
            autenticado,

        "url":
            page.url,

        "titulo":
            page.title()

    }


# =========================================================
# URL DO PRODUTO
# =========================================================

def url_produto(
    produto
):

    product_id = produto.get(
        "id"
    )

    return (
        f"{MATEUS_BASE}/produtos/"
        f"{MARKET_ID}/"
        f"{product_id}"
    )


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

                "/testar-escolha",

                "/diagnostico-login",

                "/teste-login",

                "/capturar-carrinho",

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

            browser = criar_browser(
                p
            )

            contexto = criar_contexto(
                browser
            )

            page = criar_pagina(
                contexto
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

    preferencias = request.args.get(
        "preferencias",
        ""
    ).strip()


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

        resultado = decidir_item(
            item,
            preferencias
        )


        return jsonify(
            {
                "status":
                    "ok",

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
# DIAGNÓSTICO LOGIN
# =========================================================

@app.route(
    "/diagnostico-login",
    methods=["GET"]
)
def diagnostico_login():

    try:

        with sync_playwright() as p:

            browser = criar_browser(
                p
            )

            contexto = criar_contexto(
                browser
            )

            page = criar_pagina(
                contexto
            )

            abriu = abrir_login(
                page
            )

            page.wait_for_timeout(
                1500
            )

            inputs = []

            loc_inputs = page.locator(
                "input"
            )

            for i in range(
                min(
                    loc_inputs.count(),
                    20
                )
            ):

                el = loc_inputs.nth(
                    i
                )

                try:

                    inputs.append(
                        {
                            "indice":
                                i,

                            "type":
                                el.get_attribute(
                                    "type"
                                ),

                            "name":
                                el.get_attribute(
                                    "name"
                                ),

                            "id":
                                el.get_attribute(
                                    "id"
                                ),

                            "placeholder":
                                el.get_attribute(
                                    "placeholder"
                                ),

                            "autocomplete":
                                el.get_attribute(
                                    "autocomplete"
                                ),

                            "visivel":
                                el.is_visible()
                        }
                    )

                except Exception:
                    pass


            buttons = []

            loc_buttons = page.locator(
                "button"
            )

            for i in range(
                min(
                    loc_buttons.count(),
                    30
                )
            ):

                el = loc_buttons.nth(
                    i
                )

                try:

                    buttons.append(
                        {
                            "indice":
                                i,

                            "texto":
                                (
                                    el.inner_text(
                                        timeout=500
                                    ) or ""
                                ).strip(),

                            "type":
                                el.get_attribute(
                                    "type"
                                ),

                            "visivel":
                                el.is_visible()
                        }
                    )

                except Exception:
                    pass


            retorno = {

                "status":
                    "ok",

                "login_aberto":
                    abriu,

                "url":
                    page.url,

                "titulo":
                    page.title(),

                "inputs":
                    inputs,

                "buttons":
                    buttons
            }


            browser.close()


        return jsonify(
            retorno
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
# TESTE LOGIN REAL
# =========================================================

@app.route(
    "/teste-login",
    methods=["GET"]
)
def teste_login():

    try:

        with sync_playwright() as p:

            browser = criar_browser(
                p
            )

            contexto = criar_contexto(
                browser
            )

            page = criar_pagina(
                contexto
            )

            resultado = login_mateus(
                page
            )

            browser.close()


        return jsonify(
            {
                "status":
                    "ok",

                "login":
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
# CAPTURAR API DO CARRINHO
# =========================================================

@app.route(
    "/capturar-carrinho",
    methods=["GET"]
)
def capturar_carrinho():

    item = request.args.get(
        "item",
        "cafe"
    ).strip()

    preferencias_texto = request.args.get(
        "preferencias",
        ""
    ).strip()


    try:

        decisao = decidir_item(
            item,
            preferencias_texto
        )


        produto = (
            decisao.get(
                "escolhido"
            )
            or decisao.get(
                "sugestao"
            )
        )


        if not produto:

            return jsonify(
                {
                    "status":
                        "erro",

                    "mensagem":
                        "Nenhum produto foi escolhido."
                }
            ), 400


        capturas = []


        with sync_playwright() as p:

            browser = criar_browser(
                p
            )

            contexto = criar_contexto(
                browser
            )

            page = criar_pagina(
                contexto
            )


            login = login_mateus(
                page
            )


            # ---------------------------------------------
            # ESCUTA REQUISIÇÕES DE CARRINHO
            # ---------------------------------------------

            def registrar_request(req):

                try:

                    if req.resource_type not in [
                        "xhr",
                        "fetch"
                    ]:
                        return


                    url_lower = req.url.lower()


                    palavras = [

                        "cart",

                        "basket",

                        "checkout",

                        "order",

                        "carrinho",

                        "bag",

                        "shopping"

                    ]


                    if not any(
                        palavra in url_lower
                        for palavra in palavras
                    ):

                        return


                    capturas.append(
                        {
                            "metodo":
                                req.method,

                            "url":
                                req.url,

                            "post_data":
                                req.post_data,

                            "content_type":
                                req.headers.get(
                                    "content-type",
                                    ""
                                )
                        }
                    )

                except Exception:
                    pass


            page.on(
                "request",
                registrar_request
            )


            # ---------------------------------------------
            # ABRIR PRODUTO
            # ---------------------------------------------

            produto_url = url_produto(
                produto
            )


            page.goto(
                produto_url,
                wait_until="domcontentloaded",
                timeout=60000
            )


            page.wait_for_timeout(
                3000
            )


            # ---------------------------------------------
            # TENTAR ADICIONAR
            # ---------------------------------------------

            clicou_adicionar = False


            seletores = [

                'button:has-text("Adicionar")',

                'button:has-text("Comprar")',

                'button:has-text("Adicionar ao carrinho")',

                '[aria-label*="adicionar" i]'

            ]


            for seletor in seletores:

                try:

                    botao = page.locator(
                        seletor
                    ).first


                    if botao.is_visible(
                        timeout=1500
                    ):

                        botao.click()

                        clicou_adicionar = True

                        break

                except Exception:
                    pass


            page.wait_for_timeout(
                4000
            )


            retorno = {

                "status":
                    "ok",

                "login":
                    login,

                "item":
                    item,

                "produto":
                    produto,

                "produto_url":
                    produto_url,

                "clicou_adicionar":
                    clicou_adicionar,

                "quantidade_chamadas":
                    len(
                        capturas
                    ),

                "chamadas":
                    capturas
            }


            browser.close()


        return jsonify(
            retorno
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
# EXECUTAR COMPRA / ANÁLISE
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


            quantidade = (
                item.get(
                    "quantidade",
                    "1"
                )
            )


            try:

                resultado = decidir_item(
                    nome,
                    preferencias_texto
                )


                resultado[
                    "quantidade"
                ] = quantidade


                resultados.append(
                    resultado
                )


            except Exception as e:

                resultados.append(
                    {
                        "status":
                            "ERRO",

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
