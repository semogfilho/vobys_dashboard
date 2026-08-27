# auditoria/tipo_folha_x_tipo_arquivo_sefaz.py
import pandas as pd

def executar_auditoria(conn, ano, mes, apenas_inconsistentes=False):
    cursor = conn.cursor()
    cursor.execute("SELECT owner FROM all_tables WHERE table_name = 'FOLHA' AND owner LIKE 'SW_%'")
    schemas = [row[0] for row in cursor.fetchall()]
    cursor.close()

    query_parts = []
    for schema in schemas:
        orgao_nome = schema.replace('SW_', '')
        
        # Filtro base obrigatório do período
        where_clause = f"f1.ANO = {ano} AND f1.MES = {int(mes)}"
        
        # Se marcado, captura as quebras estruturais considerando a unidade orçamentária
        if apenas_inconsistentes:
            where_clause += f"""
                AND (
                     -- 1. Arquivos filhotes sem o respectivo pai na mesma chave e unidade orçamentária
                     (
                          (f1.TIPO_ARQUIVO > '001' AND f1.TIPO_ARQUIVO < '020')
                          OR 
                          (f1.TIPO_ARQUIVO > '020')
                     )
                     AND NOT EXISTS (
                         SELECT 1
                         FROM {schema}.FOLHA f2
                         JOIN {schema}.FOLHA_CODIGO_SEFAZ fs2 ON fs2.ID_CODIGO_SEFAZ = f2.ID_CODIGO_SEFAZ
                         JOIN {schema}.FOLHA_UNID_ORCAMENTARIA u2 ON u2.ID_UNID_ORCAMENTARIA = f2.ID_UNID_ORCAMENTARIA
                         WHERE f2.ANO = f1.ANO
                           AND f2.MES = f1.MES
                           AND f2.TIPO_FOLHA_SEFAZ = f1.TIPO_FOLHA_SEFAZ
                           AND fs2.CODIGO_SEFAZ = fs.CODIGO_SEFAZ
                           AND u2.COD_UNID_ORCAMENTARIA = u.COD_UNID_ORCAMENTARIA
                           AND f2.TIPO_ARQUIVO = 
                               CASE 
                                   WHEN f1.TIPO_ARQUIVO < '020' THEN '001'
                                   ELSE '020'
                               END
                     )
                     OR
                     -- 2. Conflito por duplicidade: mais de um arquivo base (001 ou 020) para a mesma chave
                     (
                          f1.TIPO_ARQUIVO IN ('001', '020')
                          AND (
                              SELECT COUNT(*)
                              FROM {schema}.FOLHA f_dup
                              JOIN {schema}.FOLHA_CODIGO_SEFAZ fs_dup ON fs_dup.ID_CODIGO_SEFAZ = f_dup.ID_CODIGO_SEFAZ
                              JOIN {schema}.FOLHA_UNID_ORCAMENTARIA u_dup ON u_dup.ID_UNID_ORCAMENTARIA = f_dup.ID_UNID_ORCAMENTARIA
                              WHERE f_dup.ANO = f1.ANO
                                AND f_dup.MES = f1.MES
                                AND f_dup.TIPO_FOLHA_SEFAZ = f1.TIPO_FOLHA_SEFAZ
                                AND f_dup.TIPO_ARQUIVO = f1.TIPO_ARQUIVO
                                AND fs_dup.CODIGO_SEFAZ = fs.CODIGO_SEFAZ
                                AND u_dup.COD_UNID_ORCAMENTARIA = u.COD_UNID_ORCAMENTARIA
                          ) > 1
                     )
                )
            """

        query_parts.append(f"""
            SELECT
                fs.CODIGO_SEFAZ,
                f1.TIPO_ARQUIVO,
                f1.TIPO_FOLHA_SEFAZ,
                u.COD_UNID_ORCAMENTARIA as CODIGO_RELATORIO,
                t.DESCRICAO_TIPO,
                CASE 
                    WHEN f1.TIPO_ARQUIVO IN ('001', '020') THEN 'registro duplicado'
                    WHEN f1.TIPO_ARQUIVO > '001' AND f1.TIPO_ARQUIVO < '020' THEN 'Fora da Sequencia (001)'
                    ELSE 'Fora da sequencia (020)'
                END as SITUACAO,
                f1.CHAVE_FOLHA,
                '{orgao_nome}' as ORGAO,
                f1.DESCRICAO,
                f1.DATA_FECHAMENTO,
                f1.DATA_CADASTRO,
                (SELECT COUNT(*) FROM {schema}.FOLHA_FUNC ff WHERE ff.ID_FOLHA = f1.ID_FOLHA AND ff.IND_REMUNERACAO = 'S') as QTDE_REGISTROS
            FROM {schema}.FOLHA f1
            JOIN SW_PUBLICO.FOLHA_TAB_TIPO t ON f1.ID_TIPO_FOLHA = t.ID_TIPO_FOLHA
            JOIN {schema}.FOLHA_CODIGO_SEFAZ fs ON fs.ID_CODIGO_SEFAZ = f1.ID_CODIGO_SEFAZ
            JOIN {schema}.FOLHA_UNID_ORCAMENTARIA u ON u.ID_UNID_ORCAMENTARIA = f1.ID_UNID_ORCAMENTARIA
            WHERE {where_clause}
        """)

    if not query_parts:
        return pd.DataFrame()

    query_final = " UNION ALL ".join(query_parts) + " ORDER BY CODIGO_SEFAZ, TIPO_ARQUIVO, TIPO_FOLHA_SEFAZ, CODIGO_RELATORIO, ORGAO"
    df = pd.read_sql(query_final, conn)
    return df


def executar_auditoria_x1(conn, ano, mes):
    cursor = conn.cursor()
    cursor.execute("SELECT owner FROM all_tables WHERE table_name = 'FOLHA' AND owner LIKE 'SW_%'")
    schemas = [row[0] for row in cursor.fetchall()]
    cursor.close()

    query_parts = []
    for schema in schemas:
        orgao_nome = schema.replace('SW_', '')
        query_parts.append(f"""
            SELECT
                fs.CODIGO_SEFAZ,
                f1.TIPO_ARQUIVO,
                f1.TIPO_FOLHA_SEFAZ,
                t.DESCRICAO_TIPO,
                f1.CHAVE_FOLHA,
                '{orgao_nome}' as ORGAO,
                f1.DESCRICAO,
                f1.DATA_FECHAMENTO,
                f1.DATA_CADASTRO,
                (SELECT COUNT(*) FROM {schema}.FOLHA_FUNC ff WHERE ff.ID_FOLHA = f1.ID_FOLHA AND ff.IND_REMUNERACAO = 'S') as QTDE_REGISTROS
            FROM {schema}.FOLHA f1
            JOIN SW_PUBLICO.FOLHA_TAB_TIPO t ON f1.ID_TIPO_FOLHA = t.ID_TIPO_FOLHA
            JOIN {schema}.FOLHA_CODIGO_SEFAZ fs ON fs.ID_CODIGO_SEFAZ = f1.ID_CODIGO_SEFAZ
            WHERE f1.ANO = {ano}
              AND f1.MES = {int(mes)}
        """)

    if not query_parts:
        return pd.DataFrame()

    query_final = " UNION ALL ".join(query_parts)
    df = pd.read_sql(query_final, conn)
    return df



def executar_auditoria_original(conn, ano, mes):
    cursor = conn.cursor()
    cursor.execute("SELECT owner FROM all_tables WHERE table_name = 'FOLHA' AND owner LIKE 'SW_%'")
    schemas = [row[0] for row in cursor.fetchall()]
    cursor.close()

    query_parts = []
    for schema in schemas:
        orgao_nome = schema.replace('SW_', '')
        query_parts.append(f"""
            SELECT
                '{orgao_nome}' as ORGAO,
                f1.CHAVE_FOLHA,
                t.DESCRICAO_TIPO,
                f1.TIPO_ARQUIVO,
                f1.DESCRICAO,
                f1.DATA_FECHAMENTO,
                f1.DATA_CADASTRO,
                fs.CODIGO_SEFAZ,
                f1.TIPO_FOLHA_SEFAZ,
                (SELECT COUNT(*) FROM {schema}.FOLHA_FUNC ff WHERE ff.ID_FOLHA = f1.ID_FOLHA AND ff.IND_REMUNERACAO = 'S') as QTDE_REGISTROS
            FROM {schema}.FOLHA f1
            JOIN SW_PUBLICO.FOLHA_TAB_TIPO t ON f1.ID_TIPO_FOLHA = t.ID_TIPO_FOLHA
            JOIN {schema}.FOLHA_CODIGO_SEFAZ fs ON fs.ID_CODIGO_SEFAZ = f1.ID_CODIGO_SEFAZ
            WHERE f1.ANO = {ano}
              AND f1.MES = {int(mes)}
              AND (
                   (f1.TIPO_ARQUIVO > '001' AND f1.TIPO_ARQUIVO < '020')
                   OR 
                   (f1.TIPO_ARQUIVO > '020')
              )
              AND NOT EXISTS (
                  SELECT 1
                  FROM {schema}.FOLHA f2
                  WHERE f2.ANO = f1.ANO
                    AND f2.MES = f1.MES
                    -- AND f2.ID_CODIGO_SEFAZ = f1.ID_CODIGO_SEFAZ
                    AND f2.TIPO_FOLHA_SEFAZ = f1.TIPO_FOLHA_SEFAZ
                    AND f2.TIPO_ARQUIVO = 
                        CASE 
                            WHEN f1.TIPO_ARQUIVO < '020' THEN '001'
                            ELSE '020'
                        END
              )
        """)

    if not query_parts:
        return pd.DataFrame()

    query_final = " UNION ALL ".join(query_parts)
    df = pd.read_sql(query_final, conn)
    return df


def executar_auditoria_antigo(conn, ano, mes):
    cursor = conn.cursor()
    cursor.execute("SELECT owner FROM all_tables WHERE table_name = 'FOLHA' AND owner LIKE 'SW_%'")
    schemas = [row[0] for row in cursor.fetchall()]
    cursor.close()

    query_parts = []
    for schema in schemas:
        orgao_nome = schema.replace('SW_', '')
        query_parts.append(f"""
            SELECT
                '{orgao_nome}' as ORGAO,
                f.CHAVE_FOLHA,
                t.DESCRICAO_TIPO,
                f.TIPO_ARQUIVO,
                f.DESCRICAO,
                f.DATA_FECHAMENTO,
                f.DATA_CADASTRO,
                fs.CODIGO_SEFAZ,
                (SELECT COUNT(*) FROM {schema}.FOLHA_FUNC ff WHERE ff.ID_FOLHA = f.ID_FOLHA AND Ff.IND_REMUNERACAO='S') as QTDE_REGISTROS
            FROM {schema}.FOLHA f
            JOIN SW_PUBLICO.FOLHA_TAB_TIPO t ON f.ID_TIPO_FOLHA = t.ID_TIPO_FOLHA
            JOIN {schema}.FOLHA_CODIGO_SEFAZ fs ON fs.ID_CODIGO_SEFAZ = f.ID_CODIGO_SEFAZ
            WHERE f.ANO = {ano} AND f.MES = {int(mes)}
            AND (
                (f.ID_TIPO_FOLHA = 1000000 AND f.TIPO_ARQUIVO <> '001')
                OR
                (f.ID_TIPO_FOLHA = 1000001 AND f.TIPO_ARQUIVO <= '001')
            )
        """)

    query_final = " UNION ALL ".join(query_parts)
    df = pd.read_sql(query_final, conn)
    
# ADICIONE ISTO PARA DEBUGAR:
    print(f"DEBUG: Registros encontrados: {len(df)}")
    if not df.empty:
        df = df[["ORGAO","CODIGO_SEFAZ", "CHAVE_FOLHA", "DESCRICAO", "DATA_CADASTRO", "DATA_FECHAMENTO", "DESCRICAO_TIPO", "TIPO_ARQUIVO", "QTDE_REGISTROS"]]
    
    return df

