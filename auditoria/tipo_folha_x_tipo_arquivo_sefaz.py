# auditoria/tipo_folha_x_tipo_arquivo_sefaz.py
import pandas as pd


def _gerar_link_siape(df):
    """
    Formata a coluna DESCRICAO_TIPO transformando-a em URL com o rótulo após o '#'.
    Aplica URLs diferentes para folhas do tipo NORMAL e ESTAGIARIO.
    """
    if df.empty or "ID_FOLHA" not in df.columns or "DESCRICAO_TIPO" not in df.columns:
        return df

    df_temp = df.copy()

    def montar_url(row):
        descricao = str(row.get("DESCRICAO_TIPO", ""))
        id_folha = row.get("ID_FOLHA")
        orgao = str(row.get("ORGAO", "")).lower()
        tipo_registro = str(row.get("TIPO_REGISTRO", "")).upper()

        if descricao.startswith("http") or pd.isna(id_folha):
            return descricao

        if tipo_registro == "ESTAGIARIO":
            return (
                f"https://siape.sead.pi.gov.br/adm/{orgao}/"
                f"folha-estagiario-menor-aprendiz-bolsista/"
                f"estagiario-menor-aprendiz-bolsista/folhas/folha/"
                f"{int(id_folha)}/dados-folha#{descricao}"
            )

        return (
            f"https://siape.sead.pi.gov.br/adm/{orgao}/"
            f"folha-funcionario/folhas/folhas/folha-de-pagamento/"
            f"{int(id_folha)}/inicial/dados-da-folha#{descricao}"
        )

    df_temp["DESCRICAO_TIPO"] = df_temp.apply(montar_url, axis=1)
    return df_temp


def executar_auditoria(conn, ano, mes, apenas_inconsistentes=False):
    cursor = conn.cursor()
    cursor.execute("SELECT owner FROM all_tables WHERE table_name = 'FOLHA' AND owner LIKE 'SW_%'")
    schemas_geral = [row[0] for row in cursor.fetchall()]

    cursor.execute("SELECT owner FROM all_tables WHERE table_name = 'ESTAG_FOLHA' AND owner LIKE 'SW_%'")
    schemas_estag = {row[0] for row in cursor.fetchall()}
    cursor.close()

    query_parts = []
    for schema in schemas_geral:
        orgao_nome = schema.replace('SW_', '')

        # --- 1. QUERY DA FOLHA TRADICIONAL ---
        where_clause_f1 = f"""
            f1.ANO = {ano}
            AND f1.MES = {int(mes)}
        """

        if apenas_inconsistentes:
            where_clause_f1 += f"""
                AND (
                     (
                          (
                              -- Se for suplementar, a faixa válida começa em '002' (não exige '001')
                              (UPPER(t.DESCRICAO_TIPO) LIKE '%SUPLEMENTAR%' AND f1.TIPO_ARQUIVO > '002' AND f1.TIPO_ARQUIVO < '020')
                              OR
                              (UPPER(t.DESCRICAO_TIPO) NOT LIKE '%SUPLEMENTAR%' AND f1.TIPO_ARQUIVO > '001' AND f1.TIPO_ARQUIVO < '020')
                          )
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
                                    WHEN f1.TIPO_ARQUIVO < '020' THEN 
                                        CASE 
                                            WHEN UPPER(t.DESCRICAO_TIPO) LIKE '%SUPLEMENTAR%' THEN '002'
                                            ELSE '001'
                                        END
                                    ELSE '020'
                                END
                     )
                     OR
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

        coluna_situacao_f1 = f"""
            CASE
                WHEN f1.TIPO_ARQUIVO IN ('001', '020') THEN 'Estrutural SEFAZ duplicado'
                WHEN UPPER(t.DESCRICAO_TIPO) LIKE '%SUPLEMENTAR%' AND f1.TIPO_ARQUIVO > '002' AND f1.TIPO_ARQUIVO < '020' THEN 'Tipo de Arquivo Fora da Sequencia (002)'
                WHEN UPPER(t.DESCRICAO_TIPO) NOT LIKE '%SUPLEMENTAR%' AND f1.TIPO_ARQUIVO > '001' AND f1.TIPO_ARQUIVO < '020' THEN 'Tipo de Arquivo Fora da Sequencia (001)'
                ELSE 'Tipo de Arquivo Fora da Sequencia (020)'
            END as SITUACAO,
        """ if apenas_inconsistentes else ""

        if apenas_inconsistentes:
            select_pagamentos = "0 as QTDE_PAGAMENTOS"
            join_detalhes = ""
        else:
            select_pagamentos = "NVL(det.qtd, 0) as QTDE_PAGAMENTOS"
            join_detalhes = f"""
                LEFT JOIN (
                    SELECT id_folha, COUNT(*) as qtd
                    FROM {schema}.FOLHA_FUNC
                    WHERE IND_REMUNERACAO = 'S'
                    GROUP BY id_folha
                ) det ON det.id_folha = f1.id_folha
            """

        subquery_folha = f"""
            SELECT
                f1.ID_FOLHA,
                fs.CODIGO_SEFAZ,
                f1.TIPO_ARQUIVO,
                f1.TIPO_FOLHA_SEFAZ,
                u.COD_UNID_ORCAMENTARIA as CODIGO_RELATORIO,
                t.DESCRICAO_TIPO,
                {coluna_situacao_f1}
                f1.CHAVE_FOLHA,
                '{orgao_nome}' as ORGAO,
                f1.DESCRICAO,
                f1.DATA_FECHAMENTO,
                f1.DATA_CADASTRO,
                'NORMAL' as TIPO_REGISTRO,
                {select_pagamentos}
            FROM {schema}.FOLHA f1
            JOIN SW_PUBLICO.FOLHA_TAB_TIPO t ON f1.ID_TIPO_FOLHA = t.ID_TIPO_FOLHA
            JOIN {schema}.FOLHA_CODIGO_SEFAZ fs ON fs.ID_CODIGO_SEFAZ = f1.ID_CODIGO_SEFAZ
            JOIN {schema}.FOLHA_UNID_ORCAMENTARIA u ON u.ID_UNID_ORCAMENTARIA = f1.ID_UNID_ORCAMENTARIA
            {join_detalhes}
            WHERE {where_clause_f1}
        """
        query_parts.append(subquery_folha)

        # --- 2. QUERY DA FOLHA DE ESTAGIÁRIOS ---
        if schema in schemas_estag:
            where_clause_ef = f"""
                ef.ANO = {ano}
                AND ef.MES = {int(mes)}
            """

            if apenas_inconsistentes:
                where_clause_ef += f"""
                    AND (
                         (
                              (LPAD(TO_CHAR(ef.seq_arquivo), 3, '0') > '001' AND LPAD(TO_CHAR(ef.seq_arquivo), 3, '0') < '020')
                              OR
                              (LPAD(TO_CHAR(ef.seq_arquivo), 3, '0') > '020')
                         )
                         AND NOT EXISTS (
                              SELECT 1
                              FROM {schema}.ESTAG_FOLHA ef2
                              JOIN {schema}.FOLHA_CODIGO_SEFAZ fs2 ON fs2.ID_CODIGO_SEFAZ = ef2.ID_CODIGO_SEFAZ
                              WHERE ef2.ANO = ef.ANO
                                AND ef2.MES = ef.MES
                                AND fs2.CODIGO_SEFAZ = fs.CODIGO_SEFAZ
                                AND LPAD(TO_CHAR(ef2.seq_arquivo), 3, '0') =
                                    CASE
                                        WHEN LPAD(TO_CHAR(ef.seq_arquivo), 3, '0') < '020' THEN '001'
                                        ELSE '020'
                                    END
                         )
                         OR
                         (
                              LPAD(TO_CHAR(ef.seq_arquivo), 3, '0') IN ('001', '020')
                              AND (
                                  SELECT COUNT(*)
                                  FROM {schema}.ESTAG_FOLHA ef_dup
                                  JOIN {schema}.FOLHA_CODIGO_SEFAZ fs_dup ON fs_dup.ID_CODIGO_SEFAZ = ef_dup.ID_CODIGO_SEFAZ
                                  WHERE ef_dup.ANO = ef.ANO
                                    AND ef_dup.MES = ef.MES
                                    AND LPAD(TO_CHAR(ef_dup.seq_arquivo), 3, '0') = LPAD(TO_CHAR(ef.seq_arquivo), 3, '0')
                                    AND fs_dup.CODIGO_SEFAZ = fs.CODIGO_SEFAZ
                              ) > 1
                         )
                    )
                """

            coluna_situacao_ef = f"""
                CASE
                    WHEN LPAD(TO_CHAR(ef.seq_arquivo), 3, '0') IN ('001', '020') THEN 'Estrutural SEFAZ duplicado'
                    WHEN LPAD(TO_CHAR(ef.seq_arquivo), 3, '0') > '001' AND LPAD(TO_CHAR(ef.seq_arquivo), 3, '0') < '020' THEN 'Codigo de Arquivo Fora da Sequencia (001)'
                    ELSE 'Codigo de Arquivo Fora da Sequencia (020)'
                END as SITUACAO,
            """ if apenas_inconsistentes else ""

            if apenas_inconsistentes:
                select_pagamentos_estag = "0 as QTDE_PAGAMENTOS"
                join_detalhes_estag = ""
            else:
                select_pagamentos_estag = "NVL(det_e.qtd, 0) as QTDE_PAGAMENTOS"
                join_detalhes_estag = f"""
                    LEFT JOIN (
                        SELECT id_folha, COUNT(*) as qtd
                        FROM {schema}.Estagiario_Pagamento
                        GROUP BY id_folha
                    ) det_e ON det_e.id_folha = ef.id_folha
                """

            subquery_estagiario = f"""
                SELECT
                    ef.ID_FOLHA,
                    fs.CODIGO_SEFAZ as CODIGO_SEFAZ,
                    LPAD(TO_CHAR(ef.seq_arquivo), 3, '0') as TIPO_ARQUIVO,
                    'C5' as TIPO_FOLHA_SEFAZ,
                    '00' as CODIGO_RELATORIO,
                    'Estagiário' as DESCRICAO_TIPO,
                    {coluna_situacao_ef}
                    ef.MASCARA as CHAVE_FOLHA,
                    '{orgao_nome}' as ORGAO,
                    ef.DESCRICAO,
                    ef.DATA_FECHAMENTO,
                    ef.DATA_CADASTRO,
                    'ESTAGIARIO' as TIPO_REGISTRO,
                    {select_pagamentos_estag}
                FROM {schema}.ESTAG_FOLHA ef
                JOIN SW_PUBLICO.FOLHA_TAB_TIPO t ON ef.ID_TIPO_FOLHA = t.ID_TIPO_FOLHA
                JOIN {schema}.FOLHA_CODIGO_SEFAZ fs ON fs.ID_CODIGO_SEFAZ = ef.ID_CODIGO_SEFAZ
                {join_detalhes_estag}
                WHERE {where_clause_ef}
            """
            query_parts.append(subquery_estagiario)

    if not query_parts:
        return pd.DataFrame()

    query_final = " UNION ALL ".join(query_parts) + " ORDER BY CODIGO_SEFAZ, TIPO_ARQUIVO, TIPO_FOLHA_SEFAZ, CODIGO_RELATORIO, ORGAO"
    df = pd.read_sql(query_final, conn)

    if "QTDE_PAGAMENTOS" in df.columns:
        df = df.rename(columns={"QTDE_PAGAMENTOS": "QTDE PAGAMENTOS"})

    return _gerar_link_siape(df)


def executar_auditoria_com_a_Quantidade(conn, ano, mes, apenas_inconsistentes=False):
    cursor = conn.cursor()
    cursor.execute("SELECT owner FROM all_tables WHERE table_name = 'FOLHA' AND owner LIKE 'SW_%'")
    schemas = [row[0] for row in cursor.fetchall()]
    cursor.close()

    query_parts = []
    for schema in schemas:
        orgao_nome = schema.replace('SW_', '')
        
        where_clause = f"f1.ANO = {ano} AND f1.MES = {int(mes)}"
        
        if apenas_inconsistentes:
            where_clause += f"""
                AND (
                     (
                          (
                              (UPPER(t.DESCRICAO_TIPO) LIKE '%SUPLEMENTAR%' AND f1.TIPO_ARQUIVO > '002' AND f1.TIPO_ARQUIVO < '020')
                              OR
                              (UPPER(t.DESCRICAO_TIPO) NOT LIKE '%SUPLEMENTAR%' AND f1.TIPO_ARQUIVO > '001' AND f1.TIPO_ARQUIVO < '020')
                          )
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
                                   WHEN f1.TIPO_ARQUIVO < '020' THEN 
                                       CASE 
                                           WHEN UPPER(t.DESCRICAO_TIPO) LIKE '%SUPLEMENTAR%' THEN '002'
                                           ELSE '001'
                                       END
                                   ELSE '020'
                               END
                     )
                     OR
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
                f1.ID_FOLHA,
                fs.CODIGO_SEFAZ,
                f1.TIPO_ARQUIVO,
                f1.TIPO_FOLHA_SEFAZ,
                u.COD_UNID_ORCAMENTARIA as CODIGO_RELATORIO,
                t.DESCRICAO_TIPO,
                CASE 
                    WHEN f1.TIPO_ARQUIVO IN ('001', '020') THEN 'registro duplicado'
                    WHEN UPPER(t.DESCRICAO_TIPO) LIKE '%SUPLEMENTAR%' AND f1.TIPO_ARQUIVO > '002' AND f1.TIPO_ARQUIVO < '020' THEN 'Fora da Sequencia (002)'
                    WHEN UPPER(t.DESCRICAO_TIPO) NOT LIKE '%SUPLEMENTAR%' AND f1.TIPO_ARQUIVO > '001' AND f1.TIPO_ARQUIVO < '020' THEN 'Fora da Sequencia (001)'
                    ELSE 'Fora da sequencia (020)'
                END as SITUACAO,
                f1.CHAVE_FOLHA,
                '{orgao_nome}' as ORGAO,
                f1.DESCRICAO,
                f1.DATA_FECHAMENTO,
                f1.DATA_CADASTRO,
                'NORMAL' as TIPO_REGISTRO,
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
    return _gerar_link_siape(df)


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
                f1.ID_FOLHA,
                fs.CODIGO_SEFAZ,
                f1.TIPO_ARQUIVO,
                f1.TIPO_FOLHA_SEFAZ,
                t.DESCRICAO_TIPO,
                f1.CHAVE_FOLHA,
                '{orgao_nome}' as ORGAO,
                f1.DESCRICAO,
                f1.DATA_FECHAMENTO,
                f1.DATA_CADASTRO,
                'NORMAL' as TIPO_REGISTRO,
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
    return _gerar_link_siape(df)


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
                f1.ID_FOLHA,
                '{orgao_nome}' as ORGAO,
                f1.CHAVE_FOLHA,
                t.DESCRICAO_TIPO,
                f1.TIPO_ARQUIVO,
                f1.DESCRICAO,
                f1.DATA_FECHAMENTO,
                f1.DATA_CADASTRO,
                fs.CODIGO_SEFAZ,
                f1.TIPO_FOLHA_SEFAZ,
                'NORMAL' as TIPO_REGISTRO,
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
    return _gerar_link_siape(df)


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
                f.ID_FOLHA,
                '{orgao_nome}' as ORGAO,
                f.CHAVE_FOLHA,
                t.DESCRICAO_TIPO,
                f.TIPO_ARQUIVO,
                f.DESCRICAO,
                f.DATA_FECHAMENTO,
                f.DATA_CADASTRO,
                fs.CODIGO_SEFAZ,
                'NORMAL' as TIPO_REGISTRO,
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

    if not query_parts:
        return pd.DataFrame()

    query_final = " UNION ALL ".join(query_parts) + " ORDER BY CODIGO_SEFAZ, TIPO_ARQUIVO, TIPO_FOLHA_SEFAZ, CODIGO_RELATORIO, ORGAO"
    df = pd.read_sql(query_final, conn)
    
    if not df.empty:
        df = df[["ID_FOLHA", "ORGAO", "CODIGO_SEFAZ", "CHAVE_FOLHA", "DESCRICAO", "DATA_CADASTRO", "DATA_FECHAMENTO", "DESCRICAO_TIPO", "TIPO_ARQUIVO", "TIPO_REGISTRO", "QTDE_REGISTROS"]]
    
    return _gerar_link_siape(df)

