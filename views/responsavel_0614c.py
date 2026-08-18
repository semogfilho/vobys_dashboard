# -*- coding: utf-8 -*-
import streamlit as st
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
            .sub-bloco-titulo { font-size: 0.85rem !important; font-weight: bold !important; letter-spacing: 0.5px; margin-bottom: 6px !important; margin-top: 4px !important; }
            .auditoria-box { background-color: #f0f7ff; padding: 15px; border-radius: 8px; border-left: 5px solid #2563eb; margin-bottom: 20px; font-weight: 500; color: #1e3a8a; }
        </style>
    """, unsafe_allow_html=True)

    def colorir_status(row):
        if row['STATUS ATUAL'] == 'ABERTA': return ['background-color: #fff5f5; color: #c92a2a; font-weight: 500;'] * len(row)
        return ['background-color: #f4fbf7; color: #2b8a3e; font-weight: normal;'] * len(row)

    st.title(".. Painel de Controle - Produtividade por Responsável")

    # --- LÓGICA DE DADOS ---
    schemas_jose, schemas_pedro, schemas_armando, schemas_deividy, schemas_sarah = get_listas_schemas_responsaveis()
    cursor = conn.cursor()
    
    # [Coleta de dados do banco]
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

    resultados = []
    for schema in todos_schemas_banco:
        resp = 'DEMAIS'
        if schema in schemas_jose: resp = 'JOSE GOMES'
        elif schema in schemas_pedro: resp = 'PEDRO MENDES'
        elif schema in schemas_armando: resp = 'ARMANDO'
        elif schema in schemas_deividy: resp = 'DEIVIDY'
        elif schema in schemas_sarah: resp = 'SARAH'
        
        n_tot, n_ab, e_tot, e_ab = 0, 0, 0, 0
        chaves_lista = []
        if schema in schemas_com_folha:
            cursor.execute(f"SELECT COUNT(*) FROM {schema}.FOLHA WHERE ANO = {ano_selecionado} AND MES = {int(mes_chave)}")
            n_tot = cursor.fetchone()[0]
            sql_n = f"SELECT f.CHAVE_FOLHA || ' (' || t.DESCRICAO_TIPO || ')' FROM {schema}.FOLHA f JOIN SW_PUBLICO.FOLHA_TAB_TIPO t ON f.ID_TIPO_FOLHA = t.ID_TIPO_FOLHA WHERE f.ANO = {ano_selecionado} AND f.MES = {int(mes_chave)} AND f.DATA_FECHAMENTO IS NULL"
            n_rows = cursor.execute(sql_n).fetchall()
            n_ab = len(n_rows)
            chaves_lista.extend([r[0] for r in n_rows])
            
        if schema in schemas_com_estag:
            cursor.execute(f"SELECT COUNT(*) FROM {schema}.ESTAG_FOLHA WHERE ANO = {ano_selecionado} AND MES = {int(mes_chave)}")
            e_tot = cursor.fetchone()[0]
            sql_e = f"SELECT ef.MASCARA || ' (' || t.DESCRICAO_TIPO || ')' FROM {schema}.ESTAG_FOLHA ef JOIN SW_PUBLICO.FOLHA_TAB_TIPO t ON ef.ID_TIPO_FOLHA = t.ID_TIPO_FOLHA WHERE ef.ANO = {ano_selecionado} AND ef.MES = {int(mes_chave)} AND ef.DATA_FECHAMENTO IS NULL"
            e_rows = cursor.execute(sql_e).fetchall()
            e_ab = len(e_rows)
            chaves_lista.extend([r[0] for r in e_rows])

        if (n_tot + e_tot) > 0:
            resultados.append({'RESPONSAVEL': resp, 'ORGAO': schema.replace('SW_', ''), 'STATUS': 'ABERTA' if (n_ab + e_ab) > 0 else 'FECHADA', 'CHAVES': ", ".join(chaves_lista), 'N_TOT': n_tot, 'N_AB': n_ab, 'E_TOT': e_tot, 'E_AB': e_ab})
    cursor.close()
    
    df = pd.DataFrame(resultados)
    df['QTD FECHADAS'] = (df['N_TOT'] + df['E_TOT']) - (df['N_AB'] + df['E_AB'])
    
    # --- RESUMO CONSOLIDADO ---
    st.markdown(f"### 📊 CONSOLIDADO GERAL ({mes_nome}/{ano_selecionado})")
    
    df_resumo = df[['ORGAO', 'STATUS', 'QTD FECHADAS', 'CHAVES']]
    df_resumo.columns = ['ÓRGÃO / SCHEMA', 'STATUS ATUAL', 'QTD FECHADAS', 'COMPOSIÇÃO DAS FOLHAS ABERTAS']
    
    df_styled = df_resumo.style.apply(colorir_status, axis=1)
    st.dataframe(df_styled, use_container_width=True, hide_index=True)

    st.markdown(f"""
        <div class="auditoria-box">
            📌 Visão consolidada, status de fechamento e auditoria de pendências por operador em {mes_nome}/{ano_selecionado}.
        </div>
    """, unsafe_allow_html=True)

    # --- LISTAGEM RESPONSÁVEIS ---
    for responsavel in ['JOSE GOMES', 'PEDRO MENDES', 'ARMANDO', 'DEIVIDY', 'SARAH', 'DEMAIS']:
        df_resp = df[df['RESPONSAVEL'] == responsavel]
        if df_resp.empty: continue
        
        tot_geral = df_resp[['N_TOT', 'E_TOT']].sum().sum()
        ab_geral = df_resp[['N_AB', 'E_AB']].sum().sum()
        indice = ((tot_geral - ab_geral) / tot_geral * 100) if tot_geral > 0 else 100.0
        
        titulo = f"👤 {responsavel} | 🏛️ Órgãos: {len(df_resp)} | 📄 Total: {tot_geral} | 🎯 Índice: {indice:.1f}%"
        
        with st.expander(titulo):
            c1, c2 = st.columns(2)
            with c1:
                st.markdown('<p class="sub-bloco-titulo">[VOLUMETRIA: NORMAL]</p>', unsafe_allow_html=True)
                g1, g2 = st.columns(2)
                g1.metric("Total", df_resp['N_TOT'].sum())
                g2.metric("Abertas", df_resp['N_AB'].sum())
            with c2:
                st.markdown('<p class="sub-bloco-titulo">[VOLUMETRIA: ESTAGIÁRIO]</p>', unsafe_allow_html=True)
                g1, g2 = st.columns(2)
                g1.metric("Total", df_resp['E_TOT'].sum())
                g2.metric("Abertas", df_resp['E_AB'].sum())
            
            df_resp_styled = df_resp[['ORGAO', 'STATUS', 'QTD FECHADAS', 'CHAVES']].rename(columns={'STATUS': 'STATUS ATUAL'}).style.apply(colorir_status, axis=1)
            st.dataframe(df_resp_styled, use_container_width=True, hide_index=True)

