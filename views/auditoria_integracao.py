# -*- coding: utf-8 -*-
import pandas as pd
import streamlit as st
from queries import get_query_auditoria_desvios

def render(conn, ano_selecionado, mes_selecionado):
    # Adicionando o mês/ano ao título para contexto
    meses_map = {1: 'Jan', 2: 'Fev', 3: 'Mar', 4: 'Abr', 5: 'Mai', 6: 'Jun',
                 7: 'Jul', 8: 'Ago', 9: 'Set', 10: 'Out', 11: 'Nov', 12: 'Dez'}
    mes_nome = meses_map.get(int(mes_selecionado), "")
    st.subheader(f"Auditoria de Desvios de Competência (SIAFE) | {mes_nome}/{ano_selecionado}")
    
    query = get_query_auditoria_desvios(ano_selecionado, int(mes_selecionado))
    
    with st.spinner("Analisando desvios de competência..."):
        try:
            df = pd.read_sql(query, conn)
            
            # --- AJUSTE: FILTRO DE SUPLEMENTARES LEGÍTIMAS ---
            # Remove registros onde é Suplementar (ID 1000001) e o processamento é no mês seguinte ao da competência
            if not df.empty and 'ID_TIPO_FOLHA' in df.columns and 'MES' in df.columns:
                # Nota: Ajuste os nomes das colunas 'MES_PROCESSAMENTO' e 'MES_COMPETENCIA' 
                # se a sua query retornar nomes diferentes.
                condicao_legitima = (
                    (df['ID_TIPO_FOLHA'] == 1000001) & 
                    (df['MES_PROCESSAMENTO'] == int(mes_selecionado)) & 
                    (df['MES_COMPETENCIA'] == int(mes_selecionado) - 1)
                )
                df = df[~condicao_legitima].copy()
            # --------------------------------------------------
            
            if not df.empty:
                st.warning(f"Foram encontrados {len(df)} eventos com desvio de competência.")
                
                colunas_data = ['DATA_INICIO_PROCESSO', 'DATA_CADASTRO', 'DATA_PROCESSAMENTO']
                for col in colunas_data:
                    if col in df.columns:
                        df[col] = pd.to_datetime(df[col]).dt.strftime('%d/%m/%Y %H:%M')

                st.dataframe(
                    df, 
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "ID_SIAFE_EVENTO_INTEGRACAO": st.column_config.NumberColumn("ID EVENTO", format="%d"),
                        "DATA_INICIO_PROCESSO": "INÍCIO PROCESSO",
                        "DATA_CADASTRO": "DATA CADASTRO",
                        "DATA_PROCESSAMENTO": "DATA PROC.",
                        "STATUS_VOBYS": "STATUS",
                        "IND_TIPO_REQUISICAO": "TIPO REQUISIÇÃO"
                    }
                )
                
                csv = df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="Exportar CSV de Auditoria",
                    data=csv,
                    file_name=f"auditoria_desvios_{ano_selecionado}_{mes_selecionado}.csv",
                    mime="text/csv"
                )
            else:
                st.success(f"Nenhum desvio de competência detectado para {mes_nome}/{ano_selecionado}.")
                
        except Exception as e:
            st.error(f"Erro ao carregar auditoria: {e}")

