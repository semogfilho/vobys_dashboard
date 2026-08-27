import streamlit as st
import pandas as pd
import json, copy
import auth_ui
import dados_bancarios_view

st.cache_data.clear()

from auditoria import (
    tipo_folha_x_tipo_arquivo_sefaz,
    colaboradores_novatos,
    novos_dados_bancario,
    batimento_json
)

def render(conn, ano, mes, sub_opcao):

    # Opção 1: Consistência Folha
    if sub_opcao == "Consistência Folha":
        mes_exibicao = "13º" if int(mes) == 13 else f"{int(mes):02d}"

        # Layout com colunas para posicionar o checkbox próximo ao título
        col_tit, col_chk = st.columns([3, 1])
        with col_tit:
            st.subheader(f"📊 Consistência da Folha ({mes_exibicao}/{ano})")
        with col_chk:
            # Checkbox para alternar o modo de visão
            filtrar_inconsistencias = st.checkbox("🔍 Apenas Inconsistências", value=False)

        # Passa o estado do checkbox para a função
        df_consistencia = tipo_folha_x_tipo_arquivo_sefaz.executar_auditoria(conn, ano, mes, apenas_inconsistentes=filtrar_inconsistencias)

        if df_consistencia is not None and not df_consistencia.empty:
            for col in ['DATA_FECHAMENTO', 'DATA_CADASTRO']:
                if col in df_consistencia.columns:
                    df_consistencia[col] = pd.to_datetime(df_consistencia[col], errors='coerce')

            # Função para aplicar estilo de destaque em vermelho na coluna SITUACAO
            def colorir_situacao(val):
                if val in ['Estrutural SEFAZ duplicado', 'Codigo de Arquivo Fora da Sequencia (001)', 'Codigo de Arquivo Fora da sequencia (020)']:
                    return 'color: #ff4b4b; font-weight: bold;'
                return ''

            # Aplica o estilo se a coluna SITUACAO existir no DataFrame
            if 'SITUACAO' in df_consistencia.columns:
                df_exibicao = df_consistencia.style.applymap(colorir_situacao, subset=['SITUACAO'])
            else:
                df_exibicao = df_consistencia

            st.dataframe(
                df_exibicao,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "DATA_FECHAMENTO": st.column_config.DatetimeColumn(
                        "Data Fechamento", format="DD-MM-YYYY HH:mm:ss"
                    ),
                    "DATA_CADASTRO": st.column_config.DatetimeColumn(
                        "Data Cadastro", format="DD-MM-YYYY HH:mm:ss"
                    ),
                    "SITUACAO": st.column_config.TextColumn(
                        "Situação", help="Status da consistência estrutural do arquivo"
                    )
                }
            )

            # --- TOTAL DE REGISTROS LISTADOS ---
            total_linhas = len(df_consistencia)
            st.metric(label="📌 Total de Registros Listados", value=f"{total_linhas:,.0f}".replace(",", "."))

        else:
            st.warning("Nenhum registro encontrado para o filtro selecionado.")

    # Opção 2: Auditoria de Integridade (Batimento)
    elif sub_opcao == "Auditoria de Integridade":
        mes_exibicao = "13º" if int(mes) == 13 else f"{int(mes):02d}"
        st.subheader(f"🔄 Batimento: Folha vs. JSON SEFAZ ({mes_exibicao}/{ano})")

        query_ids = f"""
            SELECT sei.id_siafe_evento_integracao, sei.recibo, sei.codigo_sefaz,
                   upper('sw_'||e.sigla) as schema_nome, sei.chave_folha
            FROM sw_publico.SIAFE_EVENTO_INTEGRACAO sei
            LEFT JOIN sw_publico.empresa e ON e.id_empresa = sei.id_empresa
            WHERE sei.ano = {ano} AND sei.mes = {mes} AND sei.ind_tipo_requisicao = 'V1'
        """
        df_opcoes = pd.read_sql(query_ids, conn)
        df_opcoes.columns = [c.lower() for c in df_opcoes.columns]

        df_opcoes['display'] = (
            df_opcoes['schema_nome'] + " | ID: " + df_opcoes['id_siafe_evento_integracao'].astype(str) +
            " | Recibo: " + df_opcoes['recibo'].astype(str) + " | Sefaz: " + df_opcoes['codigo_sefaz'].astype(str) +
            " | Chave: " + df_opcoes['chave_folha'].astype(str)
        )

        pesquisa = st.text_input("Filtrar órgãos:", placeholder="Digite o nome do órgão...")
        df_filtrado = df_opcoes[df_opcoes['schema_nome'].str.contains(pesquisa, case=False, na=False)] if pesquisa else df_opcoes

        selecionados = st.multiselect(
            "Selecione os IDs para Batimento:",
            options=df_filtrado['id_siafe_evento_integracao'].tolist(),
            format_func=lambda x: df_opcoes[df_opcoes['id_siafe_evento_integracao'] == x]['display'].iloc[0]
        )

        if st.button("Executar Batimento Consolidado"):
            if not selecionados:
                st.warning("Selecione pelo menos um ID de integração.")
            else:
                progress_bar = st.progress(0)
                status_text = st.empty()
                total = len(selecionados)

                dif_folha_list, dif_json_list = [], []
                df_folha_total_list, df_json_total_list = [], []

                for i, id_sel in enumerate(selecionados):
                    status_text.text(f"Processando ID {id_sel} ({i+1}/{total})...")
                    d_folha, d_json, _, _, erro, d_folha_t, d_json_t = batimento_json.processar_batimento_consolidado(conn, [id_sel], ano, mes)

                    if not erro:
                        dif_folha_list.append(d_folha); dif_json_list.append(d_json)
                        df_folha_total_list.append(d_folha_t); df_json_total_list.append(d_json_t)
                    else:
                        st.error(f"Erro ao processar ID {id_sel}: {erro}")

                    progress_bar.progress((i + 1) / total)

                status_text.empty()
                progress_bar.empty()

                dif_folha = pd.concat(dif_folha_list, ignore_index=True) if dif_folha_list else pd.DataFrame()
                dif_json = pd.concat(dif_json_list, ignore_index=True) if dif_json_list else pd.DataFrame()
                df_folha_total = pd.concat(df_folha_total_list, ignore_index=True) if df_folha_total_list else pd.DataFrame()
                df_json_total = pd.concat(df_json_total_list, ignore_index=True) if df_json_total_list else pd.DataFrame()

                cpfs_faltantes_na_folha = df_json_total[~df_json_total['CPF_LIMPO'].isin(df_folha_total['CPF_LIMPO'])] if not df_folha_total.empty else pd.DataFrame()
                cpfs_faltantes_no_json = df_folha_total[~df_folha_total['CPF_LIMPO'].isin(df_json_total['CPF_LIMPO'])] if not df_json_total.empty else pd.DataFrame()

                resultados_finais = []
                if not cpfs_faltantes_no_json.empty:
                    with st.status("Buscando saldos na folha...", expanded=True) as status:
                        prog_saldos = st.progress(0)
                        grupos = list(cpfs_faltantes_no_json.groupby(['ORGAO', 'CHAVE_FOLHA']))

                        for i, ((orgao, chave), grupo) in enumerate(grupos):
                            prog_saldos.progress((i + 1) / len(grupos))
                            lista_busca = [m.replace('X', '') for m in grupo['COD_LIMPO'].astype(str).unique()]

                            df_saldos = batimento_json.buscar_saldos_folha(conn, orgao, lista_busca, chave, ano, mes)

                            if not df_saldos.empty:
                                df_saldos.columns = [c.lower() for c in df_saldos.columns]
                                grupo = grupo.merge(df_saldos[['cod_limpo', 'saldo_liquido']], left_on='COD_LIMPO', right_on='cod_limpo', how='left')
                                grupo['SALDO_LIQUIDO'] = pd.to_numeric(grupo['saldo_liquido'].fillna(0.00))
                            else:
                                grupo['SALDO_LIQUIDO'] = 0.00
                            resultados_finais.append(grupo)
                        status.update(label="Busca finalizada!", state="complete", expanded=False)

                df_exibir_aba4 = pd.concat(resultados_finais, ignore_index=True) if resultados_finais else pd.DataFrame()
                df_filtrado_aba4 = df_exibir_aba4[df_exibir_aba4['SALDO_LIQUIDO'] > 0] if not df_exibir_aba4.empty else pd.DataFrame()

                total_registros = len(df_folha_total) if not df_folha_total.empty else 1

                cols = st.columns(4)
                cols[0].metric("Divergências na Folha", len(dif_folha), f"{(len(dif_folha)/total_registros)*100:.2f}%")
                cols[1].metric("Divergências no JSON", len(dif_json), f"{(len(dif_json)/total_registros)*100:.2f}%")
                cols[2].metric("Faltam na Folha", len(cpfs_faltantes_na_folha), f"{(len(cpfs_faltantes_na_folha)/total_registros)*100:.2f}%")
                cols[3].metric("Faltam no JSON", len(df_filtrado_aba4), f"{(len(df_filtrado_aba4)/total_registros)*100:.2f}%")

                aba1, aba2, aba3, aba4 = st.tabs([
                    "❌ Divergências na Folha",
                    "❌ Divergências no JSON",
                    "⚠️ Faltam na Folha",
                    "⚠️ Faltam no JSON"
                ])

                with aba1:
                    if not dif_folha.empty:
                        st.dataframe(dif_folha.drop(columns=['MATRICULA_LIMPA', 'COD_LIMPO', 'CPF_LIMPO', 'chave'], errors='ignore'), use_container_width=True, hide_index=False)
                    else:
                        st.info("Nenhum registro divergente.")

                with aba2:
                    if not dif_json.empty:
                        st.dataframe(dif_json.drop(columns=['MATRICULA_LIMPA', 'CPF_LIMPO', 'chave', 'dataPagamento'], errors='ignore'), use_container_width=True, hide_index=False)
                    else:
                        st.info("Nenhum registro divergente.")

                with aba3:
                    if not cpfs_faltantes_na_folha.empty:
                        st.dataframe(cpfs_faltantes_na_folha.drop(columns=['MATRICULA_LIMPA', 'CPF_LIMPO', 'chave', 'dataPagamento'], errors='ignore'), use_container_width=True, hide_index=False)
                    else:
                        st.success("Nenhum CPF faltando na folha.")

                with aba4:
                    if not df_filtrado_aba4.empty:
                        st.dataframe(
                            df_filtrado_aba4[['NOME', 'CPF_PESSOA', 'COD_INSTITUCIONAL', 'ORGAO', 'CHAVE_FOLHA', 'SALDO_LIQUIDO']],
                            use_container_width=True,
                            hide_index=True,
                            column_config={"SALDO_LIQUIDO": st.column_config.NumberColumn("Saldo Líquido", format="R$ %.2f")}
                        )
                    else:
                        st.success("Tudo sincronizado!")

    elif sub_opcao == "Novos Colaboradores":
        st.subheader("👥 Novos Colaboradores")
        df = colaboradores_novatos.executar_auditoria_novatos(conn, ano, mes)
        st.dataframe(df)

# Opção 3: Dados Bancários
    elif sub_opcao == "Dados Bancários":
        dados_bancarios_view.renderizar_dados_bancarios(conn, ano, mes, auth_ui, novos_dados_bancario)
