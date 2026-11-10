# -*- coding: utf-8 -*-
import streamlit as st
import oracledb
import pandas as pd
from queries import get_listas_schemas_responsaveis

def render(conn, ano_selecionado, mes_chave, meses_disponiveis):
    # Adicionando o mês/ano ao título para contexto
    meses_map = {1: 'Jan', 2: 'Fev', 3: 'Mar', 4: 'Abr', 5: 'Mai', 6: 'Jun',
                 7: 'Jul', 8: 'Ago', 9: 'Set', 10: 'Out', 11: 'Nov', 12: 'Dez'}
    mes_nome = meses_map.get(int(mes_chave), "")


    # --- CSS AVANÇADO PARA PADRONIZAÇÃO E LIMPEZA DE LAYOUT ---
    st.markdown("""
        <style>
            .block-container {
                padding-top: 1rem !important;
                padding-bottom: 1rem !important;
            }
            div[data-testid="stVerticalBlock"] > div:first-child {
                margin-top: 0px !important;
                padding-top: 0px !important;
            }
            div[data-testid="stMetric"] {
                background-color: #f8f9fa;
                padding: 12px 15px !important;
                border-radius: 6px !important;
                border: 1px solid #e9ecef !important;
            }
            .sub-bloco-titulo {
                font-size: 0.85rem !important;
                font-weight: bold !important;
                letter-spacing: 0.5px;
                margin-bottom: 6px !important;
                margin-top: 4px !important;
            }
            .stExpander details summary p {
                font-size: 0.95rem !important;
                font-family: sans-serif !important;
            }
        </style>
    """, unsafe_allow_html=True)

    titulo_limpo = "Painel de Controle - Produtividade por Responsável"
    st.title(f".. {titulo_limpo}")
    
    # Coleta de dados
    schemas_jose, schemas_pedro, schemas_armando, schemas_deividy, schemas_sarah = get_listas_schemas_responsaveis()
    cursor = conn.cursor()
    
    # Validação dinâmica
    todos_schemas_banco = []
    try:
        cursor.execute("SELECT owner FROM all_tables WHERE table_name = 'FOLHA_FUNC' AND owner LIKE 'SW_%' AND owner NOT IN ('SW_PUBLICO', 'SW_MODELO') ORDER BY owner")
        todos_schemas_banco = [row[0] for row in cursor.fetchall()]
    except:
        todos_schemas_banco = list(set(schemas_jose + schemas_pedro + schemas_armando + schemas_deividy + schemas_sarah))

    schemas_com_folha, schemas_com_estag = set(), set()
    try:
        cursor.execute("SELECT owner FROM all_tables WHERE table_name = 'FOLHA' AND owner LIKE 'SW_%'")
        schemas_com_folha = set(row[0] for row in cursor.fetchall())
        cursor.execute("SELECT owner FROM all_tables WHERE table_name = 'ESTAG_FOLHA' AND owner LIKE 'SW_%'")
        schemas_com_estag = set(row[0] for row in cursor.fetchall())
    except: pass

    todos_schemas_mapeados = []
    for schema in todos_schemas_banco:
        if schema in schemas_jose: todos_schemas_mapeados.append(('JOSE GOMES', schema))
        elif schema in schemas_pedro: todos_schemas_mapeados.append(('PEDRO MENDES', schema))
        elif schema in schemas_armando: todos_schemas_mapeados.append(('ARMANDO', schema))
        elif schema in schemas_deividy: todos_schemas_mapeados.append(('DEIVIDY', schema))
        elif schema in schemas_sarah: todos_schemas_mapeados.append(('SARAH', schema))
        else: todos_schemas_mapeados.append(('DEMAIS', schema))
    
    resultados = []
    with st.spinner("Sincronizando metadados de auditoria..."):
        for resp, schema in todos_schemas_mapeados:
            orgao_nome = schema.replace('SW_', '')
            if schema not in schemas_com_folha and schema not in schemas_com_estag: continue

            qtd_total_periodo, qtd_abertas, chaves_lista = 0, 0, []
            qtd_folhas_totais, qtd_folhas_abertas_fisicas = 0, 0

            if schema in schemas_com_folha:
                cursor.execute(f"SELECT COUNT(*) FROM {schema}.FOLHA WHERE ANO = {ano_selecionado} AND MES = {int(mes_chave)}")
                f_tot = cursor.fetchone()[0]
                qtd_total_periodo += f_tot
                qtd_folhas_totais += f_tot
                cursor.execute(f"SELECT f.CHAVE_FOLHA || ' (' || t.DESCRICAO_TIPO || ')' FROM {schema}.FOLHA f JOIN SW_PUBLICO.FOLHA_TAB_TIPO t ON f.ID_TIPO_FOLHA = t.ID_TIPO_FOLHA WHERE f.ANO = {ano_selecionado} AND f.MES = {int(mes_chave)} AND f.DATA_FECHAMENTO IS NULL ORDER BY f.CHAVE_FOLHA")
                func_rows = cursor.fetchall()
                if func_rows:
                    qtd_abertas += len(func_rows)
                    qtd_folhas_abertas_fisicas += len(func_rows)
                    chaves_lista.extend([r[0] for r in func_rows])

            if schema in schemas_com_estag:
                cursor.execute(f"SELECT COUNT(*) FROM {schema}.ESTAG_FOLHA WHERE ANO = {ano_selecionado} AND MES = {int(mes_chave)}")
                e_tot = cursor.fetchone()[0]
                qtd_total_periodo += e_tot
                qtd_folhas_totais += e_tot
                cursor.execute(f"SELECT ef.MASCARA || ' (' || t.DESCRICAO_TIPO || ')' FROM {schema}.ESTAG_FOLHA ef JOIN SW_PUBLICO.FOLHA_TAB_TIPO t ON ef.ID_TIPO_FOLHA = t.ID_TIPO_FOLHA WHERE ef.ANO = {ano_selecionado} AND ef.MES = {int(mes_chave)} AND ef.DATA_FECHAMENTO IS NULL ORDER BY ef.MASCARA")
                estag_rows = cursor.fetchall()
                if estag_rows:
                    qtd_abertas += len(estag_rows)
                    qtd_folhas_abertas_fisicas += len(estag_rows)
                    chaves_lista.extend([r[0] for r in estag_rows])

            if qtd_total_periodo > 0:
                resultados.append({'RESPONSAVEL': resp, 'STATUS': 'ABERTA' if qtd_abertas > 0 else 'FECHADA', 'ORGAO': orgao_nome, 'CHAVES': ", ".join(chaves_lista) if qtd_abertas > 0 else '---', 'FOLHAS_F_TOTAL': qtd_folhas_totais, 'FOLHAS_F_ABERTAS': qtd_folhas_abertas_fisicas})
    cursor.close()

    if not resultados:
        st.info("Nenhum órgão possui movimentação de folhas registradas.")
        return

    df_resultado = pd.DataFrame(resultados)

    # =========================================================================
    # --- 1. RESUMO CONSOLIDADO GERAL (MOVIDO PARA O TOPO) ---
    # =========================================================================
    #st.markdown("---")
    st.markdown(f"""
        <div style="background-color: #1e3a8a; padding: 8px 15px; margin-top: 10px; margin-bottom: 15px; border-radius: 6px; border-left: 5px solid #3b82f6;">
            <span style="color: #ffffff; font-weight: bold; font-size: 1.15rem; letter-spacing: 0.5px;">
                📊 CONSOLIDADO GERAL DO PERÍODO :( {mes_nome}/{ano_selecionado})
            </span>
        </div>
    """, unsafe_allow_html=True)

    geral_total_orgaos = len(df_resultado)
    geral_org_abertos = len(df_resultado[df_resultado['STATUS'] == 'ABERTA'])
    geral_org_fechados = len(df_resultado[df_resultado['STATUS'] == 'FECHADA'])
    geral_folhas_totais = int(df_resultado['FOLHAS_F_TOTAL'].sum())
    geral_folhas_abertas = int(df_resultado['FOLHAS_F_ABERTAS'].sum())
    geral_folhas_fechadas = geral_folhas_totais - geral_folhas_abertas
    geral_taxa_folhas = (geral_folhas_fechadas / geral_folhas_totais * 100) if geral_folhas_totais > 0 else 100.0

    c_esq_g, c_dir_g = st.columns(2)
    with c_esq_g:
        st.markdown("<p style='margin-bottom: 4px; font-size: 0.9rem; color: #1f2937; font-weight: bold;'>[BALANÇO DE ESTRUTURAS - ÓRGÃOS]</p>", unsafe_allow_html=True)
        with st.container(border=True):
            g1, g2, g3 = st.columns(3)
            g1.metric("Total Órgãos", value=f"{geral_total_orgaos}")
            g2.metric("Total Abertos", value=f"{geral_org_abertos}", delta=f"{geral_org_abertos} pend.", delta_color="inverse")
            g3.metric("Total Fechados", value=f"{geral_org_fechados}")
    with c_dir_g:
        st.markdown("<p style='margin-bottom: 4px; font-size: 0.9rem; color: #1e40af; font-weight: bold;'>[BALANÇO DE PRODUTIVIDADE - FOLHAS FÍSICAS]</p>", unsafe_allow_html=True)
        with st.container(border=True):
            gf1, gf2, gf3 = st.columns(3)
            gf1.metric("Volumetria Total", value=f"{geral_folhas_totais}")
            gf2.metric("Folhas Abertas", value=f"{geral_folhas_abertas}", delta=f"{geral_folhas_abertas} travadas", delta_color="inverse")
            gf3.metric("Folhas Fechadas", value=f"{geral_folhas_fechadas}")

    if geral_folhas_abertas == 0: st.success(f"🎉 **Meta Atingida!** 100% das {geral_folhas_totais} folhas físicas liquidadas.")
    else: st.info(f"📈 **Indicador de Performance:** O sistema já concluiu **{geral_taxa_folhas:.1f}%** da volumetria física. Restam {geral_folhas_abertas} folhas.")
    #st.markdown("---")

    #st.markdown(f"**Visão consolidada, status de fechamento e auditoria de pendências por operador em {meses_disponiveis[mes_chave]}/{ano_selecionado}.**")
    #st.markdown("<br>", unsafe_allow_html=True)
# --- 2. SUBTÍTULO DESTAQUE ---
    st.markdown(f"""
        <div style="
            background-color: #f8fafc;
            border-left: 6px solid #1e3a8a;
            padding: 20px;
            border-radius: 8px;
            margin: 25px 0;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        ">
            <h3 style="margin: 0; color: #1e293b; font-size: 1.25rem; display: flex; align-items: center;">
                <span style="margin-right: 12px; font-size: 1.5rem;">🔍</span>
                Detalhamento Operacional: Auditoria por Responsável
            </h3>
            <p style="margin: 8px 0 0 40px; color: #475569; font-size: 1rem; line-height: 1.5;">
                Visão detalhada do status de fechamento e conformidade de pendências por responsável referente a <strong>{meses_disponiveis[mes_chave]}/{ano_selecionado}</strong>.
            </p>
        </div>
    """, unsafe_allow_html=True)
    # =========================================================================
    # --- 2. DETALHAMENTO POR RESPONSÁVEL ---
    # =========================================================================
    def colorir_status(row):
        if row['STATUS'] == 'ABERTA': return ['background-color: #fff5f5; color: #c92a2a; font-weight: 500;'] * len(row)
        return ['background-color: #f4fbf7; color: #2b8a3e; font-weight: normal;'] * len(row)

    for responsavel in ['JOSE GOMES', 'PEDRO MENDES', 'ARMANDO', 'DEIVIDY', 'SARAH', 'DEMAIS']:
        df_original_resp = df_resultado[df_resultado['RESPONSAVEL'] == responsavel]
        if df_original_resp.empty: continue
            
        total_orgaos = len(df_original_resp)
        num_abertas = len(df_original_resp[df_original_resp['STATUS'] == 'ABERTA'])
        num_fechadas = len(df_original_resp[df_original_resp['STATUS'] == 'FECHADA'])
        taxa = (num_fechadas / total_orgaos * 100) if total_orgaos > 0 else 100.0
        tot_folhas_fisicas = int(df_original_resp['FOLHAS_F_TOTAL'].sum())
        abertas_folhas_fisicas = int(df_original_resp['FOLHAS_F_ABERTAS'].sum())
        fechadas_folhas_fisicas = tot_folhas_fisicas - abertas_folhas_fisicas

        titulo = f"👤 **RESPONSÁVEL:** {responsavel} | 🏛️ **Órgãos:** {total_orgaos} | 📄 **[VOLUMETRIA FOLHAS]:** {tot_folhas_fisicas} | 🎯 **ÍNDICE:** {taxa:.1f}%"
        with st.expander(titulo, expanded=(responsavel == 'JOSE GOMES')):
            c_esq, c_dir = st.columns(2)
            with c_esq:
                st.markdown('<p class="sub-bloco-titulo" style="color: #1f2937;">[BALANÇO DE ESTRUTURAS - ÓRGÃOS]</p>', unsafe_allow_html=True)
                with st.container(border=True):
                    g1, g2, g3 = st.columns(3)
                    g1.metric("Total Órgãos", f"{total_orgaos}")
                    g2.metric("Total Abertos", f"{num_abertas}")
                    g3.metric("Total Fechados", f"{num_fechadas}")
            with c_dir:
                st.markdown('<p class="sub-bloco-titulo" style="color: #1e40af;">[BALANÇO DE PRODUTIVIDADE - FOLHAS FÍSICAS]</p>', unsafe_allow_html=True)
                with st.container(border=True):
                    gf1, gf2, gf3 = st.columns(3)
                    gf1.metric("Volumetria Total", f"{tot_folhas_fisicas}")
                    gf2.metric("Folhas Abertas", f"{abertas_folhas_fisicas}")
                    gf3.metric("Folhas Fechadas", f"{fechadas_folhas_fisicas}")

            df_filtrado = df_original_resp[['ORGAO', 'STATUS', 'FOLHAS_F_TOTAL', 'CHAVES', 'FOLHAS_F_ABERTAS']].copy()
            df_filtrado['FOLHAS_FECHADAS'] = df_filtrado['FOLHAS_F_TOTAL'] - df_filtrado['FOLHAS_F_ABERTAS']
            df_filtrado = df_filtrado[['ORGAO', 'STATUS', 'FOLHAS_FECHADAS', 'CHAVES']]
            df_filtrado['ORDEM'] = df_filtrado['STATUS'].map({'ABERTA': 1, 'FECHADA': 2})
            df_filtrado = df_filtrado.sort_values('ORDEM').drop(columns=['ORDEM'])

            df_colorido = df_filtrado.style.apply(colorir_status, axis=1).set_properties(**{'text-align': 'center'}, subset=['STATUS', 'FOLHAS_FECHADAS'])
            st.dataframe(df_colorido, use_container_width=True, hide_index=True, column_config={
                "ORGAO": st.column_config.TextColumn("ÓRGÃO / SCHEMA"),
                "STATUS": st.column_config.TextColumn("STATUS ATUAL"),
                "FOLHAS_FECHADAS": st.column_config.NumberColumn("QTD FECHADAS", format="%d", width="medium"),
                "CHAVES": st.column_config.TextColumn("COMPOSIÇÃO DAS FOLHAS ABERTAS")
            })

