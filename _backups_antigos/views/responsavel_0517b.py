# -*- coding: utf-8 -*-
import streamlit as st
import oracledb
import pandas as pd
from queries import get_listas_schemas_responsaveis

def render(conn, ano_selecionado, mes_chave, meses_disponiveis):
    # --- CSS AVANCADO PARA REESTRUTURACAO DO DESIGN ---
    st.markdown("""
        <style>
            .block-container {
                padding-top: 0.5rem !important;
                padding-bottom: 0.5rem !important;
            }
            div[data-testid="stVerticalBlock"] > div:first-child {
                margin-top: 0px !important;
                padding-top: 0px !important;
            }
            div[data-testid="stMetric"] {
                background-color: #f8f9fa;
                padding: 10px 15px !important;
                border-radius: 8px !important;
                border: 1px solid #e9ecef !important;
            }
        </style>
    """, unsafe_allow_html=True)

    # Titulos corporativos limpos com Unicode puro
    titulo_limpo = "Painel de Controle - Produtividade por Respons\u00E1vel"
    st.title(f".. {titulo_limpo}")
    
    # Visão consolidada e status do fechamento
    subtitulo = f"Vis\u00E3o consolidada, status de fechamento e auditoria de pend\u00EAncias por operador em {meses_disponiveis[mes_chave]}/{ano_selecionado}."
    st.markdown(f"**{subtitulo}**")
    st.markdown("---")

    schemas_jose, schemas_pedro = get_listas_schemas_responsaveis()
    
    cursor = conn.cursor()
    
    # 1. Varredura e validacao dinamica de schemas do banco
    todos_schemas_banco = []
    try:
        query_filtros = """
            SELECT owner 
            FROM all_tables 
            WHERE table_name = 'FOLHA_FUNC' 
              AND owner LIKE 'SW_%'
              AND owner NOT IN ('SW_PUBLICO', 'SW_MODELO')
            ORDER BY owner
        """
        cursor.execute(query_filtros)
        todos_schemas_banco = [row[0] for row in cursor.fetchall()]
    except Exception as e:
        st.error(f"Erro ao aplicar a regra de schemas validos: {e}")
        todos_schemas_banco = list(set(schemas_jose + schemas_pedro))

    # 2. Mapeamento de tabelas existentes na memoria do servidor
    schemas_com_folha = set()
    schemas_com_estag = set()
    try:
        cursor.execute("SELECT owner FROM all_tables WHERE table_name = 'FOLHA' AND owner LIKE 'SW_%'")
        schemas_com_folha = set(row[0] for row in cursor.fetchall())
        
        cursor.execute("SELECT owner FROM all_tables WHERE table_name = 'ESTAG_FOLHA' AND owner LIKE 'SW_%'")
        schemas_com_estag = set(row[0] for row in cursor.fetchall())
    except Exception as e:
        msg_warn = "Erro ao pr\u00E9-carregar estrutura de tabelas:"
        st.warning(f"{msg_warn} {e}")

    # Divisao de escopo
    todos_schemas_mapeados = []
    for schema in todos_schemas_banco:
        if schema in schemas_jose:
            todos_schemas_mapeados.append(('JOSE GOMES', schema))
        elif schema in schemas_pedro:
            todos_schemas_mapeados.append(('PEDRO MENDES', schema))
        else:
            todos_schemas_mapeados.append(('DEMAIS', schema))

    if not todos_schemas_mapeados:
        todos_schemas_mapeados = [('JOSE GOMES', s) for s in schemas_jose] + [('PEDRO MENDES', s) for s in schemas_pedro]
    
    resultados = []

    with st.spinner("Sincronizando metadados de auditoria e conformidade..."):
        for resp, schema in todos_schemas_mapeados:
            orgao_nome = schema.replace('SW_', '')
            
            tem_tabela_folha = schema in schemas_com_folha
            tem_tabela_estag = schema in schemas_com_estag

            if not tem_tabela_folha and not tem_tabela_estag:
                continue

            qtd_total_periodo = 0
            qtd_func_total = 0
            qtd_func_abertas = 0
            qtd_estag_total = 0
            qtd_estag_abertas = 0
            chaves_lista = []

            # ---- LEITURA: FUNCIONARIOS ----
            if tem_tabela_folha:
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM {schema}.FOLHA WHERE ANO = {ano_selecionado} AND MES = {int(mes_chave)}")
                    qtd_func_total = cursor.fetchone()[0]
                    qtd_total_periodo += qtd_func_total

                    # Captura TODAS as folhas do mês (abertas e fechadas) com seu respectivo status
                    sql_func_chaves = f"""
                        SELECT f.CHAVE_FOLHA || ' (Func:' || CASE WHEN f.DATA_FECHAMENTO IS NULL THEN 'ABERTA' ELSE 'FECHADA' END || ')'
                        FROM {schema}.FOLHA f
                        WHERE f.ANO = {ano_selecionado} AND f.MES = {int(mes_chave)}
                        ORDER BY f.CHAVE_FOLHA
                    """
                    cursor.execute(sql_func_chaves)
                    func_rows = cursor.fetchall()
                    if func_rows:
                        chaves_lista.extend([r[0] for r in func_rows])
                        
                    # Contabiliza especificamente as abertas para controle de status
                    cursor.execute(f"SELECT COUNT(*) FROM {schema}.FOLHA WHERE ANO = {ano_selecionado} AND MES = {int(mes_chave)} AND DATA_FECHAMENTO IS NULL")
                    qtd_func_abertas = cursor.fetchone()[0]
                except oracledb.DatabaseError:
                    pass

            # ---- LEITURA: ESTAGIARIOS ----
            if tem_tabela_estag:
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM {schema}.ESTAG_FOLHA WHERE ANO = {ano_selecionado} AND MES = {int(mes_chave)}")
                    qtd_estag_total = cursor.fetchone()[0]
                    qtd_total_periodo += qtd_estag_total

                    # Captura TODOS os estágios do mês (abertas e fechadas) com seu respectivo status
                    sql_estag_chaves = f"""
                        SELECT ef.MASCARA || ' (Estag:' || CASE WHEN ef.DATA_FECHAMENTO IS NULL THEN 'ABERTA' ELSE 'FECHADA' END || ')'
                        FROM {schema}.ESTAG_FOLHA ef
                        WHERE ef.ANO = {ano_selecionado} AND ef.MES = {int(mes_chave)}
                        ORDER BY ef.MASCARA
                    """
                    cursor.execute(sql_estag_chaves)
                    estag_rows = cursor.fetchall()
                    if estag_rows:
                        chaves_lista.extend([r[0] for r in estag_rows])
                        
                    # Contabiliza especificamente as abertas para controle de status
                    cursor.execute(f"SELECT COUNT(*) FROM {schema}.ESTAG_FOLHA WHERE ANO = {ano_selecionado} AND MES = {int(mes_chave)} AND DATA_FECHAMENTO IS NULL")
                    qtd_estag_abertas = cursor.fetchone()[0]
                except oracledb.DatabaseError:
                    pass

            if qtd_total_periodo == 0:
                continue

            # O órgão estará aberto se houver pendência em funcionários ou estágios
            tot_abertas_orgao = qtd_func_abertas + qtd_estag_abertas
            status = 'ABERTA' if tot_abertas_orgao > 0 else 'FECHADA'
            chaves_str = ", ".join(chaves_lista) if chaves_lista else '---'

            resultados.append({
                'RESPONSAVEL': resp,
                'STATUS': status,
                'ORGAO': orgao_nome,
                'CHAVES': chaves_str,
                'FOLHAS_TOTAL': qtd_total_periodo,
                'FOLHAS_ABERTAS': tot_abertas_orgao,
                'FOLHAS_FECHADAS': (qtd_total_periodo - tot_abertas_orgao)
            })
            
    cursor.close()

    if not resultados:
        msg_info = "Nenhum \u00F3rg\u00E3o possui movimenta\u00E7\u00E3o de folhas registradas em"
        st.info(f"{msg_info} {meses_disponiveis[mes_chave]}/{ano_selecionado}.")
        return

    df_resultado = pd.DataFrame(resultados)

    def colorir_status(row):
        if row['STATUS'] == 'ABERTA':
            return ['background-color: #fff5f5; color: #c92a2a; font-weight: 500;'] * 3
        elif row['STATUS'] == 'FECHADA':
            return ['background-color: #f4fbf7; color: #2b8a3e; font-weight: normal;'] * 3
        return [''] * 3

    # Renderizacao estruturada por operador
    for responsavel in ['JOSE GOMES', 'PEDRO MENDES', 'DEMAIS']:
        df_filtrado_resp = df_resultado[df_resultado['RESPONSAVEL'] == responsavel]
        
        if df_filtrado_resp.empty:
            continue
            
        # 1. Métrica de Estrutura (Órgãos)
        total_orgaos = len(df_filtrado_resp)
        org_abertos = len(df_filtrado_resp[df_filtrado_resp['STATUS'] == 'ABERTA'])
        org_fechados = len(df_filtrado_resp[df_filtrado_resp['STATUS'] == 'FECHADA'])
        
        # 2. Métrica de Volumetria Real (Folhas Físicas Calculadas)
        total_folhas_fisicas = int(df_filtrado_resp['FOLHAS_TOTAL'].sum())
        folhas_fisicas_abertas = int(df_filtrado_resp['FOLHAS_ABERTAS'].sum())
        folhas_fisicas_fechadas = int(df_filtrado_resp['FOLHAS_FECHADAS'].sum())
        
        # O índice de fechamento real e preciso deve ser baseado na volumetria das folhas
        taxa_eficiencia = (folhas_fisicas_fechadas / total_folhas_fisicas * 100) if total_folhas_fisicas > 0 else 100.0

        # Divisor de cabeçalho do Operador
        st.markdown(f"""
            <div style="background-color: #343a40; padding: 6px 12px; margin-top: 15px; margin-bottom: 10px; border-radius: 4px;">
                <span style="color: #ffffff; font-weight: bold; font-size: 1.1rem; letter-spacing: 0.5px;">
                    .. RESPONS\u00C1VEL: {responsavel}
                </span>
            </div>
        """, unsafe_allow_html=True)
        
        # Renderização dos cartões em duas linhas para não esmagar a tela e dar um aspecto profissional
        st.markdown("<p style='margin-bottom: 2px; font-size: 0.85rem; color: #6c757d; font-weight: bold;'>[ESTRUTURA DE ÓRGÃOS]</p>", unsafe_allow_html=True)
        m1, m2, m3 = st.columns(3)
        with m1:
            st.metric(label="Total \u00D3rg\u00E3os", value=f"{total_orgaos}")
        with m2:
            st.metric(label="\u00D3rg\u00E3os Abertos", value=f"{org_abertos}")
        with m3:
            st.metric(label="\u00D3rg\u00E3os Fechados", value=f"{org_fechados}")
            
        st.markdown("<p style='margin-top: 5px; margin-bottom: 2px; font-size: 0.85rem; color: #004085; font-weight: bold;'>[VOLUMETRIA DE FOLHAS FÍSICAS]</p>", unsafe_allow_html=True)
        f1, f2, f3, f4 = st.columns(4)
        with f1:
            st.metric(label="Total Folhas", value=f"{total_folhas_fisicas}")
        with f2:
            st.metric(label="Folhas Abertas", value=f"{folhas_fisicas_abertas}")
        with f3:
            st.metric(label="Folhas Fechadas", value=f"{folhas_fisicas_fechadas}")
        with f4:
            st.metric(label="\u00CDndice de Fechamento", value=f"{taxa_eficiencia:.1f}%")

        # Preparação do DataFrame Visual para a tabela abaixo dos cartões
        df_visual = df_filtrado_resp[['ORGAO', 'STATUS', 'CHAVES']].copy()
        df_visual['ORDEM'] = df_visual['STATUS'].map({'ABERTA': 1, 'FECHADA': 2})
        df_visual = df_visual.sort_values('ORDEM').drop(columns=['ORDEM'])

        df_colorido = df_visual.style.apply(colorir_status, axis=1)
        
        st.dataframe(
            df_colorido, 
            use_container_width=True, 
            hide_index=True,
            column_config={
                "ORGAO": st.column_config.TextColumn("\u00D3RG\u00C3O / SCHEMA"),
                "STATUS": st.column_config.TextColumn("STATUS ATUAL"),
                "CHAVES": st.column_config.TextColumn("COMPOSI\u00C7\u00C3O E AUDITORIA DAS FOLHAS NO M\u00CAS")
            }
        )
        st.markdown("<div style='margin-bottom: 15px;'></div>", unsafe_allow_html=True)

