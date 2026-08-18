# -*- coding: utf-8 -*-
import streamlit as st
import oracledb
import pandas as pd
from queries import get_listas_schemas_responsaveis

def render(conn, ano_selecionado, mes_chave, meses_disponiveis):
    meses_map = {1: 'Jan', 2: 'Fev', 3: 'Mar', 4: 'Abr', 5: 'Mai', 6: 'Jun',
                 7: 'Jul', 8: 'Ago', 9: 'Set', 10: 'Out', 11: 'Nov', 12: 'Dez'}
    mes_nome = meses_map.get(int(mes_chave), "")

    # --- CSS ---
    st.markdown("""
        <style>
            .block-container { padding-top: 1rem !important; padding-bottom: 1rem !important; }
            div[data-testid="stMetric"] { background-color: #f8f9fa; padding: 12px 15px !important; border-radius: 6px !important; border: 1px solid #e9ecef !important; }
            .sub-bloco-titulo { font-size: 0.85rem !important; font-weight: bold !important; letter-spacing: 0.5px; margin-bottom: 6px !important; margin-top: 4px !important; }
        </style>
    """, unsafe_allow_html=True)

    st.title(".. Painel de Controle - Produtividade por Responsável")
    
    schemas_jose, schemas_pedro, schemas_armando, schemas_deividy, schemas_sarah = get_listas_schemas_responsaveis()
    cursor = conn.cursor()
    
    # Mapeamento e Coleta
    todos_schemas_banco = []
    try:
        cursor.execute("SELECT owner FROM all_tables WHERE table_name = 'FOLHA_FUNC' AND owner LIKE 'SW_%' AND owner NOT IN ('SW_PUBLICO', 'SW_MODELO') ORDER BY owner")
        todos_schemas_banco = [row[0] for row in cursor.fetchall()]
    except:
        todos_schemas_banco = list(set(schemas_jose + schemas_pedro + schemas_armando + schemas_deividy + schemas_sarah))

    schemas_com_folha = set(row[0] for row in cursor.execute("SELECT owner FROM all_tables WHERE table_name = 'FOLHA' AND owner LIKE 'SW_%'").fetchall())
    schemas_com_estag = set(row[0] for row in cursor.execute("SELECT owner FROM all_tables WHERE table_name = 'ESTAG_FOLHA' AND owner LIKE 'SW_%'").fetchall())

    todos_schemas_mapeados = []
    for schema in todos_schemas_banco:
        resp = 'DEMAIS'
        if schema in schemas_jose: resp = 'JOSE GOMES'
        elif schema in schemas_pedro: resp = 'PEDRO MENDES'
        elif schema in schemas_armando: resp = 'ARMANDO'
        elif schema in schemas_deividy: resp = 'DEIVIDY'
        elif schema in schemas_sarah: resp = 'SARAH'
        todos_schemas_mapeados.append((resp, schema))
    
    resultados = []
    for resp, schema in todos_schemas_mapeados:
        n_tot, n_ab, e_tot, e_ab = 0, 0, 0, 0
        chaves_lista = []
        if schema in schemas_com_folha:
            n_tot = cursor.execute(f"SELECT COUNT(*) FROM {schema}.FOLHA WHERE ANO = {ano_selecionado} AND MES = {int(mes_chave)}").fetchone()[0]
            n_rows = cursor.execute(f"SELECT f.CHAVE_FOLHA || ' (' || t.DESCRICAO_TIPO || ')' FROM {schema}.FOLHA f JOIN SW_PUBLICO.FOLHA_TAB_TIPO t ON f.ID_TIPO_FOLHA = t.ID_TIPO_FOLHA WHERE f.ANO = {ano_selecionado} AND f.MES = {int(mes_chave)} AND f.DATA_FECHAMENTO IS NULL ORDER BY f.CHAVE_FOLHA").fetchall()
            n_ab = len(n_rows)
            chaves_lista.extend([r[0] for r in n_rows])
        if schema in schemas_com_estag:
            e_tot = cursor.execute(f"SELECT COUNT(*) FROM {schema}.ESTAG_FOLHA WHERE ANO = {ano_selecionado} AND MES = {int(mes_chave)}").fetchone()[0]
            e_rows = cursor.execute(f"SELECT ef.MASCARA || ' (' || t.DESCRICAO_TIPO || ')' FROM {schema}.ESTAG_FOLHA ef JOIN SW_PUBLICO.FOLHA_TAB_TIPO t ON ef.ID_TIPO_FOLHA = t.ID_TIPO_FOLHA WHERE ef.ANO = {ano_selecionado} AND ef.MES = {int(mes_chave)} AND ef.DATA_FECHAMENTO IS NULL ORDER BY ef.MASCARA").fetchall()
            e_ab = len(e_rows)
            chaves_lista.extend([r[0] for r in e_rows])

        if (n_tot + e_tot) > 0:
            resultados.append({'RESPONSAVEL': resp, 'ORGAO': schema.replace('SW_', ''), 'STATUS': 'ABERTA' if (n_ab + e_ab) > 0 else 'FECHADA', 'CHAVES': ", ".join(chaves_lista) if chaves_lista else '---', 'N_TOT': n_tot, 'N_AB': n_ab, 'E_TOT': e_tot, 'E_AB': e_ab})
    cursor.close()

    df = pd.DataFrame(resultados)

    # --- RESUMO CONSOLIDADO GERAL ---
    geral_total_orgaos = len(df)
    geral_org_abertos = len(df[df['STATUS'] == 'ABERTA'])
    geral_folhas_totais = df[['N_TOT', 'E_TOT']].sum().sum()
    geral_folhas_abertas = df[['N_AB', 'E_AB']].sum().sum()
    geral_folhas_fechadas = geral_folhas_totais - geral_folhas_abertas
    geral_taxa = ((geral_folhas_totais - geral_folhas_abertas) / geral_folhas_totais * 100) if geral_folhas_totais > 0 else 100.0

    st.markdown(f"### 📊 CONSOLIDADO GERAL ({mes_nome}/{ano_selecionado})")
    c_esq_g, c_dir_g = st.columns(2)
    with c_esq_g:
        st.markdown("<p style='margin-bottom: 4px; font-size: 0.9rem; color: #1f2937; font-weight: bold;'>[BALANÇO DE ESTRUTURAS - ÓRGÃOS]</p>", unsafe_allow_html=True)
        with st.container(border=True):
            g1, g2, g3 = st.columns(3)
            g1.metric("Total Órgãos", value=f"{geral_total_orgaos}")
            g2.metric("Total Abertos", value=f"{geral_org_abertos}", delta=f"{geral_org_abertos} pend.", delta_color="inverse")
            g3.metric("Total Fechados", value=f"{geral_total_orgaos - geral_org_abertos}")
    with c_dir_g:
        st.markdown("<p style='margin-bottom: 4px; font-size: 0.9rem; color: #1e40af; font-weight: bold;'>[BALANÇO DE PRODUTIVIDADE - FOLHAS FÍSICAS]</p>", unsafe_allow_html=True)
        with st.container(border=True):
            gf1, gf2, gf3 = st.columns(3)
            gf1.metric("Volumetria Total", value=f"{geral_folhas_totais}")
            gf2.metric("Folhas Abertas", value=f"{geral_folhas_abertas}", delta=f"{geral_folhas_abertas} travadas", delta_color="inverse")
            gf3.metric("Folhas Fechadas", value=f"{geral_folhas_fechadas}")

    if geral_folhas_abertas == 0: st.success(f"🎉 **Meta Atingida!** 100% liquidadas.")
    else: st.info(f"📈 **Indicador de Performance:** Concluído **{geral_taxa:.1f}%**. Restam {geral_folhas_abertas} folhas.")

    # --- DETALHAMENTO POR RESPONSÁVEL ---
    def colorir_status(row):
        if row['STATUS'] == 'ABERTA': return ['background-color: #fff5f5; color: #c92a2a; font-weight: 500;'] * len(row)
        return ['background-color: #f4fbf7; color: #2b8a3e; font-weight: normal;'] * len(row)

    for responsavel in ['JOSE GOMES', 'PEDRO MENDES', 'ARMANDO', 'DEIVIDY', 'SARAH', 'DEMAIS']:
        df_resp = df[df['RESPONSAVEL'] == responsavel]
        if df_resp.empty: continue
            
        tot_n = df_resp['N_TOT'].sum(); ab_n = df_resp['N_AB'].sum()
        tot_e = df_resp['E_TOT'].sum(); ab_e = df_resp['E_AB'].sum()
        total = tot_n + tot_e
        abertas = ab_n + ab_e
        indice = ((total - abertas) / total * 100) if total > 0 else 100.0
        
        titulo = f"👤 **RESPONSÁVEL:** {responsavel} | 🏛️ **Órgãos:** {len(df_resp)} | 📄 **Total:** {total} | 🎯 **ÍNDICE:** {indice:.1f}%"
        with st.expander(titulo, expanded=(responsavel == 'JOSE GOMES')):
            c_org, c_vol_n, c_vol_e = st.columns([1, 1, 1])
            with c_org:
                st.markdown('<p class="sub-bloco-titulo">[BALANÇO DE ESTRUTURAS]</p>', unsafe_allow_html=True)
                g1, g2 = st.columns(2)
                g1.metric("Total Órgãos", len(df_resp))
                g2.metric("Abertos", len(df_resp[df_resp['STATUS'] == 'ABERTA']))
            with c_vol_n:
                st.markdown('<p class="sub-bloco-titulo">[VOLUMETRIA: NORMAL]</p>', unsafe_allow_html=True)
                g1, g2 = st.columns(2)
                g1.metric("Total", tot_n)
                g2.metric("Abertas", ab_n)
            with c_vol_e:
                st.markdown('<p class="sub-bloco-titulo">[VOLUMETRIA: ESTAGIÁRIO]</p>', unsafe_allow_html=True)
                g1, g2 = st.columns(2)
                g1.metric("Total", tot_e)
                g2.metric("Abertas", ab_e)

            df_display = df_resp[['ORGAO', 'STATUS', 'CHAVES']]
            df_display['ORDEM'] = df_display['STATUS'].map({'ABERTA': 1, 'FECHADA': 2})
            df_display = df_display.sort_values('ORDEM').drop(columns=['ORDEM'])
            st.dataframe(df_display.style.apply(colorir_status, axis=1), use_container_width=True, hide_index=True)

