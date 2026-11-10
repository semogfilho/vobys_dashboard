# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
from queries import get_listas_schemas_responsaveis

# --- CÁLCULO SEGURO DAS MÉTRICAS ---
        # Garante que as colunas existem antes de somar, caso contrário assume 0
def safe_sum(col_name):
    return df_resp[col_name].sum() if col_name in df_resp.columns else 0

def render(conn, ano_selecionado, mes_chave, meses_disponiveis):
# Ajuste para identificar o 13º
    if int(mes_chave) == 13:
        mes_exibicao = "13º"
        # Se você deseja forçar o ano para 2025 quando for 13º, faça:
        ano_exibicao = 2025 
    else:
        meses_map = {1: 'Jan', 2: 'Fev', 3: 'Mar', 4: 'Abr', 5: 'Mai', 6: 'Jun',
                     7: 'Jul', 8: 'Ago', 9: 'Set', 10: 'Out', 11: 'Nov', 12: 'Dez'}
        mes_exibicao = meses_map.get(int(mes_chave), "")
        ano_exibicao = ano_selecionado


    # --- CSS ---
    st.markdown("""
        <style>
            .block-container { padding-top: 1rem !important; }
            .resumo-header { background-color: #1e3a8a; padding: 10px 15px; border-radius: 6px; color: white; font-weight: bold; margin-bottom: 15px; }
            .sub-bloco-titulo { font-size: 0.85rem !important; font-weight: bold !important; letter-spacing: 0.5px; margin-bottom: 6px !important; margin-top: 4px !important; }
        </style>
    """, unsafe_allow_html=True)

    def colorir_status(row):
        if row['STATUS ATUAL'] == 'ABERTA': return ['background-color: #fff5f5; color: #c92a2a; font-weight: 500;'] * len(row)
        return ['background-color: #f4fbf7; color: #2b8a3e; font-weight: normal;'] * len(row)

    st.title(f".. Painel de Controle ({mes_exibicao}/{ano_exibicao})")

    # --- LÓGICA DE DADOS ---
    schemas_jose, schemas_pedro, schemas_armando, schemas_deividy, schemas_sarah = get_listas_schemas_responsaveis()
    cursor = conn.cursor()
    
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
# Antes da query, defina o ano da consulta:
        ano_consulta = 2025 if int(mes_chave) == 13 else ano_selecionado

        if schema in schemas_com_folha:
            cursor.execute(f"SELECT COUNT(*) FROM {schema}.FOLHA WHERE ANO = {ano_consulta} AND MES = {int(mes_chave)}")
            n_tot = cursor.fetchone()[0]
            sql_n = f"SELECT f.CHAVE_FOLHA || ' (' || t.DESCRICAO_TIPO || ')' FROM {schema}.FOLHA f JOIN SW_PUBLICO.FOLHA_TAB_TIPO t ON f.ID_TIPO_FOLHA = t.ID_TIPO_FOLHA WHERE f.ANO = {ano_consulta} AND f.MES = {int(mes_chave)} AND f.DATA_FECHAMENTO IS NULL"
            n_rows = cursor.execute(sql_n).fetchall()
            n_ab = len(n_rows)
            chaves_lista.extend([r[0] for r in n_rows])
        if schema in schemas_com_estag:
            cursor.execute(f"SELECT COUNT(*) FROM {schema}.ESTAG_FOLHA WHERE ANO = {ano_consulta} AND MES = {int(mes_chave)}")
            e_tot = cursor.fetchone()[0]
            sql_e = f"SELECT ef.MASCARA || ' (' || t.DESCRICAO_TIPO || ')' FROM {schema}.ESTAG_FOLHA ef JOIN SW_PUBLICO.FOLHA_TAB_TIPO t ON ef.ID_TIPO_FOLHA = t.ID_TIPO_FOLHA WHERE ef.ANO = {ano_consulta} AND ef.MES = {int(mes_chave)} AND ef.DATA_FECHAMENTO IS NULL"
            e_rows = cursor.execute(sql_e).fetchall()
            e_ab = len(e_rows)
            chaves_lista.extend([r[0] for r in e_rows])

        if (n_tot + e_tot) > 0:
            resultados.append({'RESPONSAVEL': resp, 'ORGAO': schema.replace('SW_', ''), 'STATUS': 'ABERTA' if (n_ab + e_ab) > 0 else 'FECHADA', 'CHAVES': ", ".join(chaves_lista), 'N_TOT': n_tot, 'N_AB': n_ab, 'E_TOT': e_tot, 'E_AB': e_ab})
    cursor.close()
# --- CORREÇÃO: Inicialização Blindada ---
    # Define as colunas esperadas para o DataFrame
    cols_esperadas = ['RESPONSAVEL', 'ORGAO', 'STATUS', 'CHAVES', 'N_TOT', 'N_AB', 'E_TOT', 'E_AB']
    
    if resultados:
        df = pd.DataFrame(resultados)
    else:
        # Se não houver resultados, cria um DF vazio mas com as colunas definidas
        df = pd.DataFrame(columns=cols_esperadas)
        # Inicializa as colunas numéricas com 0 para evitar erros de cálculo
        for col in ['N_TOT', 'N_AB', 'E_TOT', 'E_AB']:
            df[col] = 0

    
    df['QTD FECHADAS'] = (df['N_TOT'] + df['E_TOT']) - (df['N_AB'] + df['E_AB'])
    
    # --- RESUMO CONSOLIDADO ---
    st.markdown(f'<div class="resumo-header">📊 CONSOLIDADO GERAL DO PERÍODO:</div>', unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**[BALANÇO DE ESTRUTURAS - ÓRGÃOS]**")
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Órgãos", len(df))
        c2.metric("Total Abertos", df['STATUS'].value_counts().get('ABERTA', 0))
        c3.metric("Total Fechados", df['STATUS'].value_counts().get('FECHADA', 0))
    
# --- 1. Calcule os totais de forma centralizada ---
    # Somamos todas as linhas de abertas (Normais + Estagiários)
    ab_geral = df[['N_AB', 'E_AB']].sum().sum()
    
    # Somamos a volumetria total
    tot_geral = df[['N_TOT', 'E_TOT']].sum().sum()
    
    # Calcula a % de conclusão
    concluido = ((tot_geral - ab_geral) / tot_geral * 100) if tot_geral > 0 else 0

    # --- 2. Exibição das métricas usando as variáveis calculadas ---
    # No bloco com2, substitua o c2.metric para usar a variável calculada
    with col2:
        st.markdown("**[BALANÇO DE PRODUTIVIDADE - FOLHAS FÍSICAS]**")
        c1, c2, c3 = st.columns(3)
        c1.metric("Volumetria Total", tot_geral)
        c2.metric("Folhas Abertas", int(ab_geral)) # Garantimos que exiba o mesmo valor do st.info
        c3.metric("Folhas Fechadas", df['QTD FECHADAS'].sum())

# Criamos colunas: uma para o texto do indicador e outra para o botão
    col_info, col_btn = st.columns([0.65, 0.35])
    
    with col_info:
        st.info(f"📈 **Indicador de Performance:** O sistema já concluiu {concluido:.1f}% da volumetria de **Folhas Físicas**. Restam {int(ab_geral)} folhas pendentes.")
        
    with col_btn:
	# Usamos CSS no container pai para "puxar" o botão para a esquerda (aproximando do texto)
        st.markdown("""
            <style>
                .container-botao-pendencia {
                    display: flex;
                    align-items: center;
                    gap: 10px; /* Espaço entre o texto e o botão */
                }
                /* Alvo específico apenas para este container */
                .container-botao-pendencia .stPopover {
                    margin-top: -35px; /* Ajuste vertical */
                    margin-left: 10px;  /* Ajuste horizontal */
                }
                /* Aumenta a largura do corpo do popover para o dobro do tamanho padrão */
                div[data-testid="stPopoverBody"] {
                    width: 1000px !important;      /* Dobro da largura padrão (aprox. 500px) */
                    max-width: 1000px !important;
                    /* Se precisar centralizar melhor na tela após aumentar: */
                    left: -200px !important;      
                }
        
                /* Garante que o conteúdo dentro do popover respeite a nova largura */
                [data-testid="stPopover"] { 
                    width: 100% !important; 
                }
            </style>
        """, unsafe_allow_html=True)

        with st.popover("Ver Pendências", use_container_width=False):
            st.markdown("### 📋 Folhas Abertas")
            # Filtra apenas as linhas que possuem folhas abertas (N_AB > 0 ou E_AB > 0)
            df_abertas = df[(df['N_AB'] > 0) | (df['E_AB'] > 0)]
            
            if not df_abertas.empty:
                st.dataframe(
                    df_abertas[['ORGAO', 'N_AB', 'E_AB', 'CHAVES']],
                    column_config={
                        "ORGAO": "Órgão",
                        "N_AB": "Normais",
                        "E_AB": "Estagiários",
                        "CHAVES": "Composição"
                    },
                    hide_index=True,
                    use_container_width=True
                )
            else:
                st.success("Tudo processado! Nenhuma pendência encontrada.")

    #st.title(f".. {titulo_limpo}")
    st.markdown(f'<div class="resumo-header">📊 Produtividade por Responsável</div>', unsafe_allow_html=True)


    # --- LISTAGEM RESPONSÁVEIS ---
    for responsavel in ['JOSE GOMES', 'PEDRO MENDES', 'ARMANDO', 'DEIVIDY', 'SARAH', 'DEMAIS']:
        df_resp = df[df['RESPONSAVEL'] == responsavel]
        if df_resp.empty: continue

# 3. Função auxiliar de segurança para somas (evita KeyError)
        def safe_sum(col_name):
            return df_resp[col_name].sum() if col_name in df_resp.columns else 0

# --- INSIRA A ORDENAÇÃO AQUI ---
        # Por exemplo, ordenar por Órgão (AZ) e depois pela maior quantidade de abertas
        df_resp = df_resp.sort_values(by=['STATUS'], ascending=[True])
        
        tot_geral_resp = safe_sum('N_TOT') + safe_sum('E_TOT')
        ab_geral_resp = safe_sum('N_AB') + safe_sum('E_AB')
        indice = ((tot_geral_resp - ab_geral_resp) / tot_geral_resp * 100) if tot_geral_resp > 0 else 0

        
        qtd_abertos = df_resp[df_resp['STATUS'] == 'ABERTA'].shape[0]
        qtd_fechados = df_resp[df_resp['STATUS'] == 'FECHADA'].shape[0]
        
        titulo = (f"👤 RESPONSÁVEL: {responsavel} | 🏛️ Órgãos: {len(df_resp)} ({qtd_abertos} Abertos / {qtd_fechados} Fechados) "
                  f"| 📄 [VOLUMETRIA]: {tot_geral_resp} | 🎯 ÍNDICE: {indice:.1f}%")
        
        with st.expander(titulo):
            ca, cb = st.columns(2)
            with ca:
                st.markdown('<p class="sub-bloco-titulo">[VOLUMETRIA: NORMAL]</p>', unsafe_allow_html=True)
                g1, g2 = st.columns(2)
                g1.metric("Total Normais", int(safe_sum('N_TOT')))
                g2.metric("Abertas Normais", int(safe_sum('N_AB')))
            with cb:
                st.markdown('<p class="sub-bloco-titulo">[VOLUMETRIA: ESTAGIÁRIO]</p>', unsafe_allow_html=True)
                g1, g2 = st.columns(2)
                g1.metric("Total Estag", int(safe_sum('E_TOT')))
                g2.metric("Abertas Estag", int(safe_sum('E_AB')))
            
            st.markdown("---")
            df_resp_styled = df_resp[['ORGAO', 'STATUS', 'QTD FECHADAS', 'CHAVES']].rename(columns={'ORGAO': 'ÓRGÃO / SCHEMA', 'STATUS': 'STATUS ATUAL', 'CHAVES': 'COMPOSIÇÃO DAS FOLHAS ABERTAS'}).style.apply(colorir_status, axis=1)
            st.dataframe(df_resp_styled, use_container_width=True, hide_index=True)

