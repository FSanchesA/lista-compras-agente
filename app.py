from flask import Flask, request, jsonify
from playwright.sync_api import sync_playwright

import os
import re
import json
import time
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

MATEUS_BASE = (
    "https://mateusmais.com.br"
)

MATEUS_APP_API = (
    "https://app.mateusmais.com.br"
)

MATEUS_API = (
    "https://app.mateusmais.com.br/"
    "api/products/internal/v1/service/"
)

MATEUS_CART_API = (
    "https://cart-v2.mateusmais.com.br/"
    "api/v1/cart/"
)

MARKET_ID = (
    "2857c51e-ffc9-4365-b39a-0156cfc032b9"
)

INDEX_PRODUTOS = (
    "SHOWCASE_catalog_product_api_index_PROD"
)

SESSION_FILE = (
    "/tmp/mateus_storage_state.json"
)

SESSION_META_FILE = (
    "/tmp/mateus_session_meta.json"
)

SESSION_STORAGE_FILE = (
    "/tmp/mateus_session_storage.json"
)

SESSION_MAX_AGE = (
    60 * 60 * 8
)


# =========================================================
# NORMALIZAÇÃO
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

                limite = float(
                    valor
                )

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
# TAMANHO
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
# PREÇO
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

        "Origin":
            "https://mateusmais.com.br",

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
# COMPATIBILIDADE
# =========================================================

def tamanho_compativel(
    produto,
    tamanho
):

    if not tamanho:

        return True

    medida = produto.get(
        "medida"
    )

    tipo = produto.get(
        "tipo_medida"
    )

    if (
        medida is None
        or tipo is None
    ):

        return False

    try:

        medida = float(
            medida
        )

    except Exception:

        return False

    valor = float(
        tamanho[
            "valor"
        ]
    )

    tipo_pref = tamanho[
        "tipo"
    ]

    if tipo == tipo_pref:

        return abs(
            medida -
            valor
        ) < 0.01

    if (
        tipo == "G"
        and tipo_pref == "KG"
    ):

        return abs(
            medida -
            valor * 1000
        ) < 1

    if (
        tipo == "KG"
        and tipo_pref == "G"
    ):

        return abs(
            medida * 1000 -
            valor
        ) < 1

    if (
        tipo == "ML"
        and tipo_pref == "L"
    ):

        return abs(
            medida -
            valor * 1000
        ) < 1

    if (
        tipo == "L"
        and tipo_pref == "ML"
    ):

        return abs(
            medida * 1000 -
            valor
        ) < 1

    return False


def score_compatibilidade(
    produto,
    descricao
):

    descricao = remover_tamanho(
        descricao
    )

    palavras = [
        x
        for x in normalizar_texto(
            descricao
        ).split()
        if len(x) >= 2
    ]

    if not palavras:

        return 0

    texto_produto = normalizar_texto(
        (
            str(
                produto.get(
                    "marca",
                    ""
                )
            )
            +
            " "
            +
            str(
                produto.get(
                    "nome",
                    ""
                )
            )
        )
    )

    acertos = sum(
        1
        for palavra in palavras
        if palavra in texto_produto
    )

    return (
        acertos /
        len(
            palavras
        )
    )


# =========================================================
# ESCOLHA POR PREFERÊNCIA
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
                x[
                    "score"
                ]
                for x in candidatos
            )

            melhores = [
                x
                for x in candidatos
                if abs(
                    x[
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

            escolhido = (
                melhores[
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
                        f"Preferência nº "
                        f"{prioridade} atendida."
                    )
            }

    return None


# =========================================================
# SUGESTÃO MELHOR CUSTO
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


# =========================================================
# SESSÃO
# =========================================================

def sessao_existe():

    if not os.path.exists(
        SESSION_FILE
    ):

        return False

    if not os.path.exists(
        SESSION_META_FILE
    ):

        return False

    try:

        with open(
            SESSION_META_FILE,
            "r",
            encoding="utf-8"
        ) as arquivo:

            meta = json.load(
                arquivo
            )

        criado = meta.get(
            "timestamp",
            0
        )

        idade = (
            time.time() -
            criado
        )

        return (
            idade <
            SESSION_MAX_AGE
        )

    except Exception:

        return False


def salvar_meta_sessao():

    with open(
        SESSION_META_FILE,
        "w",
        encoding="utf-8"
    ) as arquivo:

        json.dump(
            {
                "timestamp":
                    time.time()
            },
            arquivo
        )


# =========================================================
# CAPTURAR SESSION STORAGE
# =========================================================

def capturar_session_storage(
    page
):

    try:

        dados = page.evaluate(
            """
            () => {
                const resultado = {};

                for (
                    let i = 0;
                    i < sessionStorage.length;
                    i++
                ) {

                    const chave =
                        sessionStorage.key(i);

                    resultado[chave] =
                        sessionStorage.getItem(chave);
                }

                return resultado;
            }
            """
        )

        with open(
            SESSION_STORAGE_FILE,
            "w",
            encoding="utf-8"
        ) as arquivo:

            json.dump(
                dados,
                arquivo,
                ensure_ascii=False
            )

        return len(
            dados
        )

    except Exception:

        return 0


# =========================================================
# GERAR SESSÃO
# =========================================================

def gerar_sessao():

    usuario = os.getenv(
        "MATEUS_LOGIN"
    )

    senha = os.getenv(
        "MATEUS_SENHA"
    )

    if not usuario or not senha:

        raise Exception(
            "Credenciais do Mateus "
            "não configuradas no Render."
        )

    with sync_playwright() as p:

        browser = criar_browser(
            p
        )

        context = browser.new_context(
            viewport={
                "width":
                    1440,

                "height":
                    900
            },
            locale="pt-BR"
        )

        page = context.new_page()

        page.goto(
            "https://mateusmais.com.br/login",
            wait_until="domcontentloaded",
            timeout=60000
        )

        campo_login = page.locator(
            'input#login'
        )

        campo_login.wait_for(
            state="visible",
            timeout=30000
        )

        campo_login.fill(
            usuario
        )

        campo_senha = page.locator(
            'input#password'
        )

        campo_senha.wait_for(
            state="visible",
            timeout=30000
        )

        campo_senha.fill(
            senha
        )

        botao_entrar = page.locator(
            'button[type="submit"]'
        )

        botao_entrar.wait_for(
            state="visible",
            timeout=30000
        )

        botao_entrar.click()

        try:

            page.wait_for_url(
                lambda url:
                    "/login"
                    not in url,
                timeout=60000
            )

        except Exception:

            pass

        page.wait_for_timeout(
            2500
        )

        url_final = page.url

        if "/login" in url_final:

            browser.close()

            raise Exception(
                "Login não foi concluído."
            )

        context.storage_state(
            path=SESSION_FILE
        )

        cookies = context.cookies()

        session_storage_qtd = (
            capturar_session_storage(
                page
            )
        )

        salvar_meta_sessao()

        browser.close()

    return {

        "status":
            "LOGIN_OK",

        "autenticado":
            True,

        "cookies_salvos":
            len(
                cookies
            ),

        "session_storage_salvos":
            session_storage_qtd,

        "url":
            url_final
    }


# =========================================================
# STORAGE STATE
# =========================================================

def ler_storage_state():

    if not os.path.exists(
        SESSION_FILE
    ):

        return None

    with open(
        SESSION_FILE,
        "r",
        encoding="utf-8"
    ) as arquivo:

        return json.load(
            arquivo
        )


# =========================================================
# LOCAL STORAGE
# =========================================================

def obter_local_storage(
    chave_procurada
):

    state = ler_storage_state()

    if not state:

        return None

    for origin in state.get(
        "origins",
        []
    ):

        for item in origin.get(
            "localStorage",
            []
        ):

            if item.get(
                "name"
            ) == chave_procurada:

                return item.get(
                    "value"
                )

    return None


# =========================================================
# TOKEN
# =========================================================

def obter_auth_token():

    valor = obter_local_storage(
        "auth:token"
    )

    if not valor:

        return None

    try:

        parsed = json.loads(
            valor
        )

        if isinstance(
            parsed,
            str
        ):

            return parsed

        if isinstance(
            parsed,
            dict
        ):

            for chave in [
                "token",
                "access_token",
                "accessToken",
                "value"
            ]:

                if parsed.get(
                    chave
                ):

                    return str(
                        parsed[
                            chave
                        ]
                    )

    except Exception:

        pass

    return str(
        valor
    ).strip(
        '"'
    )


# =========================================================
# GARANTIR SESSÃO
# =========================================================

def garantir_sessao():

    if sessao_existe():

        return {

            "status":
                "SESSAO_REUTILIZADA",

            "nova":
                False
        }

    resultado = gerar_sessao()

    return {

        "status":
            resultado[
                "status"
            ],

        "nova":
            True
    }


# =========================================================
# SESSION HTTP AUTENTICADA
# =========================================================

def criar_requests_session(
    incluir_auth=True
):

    session = requests.Session()

    session.headers.update(
        {
            "User-Agent":
                (
                    "Mozilla/5.0 "
                    "(Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 "
                    "(KHTML, like Gecko) "
                    "Chrome/151 Safari/537.36"
                ),

            "Accept":
                "application/json, text/plain, */*",

            "Content-Type":
                "application/json",

            "Origin":
                "https://mateusmais.com.br",

            "Referer":
                "https://mateusmais.com.br/"
        }
    )

    if incluir_auth:

        token = obter_auth_token()

        if token:

            # =============================================
            # PADRÃO REAL IDENTIFICADO NO MATEUS
            # Authorization: token <TOKEN>
            # =============================================

            session.headers.update(
                {
                    "Authorization":
                        (
                            "token " +
                            token
                        )
                }
            )

    return session


# =========================================================
# DIAGNÓSTICO TOKEN
# =========================================================

def diagnosticar_token():

    token = obter_auth_token()

    if not token:

        return {

            "token_encontrado":
                False,

            "tamanho":
                0,

            "valor_exposto":
                False
        }

    return {

        "token_encontrado":
            True,

        "tamanho":
            len(
                token
            ),

        "authorization":
            "token <oculto>",

        "valor_exposto":
            False
    }


# =========================================================
# ADICIONAR PRODUTO AO CARRINHO VIA API
# =========================================================

def adicionar_produto_carrinho(
    produto,
    quantidade=1
):

    if not produto:

        raise Exception(
            "Produto não informado."
        )

    produto_id = produto.get(
        "id"
    )

    if not produto_id:

        raise Exception(
            "Produto sem ID válido."
        )

    try:

        quantidade = int(
            quantidade
        )

    except Exception:

        quantidade = 1

    quantidade = max(
        1,
        quantidade
    )

    token = obter_auth_token()

    if not token:

        raise Exception(
            "Token de autenticação não encontrado."
        )

    session = criar_requests_session(
        incluir_auth=True
    )

    payload = {

        "products": [
            {
                "id":
                    produto_id,

                "quantity":
                    quantidade,

                "market_id":
                    MARKET_ID
            }
        ],

        "price_table":
            "00"
    }

    inicio = time.time()

    resposta = session.post(
        MATEUS_CART_API,
        json=payload,
        timeout=30
    )

    tempo = round(
        time.time() -
        inicio,
        2
    )

    dados_resposta = None

    try:

        dados_resposta = (
            resposta.json()
        )

    except Exception:

        pass

    return {

        "sucesso":
            resposta.status_code
            in [
                200,
                201
            ],

        "http_status":
            resposta.status_code,

        "tempo_segundos":
            tempo,

        "produto":
            {
                "id":
                    produto.get(
                        "id"
                    ),

                "sku":
                    produto.get(
                        "sku"
                    ),

                "nome":
                    produto.get(
                        "nome"
                    ),

                "marca":
                    produto.get(
                        "marca"
                    ),

                "preco":
                    produto.get(
                        "preco_efetivo"
                    ),

                "quantidade":
                    quantidade
            },

        "resposta":
            dados_resposta,

        "token_exposto":
            False
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

            "sessao_salva":
                sessao_existe(),

            "rotas": [

                "/",

                "/api-buscar?q=cafe",

                "/executar-compra",

                "/gerar-sessao",

                "/status-sessao",

                "/diagnostico-token",

                "/teste-auth-http",

                "/teste-adicionar-carrinho?item=cafe&quantidade=1"

            ]
        }
    )


# =========================================================
# STATUS SESSÃO
# =========================================================

@app.route(
    "/status-sessao",
    methods=["GET"]
)
def status_sessao():

    existe = sessao_existe()

    idade = None

    if (
        existe
        and os.path.exists(
            SESSION_META_FILE
        )
    ):

        try:

            with open(
                SESSION_META_FILE,
                "r",
                encoding="utf-8"
            ) as arquivo:

                meta = json.load(
                    arquivo
                )

            idade = round(
                time.time() -
                meta.get(
                    "timestamp",
                    time.time()
                ),
                1
            )

        except Exception:

            pass

    return jsonify(
        {
            "status":
                "ok",

            "sessao_valida":
                existe,

            "idade_segundos":
                idade,

            "validade_maxima_segundos":
                SESSION_MAX_AGE,

            "storage_state_existe":
                os.path.exists(
                    SESSION_FILE
                ),

            "token_encontrado":
                bool(
                    obter_auth_token()
                )
        }
    )


# =========================================================
# GERAR SESSÃO
# =========================================================

@app.route(
    "/gerar-sessao",
    methods=["GET"]
)
def gerar_sessao_route():

    try:

        inicio = time.time()

        resultado = gerar_sessao()

        resultado[
            "tempo_segundos"
        ] = round(
            time.time() -
            inicio,
            2
        )

        return jsonify(
            {
                "status":
                    "ok",

                "sessao":
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
# DIAGNÓSTICO TOKEN
# =========================================================

@app.route(
    "/diagnostico-token",
    methods=["GET"]
)
def diagnostico_token_route():

    try:

        if not sessao_existe():

            return jsonify(
                {
                    "status":
                        "erro",

                    "mensagem":
                        (
                            "Sessão não está válida. "
                            "Execute /gerar-sessao primeiro."
                        )
                }
            ), 400

        return jsonify(
            {
                "status":
                    "ok",

                "auth":
                    diagnosticar_token()
            }
        )

    except Exception as e:

        return jsonify(
            {
                "status":
                    "erro",

                "erro":
                    str(e)
            }
        ), 500


# =========================================================
# TESTE HTTP AUTH
# =========================================================

@app.route(
    "/teste-auth-http",
    methods=["GET"]
)
def teste_auth_http():

    try:

        inicio = time.time()

        garantia = garantir_sessao()

        session = criar_requests_session(
            incluir_auth=True
        )

        resposta = session.get(
            MATEUS_URL,
            timeout=20,
            allow_redirects=True
        )

        tempo = round(
            time.time() -
            inicio,
            2
        )

        return jsonify(
            {
                "status":
                    "ok",

                "sessao":
                    garantia,

                "token_encontrado":
                    bool(
                        obter_auth_token()
                    ),

                "authorization_formato":
                    "token <oculto>",

                "http_status":
                    resposta.status_code,

                "tempo_segundos":
                    tempo,

                "token_exposto":
                    False
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
# TESTE ADICIONAR 1 PRODUTO AO CARRINHO
# =========================================================

@app.route(
    "/teste-adicionar-carrinho",
    methods=["GET"]
)
def teste_adicionar_carrinho():

    try:

        item = request.args.get(
            "item",
            "cafe"
        ).strip()

        preferencias = request.args.get(
            "preferencias",
            ""
        ).strip()

        try:

            quantidade = int(
                request.args.get(
                    "quantidade",
                    "1"
                )
            )

        except Exception:

            quantidade = 1

        quantidade = max(
            quantidade,
            1
        )

        # -------------------------------------------------
        # GARANTIR LOGIN / TOKEN
        # -------------------------------------------------

        sessao = garantir_sessao()

        # -------------------------------------------------
        # ESCOLHER PRODUTO
        # -------------------------------------------------

        decisao = decidir_item(
            item,
            preferencias
        )

        produto = (
            decisao.get(
                "escolhido"
            )
            or
            decisao.get(
                "sugestao"
            )
        )

        if not produto:

            return jsonify(
                {
                    "status":
                        "erro",

                    "mensagem":
                        (
                            "Nenhum produto compatível "
                            "foi encontrado."
                        ),

                    "item":
                        item,

                    "decisao":
                        decisao
                }
            ), 404

        # -------------------------------------------------
        # ADICIONAR AO CARRINHO
        # -------------------------------------------------

        resultado_carrinho = (
            adicionar_produto_carrinho(
                produto,
                quantidade
            )
        )

        return jsonify(
            {
                "status":
                    (
                        "ok"
                        if resultado_carrinho[
                            "sucesso"
                        ]
                        else "erro"
                    ),

                "sessao":
                    sessao,

                "item_solicitado":
                    item,

                "decisao":
                    {
                        "status":
                            decisao.get(
                                "status"
                            ),

                        "motivo":
                            decisao.get(
                                "motivo"
                            ),

                        "preferencia_atendida":
                            decisao.get(
                                "preferencia_atendida"
                            )
                    },

                "carrinho":
                    resultado_carrinho
            }
        ), (
            200
            if resultado_carrinho[
                "sucesso"
            ]
            else 400
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

        resultado = buscar_produtos_api(
            termo,
            limite=50
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
                    str(e)
            }
        ), 500


# =========================================================
# EXECUTAR COMPRA - SOMENTE ANÁLISE POR ENQUANTO
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
                item.get(
                    "item",
                    ""
                ).strip()
            )

            preferencias = item.get(
                "preferencias",
                ""
            )

            quantidade = item.get(
                "quantidade",
                "1"
            )

            try:

                resultado = decidir_item(
                    nome,
                    preferencias
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
