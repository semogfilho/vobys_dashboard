import streamlit as st
import pandas as pd
import json, copy
import auth_ui

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

        st.subheader(f"📊 Consistência da Folha ({mes_exibicao}/{ano})")
        df_consistencia = tipo_folha_x_tipo_arquivo_sefaz.executar_auditoria(conn, ano, mes)

        if df_consistencia is not None and not df_consistencia.empty:
            for col in ['DATA_FECHAMENTO', 'DATA_CADASTRO']:
                if col in df_consistencia.columns:
                    df_consistencia[col] = pd.to_datetime(df_consistencia[col], errors='coerce')

            st.dataframe(
                df_consistencia,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "DATA_FECHAMENTO": st.column_config.DatetimeColumn(
                        "Data Fechamento", format="DD-MM-YYYY HH:mm:ss"
                    ),
                    "DATA_CADASTRO": st.column_config.DatetimeColumn(
                        "Data Cadastro", format="DD-MM-YYYY HH:mm:ss"
                    )
                }
            )
        else:
            st.warning("Nenhum registro de inconsistência encontrado para o período selecionado.")

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
        mes_exibicao = "13º" if int(mes) == 13 else f"{int(mes):02d}"
        st.subheader(f"🏦 Dados Bancários (Controle SEFAZ) ({mes_exibicao}/{ano})")

        @st.cache_data(ttl=600, show_spinner=False)
        def carregar_dados_bancarios(ano, mes):
            return novos_dados_bancario.listar_novatos_bancario_com_status(conn, ano, mes)

        if 'df_bancario' not in st.session_state or st.session_state.get('last_params') != (ano, mes):
            with st.spinner("Buscando dados no banco..."):
                df_temp = carregar_dados_bancarios(ano, mes)
                st.session_state.df_bancario = df_temp
                st.session_state.last_params = (ano, mes)

        if not st.session_state.df_bancario.empty:
            if "ENVIAR" not in st.session_state.df_bancario.columns:
                st.session_state.df_bancario["ENVIAR"] = False

            st.session_state.df_bancario = st.session_state.df_bancario.sort_values(by=["ORGAO", "CPF"])

            # -------------------------------------------------------------
            # TELA 1: PROCESSAMENTO EM LOTE (Isolada)
            # -------------------------------------------------------------
            if 'processamento_pendente' in st.session_state and st.session_state.processamento_pendente:
                registros = st.session_state.processamento_pendente

                # Validação prévia de credenciais fora do laço para evitar DuplicateWidgetID
                existe_envio_real = any(not r.get("SOMENTE_VISUALIZAR", True) for r in registros)
                if existe_envio_real and not auth_ui.verificar_credenciais_sefaz():
                    st.warning("⚠️ Credenciais da SEFAZ não validadas. Por favor, autentique-se antes de continuar.")
                    st.stop()

                for idx, registro in enumerate(registros):
                    cpf_reg = ''.join(filter(str.isdigit, str(registro['CPF'])))
                    schema_dinamico = f"SW_{registro.get('ORGAO')}"

                    dados_busca = novos_dados_bancario.buscar_dados_completos(conn, schema_dinamico, registro['COD_INSTITUCIONAL'])

                    if dados_busca is None or (isinstance(dados_busca, pd.DataFrame) and dados_busca.empty):
                        st.warning(f"⚠️ Dados cadastrais não encontrados no schema {schema_dinamico} para o código {registro['COD_INSTITUCIONAL']}.")
                        continue

                    payload = novos_dados_bancario.montar_json_sefaz(dados_busca)

                    st.subheader(f"JSON: {registro.get('NOME_ATUAL')}")
                    st.json(payload)

                    mask = (st.session_state.df_bancario['CPF'].astype(str).str.replace(r'\D', '', regex=True) == cpf_reg) & \
                           (st.session_state.df_bancario['COD_INSTITUCIONAL'] == registro['COD_INSTITUCIONAL'])

                    if registro.get("SOMENTE_VISUALIZAR", True):
                        st.info(f"Modo Visualização: {registro.get('NOME_ATUAL')} (Não enviado à SEFAZ)")
                    else:
                        try:
                            sucesso, json_str, retorno = novos_dados_bancario.enviar_para_sefaz(payload)

                            try:
                                novos_dados_bancario.registrar_envio(conn, [registro], json_str, retorno)
                            except Exception as e_log:
                                st.warning(f"Envio efetuado, mas falhou ao gravar histórico: {e_log}")

                            if sucesso:
                                st.session_state.df_bancario.loc[mask, 'ENVIADO'] = 'SIM'
                                st.success(f"Gravado com sucesso: {registro.get('NOME_ATUAL')}")
                            else:
                                st.session_state.df_bancario.loc[mask, 'ENVIADO'] = 'ERRO'
                                st.error(f"Erro ao processar SEFAZ para {registro.get('NOME_ATUAL')}: {retorno}")
                        except Exception as e_envio:
                            st.session_state.df_bancario.loc[mask, 'ENVIADO'] = 'ERRO'
                            st.error(f"Falha na comunicação: {e_envio}")

                    st.session_state.df_bancario.loc[mask, 'ENVIAR'] = False
                    st.divider()

                del st.session_state.processamento_pendente

                if st.button("⬅️ Voltar ao Painel Principal", key="btn_voltar_painel_lote_absoluto"):
                    st.rerun()

            # -------------------------------------------------------------
            # TELA 2: PAINEL PRINCIPAL / AUDITORIA
            # -------------------------------------------------------------
            else:
                df_exibicao = st.session_state.df_bancario.copy()
                df_exibicao['CPF'] = df_exibicao['CPF'].astype(str).str.replace(r'\D', '', regex=True)
                df_exibicao['ENVIADO'] = df_exibicao['ENVIADO'].map({
                    'SIM': '✅ SIM', 'ERRO': '❌ ERRO', 'NÃO': '⏳ NÃO'
                }).fillna('⏳ NÃO')

                # Tira a coluna SOMENTE_VISUALIZAR da grade se existir
                if "SOMENTE_VISUALIZAR" in df_exibicao.columns:
                    df_exibicao = df_exibicao.drop(columns=["SOMENTE_VISUALIZAR"])

                df_editado = st.data_editor(
                    df_exibicao,
                    key="editor_dados_bancarios",
                    column_config={
                        "ENVIAR": st.column_config.CheckboxColumn("Selecionar", default=False)
                    },
                    disabled=["ENVIADO", "ORGAO", "COD_INSTITUCIONAL", "NOME_ATUAL", "CPF", "CHAVE_FOLHA"],
                    use_container_width=True,
                    hide_index=True,
                )

                st.session_state.df_bancario["ENVIAR"] = df_editado["ENVIAR"]

                # Layout de 3 colunas com o checkbox de Visualizar no meio
                col_btn1, col_chk, col_btn2 = st.columns([1.2, 1, 1.2])
                with col_btn1:
                    submit_button = st.button("Confirmar Envio Selecionados", key="btn_confirmar_envio")
                with col_chk:
                    chk_visualizar = st.checkbox("Somente Visualizar?", value=True, key="chk_somente_visualizar_geral")
                with col_btn2:
                    finalizar_button = st.button("Finalizar e Atualizar Tela", key="btn_finalizar_atualizar")

                if submit_button:
                    selecionados = st.session_state.df_bancario[st.session_state.df_bancario["ENVIAR"] == True].copy()
                    if selecionados.empty:
                        st.warning("Nenhum registro selecionado!")
                    else:
                        # Atribui a opção do Checkbox Geral a todos os registros do lote
                        selecionados["SOMENTE_VISUALIZAR"] = chk_visualizar

                        if not chk_visualizar:
                            if not auth_ui.verificar_credenciais_sefaz():
                                st.stop()

                        st.session_state.processamento_pendente = selecionados.to_dict('records')
                        st.rerun()

                if finalizar_button:
                    st.rerun()

                st.divider()

                col1, col2 = st.columns([1, 1])
                with col1:
                    cpf_busca = st.text_input("Consultar CPF avulso:", placeholder="Digite o CPF...", key="input_cpf_avulso")
                with col2:
                    btn_buscar = st.button("Buscar CPF na Competência", key="btn_buscar_cpf")

                if btn_buscar and cpf_busca:
                    st.session_state['cpf_buscado_ativo'] = ''.join(filter(str.isdigit, cpf_busca))

                if st.session_state.get('cpf_buscado_ativo'):
                    cpf_limpo = st.session_state['cpf_buscado_ativo']

                    if not cpf_limpo:
                        st.warning("Por favor, informe um CPF válido contendo números.")
                        del st.session_state['cpf_buscado_ativo']
                    else:
                        mask_cpf = st.session_state.df_bancario['CPF'].astype(str).str.replace(r'\D', '', regex=True) == cpf_limpo

                        with st.spinner('Consultando CPF...'):
                            if st.session_state.df_bancario[mask_cpf].any().any():
                                st.info(f"O CPF {cpf_limpo} foi localizado na lista.")
                                st.session_state.df_bancario.loc[mask_cpf, 'ENVIAR'] = True
                                
                                df_loc_exib = st.session_state.df_bancario[mask_cpf].copy()
                                if "SOMENTE_VISUALIZAR" in df_loc_exib.columns:
                                    df_loc_exib = df_loc_exib.drop(columns=["SOMENTE_VISUALIZAR"])

                                st.data_editor(
                                    df_loc_exib,
                                    column_config={
                                        "ENVIAR": st.column_config.CheckboxColumn("Selecionar", default=False)
                                    },
                                    hide_index=True,
                                    use_container_width=True,
                                    key=f"editor_cpf_localizado_{cpf_limpo}"
                                )
                            else:
                                df_encontrado = novos_dados_bancario.buscar_por_cpf(conn, cpf_limpo, ano, mes)
                                if df_encontrado is not None and not df_encontrado.empty:
                                    df_encontrado['ENVIAR'] = True
                                    st.session_state.df_bancario = pd.concat([st.session_state.df_bancario, df_encontrado]).drop_duplicates(subset=['CPF', 'COD_INSTITUCIONAL'])
                                    st.success(f"{len(df_encontrado)} registro(s) localizado(s) e adicionado(s)!")

                                    df_busc_exib = df_encontrado.copy()
                                    if "SOMENTE_VISUALIZAR" in df_busc_exib.columns:
                                        df_busc_exib = df_busc_exib.drop(columns=["SOMENTE_VISUALIZAR"])

                                    st.data_editor(
                                        df_busc_exib,
                                        column_config={
                                            "ENVIAR": st.column_config.CheckboxColumn("Selecionar", default=False)
                                        },
                                        use_container_width=True,
                                        hide_index=True,
                                        num_rows="fixed",
                                        key=f"editor_cpf_buscado_{cpf_limpo}"
                                    )
                                else:
                                    st.error("CPF não encontrado na folha desta competência.")

                        if st.button("⬅️ Voltar para lista completa", key=f"btn_voltar_lista_{cpf_limpo}"):
                            del st.session_state['cpf_buscado_ativo']
                            st.rerun()

                st.divider()
                st.subheader("🔍 Auditoria de Erros")
                df_erros = st.session_state.df_bancario[st.session_state.df_bancario['ENVIADO'] == 'ERRO']
                if not df_erros.empty:
                    cpf_err = st.selectbox("Selecione o CPF do erro:", df_erros['CPF'].unique(), key="sb_cpf_erro")
                    if st.button("Carregar Log do Servidor", key=f"btn_log_erro_{cpf_err}"):
                        st.error(f"Log: {novos_dados_bancario.buscar_detalhe_erro_no_banco(conn, cpf_err)}")
                else:
                    st.info("Nenhum erro para exibir.")
