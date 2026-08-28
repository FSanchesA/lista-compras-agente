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
    Converte textos como:
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
    Cria o navegador Chromium usando
    configurações adequadas ao Render.
    """

    browser = playwright.chromium.launch(
        headless=True,
        args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-setuid-sandbox"
        ]
    )

    return browser


def criar_pagina(browser):
    """
    Cria uma página com tamanho de desktop.
    """

    page = browser.new_page(
        viewport={
            "width": 1440,
            "height": 900
        },
        locale="pt-BR"
    )

    return page


def abrir_mateus(page):
    """
    Abre diretamente a loja
    Supermercado Mateus Cohama.
    """

    page.goto(
        MATEUS_URL,
        wait_until="domcontentloaded",
        timeout=60000
    )

    page.wait_for_timeout(
        4000
    )

    return {
        "titulo": page.title(),
        "url": page.url
    }


def login_mateus(page):
    """
    Estrutura inicial do login.

    As credenciais serão configuradas
    no Render usando variáveis de ambiente:

    MATEUS_LOGIN
    MATEUS_SENHA

    Ainda não tentamos fazer login porque
    primeiro estamos identificando os
    elementos reais do site.
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
    Primeira estrutura da busca.

    Ainda não clica em produtos.
    Primeiro estamos identificando
    corretamente a estrutura do Mateus Mais.
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
    Esta rota serve para descobrir
    como o site Mateus Mais está estruturado.

    Ela lista:
    - inputs
    - buttons
    - links

    Assim identificamos o campo de busca,
    botão de login, carrinho etc.
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
                3000
            )

            inputs = (
                page
                .locator(
                    "input"
                )
                .evaluate_all(
                    """
                    elements => elements.map(
                        (el, i) => ({
                            indice: i,
                            type: el.type || "",
                            name: el.name || "",
                            id: el.id || "",
                            placeholder: el.placeholder || "",
                            ariaLabel:
                                el.getAttribute('aria-label') || "",
                            autocomplete:
                                el.getAttribute('autocomplete') || "",
                            className:
                                typeof el.className === 'string'
                                ? el.className
                                : ""
                        })
                    )
                    """
                )
            )

            buttons = (
                page
                .locator(
                    "button"
                )
                .evaluate_all(
                    """
                    elements => elements
                    .slice(0, 100)
                    .map(
                        (el, i) => ({
                            indice: i,
                            texto:
                                (el.innerText || "").trim(),
                            ariaLabel:
                                el.getAttribute('aria-label') || "",
                            title:
                                el.getAttribute('title') || "",
                            type:
                                el.getAttribute('type') || "",
                            className:
                                typeof el.className === 'string'
                                ? el.className
                                : ""
                        })
                    )
                    """
                )
            )

            links = (
                page
                .locator(
                    "a"
                )
                .evaluate_all(
                    """
                    elements => elements
                    .slice(0, 150)
                    .map(
                        (el, i) => ({
                            indice: i,
                            texto:
                                (el.innerText || "").trim(),
                            href:
                                el.href || "",
                            ariaLabel:
                                el.getAttribute('aria-label') || "",
                            title:
                                el.getAttribute('title') || ""
                        })
                    )
                    """
                )
            )

            titulo = (
                page.title()
            )

            url = (
                page.url
            )

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
                    len(inputs),

                "quantidade_buttons":
                    len(buttons),

                "quantidade_links":
                    len(links),

                "inputs":
                    inputs,

                "buttons":
                    buttons,

                "links":
                    links

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
