# auditoria/tipo_folha_x_tipo_arquivo_sefaz.py
import pandas as pd

def executar_auditoria(conn, ano, mes):
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

