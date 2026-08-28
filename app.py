from flask import Flask, request, jsonify
from playwright.sync_api import sync_playwright

import os
import re
import json
import time
import statistics
import traceback
import requests

from urllib.parse import urlencode


app = Flask(__name__)


# =========================================================
# CONFIGURAÇÕES
# =========================================================

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
# QUANTIDADE
# =========================================================

def quantidade_inteira(valor):

    try:

        if valor is None:
            return 1

        texto = str(
            valor
        ).strip()

        match = re.search(
            r"\d+",
            texto
        )

        if not match:
            return 1

        return max(
            int(
                match.group()
            ),
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
# ID
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
# DISPONIBILIDADE
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
# PREFERÊNCIA FORTE
# =========================================================

def preferencia_corresponde(
    produto,
    descricao
):

    descricao_sem_tamanho = (
        remover_tamanho(
            descricao
        )
    )

    preferencia = normalizar_texto(
        descricao_sem_tamanho
    )

    if not preferencia:
        return False

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
    ).strip()

    if preferencia in texto_produto:
        return True

    palavras = [
        palavra
        for palavra in preferencia.split()
        if len(
            palavra
        ) >= 2
    ]

    if not palavras:
        return False

    return all(
        palavra in texto_produto
        for palavra in palavras
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

            if not produto_disponivel(
                produto
            ):
                continue

            if not tamanho_compativel(
                produto,
                tamanho
            ):
                continue

            if not preferencia_corresponde(
                produto,
                descricao
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

            candidatos.append(
                produto
            )

        if not candidatos:
            continue

        candidatos.sort(
            key=lambda produto:
                produto.get(
                    "preco_efetivo"
                )
                or 999999
        )

        escolhido = candidatos[
            0
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
                    f"{prioridade} atendida: "
                    f"{descricao}."
                )
        }

    return None


# =========================================================
# TERMOS SIGNIFICATIVOS
# =========================================================

PALAVRAS_IGNORADAS = {
    "de",
    "da",
    "do",
    "das",
    "dos",
    "e",
    "em",
    "com",
    "para",
    "por",
    "a",
    "o"
}


def termos_significativos(
    texto
):

    texto = normalizar_texto(
        texto
    )

    return [
        termo
        for termo in texto.split()
        if (
            termo not in
            PALAVRAS_IGNORADAS
            and len(
                termo
            ) >= 2
        )
    ]


# =========================================================
# EQUIVALÊNCIA SEMÂNTICA RÍGIDA
# =========================================================

def equivalencia_semantica(
    item,
    produto
):

    """
    Regra principal:

    1 conceito:
    pode aparecer no nome, categoria ou seção.

    2 conceitos:
    os dois precisam estar no NOME.

    3+ conceitos:
    os dois primeiros precisam estar no NOME
    e pelo menos 75% dos termos totais também.

    Exemplos:

    Peito de frango
    -> precisa conter PEITO + FRANGO no nome.

    Galinha Congelada Inteira
    -> reprova.

    Água micelar
    -> precisa conter ÁGUA + MICELAR no nome.

    Papel manteiga
    -> precisa conter PAPEL + MANTEIGA no nome.
    """

    termos = termos_significativos(
        item
    )

    if not termos:
        return True

    nome = normalizar_texto(
        produto.get(
            "nome",
            ""
        )
    )

    categoria = normalizar_texto(
        produto.get(
            "categoria",
            ""
        )
    )

    secao = normalizar_texto(
        produto.get(
            "secao",
            ""
        )
    )

    # =====================================================
    # UM CONCEITO
    # =====================================================

    if len(
        termos
    ) == 1:

        termo = termos[
            0
        ]

        return (
            termo in nome
            or termo in categoria
            or termo in secao
        )

    # =====================================================
    # DOIS CONCEITOS
    # =====================================================

    if len(
        termos
    ) == 2:

        return all(
            termo in nome
            for termo in termos
        )

    # =====================================================
    # TRÊS OU MAIS CONCEITOS
    # =====================================================

    conceitos_principais = termos[
        :2
    ]

    principais_ok = all(
        termo in nome
        for termo in conceitos_principais
    )

    if not principais_ok:
        return False

    acertos_nome = sum(
        1
        for termo in termos
        if termo in nome
    )

    proporcao = (
        acertos_nome /
        len(
            termos
        )
    )

    return proporcao >= 0.75


# =========================================================
# QUALIFICADORES ESPECIAIS
# =========================================================

QUALIFICADORES_ESPECIAIS = [

    "defumado",
    "defumada",

    "light",

    "diet",

    "zero",

    "premium",

    "especial",

    "gourmet",

    "bifasico",
    "bifasica",

    "regenerador",
    "regeneradora",

    "detox",

    "profissional",

    "importado",
    "importada",

    "temperado",
    "temperada",

    "empanado",
    "empanada",

    "recheado",
    "recheada"
]


def penalidade_qualificadores(
    item,
    produto
):

    termo_item = normalizar_texto(
        item
    )

    nome_produto = normalizar_texto(
        produto.get(
            "nome",
            ""
        )
    )

    penalidade = 0

    for qualificador in QUALIFICADORES_ESPECIAIS:

        if (
            qualificador in nome_produto
            and
            qualificador not in termo_item
        ):

            penalidade += 0.25

    return min(
        penalidade,
        1.0
    )


# =========================================================
# RELEVÂNCIA
# =========================================================

def relevancia_produto(
    item,
    produto
):

    termos = termos_significativos(
        item
    )

    if not termos:
        return 0

    nome = normalizar_texto(
        produto.get(
            "nome",
            ""
        )
    )

    categoria = normalizar_texto(
        produto.get(
            "categoria",
            ""
        )
    )

    secao = normalizar_texto(
        produto.get(
            "secao",
            ""
        )
    )

    texto = (
        nome +
        " " +
        categoria +
        " " +
        secao
    )

    acertos = sum(
        1
        for termo in termos
        if termo in texto
    )

    return (
        acertos /
        len(
            termos
        )
    )


# =========================================================
# TIPO DE MEDIDA DOMINANTE
# =========================================================

def tipo_medida_dominante(
    produtos
):

    contagem = {}

    for produto in produtos:

        tipo = produto.get(
            "tipo_medida"
        )

        if not tipo:
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
    tipo
):

    medidas = []

    for produto in produtos:

        if produto.get(
            "tipo_medida"
        ) != tipo:

            continue

        try:

            medida = float(
                produto.get(
                    "medida"
                )
            )

            if medida > 0:

                medidas.append(
                    medida
                )

        except Exception:

            continue

    if not medidas:
        return None

    return statistics.median(
        medidas
    )


# =========================================================
# PENALIDADE DE EMBALAGEM
# =========================================================

def penalidade_embalagem(
    medida,
    referencia
):

    if (
        medida is None
        or referencia is None
    ):

        return 0.40

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

            return 0.40

        razao = (
            medida /
            referencia
        )

        if razao < 0.40:

            return 1.20

        if razao < 0.65:

            return 0.70

        if (
            razao >= 0.65
            and razao <= 1.60
        ):

            return 0

        if razao <= 2.30:

            return 0.35

        return 0.90

    except Exception:

        return 0.40


# =========================================================
# MELHOR CUSTO-BENEFÍCIO
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

    # =====================================================
    # FILTRO SEMÂNTICO
    # =====================================================

    semanticamente_validos = [
        produto
        for produto in disponiveis
        if equivalencia_semantica(
            item,
            produto
        )
    ]

    if semanticamente_validos:

        disponiveis = (
            semanticamente_validos
        )

    # =====================================================
    # MEDIDA DOMINANTE
    # =====================================================

    tipo_dominante = (
        tipo_medida_dominante(
            disponiveis
        )
    )

    referencia = None

    if tipo_dominante:

        referencia = tamanho_referencia(
            disponiveis,
            tipo_dominante
        )

    # =====================================================
    # MENOR PREÇO ABSOLUTO
    # =====================================================

    precos_absolutos = [

        produto.get(
            "preco_efetivo"
        )

        for produto in disponiveis

        if produto.get(
            "preco_efetivo"
        ) is not None

    ]

    menor_preco = (
        min(
            precos_absolutos
        )
        if precos_absolutos
        else 1
    )

    # =====================================================
    # MENOR PREÇO POR MEDIDA
    # =====================================================

    precos_medida = [

        produto.get(
            "preco_por_medida"
        )

        for produto in disponiveis

        if (
            produto.get(
                "preco_por_medida"
            )
            is not None
            and
            (
                not tipo_dominante
                or
                produto.get(
                    "tipo_medida"
                )
                ==
                tipo_dominante
            )
        )

    ]

    menor_preco_medida = (
        min(
            precos_medida
        )
        if precos_medida
        else None
    )

    ranking = []

    for produto in disponiveis:

        preco = produto.get(
            "preco_efetivo"
        )

        preco_medida = produto.get(
            "preco_por_medida"
        )

        tipo = produto.get(
            "tipo_medida"
        )

        medida = produto.get(
            "medida"
        )

        relevancia = relevancia_produto(
            item,
            produto
        )

        semantica_ok = equivalencia_semantica(
            item,
            produto
        )

        # -----------------------------------------
        # PREÇO ABSOLUTO
        # -----------------------------------------

        if (
            preco
            and menor_preco > 0
        ):

            score_preco_absoluto = (
                preco /
                menor_preco
            )

        else:

            score_preco_absoluto = 2

        # -----------------------------------------
        # PREÇO POR MEDIDA
        # -----------------------------------------

        if (
            preco_medida is not None
            and
            menor_preco_medida
            and
            menor_preco_medida > 0
        ):

            score_preco_medida = (
                preco_medida /
                menor_preco_medida
            )

        else:

            score_preco_medida = 1.5

        # -----------------------------------------
        # EMBALAGEM
        # -----------------------------------------

        if (
            tipo_dominante
            and
            tipo ==
            tipo_dominante
        ):

            penalidade_tamanho = (
                penalidade_embalagem(
                    medida,
                    referencia
                )
            )

        else:

            penalidade_tamanho = 0.70

        # -----------------------------------------
        # QUALIFICADORES
        # -----------------------------------------

        penalidade_especial = (
            penalidade_qualificadores(
                item,
                produto
            )
        )

        # -----------------------------------------
        # RELEVÂNCIA
        # -----------------------------------------

        penalidade_relevancia = (
            1 -
            relevancia
        )

        # -----------------------------------------
        # SEMÂNTICA
        # -----------------------------------------

        penalidade_semantica = (
            0
            if semantica_ok
            else 2.0
        )

        # -----------------------------------------
        # ESTOQUE
        # -----------------------------------------

        penalidade_estoque = 0

        try:

            estoque = float(
                produto.get(
                    "estoque"
                )
            )

            if estoque <= 2:

                penalidade_estoque = 0.35

            elif estoque <= 5:

                penalidade_estoque = 0.15

        except Exception:

            pass

        # =================================================
        # SCORE FINAL
        # =================================================

        score_final = (

            score_preco_absoluto
            * 0.25

            +

            score_preco_medida
            * 0.25

            +

            penalidade_tamanho
            * 0.15

            +

            penalidade_especial
            * 0.20

            +

            penalidade_relevancia
            * 0.15

            +

            penalidade_semantica
            * 1.00

            +

            penalidade_estoque
            * 0.05

        )

        ranking.append(
            {
                "produto":
                    produto,

                "score":
                    round(
                        score_final,
                        4
                    ),

                "semantica_ok":
                    semantica_ok,

                "relevancia":
                    round(
                        relevancia,
                        4
                    ),

                "penalidade_especial":
                    round(
                        penalidade_especial,
                        4
                    )
            }
        )

    ranking.sort(
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

    melhor = ranking[
        0
    ]

    top_3 = []

    for candidato in ranking[
        :3
    ]:

        produto = candidato[
            "produto"
        ]

        top_3.append(
            {
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
                    ),

                "semantica_ok":
                    candidato[
                        "semantica_ok"
                    ],

                "score":
                    candidato[
                        "score"
                    ]
            }
        )

    return {

        "produto":
            melhor[
                "produto"
            ],

        "score":
            melhor[
                "score"
            ],

        "semantica_ok":
            melhor[
                "semantica_ok"
            ],

        "tipo_medida_referencia":
            tipo_dominante,

        "tamanho_referencia":
            referencia,

        "top_3":
            top_3
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

            "alternativas":
                (
                    alternativa[
                        "top_3"
                    ]
                    if alternativa
                    else []
                ),

            "motivo":
                (
                    "Nenhuma preferência foi atendida "
                    "respeitando marca, tamanho e limite de preço."
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

        "escolhido":
            custo[
                "produto"
            ],

        "sugestao":
            None,

        "motivo":
            (
                "Escolhido após validação semântica "
                "do produto e comparação de preço, "
                "embalagem e disponibilidade."
            ),

        "criterio":
            {
                "score":
                    custo[
                        "score"
                    ],

                "semantica_ok":
                    custo[
                        "semantica_ok"
                    ],

                "tipo_medida_referencia":
                    custo[
                        "tipo_medida_referencia"
                    ],

                "tamanho_referencia":
                    custo[
                        "tamanho_referencia"
                    ]
            },

        "alternativas":
            custo[
                "top_3"
            ]
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

        idade = (
            time.time()
            -
            meta.get(
                "timestamp",
                0
            )
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
            "Credenciais do Mateus não configuradas."
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

        page.locator(
            'input#login'
        ).wait_for(
            state="visible",
            timeout=30000
        )

        page.locator(
            'input#login'
        ).fill(
            usuario
        )

        page.locator(
            'input#password'
        ).fill(
            senha
        )

        page.locator(
            'button[type="submit"]'
        ).click()

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

        capturar_session_storage(
            page
        )

        salvar_meta_sessao()

        browser.close()

    return {

        "status":
            "LOGIN_OK",

        "autenticado":
            True,

        "url":
            url_final
    }


# =========================================================
# STORAGE
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

def criar_requests_session():

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
# ENVIAR CARRINHO
# =========================================================

def enviar_lote_carrinho(
    produtos_payload
):

    session = criar_requests_session()

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

    dados = None

    try:

        dados = resposta.json()

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

        "resposta":
            dados,

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

        if not nome:
            continue

        try:

            decisao = decidir_item(
                nome,
                preferencias
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

        produto = decisao.get(
            "escolhido"
        )

        if (
            decisao.get(
                "status"
            )
            ==
            "PREFERENCIA_NAO_ATENDIDA"
        ):

            if aceitar_alternativas:

                produto = decisao.get(
                    "sugestao"
                )

            else:

                ignorados.append(
                    {
                        "item":
                            nome,

                        "quantidade":
                            quantidade,

                        "status":
                            "PREFERENCIA_NAO_ATENDIDA",

                        "motivo":
                            decisao.get(
                                "motivo"
                            ),

                        "sugestao":
                            decisao.get(
                                "sugestao"
                            ),

                        "alternativas":
                            decisao.get(
                                "alternativas",
                                []
                            )
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
                        decisao.get(
                            "status"
                        ),

                    "motivo":
                        decisao.get(
                            "motivo"
                        )
                }
            )

            continue

        produto_id = extrair_produto_id(
            produto
        )

        preco = produto.get(
            "preco_efetivo"
        )

        subtotal = (
            float(
                preco
            )
            *
            quantidade
            if preco
            else 0
        )

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
                    decisao.get(
                        "status"
                    ),

                "preferencia_atendida":
                    decisao.get(
                        "preferencia_atendida"
                    ),

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
                            preco,

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
                    ),

                "alternativas":
                    decisao.get(
                        "alternativas",
                        []
                    )
            }
        )

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

    return {

        "produtos_payload":
            list(
                consolidado.values()
            ),

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
                consolidado
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

            "rotas": [
                "/",
                "/gerar-sessao",
                "/status-sessao",
                "/executar-compra",
                "/montar-carrinho"
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

    return jsonify(
        {
            "status":
                "ok",

            "sessao_valida":
                sessao_existe(),

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

        resultado = gerar_sessao()

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
# ANALISAR COMPRA
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
            )

            quantidade = quantidade_inteira(
                entrada.get(
                    "quantidade",
                    1
                )
            )

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
# MONTAR CARRINHO
# =========================================================

@app.route(
    "/montar-carrinho",
    methods=["POST"]
)
def montar_carrinho():

    inicio = time.time()

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

        preparado = preparar_lote(
            itens,
            aceitar_alternativas
        )

        if simular:

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
                                round(
                                    time.time()
                                    -
                                    inicio,
                                    2
                                )
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
                                preparado[
                                    "produtos_payload"
                                ],

                            "price_table":
                                "00"
                        }
                }
            )

        if not preparado[
            "produtos_payload"
        ]:

            return jsonify(
                {
                    "status":
                        "SEM_PRODUTOS_APROVADOS",

                    "simulacao":
                        False,

                    "ignorados":
                        preparado[
                            "ignorados"
                        ]
                }
            )

        sessao = garantir_sessao()

        carrinho = enviar_lote_carrinho(
            preparado[
                "produtos_payload"
            ]
        )

        return jsonify(
            {
                "status":
                    (
                        "CARRINHO_MONTADO"
                        if carrinho[
                            "sucesso"
                        ]
                        else
                        "ERRO_CARRINHO"
                    ),

                "simulacao":
                    False,

                "mercado":
                    "Supermercado Mateus Cohama",

                "sessao":
                    sessao,

                "carrinho":
                    carrinho,

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
                            round(
                                time.time()
                                -
                                inicio,
                                2
                            )
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
