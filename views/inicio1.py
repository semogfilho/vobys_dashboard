# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
from queries import get_query_detalhe_erros

def render(conn, ano_selecionado, mes_chave, meses_disponiveis):
    # --- CSS OTIMIZADO ---
    st.markdown("""
        <style>
            .block-container { padding-top: 1rem !important; padding-bottom: 1rem !important; }
            div[data-testid="stVerticalBlock"] > div:first-child { margin-top: 0px !important; padding-top: 0px !important; }
            div[data-testid="stMetric"] { margin-top: -10px !important; }
            
            /* Garante largura ampla para o popover */
            [data-testid="stPopover"] > div {
                width: 900px !important;
                max-width: 900px !important;
            }
        </style>
    """, unsafe_allow_html=True)

    st.title(".. Resumo de Integração - Status Siafe")
    
    subtitulo = f"Visão consolidada por tipo de requisição de {meses_disponiveis[mes_chave]}/{ano_selecionado}."
    st.markdown(f"**{subtitulo}**")
    st.markdown("---")

    cursor = conn.cursor()
    
    sql = f"""
        SELECT 
            CASE 
                WHEN STATUS_VOBYS = 'P' THEN 'PENDENTE'
                WHEN STATUS_VOBYS = 'T' THEN 'TRANSMITIDO'
                WHEN STATUS_VOBYS = 'A' THEN 'ABERTO'
                WHEN STATUS_VOBYS = 'F' THEN 'FECHADO'
                WHEN STATUS_VOBYS = 'I' THEN 'INCONSISTENCIA DE CADASTRO'
                WHEN STATUS_VOBYS = 'O' THEN 'OUTRAS INCONSISTENCIA'
                WHEN STATUS_VOBYS = 'E' THEN 'ERRO'
                ELSE 'ABERTO'
            END AS STATUS,
            IND_TIPO_REQUISICAO AS TIPO,
            COUNT(*) AS QTD
        FROM sw_publico.SIAFE_EVENTO_INTEGRACAO
        WHERE ANO = {ano_selecionado} AND MES = {int(mes_chave)}
        GROUP BY STATUS_VOBYS, IND_TIPO_REQUISICAO
    """

    with st.spinner("Compilando métricas..."):
        try:
            cursor.execute(sql)
            rows = cursor.fetchall()
            
            if not rows:
                st.info(f"Nenhum dado encontrado para {meses_disponiveis[mes_chave]}/{ano_selecionado}.")
                cursor.close()
                return
                
            df_bruto = pd.DataFrame(rows, columns=['STATUS', 'TIPO', 'QTD'])
            df_bruto['TIPO'] = df_bruto['TIPO'].astype(str).str.upper().str.strip()
            df_pivot = df_bruto.pivot(index='STATUS', columns='TIPO', values='QTD').fillna(0).astype(int).reset_index()
            
            for col in ['V1', 'V2', 'V3', 'V4']:
                if col not in df_pivot.columns: df_pivot[col] = 0
            df_pivot = df_pivot.rename(columns={'V1': 'COLABORADOR', 'V2': 'CREDITO', 'V3': 'ORCAMENTARIO', 'V4': 'PATRONAL'})
            df_pivot['TOTAL'] = df_pivot[['COLABORADOR', 'CREDITO', 'ORCAMENTARIO', 'PATRONAL']].sum(axis=1)
            
            total_geral = df_pivot["TOTAL"].sum()
            total_abertos = df_pivot[df_pivot['STATUS'] == 'ABERTO']['TOTAL'].sum()
            total_erros = df_pivot[df_pivot['STATUS'].str.contains('ERRO|INCONSISTENCIA', na=False)]['TOTAL'].sum()
            pct_erros = (total_erros / total_geral * 100) if total_geral > 0 else 0.0

            # METRICAS
            c1, c2, c3, c4 = st.columns(4)
            with c1: st.metric(".. Volume Total", int(total_geral))
            with c2: st.metric(".. Total Aberto", int(total_abertos))
            with c3:
                st.metric(".. Inconsistências / Erros", int(total_erros), f"{pct_erros:.1f}% Impacto", delta_color="inverse")
                if total_erros > 0:
                    with st.popover("Ver Detalhes dos Erros"):
                        st.markdown("### Lista de Erros Pendentes")
                        query = get_query_detalhe_erros(ano_selecionado, int(mes_chave))
                        df_detalhe = pd.read_sql(query, conn)
                        
                        # Preparação segura do DataFrame para o LinkColumn sem usar o argumento 'url'
                        df_detalhe['LINK_FORMATADO'] = df_detalhe['LINK_EVENTO']
                        
                        st.dataframe(
                            df_detalhe[['LINK_FORMATADO', 'DESCRICAO']], 
                            use_container_width=True, 
                            hide_index=True, 
                            column_config={
                                "LINK_FORMATADO": st.column_config.LinkColumn(
                                    "ID EVENTO", 
                                    help="Clique para acessar o evento no sistema",
                                    display_text=r"evento-transmissao/(\d+)"
                                ),
                                "DESCRICAO": st.column_config.TextColumn("DESCRIÇÃO", width="large")
                            }
                        )
            with c4: st.metric("Taxa de Eficiência", f"{(100.0 - pct_erros):.1f}%")
            
            # TABELA FINAL
            row_total = pd.DataFrame([["TOTAL GERAL"] + [df_pivot[c].sum() for c in ['COLABORADOR', 'CREDITO', 'ORCAMENTARIO', 'PATRONAL', 'TOTAL']]], columns=df_pivot.columns)
            df_final = pd.concat([df_pivot, row_total], ignore_index=True)
            
            def estilo_linha(row):
                if row['STATUS'] == 'TOTAL GERAL': return ['background-color: #343a40; color: #ffffff; font-weight: bold;'] * len(row)
                if 'ERRO' in str(row['STATUS']): return ['background-color: #fce8e6; color: #a51d24;'] * len(row)
                return [''] * len(row)

            st.dataframe(df_final.style.apply(estilo_linha, axis=1), use_container_width=True, hide_index=True)

        except Exception as e:
            st.error(f"Erro ao processar: {e}")
    cursor.close()

