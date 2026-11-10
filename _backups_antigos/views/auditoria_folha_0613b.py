# -*- coding: utf-8 -*-
import pandas as pd
import streamlit as st

def render(conn, ano_selecionado, mes_selecionado):
    st.subheader("📋 Auditoria de Consistência - Folhas")

    cursor = conn.cursor()
    cursor.execute("SELECT owner FROM all_tables WHERE table_name = 'FOLHA' AND owner LIKE 'SW_%'")
    schemas = [row[0] for row in cursor.fetchall()]
    cursor.close()

    query_parts = []
    for schema in schemas:
        orgao_nome = schema.replace('SW_', '')
        # JOIN com SW_PUBLICO para recuperar a descrição do tipo
        query_parts.append(f"""
            SELECT 
                '{orgao_nome}' as ORGAO,
                f.CHAVE_FOLHA,
                t.DESCRICAO_TIPO,
                f.TIPO_ARQUIVO
            FROM {schema}.FOLHA f
            JOIN SW_PUBLICO.FOLHA_TAB_TIPO t ON f.ID_TIPO_FOLHA = t.ID_TIPO_FOLHA
            WHERE f.ANO = {ano_selecionado} AND f.MES = {int(mes_selecionado)}
            AND (
                (f.ID_TIPO_FOLHA = 1000000 AND f.TIPO_ARQUIVO <> '001')
                OR
                (f.ID_TIPO_FOLHA = 1000001 AND f.TIPO_ARQUIVO <= '001')
            )
        """)
    
    query_final = " UNION ALL ".join(query_parts)

    with st.spinner("Analisando inconsistências..."):
        try:
            df = pd.read_sql(query_final, conn)

            if not df.empty:
                st.warning(f"Foram encontradas {len(df)} inconsistências de tipo de arquivo.")

                st.dataframe(
                    df,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "ORGAO": "ÓRGÃO",
                        "CHAVE_FOLHA": "CHAVE FOLHA",
                        "DESCRICAO_TIPO": "TIPO FOLHA", # Exibe a descrição aqui
                        "TIPO_ARQUIVO": "TIPO ARQUIVO"
                    }
                )

                csv = df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="Exportar CSV de Auditoria Folha",
                    data=csv,
                    file_name=f"auditoria_folhas_{ano_selecionado}_{mes_selecionado}.csv",
                    mime="text/csv"
                )
            else:
                st.success(f"Nenhuma inconsistência de tipo encontrada para {mes_selecionado}/{ano_selecionado}.")

        except Exception as e:
            st.error(f"Erro ao executar a auditoria: {e}")

