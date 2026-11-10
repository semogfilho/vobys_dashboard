import streamlit as st
import pandas as pd
import json
import auth_ui
# Mantemos as importações originais que você já usa para as outras opções
st.cache_data.clear()

from auditoria import (
    tipo_folha_x_tipo_arquivo_sefaz,
    colaboradores_novatos,
    novos_dados_bancario,
    batimento_json
)

def render(conn, ano, mes):
    # Configuração do menu lateral
    #st.sidebar.subheader("Sub-menu de Auditoria")
    sub_opcao = st.sidebar.radio(
        "Selecione:",
        [
            "Consistência Folha", 
            "Dados Bancários (Controle SEFAZ)", 
            "Auditoria de Integridade (Batimento)"  # <--- Adicione esta linha
        ],
        key="sub_menu_auditoria_key"
    )


    # Opção 1: Consistência Folha
    if sub_opcao == "Consistência Folha":
        st.subheader("📊 Consistência da Folha")
        df_consistencia = tipo_folha_x_tipo_arquivo_sefaz.executar_auditoria(conn, ano, mes)

        if df_consistencia is not None and not df_consistencia.empty:
            st.dataframe(df_consistencia)
        else:
            st.warning("Nenhum registro de inconsistência encontrado para o período selecionado.")

    elif sub_opcao == "Auditoria de Integridade (Batimento)":
        st.subheader("🔍 Batimento: Folha vs. JSON SEFAZ")
        
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
            df_opcoes['schema_nome'] +
            " | ID: " + df_opcoes['id_siafe_evento_integracao'].astype(str) +
            " | Recibo: " + df_opcoes['recibo'].astype(str) +
            " | Sefaz: " + df_opcoes['codigo_sefaz'].astype(str) +
            " | Chave: " + df_opcoes['chave_folha'].astype(str)
        )

        pesquisa = st.text_input("Filtrar órgãos (ex: SW_SAF):", placeholder="Digite o nome do órgão para filtrar...")

        if pesquisa:
            df_filtrado = df_opcoes[df_opcoes['schema_nome'].str.contains(pesquisa, case=False, na=False)]
        else:
            df_filtrado = df_opcoes

        selecionados = st.multiselect(
            "Selecione os IDs para Batimento:",
            options=df_filtrado['id_siafe_evento_integracao'].tolist(),
            format_func=lambda x: df_opcoes[df_opcoes['id_siafe_evento_integracao'] == x]['display'].iloc[0]
        )

        if st.button("Executar Batimento Consolidado"):
            if not selecionados:
                st.warning("Selecione pelo menos um ID de integração.")
            else:
                from auditoria import batimento_json
                
                # Inicialização da barra de progresso
                progress_bar = st.progress(0)
                status_text = st.empty()
                total = len(selecionados)
                
                dif_folha_list, dif_json_list = [], []
                df_folha_total_list, df_json_total_list = [], []

                for i, id_sel in enumerate(selecionados):
                    # Atualiza a barra de progresso
                    progresso = (i + 1) / total
                    progress_bar.progress(progresso)
                    status_text.text(f"Processando ID {id_sel} ({i+1}/{total})...")
                    
                    # Processa individualmente para alimentar a barra
                    d_folha, d_json, _, _, erro, d_folha_t, d_json_t = batimento_json.processar_batimento_consolidado(conn, [id_sel])
                    
                    if not erro:
                        dif_folha_list.append(d_folha)
                        dif_json_list.append(d_json)
                        df_folha_total_list.append(d_folha_t)
                        df_json_total_list.append(d_json_t)

                # Limpa a barra após conclusão
                progress_bar.empty()
                status_text.empty()
                
                # Consolidação final
                dif_folha = pd.concat(dif_folha_list, ignore_index=True) if dif_folha_list else pd.DataFrame()
                dif_json = pd.concat(dif_json_list, ignore_index=True) if dif_json_list else pd.DataFrame()
                df_folha_total = pd.concat(df_folha_total_list, ignore_index=True) if df_folha_total_list else pd.DataFrame()
                df_json_total = pd.concat(df_json_total_list, ignore_index=True) if df_json_total_list else pd.DataFrame()

                col1, col2 = st.columns(2)
                col1.metric("Divergências na Folha", f"{len(dif_folha)}")
                col2.metric("Divergências no JSON", f"{len(dif_json)}")

                cpfs_faltantes_na_folha = df_json_total[~df_json_total['CPF_LIMPO'].isin(df_folha_total['CPF_LIMPO'])]
                cpfs_faltantes_no_json = df_folha_total[~df_folha_total['CPF_LIMPO'].isin(df_json_total['CPF_LIMPO'])]
                
                st.write("---")

                if len(dif_folha) == 0 and len(dif_json) == 0 and len(cpfs_faltantes_na_folha) == 0 and len(cpfs_faltantes_no_json) == 0:
                    st.success("Tudo sincronizado!")
                else:
                    aba1, aba2, aba3, aba4 = st.tabs([
                        f"❌ Divergências na Folha ({len(dif_folha)})",
                        f"❌ Divergências no JSON ({len(dif_json)})",
                        f"⚠️ Faltam na Folha ({len(cpfs_faltantes_na_folha)})",
                        f"⚠️ Faltam no JSON ({len(cpfs_faltantes_no_json)})"
                    ])
                    
                    with aba1:
                        if not dif_folha.empty: st.dataframe(dif_folha.reset_index(drop=True), use_container_width=True)
                        else: st.info("Nenhum registro divergente.")
                    with aba2:
                        if not dif_json.empty: st.dataframe(dif_json.reset_index(drop=True), use_container_width=True)
                        else: st.info("Nenhum registro divergente.")
                    with aba3:
                        if not cpfs_faltantes_na_folha.empty: st.dataframe(cpfs_faltantes_na_folha.reset_index(drop=True), use_container_width=True)
                        else: st.success("Nenhum CPF faltando na folha.")
                    with aba4:
                        if not cpfs_faltantes_no_json.empty:
                            resultados_finais = []
                            for (orgao, chave), grupo in cpfs_faltantes_no_json.groupby(['ORGAO', 'CHAVE_FOLHA']):
                                lista_matriculas = grupo['COD_LIMPO'].astype(str).str.replace(r'[^0-9X]', '', regex=True).unique().tolist()
                                df_saldos = batimento_json.buscar_saldos_folha(conn, orgao, lista_matriculas, chave, ano, mes)
                                if not df_saldos.empty:
                                    df_saldos.columns = [c.lower() for c in df_saldos.columns]
                                    grupo = grupo.merge(df_saldos[['cod_limpo', 'saldo_liquido']], left_on='COD_LIMPO', right_on='cod_limpo', how='left')
                                    grupo['SALDO_LIQUIDO'] = grupo['saldo_liquido'].fillna(0.00)
                                else:
                                    grupo['SALDO_LIQUIDO'] = 0.00
                                resultados_finais.append(grupo)

                            df_exibir = pd.concat(resultados_finais, ignore_index=True)
                            df_exibir = df_exibir.sort_values(by='SALDO_LIQUIDO', ascending=False)
                            
                            st.warning(f"Existem {len(df_exibir)} registros na Folha que não foram enviados ao JSON SEFAZ.")
                            st.dataframe(
                                df_exibir[['NOME', 'CPF_PESSOA', 'COD_INSTITUCIONAL', 'COD_LIMPO', 'ORGAO', 'CHAVE_FOLHA', 'SALDO_LIQUIDO']],
                                use_container_width=True,
                                column_config={"SALDO_LIQUIDO": st.column_config.NumberColumn("Saldo Líquido", format="R$ %.2f")}
                            )
                        else:
                            st.success("Tudo sincronizado!")
        else:
            st.info("Selecione os IDs e clique em 'Executar Batimento Consolidado' para iniciar a auditoria.")

# Nova Opção: Batimento (Migrada para o módulo externo)


    elif sub_opcao == "Novos Colaboradores":
        st.subheader("👥 Novos Colaboradores")
        df = colaboradores_novatos.executar_auditoria_novatos(conn, ano, mes)
        st.dataframe(df)

# Opção 3: Controle SEFAZ
    elif sub_opcao == "Dados Bancários (Controle SEFAZ)":
        st.subheader("🏦 Controle de Envio de Dados Bancários")
        
        if not auth_ui.verificar_credenciais_sefaz():
            st.stop()

        @st.cache_data(ttl=600)
        def carregar_dados_bancarios(ano, mes):
            return novos_dados_bancario.listar_novatos_bancario_com_status(conn, ano, mes)

        if 'df_bancario' not in st.session_state or st.session_state.get('last_params') != (ano, mes):
            with st.spinner("Buscando dados no banco..."):
                df_temp = carregar_dados_bancarios(ano, mes)
                #st.session_state.df_bancario = df_temp.sort_values(by=["ORGAO", "CPF"])
                st.session_state.df_bancario = df_temp
                st.session_state.last_params = (ano, mes)

        if not st.session_state.df_bancario.empty:
            if "ENVIAR" not in st.session_state.df_bancario.columns:
                st.session_state.df_bancario["ENVIAR"] = False

# 1. Garante a variável de estado
            if 'ordenacao_atual' not in st.session_state:
                st.session_state.ordenacao_atual = ["ORGAO", "CPF"]

        # 2. Aplica a ordenação no DataFrame ANTES de criar a cópia para exibição
        # Isso garante que a ordem venha do seu controle, e não do padrão do banco
            st.session_state.df_bancario = st.session_state.df_bancario.sort_values(
                by=st.session_state.ordenacao_atual
            )


            df_exibicao = st.session_state.df_bancario.copy()
            df_exibicao['ENVIADO'] = df_exibicao['ENVIADO'].map({
                'SIM': '✅ SIM', 'ERRO': '❌ ERRO', 'NÃO': '⏳ NÃO'
            }).fillna('⏳ NÃO')


            with st.form("form_envio_bancario"):
                df_editado = st.data_editor(
                    df_exibicao,
                    key="editor_dados_bancarios", # ESSENCIAL: Mantém o estado do componente
                    column_config={"ENVIAR": st.column_config.CheckboxColumn("Enviar?", default=False)},
                    disabled=["ENVIADO", "ORGAO", "COD_INSTITUCIONAL", "NOME_ATUAL", "CPF", "CHAVE_FOLHA"],
                    use_container_width=True, hide_index=True,
                )
                #submit_button = st.form_submit_button("Confirmar Envio Selecionados")
	        # Criamos duas colunas para alinhar os botões
                col_btn1, col_btn2 = st.columns([1, 1])
                
                with col_btn1:
                    submit_button = st.form_submit_button("Confirmar Envio Selecionados")
                
                with col_btn2:
                    # O botão de finalizar agora fica ao lado do de confirmar
                    if st.form_submit_button("Finalizar e Atualizar Tela"):
                        st.rerun()


            if submit_button:
                st.session_state.df_bancario["ENVIAR"] = df_editado["ENVIAR"]
                selecionados = st.session_state.df_bancario[st.session_state.df_bancario["ENVIAR"] == True]
                if selecionados.empty:
                    st.warning("Nenhum registro selecionado!")
                else:
                    st.session_state.processamento_pendente = selecionados.to_dict('records')
                    st.rerun()

            # Processamento com exibição de Debug/JSON preservada
            if 'processamento_pendente' in st.session_state and st.session_state.processamento_pendente:
                registros = st.session_state.pop('processamento_pendente') # Trava de reenvio aplicada aqui
                
                st.write(f"Processando {len(registros)} registros...")
                status_container = st.container()

                for registro in registros:
                    with status_container:
                        schema_dinamico = f"SW_{registro.get('ORGAO')}"
                        dados_busca = novos_dados_bancario.buscar_dados_completos(conn, schema_dinamico, registro['COD_INSTITUCIONAL'])

                        if dados_busca is None:
                            st.error(f"Dados não encontrados para {registro.get('NOME_ATUAL')}")
                            continue

                        # O JSON de Debug/Inspeção permanece aqui:
                        payload = novos_dados_bancario.montar_json_sefaz(dados_busca)
                        st.subheader(f"Inspecionando: {registro.get('NOME_ATUAL')}")
                        st.json(payload) 

                        try:
                            sucesso, json_str, retorno = novos_dados_bancario.enviar_para_sefaz(payload)
                            
                            mask = (st.session_state.df_bancario['CPF'] == registro['CPF']) & \
                                   (st.session_state.df_bancario['COD_INSTITUCIONAL'] == registro['COD_INSTITUCIONAL'])

                            if sucesso:
                                novos_dados_bancario.registrar_envio(conn, [registro], json_str, retorno)
                                st.session_state.df_bancario.loc[mask, 'ENVIADO'] = 'SIM'
                                st.success(f"Gravado: {registro.get('NOME_ATUAL')}")
                            else:
                                st.session_state.df_bancario.loc[mask, 'ENVIADO'] = 'ERRO'
                                st.error(f"Erro SEFAZ para {registro.get('NOME_ATUAL')}: {retorno}")

                            st.session_state.df_bancario.loc[mask, 'ENVIAR'] = False
                        except Exception as e:
                            st.error(f"Erro sistêmico em {registro.get('NOME_ATUAL')}: {e}")

            # 5. Auditoria de Erros (Persistente)
            st.divider()
            st.subheader("🔍 Auditoria de Erros")
            df_erros = st.session_state.df_bancario[st.session_state.df_bancario['ENVIADO'] == 'ERRO']

            if not df_erros.empty:
                cpf_para_consultar = st.selectbox("Selecione o CPF do erro para ver o detalhe:", df_erros['CPF'].unique())
                if st.button("Carregar Log do Servidor", key="btn_carregar_log"):
                    log_erro = novos_dados_bancario.buscar_detalhe_erro_no_banco(conn, cpf_para_consultar)
                    st.text_area("Log detalhado da SEFAZ:", value=log_erro, height=200)
            else:
                st.info("Nenhum registro com erro para exibir.")

            #if st.button("Finalizar e Atualizar Tela", key="btn_finalizar_processo"):
            #    st.rerun()
        else:
            st.info("Nenhum registro encontrado para esta competência.")
