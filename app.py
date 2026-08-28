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
            except:
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
    em:
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
    except:
        return None


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

    page.goto(
        MATEUS_URL,
        wait_until="domcontentloaded",
        timeout=60000
    )

    page.wait_for_timeout(
        3000
    )

    """
    IMPORTANTE:
    Os seletores de login abaixo ainda serão
    ajustados após nosso primeiro teste real.

    Por enquanto esta função apenas prepara
    a estrutura.
    """

    return {
        "status": "login_pendente_validacao"
    }


def pesquisar_produto(
    page,
    nome,
    preferencias
):

    """
    Nesta primeira versão vamos validar
    somente abertura do site e estrutura.

    Depois vamos preencher:
    - campo de busca
    - resultados
    - preços
    - produto escolhido
    - adicionar ao carrinho
    """

    resultado = {
        "item": nome,
        "status": "pendente",
        "produto_encontrado": None,
        "preco": None,
        "mensagem": ""
    }

    try:

        page.goto(
            MATEUS_URL,
            wait_until="domcontentloaded",
            timeout=60000
        )

        page.wait_for_timeout(
            2000
        )

        titulo = page.title()

        resultado["status"] = "site_aberto"

        resultado["mensagem"] = (
            "Mateus Mais abriu corretamente. "
            f"Título da página: {titulo}"
        )

        resultado["preferencias_interpretadas"] = (
            preferencias
        )

        return resultado

    except Exception as e:

        resultado["status"] = "erro"

        resultado["mensagem"] = str(e)

        return resultado


@app.route(
    "/",
    methods=["GET"]
)
def home():

    return jsonify(
        {
            "status": "online",
            "servico": "Agente Lista de Compras",
            "mercado": "Mateus Cohama"
        }
    )


@app.route(
    "/teste",
    methods=["GET"]
)
def teste():

    try:

        with sync_playwright() as p:

            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage"
                ]
            )

            page = browser.new_page()

            page.goto(
                MATEUS_URL,
                wait_until="domcontentloaded",
                timeout=60000
            )

            page.wait_for_timeout(
                3000
            )

            titulo = page.title()

            url_final = page.url

            browser.close()

        return jsonify(
            {
                "status": "ok",
                "titulo": titulo,
                "url": url_final
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
                    "status": "erro",
                    "mensagem": "Nenhum item recebido."
                }
            ), 400


        resultados = []


        with sync_playwright() as p:

            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage"
                ]
            )

            page = browser.new_page(
                viewport={
                    "width": 1440,
                    "height": 900
                }
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


                resultados.append(
                    resultado
                )


            browser.close()


        return jsonify(
            {
                "status": "ok",
                "mercado": "Supermercado Mateus Cohama",
                "quantidade_itens": len(resultados),
                "resultados": resultados
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
