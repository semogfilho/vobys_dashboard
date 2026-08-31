# -*- coding: utf-8 -*-

def get_query_detalhe_erros(ano, mes):
    """
    Retorna a query corrigida utilizando os aliases certos (si.RECIBO e si.IND_TIPO_REQUISICAO)
    para evitar o erro ORA-00904.
    """
    query = f"""
        WITH UltimasOcorrencias AS (
            SELECT 
                o.ID_SIAFE_EVENTO_INTEGRACAO, 
                o.ID_SIAFE_OCORRENCIA_EVENTO, 
                ROW_NUMBER() OVER ( 
                    PARTITION BY o.ID_SIAFE_EVENTO_INTEGRACAO 
                    ORDER BY o.ID_SIAFE_OCORRENCIA_EVENTO DESC 
                ) as rn, 
                o.descricao 
            FROM SW_PUBLICO.SIAFE_OCORRENCIA_EVENTO o 
        ) 
        SELECT 
            'https://siape.sead.pi.gov.br/adm/sead/gerencial/gerencial/integracao-sistema-financeiro-siafe/informacoes-a-transmitir/evento-transmissao/' || si.ID_SIAFE_EVENTO_INTEGRACAO || '/alterar' AS LINK_EVENTO, 
            si.IND_TIPO_REQUISICAO AS TIPO_REQ, -- Adicionado para o Streamlit mapear (V1, V2...)
            si.RECIBO AS NUM_RECIBO,             -- Corrigido de o.recibo para si.recibo
            uo.descricao AS DESCRICAO 
            ,CODIGO_SEFAZ	
            ,TIPO_ARQUIVO
            ,CODIGO_RELATORIO	
            ,DATA_PROCESSAMENTO	

        FROM SW_PUBLICO.SIAFE_EVENTO_INTEGRACAO si 
        LEFT JOIN UltimasOcorrencias uo 
          ON si.ID_SIAFE_EVENTO_INTEGRACAO = uo.ID_SIAFE_EVENTO_INTEGRACAO 
         AND uo.rn = 1 
        WHERE si.ANO = {ano} 
          AND si.MES = {int(mes)} 
          AND si.STATUS_VOBYS in ('X', 'E')
          --AND si.STATUS_VOBYS in ('E')
        ORDER BY si.ID_SIAFE_EVENTO_INTEGRACAO DESC
    """
    return query

def get_query_auditoria_desvios(ano, mes):
    query = f"""
    SELECT
        si.ANO,
        si.MES,si.id_siafe_evento_integracao,
        si.codigo_sefaz,
        si.CHAVE_FOLHA,
        si.DATA_CADASTRO,
        si.DATA_PROCESSAMENTO,
        si.RECIBO,
        si.TIPO_ARQUIVO,
        pr.DATA_inicio AS DATA_INICIO_PROCESSO,
        -- ... (mantenha os CASEs de STATUS e TIPO_REQUISICAO como estão)
        CASE
            WHEN si.STATUS_VOBYS = 'P' THEN 'PENDENTE'
            WHEN si.STATUS_VOBYS = 'T' THEN 'TRANSMITIDO'
            WHEN si.STATUS_VOBYS = 'A' THEN 'ABERTO'
            WHEN si.STATUS_VOBYS = 'F' THEN 'FECHADO'
            WHEN si.STATUS_VOBYS = 'I' THEN 'INCONSISTENCIA DE CADASTRO'
            WHEN si.STATUS_VOBYS = 'O' THEN 'OUTRAS INCONSISTENCIAS'
            WHEN si.STATUS_VOBYS = 'E' THEN 'ERRO'
            ELSE 'ABERTO'
        --END AS STATUS, STATUS_VOBYS,
        END AS STATUS_VOBYS,
        CASE
            WHEN si.IND_TIPO_REQUISICAO = 'V1' THEN 'COLABORADOR'
            WHEN si.IND_TIPO_REQUISICAO = 'V2' THEN 'CREDITO'
            WHEN si.IND_TIPO_REQUISICAO = 'V3' THEN 'ORCAMENTARIO'
            WHEN si.IND_TIPO_REQUISICAO = 'V4' THEN 'PATRONAL'
            ELSE si.IND_TIPO_REQUISICAO
        END AS IND_TIPO_REQUISICAO
    FROM sw_publico.SIAFE_EVENTO_INTEGRACAO si
    INNER JOIN sw_seadprevpi.siafe_proc_inf_trans it 
        ON INSTR(',' || it.ids || ',', ',' || si.ID_SIAFE_EVENTO_INTEGRACAO || ',') > 0
    INNER JOIN SW_SEADPREVPI.PROCESSO pr 
        ON pr.ID_PROCESSO = it.ID_PROCESSO
    WHERE si.STATUS_VOBYS IS NOT NULL
    -- Regra original de desvio
    AND TO_NUMBER(TO_CHAR(pr.DATA_INICIO, 'YYYYMM')) > TO_NUMBER(TO_CHAR(si.DATA_CADASTRO, 'YYYYMM'))
    AND TO_NUMBER(TO_CHAR(pr.DATA_inicio, 'YYYYMM')) = TO_NUMBER({ano} || LPAD({mes}, 2, '0'))
    -- NOVA REGRA: Exclui suplementares (ID 1000001) processadas no mês seguinte ao cadastro
    AND NOT (si.ID_TIPO_FOLHA = 1000001 
             AND TO_NUMBER(TO_CHAR(pr.DATA_INICIO, 'YYYYMM')) = TO_NUMBER(TO_CHAR(si.DATA_CADASTRO, 'YYYYMM')) + 1)
    ORDER BY pr.DATA_INICIO DESC
    """
    return query

def get_query_status_siafe(ano, mes):
    """
    Retorna a matriz pivotada de status simplificada com ROLLUP usando agregação condicional.
    Converte o mês para inteiro para garantir compatibilidade se armazenado como NUMBER.
    """
    mes_numerico = int(mes)

    query = f"""
    SELECT
        CASE WHEN GROUPING(STATUS_DESC) = 1 THEN 'TOTAL GERAL' ELSE STATUS_DESC END AS STATUS,
        COUNT(DECODE(IND_TIPO_REQUISICAO, 'V1', 1)) AS COL,
        COUNT(DECODE(IND_TIPO_REQUISICAO, 'V2', 1)) AS CRE,
        COUNT(DECODE(IND_TIPO_REQUISICAO, 'V3', 1)) AS ORC,
        COUNT(DECODE(IND_TIPO_REQUISICAO, 'V4', 1)) AS PATR,
        COUNT(CASE WHEN IND_TIPO_REQUISICAO IN ('V1','V2','V3','V4') THEN 1 END) AS TOTAL
    FROM (
        SELECT 
            DECODE(STATUS_VOBYS, 'P','PENDENTE', 'T','TRANSMITIDO', 'A','ABERTO', 'F','FECHADO', 
                                 'I','INCONSISTENCIA DE CADASTRO', 'O','OUTRAS INCONSISTENCIA', 
                                 'E','ERRO', STATUS_VOBYS) AS STATUS_DESC,
            IND_TIPO_REQUISICAO
        FROM sw_publico.SIAFE_EVENTO_INTEGRACAO
        WHERE mes = {mes_numerico} AND ano = {ano}
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
        'SW_SASC', 'SW_IMEPI', 'SW_SEJUSPI', 'SW_SEADPREVPI','SW_REENVIO'
    ]
    
    # Órgãos alocados para a Sarah
    schemas_sarah = [
        'SW_AGRESP', 'SW_SECMULHERES', 'SW_SERES', 'SW_DEFCIVIL', 
        'SW_SECID', 'SW_SEID', 'SW_SETUR', 'SW_SADA', 
        'SW_GAMIL', 'SW_GMG', 'SW_METRO', 'SW_EMGERPI_CORESA', 'SW_EMGERPI_EMATER', 
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
GET_SIGLAS_EMPRESA = """
    SELECT 
        NVL(e.ORGAO_SIAFI, t.codigo) AS Cod_Sefaz, 
        COALESCE(e.SIGLA, t.nome) AS Sigla
    FROM sw_publico.empresa e
    FULL OUTER JOIN josegomes.tb_use_sefaz t ON e.ORGAO_SIAFI = t.codigo
"""

# -*- coding: utf-8 -*-

def get_query_json_patronal_emgerpi(ano, mes):
    """
    Retorna a query SQL para geração e consolidação do JSON Patronal EMGERPI (V4).
    """
    return f"""
        WITH base_limpa AS (
            SELECT 
                sei.id_siafe_evento_integracao,
                sei.codigo_sefaz,
                MIN(sei.codigo_sefaz) OVER () AS min_codigo_sefaz,
                SUBSTR(
                    UTL_RAW.CAST_TO_VARCHAR2(seip.json),
                    INSTR(UTL_RAW.CAST_TO_VARCHAR2(seip.json), '{{'),
                    INSTR(UTL_RAW.CAST_TO_VARCHAR2(seip.json), '}}', -1) - INSTR(UTL_RAW.CAST_TO_VARCHAR2(seip.json), '{{') + 1
                ) AS json_valido
            FROM SW_PUBLICO.SIAFE_EVENTO_INTEGRACAO sei
            INNER JOIN SW_PUBLICO.EMPRESA e 
                ON e.id_empresa = sei.id_empresa
            INNER JOIN SW_PUBLICO.Siafe_Evento_Integ_Payload seip
                ON seip.id_siafe_evento_integracao = sei.id_siafe_evento_integracao
            WHERE e.cnpj = '06.643.068/0001-75' 
              AND sei.ano = {ano} 
              AND sei.mes = {int(mes)} 
              AND sei.ind_tipo_requisicao = 'V4'
              order by sei.codigo_sefaz
        ),
        cabecalho_principal AS (
            SELECT 
                MAX(CASE WHEN b.codigo_sefaz = b.min_codigo_sefaz THEN jt.codigo_unidade END) AS codigo_unidade,
                MAX(CASE WHEN b.codigo_sefaz = b.min_codigo_sefaz THEN jt.mes END) AS mes,
                MAX(CASE WHEN b.codigo_sefaz = b.min_codigo_sefaz THEN jt.id_tipo_folha END) AS id_tipo_folha,
                MAX(CASE WHEN b.codigo_sefaz = b.min_codigo_sefaz THEN jt.codigo_externo END) AS codigo_externo,
                MAX(CASE WHEN b.codigo_sefaz = b.min_codigo_sefaz THEN jt.codigo_relatorio END) AS codigo_relatorio,
                MAX(CASE WHEN b.codigo_sefaz = b.min_codigo_sefaz THEN jt.competencia END) AS competencia
            FROM base_limpa b,
                 JSON_TABLE(b.json_valido, '$'
                     COLUMNS (
                         codigo_unidade   VARCHAR2(100) PATH '$.codigoUnidadeSistemaExterno',
                         mes              NUMBER        PATH '$.mes',
                         id_tipo_folha    NUMBER        PATH '$.idTipoFolha',
                         codigo_externo   VARCHAR2(100) PATH '$.codigoExterno',
                         codigo_relatorio VARCHAR2(100) PATH '$.codigoRelatorioFolhaPagamento',
                         competencia      VARCHAR2(20)  PATH '$.competencia'
                     )
                 ) jt
        )
        SELECT 
            REPLACE(
                JSON_SERIALIZE(
                    JSON_OBJECT(
                        'codigoUnidadeSistemaExterno' VALUE c.codigo_unidade,
                        'mes'                         VALUE c.mes,
                        'idTipoFolha'                 VALUE c.id_tipo_folha,
                        'codigoExterno'               VALUE c.codigo_externo,
                        'codigoRelatorioFolhaPagamento' VALUE c.codigo_relatorio,
                        'competencia'                 VALUE c.competencia,
                        'pagamentos'                  VALUE (
                            SELECT JSON_ARRAYAGG(
                                       JSON_OBJECT(
                                           'codigoSefaz'          VALUE b_sub.codigo_sefaz,
                                           'regimePrevidenciario' VALUE p.regime_previdenciario,
                                           'codigoRubrica'        VALUE p.codigo_rubrica,
                                           'tipoVinculo'          VALUE p.tipo_vinculo,
                                           'valor'                VALUE p.valor,
                                           'valorDesconto'        VALUE p.valor_desconto
                                       )
                                       RETURNING CLOB
                                   )
                            FROM base_limpa b_sub,
                                 JSON_TABLE(b_sub.json_valido, '$.pagamentos[*]' 
                                     COLUMNS (
                                         regime_previdenciario VARCHAR2(50)  PATH '$.regimePrevidenciario',
                                         codigo_rubrica        VARCHAR2(50)  PATH '$.codigoRubrica',
                                         tipo_vinculo          VARCHAR2(50)  PATH '$.tipoVinculo',
                                         valor                 NUMBER        PATH '$.valor',
                                         valor_desconto        NUMBER        PATH '$.valorDesconto'
                                     )
                                 ) p
                        )
                        RETURNING CLOB
                    ) 
                    PRETTY
                ),
                '"pagamentos" :' || CHR(10) || '  [',
                '"pagamentos": ['
            ) AS novo_json_final
        FROM cabecalho_principal c
    """

