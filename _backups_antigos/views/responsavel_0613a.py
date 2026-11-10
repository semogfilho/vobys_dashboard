# -*- coding: utf-8 -*-
import streamlit as st
import oracledb
import pandas as pd
from queries import get_listas_schemas_responsaveis

def render(conn, ano_selecionado, mes_chave, meses_disponiveis):
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
            /* Customização dos Cards de Métrica nativos */
            div[data-testid="stMetric"] {
                background-color: #f8f9fa;
                padding: 12px 15px !important;
                border-radius: 6px !important;
                border: 1px solid #e9ecef !important;
            }
            /* Subtítulos estilizados dos blocos de métricas internos */
            .sub-bloco-titulo {
                font-size: 0.85rem !important;
                font-weight: bold !important;
                letter-spacing: 0.5px;
                margin-bottom: 6px !important;
                margin-top: 4px !important;
            }
            /* Garante uma boa visualização do texto do expander */
            .stExpander details summary p {
                font-size: 0.95rem !important;
                font-family: sans-serif !important;
            }
        </style>
    """, unsafe_allow_html=True)

    # Títulos corporativos limpos com Unicode puro
    titulo_limpo = "Painel de Controle - Produtividade por Respons\u00E1vel"
    st.title(f".. {titulo_limpo}")
    
    subtitulo = f"Vis\u00E3o consolidada, status de fechamento e auditoria de pend\u00EAncias por operador em {meses_disponiveis[mes_chave]}/{ano_selecionado}."
    st.markdown(f"**{subtitulo}**")
    st.markdown("---")

    # Coleta padronizada dos dados de origem externa (Retorno Quíntuplo Atualizado)
    schemas_jose, schemas_pedro, schemas_armando, schemas_deividy, schemas_sarah = get_listas_schemas_responsaveis()
    
    cursor = conn.cursor()
    
    # 1. Varredura e validação dinâmica de schemas do banco
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
        todos_schemas_banco = list(set(schemas_jose + schemas_pedro + schemas_armando + schemas_deividy + schemas_sarah))

    # 2. Mapeamento de tabelas existentes na memória do servidor
    schemas_com_folha = set()
    schemas_com_estag = set()
    try:
        cursor.execute("SELECT owner FROM all_tables WHERE table_name = 'FOLHA' AND owner LIKE 'SW_%'")
        schemas_com_folha = set(row[0] for row in cursor.fetchall())
        
        cursor.execute("SELECT owner FROM all_tables WHERE table_name = 'ESTAG_FOLHA' AND owner LIKE 'SW_%'")
        schemas_com_estag = set(row[0] for row in cursor.fetchall())
    except Exception as e:
        pass

    # Divisão de escopo por operador (incluindo ARMANDO, DEIVIDY e SARAH)
    todos_schemas_mapeados = []
    for schema in todos_schemas_banco:
        if schema in schemas_jose:
            todos_schemas_mapeados.append(('JOSE GOMES', schema))
        elif schema in schemas_pedro:
            todos_schemas_mapeados.append(('PEDRO MENDES', schema))
        elif schema in schemas_armando:
            todos_schemas_mapeados.append(('ARMANDO', schema))
        elif schema in schemas_deividy:
            todos_schemas_mapeados.append(('DEIVIDY', schema))
        elif schema in schemas_sarah:
            todos_schemas_mapeados.append(('SARAH', schema))
        else:
            todos_schemas_mapeados.append(('DEMAIS', schema))

    if not todos_schemas_mapeados:
        todos_schemas_mapeados = (
            [('JOSE GOMES', s) for s in schemas_jose] + 
            [('PEDRO MENDES', s) for s in schemas_pedro] +
            [('ARMANDO', s) for s in schemas_armando] +
            [('DEIVIDY', s) for s in schemas_deividy] +
            [('SARAH', s) for s in schemas_sarah]
        )
    
    resultados = []

    with st.spinner("Sincronizando metadados de auditoria e conformidade..."):
        for resp, schema in todos_schemas_mapeados:
            orgao_nome = schema.replace('SW_', '')
            
            tem_tabela_folha = schema in schemas_com_folha
            tem_tabela_estag = schema in schemas_com_estag

            if not tem_tabela_folha and not tem_tabela_estag:
                continue

            qtd_total_periodo = 0
            qtd_abertas = 0
            chaves_lista = []

            qtd_folhas_totais = 0
            qtd_folhas_abertas_fisicas = 0

            # ---- LEITURA: FUNCIONÁRIOS ----
            if tem_tabela_folha:
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM {schema}.FOLHA WHERE ANO = {ano_selecionado} AND MES = {int(mes_chave)}")
                    f_tot = cursor.fetchone()[0]
                    qtd_total_periodo += f_tot
                    qtd_folhas_totais += f_tot

                    sql_func_abertas = f"""
                        SELECT f.CHAVE_FOLHA || ' (' || t.DESCRICAO_TIPO || ')'
                        FROM {schema}.FOLHA f
                        JOIN SW_PUBLICO.FOLHA_TAB_TIPO t ON f.ID_TIPO_FOLHA = t.ID_TIPO_FOLHA
                        WHERE f.ANO = {ano_selecionado} AND f.MES = {int(mes_chave)} AND f.DATA_FECHAMENTO IS NULL
                        ORDER BY f.CHAVE_FOLHA
                    """
                    cursor.execute(sql_func_abertas)
                    func_rows = cursor.fetchall()
                    if func_rows:
                        qtd_abertas += len(func_rows)
                        qtd_folhas_abertas_fisicas += len(func_rows)
                        chaves_lista.extend([r[0] for r in func_rows])
                except oracledb.DatabaseError:
                    pass

            # ---- LEITURA: ESTAGIÁRIOS ----
            if tem_tabela_estag:
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM {schema}.ESTAG_FOLHA WHERE ANO = {ano_selecionado} AND MES = {int(mes_chave)}")
                    e_tot = cursor.fetchone()[0]
                    qtd_total_periodo += e_tot
                    qtd_folhas_totais += e_tot

                    sql_estag_abertas = f"""
                        SELECT ef.MASCARA || ' (' || t.DESCRICAO_TIPO || ')'
                        FROM {schema}.ESTAG_FOLHA ef
                        JOIN SW_PUBLICO.FOLHA_TAB_TIPO t ON ef.ID_TIPO_FOLHA = t.ID_TIPO_FOLHA
                        WHERE ef.ANO = {ano_selecionado} AND ef.MES = {int(mes_chave)} AND ef.DATA_FECHAMENTO IS NULL
                        ORDER BY ef.MASCARA
                    """
                    cursor.execute(sql_estag_abertas)
                    estag_rows = cursor.fetchall()
                    if estag_rows:
                        qtd_abertas += len(estag_rows)
                        qtd_folhas_abertas_fisicas += len(estag_rows)
                        chaves_lista.extend([r[0] for r in estag_rows])
                except oracledb.DatabaseError:
                    pass

            if qtd_total_periodo == 0:
                continue

            status = 'ABERTA' if qtd_abertas > 0 else 'FECHADA'
            chaves_str = ", ".join(chaves_lista) if qtd_abertas > 0 else '---'

            resultados.append({
                'RESPONSAVEL': resp,
                'STATUS': status,
                'ORGAO': orgao_nome,
                'CHAVES': chaves_str,
                'FOLHAS_F_TOTAL': qtd_folhas_totais,
                'FOLHAS_F_ABERTAS': qtd_folhas_abertas_fisicas
            })
            
    cursor.close()

    if not resultados:
        st.info(f"Nenhum \u00F3rg\u00E3o possui movimenta\u00E7\u00E3o de folhas registradas em {meses_disponiveis[mes_chave]}/{ano_selecionado}.")
        return

    df_resultado = pd.DataFrame(resultados)

    def colorir_status(row):
        if row['STATUS'] == 'ABERTA':
            return ['background-color: #fff5f5; color: #c92a2a; font-weight: 500;'] * len(row)
        return ['background-color: #f4fbf7; color: #2b8a3e; font-weight: normal;'] * len(row)

    # Renderização estruturada por operador com os novos analistas incluídos na esteira
    for responsavel in ['JOSE GOMES', 'PEDRO MENDES', 'ARMANDO', 'DEIVIDY', 'SARAH', 'DEMAIS']:
        df_original_resp = df_resultado[df_resultado['RESPONSAVEL'] == responsavel]
        
        if df_original_resp.empty:
            continue
            
        total_orgaos = len(df_original_resp)
        num_abertas = len(df_original_resp[df_original_resp['STATUS'] == 'ABERTA'])
        num_fechadas = len(df_original_resp[df_original_resp['STATUS'] == 'FECHADA'])
        taxa_eficiencia = (num_fechadas / total_orgaos * 100) if total_orgaos > 0 else 100.0

        tot_folhas_fisicas = int(df_original_resp['FOLHAS_F_TOTAL'].sum())
        abertas_folhas_fisicas = int(df_original_resp['FOLHAS_F_ABERTAS'].sum())
        fechadas_folhas_fisicas = tot_folhas_fisicas - abertas_folhas_fisicas

        # --- FORMATAÇÃO REATIVA UTILIZANDO SINTAXE MARKDOWN NATIVA ---
        if taxa_eficiencia == 100.0:
            status_abertos = f":green[(Abertos: {num_abertas})]"
            status_folhas = f":green[(Abertas: {abertas_folhas_fisicas})]"
            texto_indice = f":green[**🎯 ÍNDICE: {taxa_eficiencia:.1f}%**]"
        else:
            status_abertos = f":red[(**Abertos: {num_abertas}**)]"
            status_folhas = f":red[(**Abertas: {abertas_folhas_fisicas}**)]"
            texto_indice = f":red[**🎯 ÍNDICE: {taxa_eficiencia:.1f}%**]"

        titulo_expander_consolidado = (
            f"👤 **RESPONSÁVEL:** {responsavel}  |  "
            f"🏛️ **Órgãos:** {total_orgaos} {status_abertos}  |  "
            f"📄 **[VOLUMETRIA FOLHAS]:** {tot_folhas_fisicas} {status_folhas}  |  "
            f"{texto_indice}"
        )

        with st.expander(titulo_expander_consolidado, expanded=(responsavel == 'JOSE GOMES')):
            
            # --- APRESENTAÇÃO EM DOIS BLOCOS ENVELOPADOS ---
            c_esq, c_dir = st.columns(2)
            
            with c_esq:
                st.markdown('<p class="sub-bloco-titulo" style="color: #1f2937;">[BALANÇO DE ESTRUTURAS - ÓRGÃOS]</p>', unsafe_allow_html=True)
                with st.container(border=True):
                    g1, g2, g3 = st.columns(3)
                    g1.metric(label="Total \u00D3rg\u00E3os", value=f"{total_orgaos}")
                    g2.metric(
                        label="Total Abertos", 
                        value=f"{num_abertas}", 
                        delta=f"{num_abertas} pend." if num_abertas > 0 else "0 pend.", 
                        delta_color="inverse" if num_abertas > 0 else "normal"
                    )
                    g3.metric(label="Total Fechados", value=f"{num_fechadas}")
                    
            with c_dir:
                st.markdown('<p class="sub-bloco-titulo" style="color: #1e40af;">[BALANÇO DE PRODUTIVIDADE - FOLHAS FÍSICAS]</p>', unsafe_allow_html=True)
                with st.container(border=True):
                    gf1, gf2, gf3 = st.columns(3)
                    gf1.metric(label="Volumetria Total", value=f"{tot_folhas_fisicas}")
                    gf2.metric(
                        label="Folhas Abertas", 
                        value=f"{abertas_folhas_fisicas}", 
                        delta=f"{abertas_folhas_fisicas} travadas" if abertas_folhas_fisicas > 0 else "0 travadas", 
                        delta_color="inverse" if abertas_folhas_fisicas > 0 else "normal"
                    )
                    gf3.metric(label="Folhas Fechadas", value=f"{fechadas_folhas_fisicas}")

            st.markdown("<div style='margin-bottom: 12px;'></div>", unsafe_allow_html=True)

            # Tabela analítica interna
            df_filtrado = df_original_resp[['ORGAO', 'STATUS', 'CHAVES']].copy()
            df_filtrado['ORDEM'] = df_filtrado['STATUS'].map({'ABERTA': 1, 'FECHADA': 2})
            df_filtrado = df_filtrado.sort_values('ORDEM').drop(columns=['ORDEM'])

            df_colorido = df_filtrado.style.apply(colorir_status, axis=1)
            st.dataframe(
                df_colorido, 
                width='stretch', 
                hide_index=True,
                column_config={
                    "ORGAO": st.column_config.TextColumn("\u00D3RG\u00C3O / SCHEMA"),
                    "STATUS": st.column_config.TextColumn("STATUS ATUAL"),
                    "CHAVES": st.column_config.TextColumn("COMPOSI\u00C7\u00C3O DAS FOLHAS ABERTAS")
                }
            )

    # =========================================================================
    # --- RESUMO CONSOLIDADO GERAL (FINAL DA PÁGINA) ---
    # =========================================================================
    st.markdown("---")
    st.markdown("""
        <div style="background-color: #1e3a8a; padding: 8px 15px; margin-top: 10px; margin-bottom: 15px; border-radius: 6px; border-left: 5px solid #3b82f6;">
            <span style="color: #ffffff; font-weight: bold; font-size: 1.15rem; letter-spacing: 0.5px;">
                📊 CONSOLIDADO GERAL DO PERÍODO (MÊS ATUAL)
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
            g1.metric(label="Total \u00D3rg\u00E3os", value=f"{geral_total_orgaos}")
            g2.metric(label="Total Abertos", value=f"{geral_org_abertos}", delta=f"{geral_org_abertos} pend.", delta_color="inverse")
            g3.metric(label="Total Fechados", value=f"{geral_org_fechados}")
            
    with c_dir_g:
        st.markdown("<p style='margin-bottom: 4px; font-size: 0.9rem; color: #1e40af; font-weight: bold;'>[BALANÇO DE PRODUTIVIDADE - FOLHAS FÍSICAS]</p>", unsafe_allow_html=True)
        with st.container(border=True):
            gf1, gf2, gf3 = st.columns(3)
            gf1.metric(label="Volumetria Total", value=f"{geral_folhas_totais}")
            gf2.metric(label="Folhas Abertas", value=f"{geral_folhas_abertas}", delta=f"{geral_folhas_abertas} travadas", delta_color="inverse")
            gf3.metric(label="Folhas Fechadas", value=f"{geral_folhas_fechadas}")

    st.markdown("<div style='margin-bottom: 8px;'></div>", unsafe_allow_html=True)
    if geral_folhas_abertas == 0:
        st.success(f"🎉 **Meta Atingida!** 100% das {geral_folhas_totais} folhas físicas distribuídas nos {geral_total_orgaos} órgãos foram liquidadas e encerradas com sucesso no banco!")
    else:
        st.info(f"📈 **Indicador de Performance:** O sistema já concluiu **{geral_taxa_folhas:.1f}%** de toda a volumetria física de folhas do mês. Restam apenas {geral_folhas_abertas} folhas para o fechamento total da folha do Estado.")



