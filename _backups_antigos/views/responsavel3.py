# -*- coding: utf-8 -*-
import streamlit as st
import oracledb
import pandas as pd
from queries import get_listas_schemas_responsaveis

def render(conn, ano_selecionado, mes_chave, meses_disponiveis):
    # Titulos e labels tratados com escape Unicode para evitar erros de encoding no terminal
    titulo_limpo = "Painel de Controle - Por Respons\u00E1vel"
    st.title(titulo_limpo)
    
    subtitulo = f"Monitoramento Unificado de Folhas (Func. e Estag.) em {meses_disponiveis[mes_chave]}/{ano_selecionado}."
    st.write(subtitulo)

    schemas_jose, schemas_pedro = get_listas_schemas_responsaveis()
    
    cursor = conn.cursor()
    
    # 1. Busca inicial de schemas validos
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

    # 2. Carrega na memoria a existencia das tabelas de controle por schema
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

    # Mapeia quem pertence a quem
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

    with st.spinner("Filtrando e varrendo folhas de Funcionarios e Estagiarios..."):
        for resp, schema in todos_schemas_mapeados:
            orgao_nome = schema.replace('SW_', '')
            
            tem_tabela_folha = schema in schemas_com_folha
            tem_tabela_estag = schema in schemas_com_estag

            if not tem_tabela_folha and not tem_tabela_estag:
                continue

            qtd_total_periodo = 0
            qtd_abertas = 0
            chaves_lista = []

            # ---- PARTE 1: FUNCIONARIOS ----
            if tem_tabela_folha:
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM {schema}.FOLHA WHERE ANO = {ano_selecionado} AND MES = {int(mes_chave)}")
                    qtd_total_periodo += cursor.fetchone()[0]

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
                        chaves_lista.extend([r[0] for r in func_rows])
                except oracledb.DatabaseError:
                    pass

            # ---- PARTE 2: ESTAGIARIOS ----
            if tem_tabela_estag:
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM {schema}.ESTAG_FOLHA WHERE ANO = {ano_selecionado} AND MES = {int(mes_chave)}")
                    qtd_total_periodo += cursor.fetchone()[0]

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
                        chaves_lista.extend([r[0] for r in estag_rows])
                except oracledb.DatabaseError:
                    pass

            if qtd_total_periodo == 0:
                continue

            if qtd_abertas > 0:
                status = 'ABERTA'
                chaves_str = ", ".join(chaves_lista)
            else:
                status = 'FECHADA'
                chaves_str = '---'

            resultados.append({
                'RESPONSAVEL': resp,
                'STATUS': status,
                'ORGAO': orgao_nome,
                'CHAVES': chaves_str
            })
            
    cursor.close()

    if not resultados:
        msg_info = "Nenhum \u00F3rg\u00E3o possui movimenta\u00E7\u00E3o de folhas registradas em"
        st.info(f"{msg_info} {meses_disponiveis[mes_chave]}/{ano_selecionado}.")
        return

    df_resultado = pd.DataFrame(resultados)

    def colorir_status(row):
        if row['STATUS'] == 'ABERTA':
            return ['background-color: #ffe6e6; color: #cc0000; font-weight: bold;'] * len(row)
        elif row['STATUS'] == 'FECHADA':
            return ['background-color: #e6f9ed; color: #1e7e34; font-weight: bold;'] * len(row)
        return [''] * len(row)

    for responsavel in ['JOSE GOMES', 'PEDRO MENDES', 'DEMAIS']:
        df_filtrado = df_resultado[df_resultado['RESPONSAVEL'] == responsavel][['ORGAO', 'STATUS', 'CHAVES']]
        
        if df_filtrado.empty:
            continue
            
        # Calcula resumo de Abertas e Fechadas para colocar proximo ao nome
        num_abertas = len(df_filtrado[df_filtrado['STATUS'] == 'ABERTA'])
        num_fechadas = len(df_filtrado[df_filtrado['STATUS'] == 'FECHADA'])
        
        # Monta a string do subheader com os contadores resumidos
        label_resumo = f"({num_abertas} Abertas / {num_fechadas} Fechadas)"
        st.subheader(f"Respons\u00E1vel: {responsavel} {label_resumo}")
        
        df_filtrado['ORDEM'] = df_filtrado['STATUS'].map({'ABERTA': 1, 'FECHADA': 2})
        df_filtrado = df_filtrado.sort_values('ORDEM').drop(columns=['ORDEM'])

        df_colorido = df_filtrado.style.apply(colorir_status, axis=1)
        
        st.dataframe(
            df_colorido, 
            use_container_width=True, 
            hide_index=True,
            column_config={
                "ORGAO": st.column_config.TextColumn("\u00D3RG\u00C3O"),
                "STATUS": st.column_config.TextColumn("STATUS"),
                "CHAVES": st.column_config.TextColumn("FOLHAS ABERTAS")
            }
        )
        st.markdown("<br>", unsafe_allow_html=True)
