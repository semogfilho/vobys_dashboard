# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import time

from queries import get_query_detalhe_erros, get_query_json_patronal_emgerpi

def render(conn, ano_selecionado, mes_chave, meses_disponiveis):
    # --- CSS PARA ESTILO, ALINHAMENTO E ALARGAMENTO DO POPOVER ---
    st.markdown("""
        <style>
            .block-container { padding-top: 1rem !important; padding-bottom: 1rem !important; }

            /* FORÇA O POPOVER A TER O DOBRO DO TAMANHO (DE ~500px PARA 950px) */
            div[data-testid="stPopoverBody"] {
                width: 950px !important;
                max-width: 950px !important;
                /* Desloca o painel para a esquerda para não cortar na borda direita da tela */
                position: relative;
                left: -020px;
            }

            /* Ajuste geral do componente do popover */
            [data-testid="stPopover"] { width: 100% !important; }
            div[data-testid="stVerticalBlock"] > div:has(h3) { margin-top: -15px !important; }
        </style>
    """, unsafe_allow_html=True)

    st.title(".. Resumo de Integração - Status Siafe")
    st.markdown(f"**Visão consolidada por tipo de requisição de {meses_disponiveis[mes_chave]}/{ano_selecionado}.**")

    st.markdown("---")

    # --- CONTROLE DE MUDANÇA DE FILTRO (LIMPEZA DO JSON AO MUDAR MÊS/ANO) ---
    competencia_atual = f"{ano_selecionado}_{int(mes_chave):02d}"
    if st.session_state.get('ultima_competencia_emgerpi') != competencia_atual:
        st.session_state['json_emgerpi'] = None
        st.session_state['ultima_competencia_emgerpi'] = competencia_atual

    # --- CONTROLE DE ATUALIZAÇÃO AUTOMÁTICA ---
    if 'auto_refresh' not in st.session_state:
        st.session_state.auto_refresh = False

    # Colunas para alinhar o toggle e o contador na mesma linha
    col_t, col_c = st.columns([1, 2])

    with col_t:
        st.session_state.auto_refresh = st.toggle("Ativar Atualização (5s)", value=st.session_state.auto_refresh)

    # Placeholder para o contador dentro da segunda coluna
    with col_c:
        placeholder_contador = st.empty()

    if st.session_state.auto_refresh:
        for i in range(5, 0, -1):
            placeholder_contador.caption(f"Próxima atualização em {i}s...")
            time.sleep(1)

        # Recarrega a página após a contagem
        st.rerun()

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

            # --- PROTEÇÃO PARA QUANDO NÃO HÁ DADOS ---
            if not rows:
                df_pivot = pd.DataFrame(columns=['STATUS', 'COLABORADOR', 'CREDITO', 'ORCAMENTARIO', 'PATRONAL', 'TOTAL', 'STATUS_INTEGRA'])
            else:
                df_bruto = pd.DataFrame(rows, columns=['STATUS', 'TIPO', 'QTD'])
                df_bruto['TIPO'] = df_bruto['TIPO'].astype(str).str.upper().str.strip()
                df_pivot = df_bruto.pivot(index='STATUS', columns='TIPO', values='QTD').fillna(0).astype(int).reset_index()

                for col in ['V1', 'V2', 'V3', 'V4']:
                    if col not in df_pivot.columns: df_pivot[col] = 0
                df_pivot = df_pivot.rename(columns={'V1': 'COLABORADOR', 'V2': 'CREDITO', 'V3': 'ORCAMENTARIO', 'V4': 'PATRONAL'})
                df_pivot['TOTAL'] = df_pivot[['COLABORADOR', 'CREDITO', 'ORCAMENTARIO', 'PATRONAL']].sum(axis=1)

                # --- TRATAMENTO E FILTRO DE STATUS ---
                df_pivot['STATUS_INTEGRA'] = df_pivot['STATUS'].astype(str).str.strip().str.upper()

            # --- CÁLCULOS SEGUROS ---
            total_geral = int(df_pivot["TOTAL"].sum()) if "TOTAL" in df_pivot.columns else 0
            total_abertos = int(df_pivot[df_pivot['STATUS_INTEGRA'] == 'ABERTO']['TOTAL'].sum()) if not df_pivot.empty and 'STATUS_INTEGRA' in df_pivot.columns else 0

            # Alertas: Inconsistências e Erros
            total_erros = int(df_pivot[df_pivot['STATUS_INTEGRA'].str.contains('ERRO|INCONSISTENCIA', na=False)]['TOTAL'].sum()) if not df_pivot.empty and 'STATUS_INTEGRA' in df_pivot.columns else 0
            pct_erros = (total_erros / total_geral * 100) if total_geral > 0 else 0.0

            # CÁLCULO DE EFICIÊNCIA
            total_fechados = int(df_pivot[df_pivot['STATUS_INTEGRA'] == 'FECHADO']['TOTAL'].sum()) if not df_pivot.empty and 'STATUS_INTEGRA' in df_pivot.columns else 0
            total_transmitidos = int(df_pivot[df_pivot['STATUS_INTEGRA'] == 'TRANSMITIDO']['TOTAL'].sum()) if not df_pivot.empty and 'STATUS_INTEGRA' in df_pivot.columns else 0

            total_eficientes = total_fechados + total_transmitidos + total_abertos
            taxa_eficiencia = (total_eficientes / total_geral * 100) if total_geral > 0 else 0.0

            # METRICAS - Balanceado para manter o alinhamento
            c1, c2, c3, c4, c5 = st.columns([1, 1, 1, 1, 0.7])

            with c1: st.metric(".. Volume Total", int(total_geral))
            with c2: st.metric(".. Total Aberto", int(total_abertos))
            with c3: st.metric(".. Inconsistências / Erros", int(total_erros), f"{pct_erros:.1f}% Impacto", delta_color="inverse")
            with c4: st.metric("Taxa de Eficiência", f"{taxa_eficiencia:.1f}%")

            with c5:
                st.write("Ações")
                if total_erros > 0:
                    with st.popover("Ver Erros"):
                        col_pop_btn, col_pop_titulo = st.columns([1, 3])

                        with col_pop_btn:
                            if st.button("🔄 Atualizar", key="btn_refresh_erros"):
                                st.cache_data.clear()
                                st.rerun()

                        with col_pop_titulo:
                            st.markdown("### ⚠️ Detalhes dos Erros de Integração")

                        query = get_query_detalhe_erros(ano_selecionado, int(mes_chave))
                        df_detalhe = pd.read_sql(query, conn)

                        # Mapeamento e tradução dos tipos de requisição
                        if 'TIPO_REQ' in df_detalhe.columns:
                            df_detalhe['TIPO_REQ'] = df_detalhe['TIPO_REQ'].astype(str).str.strip().str.upper()
                            mapeamento_tipos = {
                                'V1': 'COLABORADOR',
                                'V2': 'CREDITO',
                                'V3': 'ORÇAMENTÁRIO',
                                'V4': 'PATRONAL'
                            }
                            df_detalhe['TIPO_REQ'] = df_detalhe['TIPO_REQ'].map(mapeamento_tipos).fillna(df_detalhe['TIPO_REQ'])

                        df_exibicao = df_detalhe.copy()
                        df_exibicao['LINK_LIMPO'] = df_exibicao['LINK_EVENTO'].str.replace('/alterar', '', regex=False)

                        st.dataframe(
                            df_exibicao[[
                                'LINK_LIMPO',
                                'TIPO_REQ',
                                'NUM_RECIBO',
                                'DESCRICAO',
                                'CODIGO_SEFAZ',
                                'TIPO_ARQUIVO',
                                'CODIGO_RELATORIO',
                                'DATA_PROCESSAMENTO'
                            ]],
                            use_container_width=True,
                            hide_index=True,
                            column_config={
                                "LINK_LIMPO": st.column_config.LinkColumn(
                                    "ID EVENTO",
                                    display_text=r"evento-transmissao/(\d+)"
                                ),
                                "TIPO_REQ": st.column_config.TextColumn("TIPO REQUISIÇÃO"),
                                "NUM_RECIBO": st.column_config.TextColumn("Nº RECIBO"),
                                "DESCRICAO": st.column_config.TextColumn("MOTIVO DO ERRO"),
                                "CODIGO_SEFAZ": st.column_config.TextColumn("COD_SEFAZ"),
                                "TIPO_ARQUIVO": st.column_config.TextColumn("TIPO ARQUIVO"),
                                "CODIGO_RELATORIO": st.column_config.TextColumn("CÓD. RELATÓRIO"),
                                "DATA_PROCESSAMENTO": st.column_config.DatetimeColumn("DATA PROCESSAMENTO", format="DD/MM/YYYY HH:mm:ss")
                            }
                        )

            # Limpa coluna de tratamento antes de exibir a tabela final
            df_visual = df_pivot.drop(columns=['STATUS_INTEGRA'])

            # TABELA FINAL COM ESTILO AVERMELHADO
            row_total = pd.DataFrame([["TOTAL GERAL"] + [df_visual[c].sum() for c in ['COLABORADOR', 'CREDITO', 'ORCAMENTARIO', 'PATRONAL', 'TOTAL']]], columns=df_visual.columns)
            df_final = pd.concat([df_visual, row_total], ignore_index=True)

            def aplicar_estilo(row):
                if "ERRO" in str(row['STATUS']).upper() or "INCONSISTENCIA" in str(row['STATUS']).upper():
                    return ['background-color: #fce8e6'] * len(row)
                if row['STATUS'] == 'TOTAL GERAL':
                    return ['background-color: #343a40; color: white'] * len(row)
                return [''] * len(row)

            st.dataframe(df_final.style.apply(aplicar_estilo, axis=1), width='stretch', hide_index=True)

            # --- NOVA SEÇÃO: AÇÃO PATRONAL EMGERPI ---
            st.markdown("---")
            
            # Botão principal de geração com propriedade disabled baseada em total_geral
            btn_desabilitado = (total_geral == 0)
            
            if st.button("🚀 Gerar PATRONAL EMGERPI", type="primary", use_container_width=False, disabled=btn_desabilitado):
                with st.spinner("Gerando JSON consolidado PATRONAL EMGERPI..."):
                    try:
                        sql_json = get_query_json_patronal_emgerpi(ano_selecionado, mes_chave)
                        cursor.execute(sql_json)
                        row = cursor.fetchone()

                        if row and row[0]:
                            json_res = row[0]
                            if hasattr(json_res, 'read'):
                                json_res = json_res.read()

                            st.session_state['json_emgerpi'] = str(json_res)
                        else:
                            st.session_state['json_emgerpi'] = None
                            st.warning("Nenhum registro encontrado para a requisição Patronal (V4) nesta competência.")

                    except Exception as err_json:
                        st.error(f"Erro ao gerar JSON consolidado: {err_json}")

            # Exibe o resultado e o botão de download apenas se houver JSON gerado para a competência atual
            if st.session_state.get('json_emgerpi'):
                st.success("✅ JSON Patronal EMGERPI consolidado com sucesso!")

                # Botão de download posicionado logo abaixo da geração
                st.download_button(
                    label="📥 Baixar Arquivo JSON",
                    data=st.session_state['json_emgerpi'],
                    file_name=f"PATRONAL_EMGERPI_{ano_selecionado}_{int(mes_chave):02d}.json",
                    mime="application/json"
                )

                # Exibição do JSON formatado
                st.json(st.session_state['json_emgerpi'])

        except Exception as e:
            st.error(f"Erro ao processar: {e}")

    cursor.close()

