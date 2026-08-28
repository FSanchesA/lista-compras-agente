from flask import Flask, request, jsonify
from playwright.sync_api import sync_playwright
import os
import re
import traceback


app = Flask(__name__)


MATEUS_URL = "https://mateusmais.com.br/loja/supermercado-mateus-cohama"


def parse_preferencias(texto):
    """
    Exemplo:
    Santa Clara até 13; L'Or até 20

    Retorna:
    [
        {"termo": "Santa Clara", "limite": 13.0},
        {"termo": "L'Or", "limite": 20.0}
    ]
    """

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


def extrair_preco(texto):
    """
    Converte:
    R$ 12,99

    Para:
    12.99
    """

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


def criar_browser(playwright):
    """
    Chromium configurado para o Render.
    """

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
    """
    Cria uma página desktop.
    """

    return browser.new_page(
        viewport={
            "width": 1440,
            "height": 900
        },
        locale="pt-BR"
    )


def abrir_mateus(page):
    """
    Abre a loja Mateus Cohama.
    """

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


def login_mateus(page):
    """
    Login será implementado depois que
    identificarmos os elementos reais do site.
    """

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
        "status": "login_pendente_validacao"
    }


def pesquisar_produto(
    page,
    nome,
    preferencias
):
    """
    Estrutura da busca.
    A pesquisa real será adicionada depois
    do diagnóstico do campo de pesquisa.
    """

    resultado = {
        "item": nome,
        "status": "pendente",
        "produto_encontrado": None,
        "preco": None,
        "mensagem": "",
        "preferencias_interpretadas":
            preferencias
    }

    try:

        abrir_mateus(
            page
        )

        resultado["status"] = (
            "site_aberto"
        )

        resultado["mensagem"] = (
            "Mateus Mais abriu corretamente. "
            f"Título da página: {page.title()}"
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
                "/executar-compra"
            ]
        }
    )


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


@app.route(
    "/diagnostico",
    methods=["GET"]
)
def diagnostico():
    """
    Diagnóstico leve.

    Analisa somente os primeiros inputs
    da página para identificar o campo
    de pesquisa sem sobrecarregar o Render.
    """

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
                2000
            )

            candidatos = []

            inputs = page.locator(
                "input"
            )

            total = inputs.count()

            limite = min(
                total,
                20
            )

            for i in range(
                limite
            ):

                el = inputs.nth(
                    i
                )

                try:

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
                                ) or "",

                            "autocomplete":
                                el.get_attribute(
                                    "autocomplete"
                                ) or ""
                        }
                    )

                except Exception:

                    pass

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


                resultado = (
                    pesquisar_produto(
                        page,
                        nome,
                        preferencias
                    )
                )


                resultado["quantidade"] = (
                    item.get(
                        "quantidade",
                        "1"
                    )
                )


                resultado["observacao"] = (
                    item.get(
                        "observacao",
                        ""
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
