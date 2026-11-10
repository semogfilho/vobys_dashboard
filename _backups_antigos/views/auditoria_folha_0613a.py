# -*- coding: utf-8 -*-
import pandas as pd
import streamlit as st

def render(conn, ano_selecionado, mes_selecionado):
    st.subheader("📋 Auditoria de Consistência - Folhas")

    # Mapeamento dinâmico de schemas (Lógica que já tínhamos)
    cursor = conn.cursor()
    cursor.execute("SELECT owner FROM all_tables WHERE table_name = 'FOLHA' AND owner LIKE 'SW_%'")
    schemas = [row[0] for row in cursor.fetchall()]
    cursor.close()

    # Query parametrizada para cada schema (Union All seria ideal, mas iterar mantém a segurança)
    query_parts = []
    for schema in schemas:
        query_parts.append(f"""
            SELECT 
                '{schema}' as SCHEMA,
                f.CHAVE_FOLHA,
                t.DESCRICAO_TIPO,
                f.TIPO_ARQUIVO
            FROM {schema}.FOLHA f
            JOIN SW_PUBLICO.FOLHA_TAB_TIPO t ON f.ID_TIPO_FOLHA = t.ID_TIPO_FOLHA
            WHERE f.ANO = {ano_selecionado} AND f.MES = {int(mes_selecionado)}
            AND (
                (upper(t.DESCRICAO_TIPO) = upper('Ordinária') AND f.TIPO_ARQUIVO <> '001')
                OR
                (upper(t.DESCRICAO_TIPO) = upper('Suplementar') AND f.TIPO_ARQUIVO <= '001')
            )
        """)
    
    query_final = " UNION ALL ".join(query_parts)

    with st.spinner("Analisando inconsistências de tipo de arquivo..."):
        try:
            # Execução idêntica ao auditoria_integracao
            df = pd.read_sql(query_final, conn)

            if not df.empty:
                st.warning(f"Foram encontradas {len(df)} inconsistências de tipo de arquivo.")

                # Exibição do DataFrame
                st.dataframe(
                    df,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "SCHEMA": "SCHEMA",
                        "CHAVE_FOLHA": "CHAVE FOLHA",
                        "DESCRICAO_TIPO": "TIPO FOLHA",
                        "TIPO_ARQUIVO": "TIPO ARQUIVO"
                    }
                )

                # Botão de exportação idêntico ao modelo
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

