import streamlit as st
import pandas as pd

def renderizar_dados_bancarios(conn, ano, mes, auth_ui, novos_dados_bancario):
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

            existe_envio_real = any(not r.get("SOMENTE_VISUALIZAR", True) for r in registros)
            if existe_envio_real and not auth_ui.verificar_credenciais_sefaz():
                st.warning("⚠️ Credenciais da SEFAZ não validas. Por favor, autentique-se antes de continuar.")
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
            # Prepara cópia da exibição mapeando os campos visuais
            df_exibicao = st.session_state.df_bancario.copy()
            df_exibicao['CPF'] = df_exibicao['CPF'].astype(str).str.replace(r'\D', '', regex=True)
            df_exibicao['ENVIADO'] = df_exibicao['ENVIADO'].map({
                'SIM': '✅ SIM', 'ERRO': '❌ ERRO', 'NÃO': '⏳ NÃO'
            }).fillna('⏳ NÃO')

            if "SOMENTE_VISUALIZAR" in df_exibicao.columns:
                df_exibicao = df_exibicao.drop(columns=["SOMENTE_VISUALIZAR"])

            # Função de callback para atualizar o session_state instantaneamente a cada alteração na tabela,
            # impedindo que o Streamlit descarte as seleções múltiplas intermediárias.
            def atualizar_estado_tabela():
                editor_res = st.session_state.get("editor_dados_bancarios", {})
                # Captura edições de células modificadas
                if "edited_rows" in editor_res:
                    for idx_str, alteracoes in editor_res["edited_rows"].items():
                        idx = int(idx_str)
                        if "ENVIAR" in alteracoes:
                            st.session_state.df_bancario.loc[idx, "ENVIAR"] = alteracoes["ENVIAR"]

            df_editado = st.data_editor(
                df_exibicao,
                key="editor_dados_bancarios",
                on_change=atualizar_estado_tabela,
                column_config={
                    "ENVIAR": st.column_config.CheckboxColumn("Selecionar", default=False)
                },
                disabled=["ENVIADO", "ORGAO", "COD_INSTITUCIONAL", "NOME_ATUAL", "CPF", "CHAVE_FOLHA"],
                use_container_width=True,
                hide_index=True,
            )

            # Sincronização direta de segurança
            if "ENVIAR" in df_editado.columns:
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

