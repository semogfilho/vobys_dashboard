# -*- coding: utf-8 -*-

def get_query_status_siafe(ano, mes):
    """
    Retorna a matriz pivotada de status simplificada com ROLLUP.
    Converte o mês para inteiro para garantir compatibilidade se armazenado como NUMBER.
    """
    mes_numerico = int(mes)

    query = f"""
    SELECT
        CASE
            WHEN GROUPING(STATUS_DESC) = 1 THEN 'TOTAL GERAL'
            ELSE STATUS_DESC
        END AS STATUS,
        SUM(V1) AS COL,
        SUM(V2) AS CRE,
        SUM(V3) AS ORC,
        SUM(V4) AS PATR,
        (SUM(V1) + SUM(V2) + SUM(V3) + SUM(V4)) AS TOTAL
    FROM (
        SELECT
            CASE
                WHEN STATUS_VOBYS = 'P' THEN 'PENDENTE'
                WHEN STATUS_VOBYS = 'T' THEN 'TRANSMITIDO'
                WHEN STATUS_VOBYS = 'A' THEN 'ABERTO'
                WHEN STATUS_VOBYS = 'F' THEN 'FECHADO'
                WHEN STATUS_VOBYS = 'I' THEN 'INCONSISTENCIA DE CADASTRO'
                WHEN STATUS_VOBYS = 'O' THEN 'OUTRAS INCONSISTENCIA'
                WHEN STATUS_VOBYS = 'E' THEN 'ERRO'
                ELSE STATUS_VOBYS
            END AS STATUS_DESC,
            IND_TIPO_REQUISICAO
        FROM
            sw_publico.SIAFE_EVENTO_INTEGRACAO
        WHERE
            mes = {mes_numerico} AND ano = {ano}
    )
    PIVOT (
        COUNT(*)
        FOR IND_TIPO_REQUISICAO IN ('V1' AS V1, 'V2' AS V2, 'V3' AS V3, 'V4' AS V4)
    )
    GROUP BY ROLLUP(STATUS_DESC)
    ORDER BY GROUPING(STATUS_DESC), STATUS_DESC
    """
    return query


def get_query_folha_fechada(ano, mes):
    """
    Retorna a consulta de validação de folhas fechadas para o período informado.
    """
    periodo = f"{mes}/{ano}"
    query = f"""
    SELECT
        COD_ORGAO,
        DESC_ORGAO,
        STATUS_FECHAMENTO,
        DATA_ALTERACAO
    FROM sw_publico.SIAFE_CONTROLE_FOLHA
    WHERE TO_CHAR(DATA_COMPETENCIA, 'MM/YYYY') = '{periodo}'
    ORDER BY COD_ORGAO
    """
    return query


def get_listas_schemas_responsaveis():
    """
    Retorna as listas de alocação de schemas dos órgãos (SW_) 
    divididas de forma organizada por responsável.
    """
    schemas_jose = [
        'SW_ADAPI', 'SW_ADH', 'SW_BEP', 'SW_CBMPI', 'SW_CCOM', 
        'SW_CENDROGAS', 'SW_COFIR', 'SW_FAPEPI', 'SW_FUESPI', 
        'SW_FUPIP', 'SW_IASPI', 'SW_IDEPI', 'SW_INTERPI', 
        'SW_SEAGRO', 'SW_SURPI', 'SW_TVANTARES'
    ]
    
    schemas_pedro = [
        'SW_SEINFRA', 'SW_SAF', 'SW_COJUV', 'SW_CDTER', 'SW_SEMINPER', 
        'SW_SETRANS', 'SW_AGESPISA', 'SW_SEGOV', 'SW_SEPLAN', 'SW_PGEPI', 
        'SW_PMPI', 'SW_SEFAZPI', 'SW_DER', 'SW_VICEGOV', 'SW_JUCEPI', 'SW_SEDET'
    ]
    
    # Escopo mapeado do Armando
    schemas_armando = ['SW_FUNPREV', 'SW_SSPPI', 'SW_SESAPI', 'SW_SEDUC']
    
    # Órgãos alocados para o Deividy
    schemas_deividy = [
        'SW_SECESP', 'SW_SECULT', 'SW_SETRE', 'SW_DETRAN', 'SW_SEMAR', 
        'SW_SASC', 'SW_IMEPI', 'SW_SEJUSPI', 'SW_SEADPREVPI'
    ]
    
    # Órgãos alocados para a Sarah
    schemas_sarah = [
        'SW_AGRESP', 'SW_SECMULHERES', 'SW_SERES', 'SW_DEFCIVIL', 
        'SW_SECID', 'SW_SEID', 'SW_SETUR', 'SW_SADA', 
        'SW_GAMIL', 'SW_METRO', 'SW_EMGERPI_CORESA', 'SW_EMGERPI_EMATER', 
        'SW_EMGERPI_COMEPI', 'SW_EMGERPI_COMDEPI', 'SW_EMGERPI_COHAB', 'SW_EMGERPI_PRODEPI', 
        'SW_EMGERPI_CEASA', 'SW_EMGERPI_PIEMTUR', 'SW_EMGERPI_ETELPI_FUNART', 'SW_EMGERPI_CIDAPI', 
        'SW_EMGERPI_CODIPI', 'SW_EMGERPI', 'SW_SIA'
    ]
    
    # Retorna as 5 listas mantendo a compatibilidade sequencial (tupla)
    return schemas_jose, schemas_pedro, schemas_armando, schemas_deividy, schemas_sarah


# --- QUERIES ESTÁTICAS ---

QUERY_RESPONSAVEIS = """
SELECT
    'ADMIN' AS RESPONSAVEL,
    ID_SIAFE_EVENTO_INTEGRACAO AS ID
FROM sw_publico.SIAFE_EVENTO_INTEGRACAO
WHERE DATA_CADASTRO >= TRUNC(SYSDATE, 'YEAR')
"""

QUERY_LISTAR_ORGAOS = """
SELECT
    COD_ORGAO,
    SIGLA_ORGAO,
    DESC_ORGAO
FROM sw_publico.SIAFE_ORGAO
WHERE IND_ATIVO = 'S'
ORDER BY COD_ORGAO
"""

