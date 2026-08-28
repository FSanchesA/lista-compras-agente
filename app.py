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
# BUSCA API
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
# ESCOLHA AUTOMÁTICA
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
# LOGIN E SALVAR SESSÃO
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
                "Login não foi concluído. "
                "O Mateus permaneceu na página de login."
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
# REQUESTS SESSION
# =========================================================

def criar_requests_session():

    if not sessao_existe():

        gerar_sessao()


    with open(
        SESSION_FILE,
        "r",
        encoding="utf-8"
    ) as arquivo:

        state = json.load(
            arquivo
        )


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

            "Referer":
                "https://mateusmais.com.br/"
        }
    )


    for cookie in state.get(
        "cookies",
        []
    ):

        try:

            session.cookies.set(
                cookie.get(
                    "name"
                ),

                cookie.get(
                    "value"
                ),

                domain=
                    cookie.get(
                        "domain"
                    ),

                path=
                    cookie.get(
                        "path",
                        "/"
                    )
            )

        except Exception:

            pass


    return session


# =========================================================
# DETECTAR CHAVE SUSPEITA DE AUTENTICAÇÃO
# =========================================================

def parece_chave_auth(
    nome
):

    nome = normalizar_texto(
        nome
    )


    palavras = [

        "token",

        "auth",

        "access",

        "refresh",

        "jwt",

        "bearer",

        "session",

        "login",

        "user",

        "customer",

        "cliente",

        "account",

        "credential"

    ]


    return any(
        palavra in nome
        for palavra in palavras
    )


# =========================================================
# DESCREVER VALOR SEM EXPOR CONTEÚDO
# =========================================================

def descrever_valor_seguro(
    valor
):

    if valor is None:

        return {

            "presente":
                False,

            "tamanho":
                0,

            "parece_json":
                False,

            "parece_jwt":
                False
        }


    texto = str(
        valor
    )


    parece_json = False


    try:

        json.loads(
            texto
        )

        parece_json = True

    except Exception:

        pass


    partes_jwt = texto.split(
        "."
    )


    parece_jwt = (
        len(
            partes_jwt
        ) == 3
        and all(
            len(
                parte
            ) > 5
            for parte in partes_jwt
        )
    )


    return {

        "presente":
            True,

        "tamanho":
            len(
                texto
            ),

        "parece_json":
            parece_json,

        "parece_jwt":
            parece_jwt
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

                "/teste-sessao-http",

                "/diagnostico-storage",

                "/diagnostico-auth"

            ]
        }
    )


# =========================================================
# STATUS DA SESSÃO
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

            "session_storage_existe":
                os.path.exists(
                    SESSION_STORAGE_FILE
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


        tempo = round(
            time.time() -
            inicio,
            2
        )


        resultado[
            "tempo_segundos"
        ] = tempo


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
# DIAGNÓSTICO STORAGE STATE
# =========================================================

@app.route(
    "/diagnostico-storage",
    methods=["GET"]
)
def diagnostico_storage():

    try:

        if not os.path.exists(
            SESSION_FILE
        ):

            return jsonify(
                {
                    "status":
                        "erro",

                    "mensagem":
                        "Storage state ainda não existe. "
                        "Execute /gerar-sessao primeiro."
                }
            ), 400


        with open(
            SESSION_FILE,
            "r",
            encoding="utf-8"
        ) as arquivo:

            state = json.load(
                arquivo
            )


        cookies_saida = []


        for cookie in state.get(
            "cookies",
            []
        ):

            nome = cookie.get(
                "name",
                ""
            )


            cookies_saida.append(
                {
                    "nome":
                        nome,

                    "dominio":
                        cookie.get(
                            "domain"
                        ),

                    "path":
                        cookie.get(
                            "path"
                        ),

                    "http_only":
                        cookie.get(
                            "httpOnly"
                        ),

                    "secure":
                        cookie.get(
                            "secure"
                        ),

                    "suspeita_auth":
                        parece_chave_auth(
                            nome
                        )
                }
            )


        origins_saida = []


        for origin in state.get(
            "origins",
            []
        ):

            storage_saida = []


            for entrada in origin.get(
                "localStorage",
                []
            ):

                nome = entrada.get(
                    "name",
                    ""
                )

                valor = entrada.get(
                    "value"
                )


                info = descrever_valor_seguro(
                    valor
                )


                storage_saida.append(
                    {
                        "nome":
                            nome,

                        "suspeita_auth":
                            parece_chave_auth(
                                nome
                            ),

                        "tamanho_valor":
                            info[
                                "tamanho"
                            ],

                        "parece_json":
                            info[
                                "parece_json"
                            ],

                        "parece_jwt":
                            info[
                                "parece_jwt"
                            ]
                    }
                )


            origins_saida.append(
                {
                    "origin":
                        origin.get(
                            "origin"
                        ),

                    "local_storage":
                        storage_saida
                }
            )


        session_storage_saida = []


        if os.path.exists(
            SESSION_STORAGE_FILE
        ):

            try:

                with open(
                    SESSION_STORAGE_FILE,
                    "r",
                    encoding="utf-8"
                ) as arquivo:

                    ss = json.load(
                        arquivo
                    )


                for nome, valor in ss.items():

                    info = descrever_valor_seguro(
                        valor
                    )


                    session_storage_saida.append(
                        {
                            "nome":
                                nome,

                            "suspeita_auth":
                                parece_chave_auth(
                                    nome
                                ),

                            "tamanho_valor":
                                info[
                                    "tamanho"
                                ],

                            "parece_json":
                                info[
                                    "parece_json"
                                ],

                            "parece_jwt":
                                info[
                                    "parece_jwt"
                                ]
                        }
                    )

            except Exception:

                pass


        return jsonify(
            {
                "status":
                    "ok",

                "cookies_quantidade":
                    len(
                        cookies_saida
                    ),

                "cookies":
                    cookies_saida,

                "origins":
                    origins_saida,

                "session_storage":
                    session_storage_saida,

                "seguranca":
                    (
                        "Valores sensíveis não são "
                        "exibidos neste diagnóstico."
                    )
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
# DIAGNÓSTICO DE AUTENTICAÇÃO
# =========================================================

@app.route(
    "/diagnostico-auth",
    methods=["GET"]
)
def diagnostico_auth():

    try:

        if not sessao_existe():

            return jsonify(
                {
                    "status":
                        "erro",

                    "mensagem":
                        "Sessão não está válida."
                }
            ), 400


        candidatos = []


        with open(
            SESSION_FILE,
            "r",
            encoding="utf-8"
        ) as arquivo:

            state = json.load(
                arquivo
            )


        for cookie in state.get(
            "cookies",
            []
        ):

            nome = cookie.get(
                "name",
                ""
            )


            if parece_chave_auth(
                nome
            ):

                candidatos.append(
                    {
                        "origem":
                            "cookie",

                        "nome":
                            nome,

                        "dominio":
                            cookie.get(
                                "domain"
                            )
                    }
                )


        for origin in state.get(
            "origins",
            []
        ):

            for entrada in origin.get(
                "localStorage",
                []
            ):

                nome = entrada.get(
                    "name",
                    ""
                )

                valor = entrada.get(
                    "value"
                )


                info = descrever_valor_seguro(
                    valor
                )


                if (
                    parece_chave_auth(
                        nome
                    )
                    or info[
                        "parece_jwt"
                    ]
                ):

                    candidatos.append(
                        {
                            "origem":
                                "localStorage",

                            "origin":
                                origin.get(
                                    "origin"
                                ),

                            "nome":
                                nome,

                            "parece_jwt":
                                info[
                                    "parece_jwt"
                                ],

                            "tamanho_valor":
                                info[
                                    "tamanho"
                                ]
                        }
                    )


        if os.path.exists(
            SESSION_STORAGE_FILE
        ):

            try:

                with open(
                    SESSION_STORAGE_FILE,
                    "r",
                    encoding="utf-8"
                ) as arquivo:

                    ss = json.load(
                        arquivo
                    )


                for nome, valor in ss.items():

                    info = descrever_valor_seguro(
                        valor
                    )


                    if (
                        parece_chave_auth(
                            nome
                        )
                        or info[
                            "parece_jwt"
                        ]
                    ):

                        candidatos.append(
                            {
                                "origem":
                                    "sessionStorage",

                                "nome":
                                    nome,

                                "parece_jwt":
                                    info[
                                        "parece_jwt"
                                    ],

                                "tamanho_valor":
                                    info[
                                        "tamanho"
                                    ]
                            }
                        )

            except Exception:

                pass


        return jsonify(
            {
                "status":
                    "ok",

                "quantidade_candidatos":
                    len(
                        candidatos
                    ),

                "candidatos":
                    candidatos,

                "valores_expostos":
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
# TESTAR SESSÃO VIA HTTP
# =========================================================

@app.route(
    "/teste-sessao-http",
    methods=["GET"]
)
def teste_sessao_http():

    try:

        inicio = time.time()


        garantia = garantir_sessao()


        session = criar_requests_session()


        resposta = session.get(
            MATEUS_URL,
            timeout=30,
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

                "http_status":
                    resposta.status_code,

                "url_final":
                    resposta.url,

                "tempo_segundos":
                    tempo,

                "cookies":
                    len(
                        session.cookies
                    )
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
# EXECUTAR COMPRA - ANÁLISE
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
