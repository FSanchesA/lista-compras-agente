from flask import Flask, request, jsonify
from playwright.sync_api import sync_playwright

import os
import re
import json
import time
import math
import statistics
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
        "ä": "a",
        "é": "e",
        "ê": "e",
        "ë": "e",
        "í": "i",
        "ï": "i",
        "ó": "o",
        "ô": "o",
        "õ": "o",
        "ö": "o",
        "ú": "u",
        "ü": "u",
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
# CONVERTER QUANTIDADE
# =========================================================

def quantidade_inteira(valor):

    try:

        if valor is None:
            return 1

        texto = str(
            valor
        ).strip()

        if not texto:
            return 1

        match = re.search(
            r"\d+",
            texto
        )

        if not match:
            return 1

        quantidade = int(
            match.group()
        )

        return max(
            quantidade,
            1
        )

    except Exception:

        return 1


# =========================================================
# PREFERÊNCIAS
# =========================================================

def parse_preferencias(texto):

    if not texto:
        return []

    partes = [
        p.strip()
        for p in str(
            texto
        ).split(";")
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

        if not match:
            continue

        valor = (
            match
            .group(1)
            .replace(",", ".")
        )

        try:

            return {
                "valor":
                    float(
                        valor
                    ),

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
        str(
            texto
        ),
        flags=re.IGNORECASE
    )

    texto = re.sub(
        r"\s+",
        " ",
        texto
    )

    return texto.strip()


# =========================================================
# ID DO PRODUTO
# =========================================================

def extrair_produto_id(produto):

    if not isinstance(
        produto,
        dict
    ):
        return None

    candidatos = [
        "id",
        "objectID",
        "objectId",
        "product_id",
        "productId",
        "product_uuid",
        "uuid"
    ]

    for campo in candidatos:

        valor = produto.get(
            campo
        )

        if valor not in [
            None,
            "",
            "None"
        ]:

            return str(
                valor
            )

    return None


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

    produto_id = extrair_produto_id(
        produto
    )

    preco_por_medida = None

    try:

        if (
            preco
            and medida
            and float(
                medida
            ) > 0
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
            produto_id,

        "sku":
            produto.get(
                "sku"
            ),

        "barcode":
            produto.get(
                "barcode"
            ),

        "nome":
            (
                produto.get(
                    "name"
                )
                or
                produto.get(
                    "nome"
                )
            ),

        "marca":
            (
                produto.get(
                    "brand"
                )
                or
                produto.get(
                    "marca"
                )
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
                is not None
                else None
            ),

        "for_sale":
            produto.get(
                "for_sale"
            ),

        "imagem":
            (
                produto.get(
                    "small_image"
                )
                or
                produto.get(
                    "image"
                )
            )
    }


# =========================================================
# BUSCA NA API DO MATEUS
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
# PRODUTO DISPONÍVEL
# =========================================================

def produto_disponivel(
    produto
):

    if not produto:
        return False

    if produto.get(
        "for_sale"
    ) is False:

        return False

    estoque = produto.get(
        "estoque"
    )

    if (
        estoque is not None
        and estoque <= 0
    ):

        return False

    if produto.get(
        "preco_efetivo"
    ) is None:

        return False

    if not extrair_produto_id(
        produto
    ):

        return False

    return True


# =========================================================
# TAMANHO COMPATÍVEL
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


# =========================================================
# SCORE DE COMPATIBILIDADE COM PREFERÊNCIA
# =========================================================

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
        if len(
            x
        ) >= 2
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
# ESCOLHER PELA PREFERÊNCIA
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

            if not produto_disponivel(
                produto
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

        if not candidatos:

            continue

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
                    f"Preferência nº "
                    f"{prioridade} atendida."
                )

        }

    return None


# =========================================================
# MEDIDA PADRÃO DA BUSCA
# =========================================================

def obter_tipo_medida_dominante(
    produtos
):

    contagem = {}

    for produto in produtos:

        if not produto_disponivel(
            produto
        ):

            continue

        tipo = produto.get(
            "tipo_medida"
        )

        medida = produto.get(
            "medida"
        )

        if (
            not tipo
            or medida is None
        ):

            continue

        contagem[
            tipo
        ] = (
            contagem.get(
                tipo,
                0
            )
            + 1
        )

    if not contagem:

        return None

    return max(
        contagem,
        key=
            contagem.get
    )


# =========================================================
# TAMANHO DE REFERÊNCIA
# =========================================================

def tamanho_referencia(
    produtos,
    tipo_medida
):

    medidas = []

    for produto in produtos:

        if not produto_disponivel(
            produto
        ):

            continue

        if produto.get(
            "tipo_medida"
        ) != tipo_medida:

            continue

        medida = produto.get(
            "medida"
        )

        try:

            medida = float(
                medida
            )

        except Exception:

            continue

        if medida > 0:

            medidas.append(
                medida
            )

    if not medidas:

        return None

    try:

        return statistics.median(
            medidas
        )

    except Exception:

        return None


# =========================================================
# PENALIDADE DE TAMANHO
# =========================================================

def penalidade_tamanho(
    medida,
    referencia
):

    if (
        medida is None
        or referencia is None
    ):

        return 0.35

    try:

        medida = float(
            medida
        )

        referencia = float(
            referencia
        )

        if (
            medida <= 0
            or referencia <= 0
        ):

            return 0.35

        razao = (
            medida /
            referencia
        )

        diferenca_log = abs(
            math.log(
                razao
            )
        )

        return min(
            diferenca_log,
            2.0
        )

    except Exception:

        return 0.35


# =========================================================
# MELHOR CUSTO-BENEFÍCIO SEM PREFERÊNCIA
# =========================================================

def escolher_melhor_custo_beneficio(
    item,
    produtos
):

    disponiveis = [
        produto
        for produto in produtos
        if produto_disponivel(
            produto
        )
    ]

    if not disponiveis:

        return None

    tipo_dominante = (
        obter_tipo_medida_dominante(
            disponiveis
        )
    )

    referencia = None

    if tipo_dominante:

        referencia = tamanho_referencia(
            disponiveis,
            tipo_dominante
        )

    candidatos = []

    precos_unitarios = [
        produto.get(
            "preco_por_medida"
        )
        for produto in disponiveis
        if (
            produto.get(
                "preco_por_medida"
            ) is not None
            and (
                not tipo_dominante
                or produto.get(
                    "tipo_medida"
                ) == tipo_dominante
            )
        )
    ]

    menor_preco_unitario = (
        min(
            precos_unitarios
        )
        if precos_unitarios
        else None
    )

    for produto in disponiveis:

        tipo = produto.get(
            "tipo_medida"
        )

        medida = produto.get(
            "medida"
        )

        preco = produto.get(
            "preco_efetivo"
        )

        preco_unidade = produto.get(
            "preco_por_medida"
        )

        # ---------------------------------------------
        # PENALIDADE POR TIPO DE MEDIDA FORA DO PADRÃO
        # ---------------------------------------------

        penalidade_tipo = 0

        if (
            tipo_dominante
            and tipo
            and tipo != tipo_dominante
        ):

            penalidade_tipo = 1.0

        # ---------------------------------------------
        # PENALIDADE POR TAMANHO FORA DA MEDIANA
        # ---------------------------------------------

        penalidade_embalagem = (
            penalidade_tamanho(
                medida,
                referencia
            )
            if (
                tipo_dominante
                and tipo ==
                    tipo_dominante
            )
            else 0.6
        )

        # ---------------------------------------------
        # SCORE DE PREÇO UNITÁRIO
        # ---------------------------------------------

        score_preco = 1.0

        if (
            preco_unidade is not None
            and menor_preco_unitario
            and menor_preco_unitario > 0
        ):

            score_preco = (
                preco_unidade /
                menor_preco_unitario
            )

        elif preco is not None:

            score_preco = 1.5

        # ---------------------------------------------
        # ESTOQUE
        # ---------------------------------------------

        estoque = produto.get(
            "estoque"
        )

        penalidade_estoque = 0

        try:

            if estoque is not None:

                estoque_num = float(
                    estoque
                )

                if estoque_num <= 2:

                    penalidade_estoque = 0.35

                elif estoque_num <= 5:

                    penalidade_estoque = 0.15

        except Exception:

            pass

        # ---------------------------------------------
        # SCORE FINAL
        #
        # preço/kg/L importa,
        # mas tamanho comercial também importa.
        # ---------------------------------------------

        score_final = (
            score_preco * 0.60
            +
            penalidade_embalagem * 0.30
            +
            penalidade_tipo * 0.20
            +
            penalidade_estoque * 0.10
        )

        candidatos.append(
            {
                "produto":
                    produto,

                "score":
                    score_final,

                "score_preco":
                    round(
                        score_preco,
                        4
                    ),

                "penalidade_embalagem":
                    round(
                        penalidade_embalagem,
                        4
                    ),

                "referencia_medida":
                    referencia,

                "tipo_dominante":
                    tipo_dominante
            }
        )

    candidatos.sort(
        key=lambda x:
            (
                x[
                    "score"
                ],
                x[
                    "produto"
                ].get(
                    "preco_efetivo"
                )
                or 999999
            )
    )

    melhor = candidatos[
        0
    ]

    produto = melhor[
        "produto"
    ]

    return {

        "produto":
            produto,

        "criterio":
            "MELHOR_CUSTO_BENEFICIO",

        "tipo_medida_referencia":
            melhor[
                "tipo_dominante"
            ],

        "tamanho_referencia":
            melhor[
                "referencia_medida"
            ],

        "score":
            round(
                melhor[
                    "score"
                ],
                4
            )

    }


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

    if not produtos:

        return {

            "status":
                "NAO_ENCONTRADO",

            "item":
                nome,

            "preferencias":
                preferencias,

            "escolhido":
                None,

            "sugestao":
                None,

            "motivo":
                "Nenhum produto retornado pela busca."

        }

    # =====================================================
    # COM PREFERÊNCIA
    # =====================================================

    if preferencias:

        escolha = escolher_por_preferencia(
            nome,
            preferencias,
            produtos
        )

        if escolha:

            return escolha

        alternativa = (
            escolher_melhor_custo_beneficio(
                nome,
                produtos
            )
        )

        return {

            "status":
                "PREFERENCIA_NAO_ATENDIDA",

            "item":
                nome,

            "preferencias":
                preferencias,

            "escolhido":
                None,

            "sugestao":
                (
                    alternativa[
                        "produto"
                    ]
                    if alternativa
                    else None
                ),

            "motivo":
                (
                    "Nenhuma preferência foi atendida. "
                    "Alternativa disponível para avaliação."
                )

        }

    # =====================================================
    # SEM PREFERÊNCIA
    # =====================================================

    custo = escolher_melhor_custo_beneficio(
        nome,
        produtos
    )

    if not custo:

        return {

            "status":
                "NAO_ENCONTRADO",

            "item":
                nome,

            "preferencias":
                [],

            "escolhido":
                None,

            "sugestao":
                None,

            "motivo":
                "Nenhum produto disponível."

        }

    return {

        "status":
            "MELHOR_CUSTO_BENEFICIO",

        "item":
            nome,

        "preferencias":
            [],

        "escolhido":
            custo[
                "produto"
            ],

        "sugestao":
            None,

        "motivo":
            (
                "Escolhido por custo-benefício, "
                "considerando preço proporcional, "
                "tamanho de embalagem e disponibilidade."
            ),

        "criterio":
            {
                "tipo_medida_referencia":
                    custo[
                        "tipo_medida_referencia"
                    ],

                "tamanho_referencia":
                    custo[
                        "tamanho_referencia"
                    ],

                "score":
                    custo[
                        "score"
                    ]
            }

    }


# =========================================================
# PLAYWRIGHT
# =========================================================

def criar_browser(
    playwright
):

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
# SESSION STORAGE
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

    if (
        sessao_existe()
        and obter_auth_token()
    ):

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
# HTTP AUTENTICADO
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
# ENVIAR LOTE AO CARRINHO
# =========================================================

def enviar_lote_carrinho(
    produtos_payload
):

    if not produtos_payload:

        raise Exception(
            "Nenhum produto para enviar ao carrinho."
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

        "products":
            produtos_payload,

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

    texto_resposta = None

    try:

        dados_resposta = resposta.json()

    except Exception:

        texto_resposta = (
            resposta.text[
                :1000
            ]
        )

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

        "quantidade_produtos_payload":
            len(
                produtos_payload
            ),

        "resposta":
            dados_resposta,

        "resposta_texto":
            texto_resposta,

        "token_exposto":
            False

    }


# =========================================================
# PREPARAR LOTE
# =========================================================

def preparar_lote(
    itens,
    aceitar_alternativas=False
):

    produtos_lote = []

    analisados = []

    ignorados = []

    total_estimado = 0.0

    for entrada in itens:

        nome = str(
            entrada.get(
                "item",
                ""
            )
        ).strip()

        preferencias_texto = str(
            entrada.get(
                "preferencias",
                ""
            )
            or ""
        ).strip()

        quantidade = quantidade_inteira(
            entrada.get(
                "quantidade",
                1
            )
        )

        if not nome:

            ignorados.append(
                {
                    "item":
                        "",

                    "status":
                        "ITEM_VAZIO",

                    "motivo":
                        "Nome do item não informado."
                }
            )

            continue

        try:

            decisao = decidir_item(
                nome,
                preferencias_texto
            )

        except Exception as erro:

            ignorados.append(
                {
                    "item":
                        nome,

                    "status":
                        "ERRO_ANALISE",

                    "motivo":
                        str(
                            erro
                        )
                }
            )

            continue

        status_decisao = decisao.get(
            "status"
        )

        produto = decisao.get(
            "escolhido"
        )

        # ---------------------------------------------
        # PREFERÊNCIA NÃO ATENDIDA
        # ---------------------------------------------

        if (
            status_decisao ==
            "PREFERENCIA_NAO_ATENDIDA"
        ):

            sugestao = decisao.get(
                "sugestao"
            )

            if aceitar_alternativas:

                produto = sugestao

            else:

                ignorados.append(
                    {
                        "item":
                            nome,

                        "quantidade":
                            quantidade,

                        "status":
                            status_decisao,

                        "motivo":
                            decisao.get(
                                "motivo"
                            ),

                        "sugestao":
                            sugestao
                    }
                )

                continue

        if not produto:

            ignorados.append(
                {
                    "item":
                        nome,

                    "quantidade":
                        quantidade,

                    "status":
                        (
                            status_decisao
                            or
                            "NAO_ENCONTRADO"
                        ),

                    "motivo":
                        decisao.get(
                            "motivo"
                        ),

                    "sugestao":
                        decisao.get(
                            "sugestao"
                        )
                }
            )

            continue

        produto_id = extrair_produto_id(
            produto
        )

        if not produto_id:

            ignorados.append(
                {
                    "item":
                        nome,

                    "quantidade":
                        quantidade,

                    "status":
                        "SEM_ID",

                    "motivo":
                        "Produto escolhido sem ID válido."
                }
            )

            continue

        preco = produto.get(
            "preco_efetivo"
        )

        subtotal = 0.0

        try:

            if preco is not None:

                subtotal = (
                    float(
                        preco
                    )
                    *
                    quantidade
                )

        except Exception:

            subtotal = 0.0

        total_estimado += subtotal

        produtos_lote.append(
            {
                "id":
                    produto_id,

                "quantity":
                    quantidade,

                "market_id":
                    MARKET_ID
            }
        )

        analisados.append(
            {
                "item":
                    nome,

                "quantidade":
                    quantidade,

                "status":
                    status_decisao,

                "produto":
                    {
                        "id":
                            produto_id,

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

                        "medida":
                            produto.get(
                                "medida"
                            ),

                        "tipo_medida":
                            produto.get(
                                "tipo_medida"
                            )
                    },

                "subtotal":
                    round(
                        subtotal,
                        2
                    ),

                "motivo":
                    decisao.get(
                        "motivo"
                    )
            }
        )

    # =====================================================
    # CONSOLIDAR IDs REPETIDOS
    # =====================================================

    consolidado = {}

    for produto in produtos_lote:

        produto_id = produto[
            "id"
        ]

        if produto_id not in consolidado:

            consolidado[
                produto_id
            ] = {
                "id":
                    produto_id,

                "quantity":
                    0,

                "market_id":
                    MARKET_ID
            }

        consolidado[
            produto_id
        ][
            "quantity"
        ] += produto[
            "quantity"
        ]

    payload_final = list(
        consolidado.values()
    )

    return {

        "produtos_payload":
            payload_final,

        "analisados":
            analisados,

        "ignorados":
            ignorados,

        "quantidade_recebida":
            len(
                itens
            ),

        "quantidade_aprovada":
            len(
                analisados
            ),

        "quantidade_ignorada":
            len(
                ignorados
            ),

        "quantidade_ids_unicos":
            len(
                payload_final
            ),

        "total_estimado":
            round(
                total_estimado,
                2
            )

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

                "/teste-adicionar-carrinho?item=cafe&quantidade=1",

                "/montar-carrinho"

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
                    str(
                        e
                    ),

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
                    str(
                        e
                    )
            }
        ), 500


# =========================================================
# ANALISAR COMPRA
# NÃO ALTERA CARRINHO
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

        for entrada in itens:

            nome = str(
                entrada.get(
                    "item",
                    ""
                )
            ).strip()

            preferencias = str(
                entrada.get(
                    "preferencias",
                    ""
                )
                or ""
            ).strip()

            quantidade = quantidade_inteira(
                entrada.get(
                    "quantidade",
                    1
                )
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
                            str(
                                e
                            )
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
                    str(
                        e
                    ),

                "trace":
                    traceback.format_exc()
            }
        ), 500


# =========================================================
# MONTAR CARRINHO EM LOTE
# =========================================================

@app.route(
    "/montar-carrinho",
    methods=["POST"]
)
def montar_carrinho():

    inicio_total = time.time()

    try:

        dados = request.get_json(
            force=True
        )

        itens = dados.get(
            "itens",
            []
        )

        simular = bool(
            dados.get(
                "simular",
                False
            )
        )

        aceitar_alternativas = bool(
            dados.get(
                "aceitar_alternativas",
                False
            )
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

        # =================================================
        # ANALISAR TODOS OS ITENS
        # =================================================

        preparado = preparar_lote(
            itens,
            aceitar_alternativas=
                aceitar_alternativas
        )

        produtos_payload = preparado[
            "produtos_payload"
        ]

        # =================================================
        # NENHUM PRODUTO APROVADO
        # =================================================

        if not produtos_payload:

            return jsonify(
                {
                    "status":
                        "SEM_PRODUTOS_APROVADOS",

                    "simulacao":
                        simular,

                    "resumo":
                        {
                            "itens_recebidos":
                                preparado[
                                    "quantidade_recebida"
                                ],

                            "itens_aprovados":
                                0,

                            "itens_ignorados":
                                preparado[
                                    "quantidade_ignorada"
                                ],

                            "total_estimado":
                                preparado[
                                    "total_estimado"
                                ]
                        },

                    "analisados":
                        preparado[
                            "analisados"
                        ],

                    "ignorados":
                        preparado[
                            "ignorados"
                        ]
                }
            ), 200

        # =================================================
        # SIMULAÇÃO
        # NÃO ALTERA CARRINHO
        # =================================================

        if simular:

            tempo_total = round(
                time.time() -
                inicio_total,
                2
            )

            return jsonify(
                {
                    "status":
                        "SIMULACAO_OK",

                    "simulacao":
                        True,

                    "mercado":
                        "Supermercado Mateus Cohama",

                    "resumo":
                        {
                            "itens_recebidos":
                                preparado[
                                    "quantidade_recebida"
                                ],

                            "itens_aprovados":
                                preparado[
                                    "quantidade_aprovada"
                                ],

                            "itens_ignorados":
                                preparado[
                                    "quantidade_ignorada"
                                ],

                            "produtos_unicos":
                                preparado[
                                    "quantidade_ids_unicos"
                                ],

                            "total_estimado":
                                preparado[
                                    "total_estimado"
                                ],

                            "tempo_total_segundos":
                                tempo_total
                        },

                    "analisados":
                        preparado[
                            "analisados"
                        ],

                    "ignorados":
                        preparado[
                            "ignorados"
                        ],

                    "payload_preparado":
                        {
                            "products":
                                produtos_payload,

                            "price_table":
                                "00"
                        }
                }
            )

        # =================================================
        # GARANTIR LOGIN
        # =================================================

        sessao = garantir_sessao()

        # =================================================
        # POST ÚNICO DO CARRINHO
        # =================================================

        resposta_carrinho = (
            enviar_lote_carrinho(
                produtos_payload
            )
        )

        tempo_total = round(
            time.time() -
            inicio_total,
            2
        )

        if not resposta_carrinho[
            "sucesso"
        ]:

            return jsonify(
                {
                    "status":
                        "ERRO_CARRINHO",

                    "simulacao":
                        False,

                    "sessao":
                        sessao,

                    "carrinho":
                        resposta_carrinho,

                    "resumo":
                        {
                            "itens_recebidos":
                                preparado[
                                    "quantidade_recebida"
                                ],

                            "itens_aprovados":
                                preparado[
                                    "quantidade_aprovada"
                                ],

                            "itens_ignorados":
                                preparado[
                                    "quantidade_ignorada"
                                ],

                            "total_estimado":
                                preparado[
                                    "total_estimado"
                                ],

                            "tempo_total_segundos":
                                tempo_total
                        },

                    "analisados":
                        preparado[
                            "analisados"
                        ],

                    "ignorados":
                        preparado[
                            "ignorados"
                        ]
                }
            ), 400

        return jsonify(
            {
                "status":
                    "CARRINHO_MONTADO",

                "simulacao":
                    False,

                "mercado":
                    "Supermercado Mateus Cohama",

                "sessao":
                    sessao,

                "carrinho":
                    resposta_carrinho,

                "resumo":
                    {
                        "itens_recebidos":
                            preparado[
                                "quantidade_recebida"
                            ],

                        "itens_adicionados":
                            preparado[
                                "quantidade_aprovada"
                            ],

                        "itens_ignorados":
                            preparado[
                                "quantidade_ignorada"
                            ],

                        "produtos_unicos":
                            preparado[
                                "quantidade_ids_unicos"
                            ],

                        "total_estimado":
                            preparado[
                                "total_estimado"
                            ],

                        "tempo_total_segundos":
                            tempo_total
                    },

                "adicionados":
                    preparado[
                        "analisados"
                    ],

                "ignorados":
                    preparado[
                        "ignorados"
                    ]
            }
        )

    except Exception as e:

        return jsonify(
            {
                "status":
                    "erro",

                "erro":
                    str(
                        e
                    ),

                "trace":
                    traceback.format_exc()
            }
        ), 500


# =========================================================
# TESTE INDIVIDUAL DO CARRINHO
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

        quantidade = quantidade_inteira(
            request.args.get(
                "quantidade",
                "1"
            )
        )

        sessao = garantir_sessao()

        decisao = decidir_item(
            item,
            preferencias
        )

        produto = decisao.get(
            "escolhido"
        )

        if (
            not produto
            and decisao.get(
                "status"
            ) ==
            "PREFERENCIA_NAO_ATENDIDA"
        ):

            produto = decisao.get(
                "sugestao"
            )

        if not produto:

            return jsonify(
                {
                    "status":
                        "erro",

                    "mensagem":
                        "Nenhum produto encontrado.",

                    "decisao":
                        decisao
                }
            ), 404

        produto_id = extrair_produto_id(
            produto
        )

        payload_produto = [
            {
                "id":
                    produto_id,

                "quantity":
                    quantidade,

                "market_id":
                    MARKET_ID
            }
        ]

        carrinho = enviar_lote_carrinho(
            payload_produto
        )

        return jsonify(
            {
                "status":
                    (
                        "ok"
                        if carrinho[
                            "sucesso"
                        ]
                        else "erro"
                    ),

                "sessao":
                    sessao,

                "item_solicitado":
                    item,

                "decisao":
                    decisao,

                "carrinho":
                    carrinho
            }
        ), (
            200
            if carrinho[
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
                    str(
                        e
                    ),

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
