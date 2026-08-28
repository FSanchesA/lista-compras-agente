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
# LOGIN
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
            "Credenciais do Mateus não configuradas."
        )

    abrir_mateus(
        page
    )

    return {
        "status":
            "login_pendente_validacao"
    }


# =========================================================
# PESQUISA
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
        800
    )


    campo_busca.press(
        "Enter"
    )


    page.wait_for_timeout(
        4000
    )


    return {

        "termo":
            termo,

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

            "rotas": [
                "/",
                "/teste",
                "/diagnostico",
                "/buscar?q=arroz",
                "/executar-compra"
            ]

        }
    )


# =========================================================
# TESTE SIMPLES
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

            dados_site = abrir_mateus(
                page
            )

            browser.close()


        return jsonify(
            {

                "status":
                    "ok",

                "titulo":
                    dados_site["titulo"],

                "url":
                    dados_site["url"]

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
# DIAGNÓSTICO LEVE
# =========================================================

@app.route(
    "/diagnostico",
    methods=["GET"]
)
def diagnostico():

    try:

        with sync_playwright() as p:

            browser = criar_browser(
                p
            )

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
                min(
                    total,
                    20
                )
            ):

                el = inputs.nth(
                    i
                )

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

                "status":
                    "ok",

                "titulo":
                    titulo,

                "url":
                    url,

                "quantidade_inputs":
                    total,

                "inputs":
                    candidatos

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

                "status":
                    "erro",

                "mensagem":
                    "Informe um produto para pesquisar."

            }
        ), 400


    try:

        with sync_playwright() as p:

            browser = criar_browser(
                p
            )

            page = criar_pagina(
                browser
            )


            resultado = executar_busca(
                page,
                termo
            )


            # -------------------------------------------------
            # TENTAMOS IDENTIFICAR LINKS DE PRODUTOS
            # SEM VARRER A PÁGINA INTEIRA
            # -------------------------------------------------

            produtos = []


            seletores = [

                'a[href*="/produto"]',

                'a[href*="/product"]',

                'a[href*="/p"]'

            ]


            for seletor in seletores:

                links = page.locator(
                    seletor
                )

                quantidade = min(
                    links.count(),
                    20
                )


                for i in range(
                    quantidade
                ):

                    link = links.nth(
                        i
                    )

                    try:

                        texto = (
                            link
                            .inner_text(
                                timeout=2000
                            )
                            .strip()
                        )


                        href = (
                            link.get_attribute(
                                "href"
                            ) or ""
                        )


                        if (
                            texto or
                            href
                        ):

                            registro = {

                                "texto":
                                    texto[:500],

                                "href":
                                    href

                            }


                            if (
                                registro not in
                                produtos
                            ):

                                produtos.append(
                                    registro
                                )

                    except Exception:

                        pass


                if produtos:

                    break


            resultado[
                "quantidade_produtos_detectados"
            ] = len(
                produtos
            )


            resultado[
                "produtos"
            ] = produtos[:20]


            browser.close()


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
# PESQUISAR PRODUTO PARA COMPRA
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

        dados_busca = executar_busca(
            page,
            nome
        )


        resultado["status"] = (
            "busca_executada"
        )


        resultado["url"] = (
            dados_busca["url"]
        )


        resultado["titulo"] = (
            dados_busca["titulo"]
        )


        return resultado


    except Exception as e:

        resultado["status"] = (
            "erro"
        )


        resultado["mensagem"] = (
            str(e)
        )


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

            browser = criar_browser(
                p
            )


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


                resultado["quantidade"] = (
                    item.get(
                        "quantidade",
                        "1"
                    )
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
# INICIAR APP
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
