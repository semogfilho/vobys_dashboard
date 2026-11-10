import streamlit as st
import pandas as pd
import json,  copy
import auth_ui
# Mantemos as importações originais que você já usa para as outras opções
st.cache_data.clear()

from auditoria import (
    tipo_folha_x_tipo_arquivo_sefaz,
    colaboradores_novatos,
    novos_dados_bancario,
    batimento_json
)

def render(conn, ano, mes, sub_opcao):
    # Configuração do menu lateral
    #sub_opcao = st.sidebar.radio(
    #    "Selecione:",
    #    [
    #        "Consistência Folha",
    #        "Dados Bancários (Controle SEFAZ)",
    #        "Auditoria de Integridade (Batimento)"
    #    ],
    #    key="sub_menu_auditoria_key"
    #)

                 #"Consistência Folha",
                 #"Dados Bancários",
                 #"Auditoria de Integridade"
 
    # Opção 1: Consistência Folha
    if sub_opcao == "Consistência Folha":
        # Lógica para o título dinâmico
        mes_exibicao = "13º" if int(mes) == 13 else f"{int(mes):02d}"
        
        st.subheader(f"📊 Consistência da Folha ({mes_exibicao}/{ano})")
        df_consistencia = tipo_folha_x_tipo_arquivo_sefaz.executar_auditoria(conn, ano, mes)

        if df_consistencia is not None and not df_consistencia.empty:
            # 1. Garante que as colunas de data estejam no formato datetime
            for col in ['DATA_FECHAMENTO', 'DATA_CADASTRO']:
                if col in df_consistencia.columns:
                    df_consistencia[col] = pd.to_datetime(df_consistencia[col], errors='coerce')

            # 2. Exibe com a formatação visual configurada
            st.dataframe(
                df_consistencia,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "DATA_FECHAMENTO": st.column_config.DatetimeColumn(
                        "Data Fechamento",
                        format="DD-MM-YYYY HH:mm:ss"
                    ),
                    "DATA_CADASTRO": st.column_config.DatetimeColumn(
                        "Data Cadastro",
                        format="DD-MM-YYYY HH:mm:ss"
                    )
                }
            )
        else:
            st.warning("Nenhum registro de inconsistência encontrado para o período selecionado.")


    # Opção 3: Auditoria de Integridade (Batimento)
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
                from auditoria import batimento_json

                # --- 1. PROCESSAMENTO DE BATIMENTO ---
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
                # --- DIAGNÓSTICO DE PRÉ-CRUZAMENTO ---
                st.write("---")
                col_debug1, col_debug2 = st.columns(2)
                col_debug1.metric("Total de Registros na Folha", len(df_folha_total))
                col_debug2.metric("Total de Registros no JSON", len(df_json_total))

                if not df_folha_total.empty and not df_json_total.empty:
                    # Verifica CPFs únicos em cada base
                    cpfs_folha = set(df_folha_total['CPF_LIMPO'].unique())
                    cpfs_json = set(df_json_total['CPF_LIMPO'].unique())
                    
                    st.write(f"CPFs únicos na Folha: {len(cpfs_folha)}")
                    st.write(f"CPFs únicos no JSON: {len(cpfs_json)}")
                    
                    # Identifica se há intersecção
                    interseccao = cpfs_folha.intersection(cpfs_json)
                    st.write(f"CPFs presentes em AMBAS as bases: {len(interseccao)}")
                # --------------------------------------

                cpfs_faltantes_na_folha = df_json_total[~df_json_total['CPF_LIMPO'].isin(df_folha_total['CPF_LIMPO'])] if not df_folha_total.empty else pd.DataFrame()
                cpfs_faltantes_no_json = df_folha_total[~df_folha_total['CPF_LIMPO'].isin(df_json_total['CPF_LIMPO'])] if not df_json_total.empty else pd.DataFrame()

                # --- 2. BUSCA DE SALDOS ---
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

# 1. CÁLCULO DAS PORCENTAGENS
                total_registros = len(df_folha_total) if not df_folha_total.empty else 1 
            
            # 2. LINHA DE MÉTRICAS (Alinhadas em uma linha)
                cols = st.columns(4)
                cols[0].metric("Divergências na Folha", len(dif_folha), f"{(len(dif_folha)/total_registros)*100:.2f}%")
                cols[1].metric("Divergências no JSON", len(dif_json), f"{(len(dif_json)/total_registros)*100:.2f}%")
                cols[2].metric("Faltam na Folha", len(cpfs_faltantes_na_folha), f"{(len(cpfs_faltantes_na_folha)/total_registros)*100:.2f}%")
                cols[3].metric("Faltam no JSON", len(df_filtrado_aba4), f"{(len(df_filtrado_aba4)/total_registros)*100:.2f}%")
    
            # 3. ABAS
                aba1, aba2, aba3, aba4 = st.tabs([
                    "❌ Divergências na Folha", 
                    "❌ Divergências no JSON", 
                    "⚠️ Faltam na Folha", 
                    "⚠️ Faltam no JSON"
                ])

                # --- 4. RENDERIZAÇÃO ---

                with aba1:
                    if not dif_folha.empty:
                # --- BLOCO DE INVESTIGAÇÃO (ESPELHADO) ---
                        with st.expander("🔍 Investigar Divergências na Folha (Debug)"):
                            st.write("Amostra das chaves presentes na Folha mas não encontradas no JSON:")
                            # Exibe as colunas principais para conferência
                            st.write(dif_folha[['ORGAO', 'CHAVE_FOLHA', 'CPF_PESSOA', 'COD_INSTITUCIONAL', 'chave']].head(10))
                            
                            # Diagnóstico de Chave
                            total_dif = len(dif_folha)
                            st.write(f"Total de registros divergentes: {total_dif}")
                            
                            # Dica visual para você, o especialista:
                            st.markdown("""
                            **Verifique:**
                            * A coluna `CHAVE_FOLHA` está correta para esses registros?
                            * O `COD_INSTITUCIONAL` na folha contém caracteres estranhos que o `limpar_codigo` não está tratando?
                            """)
                # -----------------------------------------
                        # Garante a ordem e remove colunas técnicas
                        st.dataframe(dif_folha.drop(columns=['MATRICULA_LIMPA', 'COD_LIMPO', 'CPF_LIMPO', 'chave'], errors='ignore'), use_container_width=True, hide_index=False)
                    else:
                        st.info("Nenhum registro divergente.")

                with aba2:
                    if not dif_json.empty:
                # --- BLOCO DE INVESTIGAÇÃO ---
                        with st.expander("🔍 Investigar Divergências (Debug)"):
                            st.write("Amostra das chaves não encontradas na folha:")
                            st.write(dif_json[['nomeCredor', 'CPF_LIMPO', 'MATRICULA_LIMPA', 'chave']].head(100))
            
                            # Verifica se há CPFs que existem no JSON mas estão totalmente ausentes da folha
                            cpfs_no_json = set(dif_json['CPF_LIMPO'])
                            cpfs_na_folha = set(df_folha_total['CPF_LIMPO'])
                            intersect = cpfs_no_json.intersection(cpfs_na_folha)
            
                            if intersect:
                                st.warning(f"Existem {len(intersect)} CPFs presentes no JSON que possuem registros na folha, mas a MATRÍCULA ou CHAVE não bateu.")
                            else:
                                st.error("Nenhum desses CPFs foi localizado na folha. Problema de carga ou filtro de competência?")
                # -----------------------------

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

# Opção 2: Dados Bancários
    elif sub_opcao == "Dados Bancários":
        mes_exibicao = "13º" if int(mes) == 13 else f"{int(mes):02d}"
        st.subheader(f"🏦 Dados Bancários (Controle SEFAZ) ({mes_exibicao}/{ano})")

        if not auth_ui.verificar_credenciais_sefaz():
            st.stop()

        @st.cache_data(ttl=600)
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

            if 'ordenacao_atual' not in st.session_state:
                st.session_state.ordenacao_atual = ["ORGAO", "CPF"]

            st.session_state.df_bancario = st.session_state.df_bancario.sort_values(
                by=st.session_state.ordenacao_atual
            )

            df_exibicao = st.session_state.df_bancario.copy()
            df_exibicao['CPF'] = df_exibicao['CPF'].astype(str).str.replace(r'\D', '', regex=True)
            df_exibicao['ENVIADO'] = df_exibicao['ENVIADO'].map({
                'SIM': '✅ SIM', 'ERRO': '❌ ERRO', 'NÃO': '⏳ NÃO'
            }).fillna('⏳ NÃO')

            # FORMULÁRIO PARA EDIÇÃO E ENVIO
            with st.form("form_envio_bancario"):
                df_editado = st.data_editor(
                    df_exibicao,
                    key="editor_dados_bancarios",
                    column_config={"ENVIAR": st.column_config.CheckboxColumn("Enviar?", default=False)},
                    disabled=["ENVIADO", "ORGAO", "COD_INSTITUCIONAL", "NOME_ATUAL", "CPF", "CHAVE_FOLHA"],
                    use_container_width=True, hide_index=True,
                )
                
                col_btn1, col_btn2 = st.columns([1, 1])
                with col_btn1:
                    submit_button = st.form_submit_button("Confirmar Envio Selecionados")
                with col_btn2:
                    finalizar_button = st.form_submit_button("Finalizar e Atualizar Tela")

            # LÓGICA DO FORM
            if submit_button:
                st.session_state.df_bancario["ENVIAR"] = df_editado["ENVIAR"]
                selecionados = st.session_state.df_bancario[st.session_state.df_bancario["ENVIAR"] == True]
                if selecionados.empty:
                    st.warning("Nenhum registro selecionado!")
                else:
                    st.session_state.processamento_pendente = selecionados.to_dict('records')
                    st.rerun()

            if finalizar_button:
                st.rerun()

            # ÁREA DE BUSCA (FORA DO FORM)
            st.divider()
            col_b1, col_b2, col_b3 = st.columns([2, 1, 1])
            with col_b1:
                cpf_busca = st.text_input("Consultar CPF avulso:", placeholder="Digite o CPF...")
            with col_b2:
                st.write(f"Competência: **{mes}/{ano}**")
            with col_b3:
                btn_buscar = st.button("Buscar CPF na Competência")

            if btn_buscar and cpf_busca:
                cpf_limpo = ''.join(filter(str.isdigit, cpf_busca))
                cpf_na_lista = st.session_state.df_bancario[
                    st.session_state.df_bancario['CPF'].astype(str).str.replace(r'\D', '', regex=True) == cpf_limpo
                ]

                if not cpf_na_lista.empty:
                    st.info(f"O CPF {cpf_limpo} já está listado.")
                    
                    # 1. Marca como True na lista principal e exibe
                    st.session_state.df_bancario.loc[
                        st.session_state.df_bancario['CPF'].astype(str).str.replace(r'\D', '', regex=True) == cpf_limpo, 
                        'ENVIAR'
                    ] = True
                    
                    st.data_editor(cpf_na_lista, use_container_width=True, hide_index=True)
                    
                    if st.button("Voltar para lista completa"):
                        st.rerun()

                else:
                    df_encontrado = novos_dados_bancario.buscar_por_cpf(conn, cpf_limpo, ano, mes)
                    if df_encontrado is not None and not df_encontrado.empty:
                        # Garante que TODOS os registros encontrados sejam marcados para envio
                        df_encontrado['ENVIAR'] = True
                        
                        # Atualiza o estado global
                        st.session_state.df_bancario = pd.concat([st.session_state.df_bancario, df_encontrado]).drop_duplicates(subset=['CPF', 'COD_INSTITUCIONAL'])
                        
                        # Remove possíveis duplicatas de colunas que podem surgir após o concat
                        st.session_state.df_bancario = st.session_state.df_bancario.loc[:, ~st.session_state.df_bancario.columns.duplicated()]

                        st.success(f"{len(df_encontrado)} registro(s) localizado(s) e adicionado(s)!")
                        
                        # O data_editor exibirá todos os registros encontrados automaticamente
                        # Ajustamos a altura para não ficar um buraco enorme na tela se forem muitos registros
                        st.data_editor(
                            df_encontrado, 
                            use_container_width=True, 
                            hide_index=True,
                            num_rows="fixed" 
                        )
                        
                        if st.button("Voltar para lista completa"):
                            st.rerun()

                    else:
                        st.error("CPF não encontrado.")
                        if st.button("Voltar para lista completa"):
                            st.rerun()


            # PROCESSAMENTO
            if 'processamento_pendente' in st.session_state and st.session_state.processamento_pendente:
                registros = st.session_state.pop('processamento_pendente')
                status_container = st.container()

                for registro in registros:
                    with status_container:
                        schema_dinamico = f"SW_{registro.get('ORGAO')}"
                        dados_busca = novos_dados_bancario.buscar_dados_completos(conn, schema_dinamico, registro['COD_INSTITUCIONAL'])
                        if dados_busca is None:
                            st.error(f"Dados não encontrados para {registro.get('NOME_ATUAL')}")
                            continue

                        payload = novos_dados_bancario.montar_json_sefaz(dados_busca)
                        payload_visual = copy.deepcopy(payload)
                        if 'dadosBancarios' in payload_visual and isinstance(payload_visual['dadosBancarios'], dict):
                            payload_visual['dadosBancarios'] = [payload_visual['dadosBancarios'][0]]
                        st.json(json.dumps(payload_visual, indent=4, ensure_ascii=False))

                        try:
                            sucesso, json_str, retorno = novos_dados_bancario.enviar_para_sefaz(payload)

                            #sucesso, json_str, retorno = True, "SIMULADO_JSON", "Simulação OK"
                            mask = (st.session_state.df_bancario['CPF'] == registro['CPF']) & \
                                   (st.session_state.df_bancario['COD_INSTITUCIONAL'] == registro['COD_INSTITUCIONAL'])

                            # Independente de ser sucesso ou erro, gravamos o log no banco
                            novos_dados_bancario.registrar_envio(conn, [registro], json_str, retorno)

                            if sucesso:
                                #novos_dados_bancario.registrar_envio(conn, [registro], json_str, retorno)
                                st.session_state.df_bancario.loc[mask, 'ENVIADO'] = 'SIM'
                                st.success(f"Gravado: {registro.get('NOME_ATUAL')}")
                            else:
                                st.session_state.df_bancario.loc[mask, 'ENVIADO'] = 'ERRO'
                                st.error(f"Erro: {retorno}")
                            st.session_state.df_bancario.loc[mask, 'ENVIAR'] = False
                        except Exception as e:
                            st.error(f"Erro sistêmico em {registro.get('NOME_ATUAL')}: {e}")

            # AUDITORIA DE ERROS
            st.divider()
            st.subheader("🔍 Auditoria de Erros")
            df_erros = st.session_state.df_bancario[st.session_state.df_bancario['ENVIADO'] == 'ERRO']
            if not df_erros.empty:
                cpf_err = st.selectbox("Selecione o CPF do erro:", df_erros['CPF'].unique())
                if st.button("Carregar Log do Servidor"):
                    st.error(f"Log: {novos_dados_bancario.buscar_detalhe_erro_no_banco(conn, cpf_err)}")
            else:
                st.info("Nenhum erro para exibir.")
