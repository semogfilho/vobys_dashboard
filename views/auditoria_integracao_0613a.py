# -*- coding: utf-8 -*-
import pandas as pd
import streamlit as st
# Removido: sqlalchemy.text
from queries import get_query_auditoria_desvios

def render(conn, ano_selecionado, mes_selecionado):
    st.subheader("Auditoria de Desvios de Competência (SIAFE)")
    
    # Busca a query parametrizada do queries.py
    query = get_query_auditoria_desvios(ano_selecionado, int(mes_selecionado))
    
    with st.spinner("Analisando desvios de competência..."):
        try:
            # Executa a query diretamente com a conexão nativa 'conn'
            df = pd.read_sql(query, conn)
            
            if not df.empty:
                st.warning(f"Foram encontrados {len(df)} eventos com desvio de competência.")
                
                # --- AJUSTE PARA EXIBIR HORAS E MINUTOS ---
                colunas_data = ['DATA_INICIO_PROCESSO', 'DATA_CADASTRO', 'DATA_PROCESSAMENTO']
                
                for col in colunas_data:
                    if col in df.columns:
                        df[col] = pd.to_datetime(df[col]).dt.strftime('%d/%m/%Y %H:%M')
                # ------------------------------------------

                # Exibição do DataFrame
                st.dataframe(
                    df, 
                    use_container_width=True, # Ajustado para 'None' para comportar-se como 'stretch' no streamlit moderno
                    hide_index=True,
                    column_config={
                        "ID_SIAFE_EVENTO_INTEGRACAO": st.column_config.NumberColumn("ID EVENTO", format="%d"),
                        "DATA_INICIO_PROCESSO": "INÍCIO PROCESSO",
                        "DATA_CADASTRO": "DATA CADASTRO",
                        "DATA_PROCESSAMENTO": "DATA PROC.",
                        "STATUS": "STATUS",
                        "IND_TIPO_REQUISICAO": "TIPO REQUISIÇÃO"
                    }
                )
                
                # Botão de exportação
                csv = df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="Exportar CSV de Auditoria",
                    data=csv,
                    file_name=f"auditoria_desvios_{ano_selecionado}_{mes_selecionado}.csv",
                    mime="text/csv"
                )
            else:
                st.success(f"Nenhum desvio de competência detectado para {mes_selecionado}/{ano_selecionado}.")
                
        except Exception as e:
            st.error(f"Erro ao carregar auditoria: {e}")

