# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
from queries import get_query_detalhe_erros

def render(conn, ano_selecionado, mes_chave, meses_disponiveis):
    # --- CSS PARA ESTILO E ALINHAMENTO ---
    st.markdown("""
        <style>
            .block-container { padding-top: 1rem !important; padding-bottom: 1rem !important; }
            /* Garante que o popover de ações seja compacto */
            [data-testid="stPopover"] { width: 100% !important; }
            div[data-testid="stVerticalBlock"] > div:has(h3) { margin-top: -15px !important; }
        </style>
    """, unsafe_allow_html=True)

    st.title(".. Resumo de Integração - Status Siafe")
    st.markdown(f"**Visão consolidada por tipo de requisição de {meses_disponiveis[mes_chave]}/{ano_selecionado}.**")
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

            # METRICAS - 5 Colunas para manter o botão "Ações" compacto ao lado
            c1, c2, c3, c4, c5 = st.columns([1, 1, 1, 1, 0.7])
            with c1: st.metric(".. Volume Total", int(total_geral))
            with c2: st.metric(".. Total Aberto", int(total_abertos))
            with c3: st.metric(".. Inconsistências / Erros", int(total_erros), f"{pct_erros:.1f}% Impacto", delta_color="inverse")
            with c4: st.metric("Taxa de Eficiência", f"{(100.0 - pct_erros):.1f}%")
            
            with c5:
                st.write("Ações")
                if total_erros > 0:
                    with st.popover("Ver Erros"):
                        # --- ALTERAÇÃO AQUI: Alinhando Título e Botão lado a lado ---
                        col_pop_titulo, col_pop_btn = st.columns([2, 1])
                        
                        with col_pop_titulo:
                            st.markdown("### ⚠️ Detalhes")
                        
                        with col_pop_btn:
                            # Botão pequeno para atualizar os dados do banco
                            if st.button("🔄 Atualizar", key="btn_refresh_erros", use_container_width=True):
                                st.cache_data.clear()
                                st.rerun()
                        
                        # Carrega e renderiza a query de detalhes atualizada
                        query = get_query_detalhe_erros(ano_selecionado, int(mes_chave))
                        df_detalhe = pd.read_sql(query, conn)
                        
                        # Exibição segura sem o parâmetro 'url'
                        st.dataframe(
                            df_detalhe[['LINK_EVENTO', 'DESCRICAO']], 
                            use_container_width=True, 
                            hide_index=True,
                            column_config={
                                "LINK_EVENTO": st.column_config.LinkColumn("ID EVENTO", display_text=r"evento-transmissao/(\d+)")
                            }
                        )

            # TABELA FINAL COM ESTILO AVERMELHADO
            row_total = pd.DataFrame([["TOTAL GERAL"] + [df_pivot[c].sum() for c in ['COLABORADOR', 'CREDITO', 'ORCAMENTARIO', 'PATRONAL', 'TOTAL']]], columns=df_pivot.columns)
            df_final = pd.concat([df_pivot, row_total], ignore_index=True)
            
            def aplicar_estilo(row):
                # Cor avermelhada suave para linhas de erro
                if "ERRO" in str(row['STATUS']).upper() or "INCONSISTENCIA" in str(row['STATUS']).upper():
                    return ['background-color: #fce8e6'] * len(row)
                if row['STATUS'] == 'TOTAL GERAL':
                    return ['background-color: #343a40; color: white'] * len(row)
                return [''] * len(row)

            st.dataframe(df_final.style.apply(aplicar_estilo, axis=1), use_container_width=True, hide_index=True)

        except Exception as e:
            st.error(f"Erro ao processar: {e}")
    cursor.close()

