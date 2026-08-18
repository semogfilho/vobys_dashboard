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
        # CORREÇÃO: Você precisa capturar o retorno e exibir
        df_consistencia = tipo_folha_x_tipo_arquivo_sefaz.executar_auditoria(conn, ano, mes)
        
        if df_consistencia is not None and not df_consistencia.empty:
            st.dataframe(df_consistencia)
        else:
            st.warning("Nenhum registro de inconsistência encontrado para o período selecionado.")

# Nova Opção: Batimento (Migrada para o módulo externo)
    elif sub_opcao == "Auditoria de Integridade (Batimento)":
        st.subheader("🔍 Batimento: Folha vs. JSON SEFAZ")

        # Inputs necessários para a função
        col1, col2 = st.columns(2)
        with col1:
            chave_selecionada = st.text_input("Chave da Folha", value="06/2026-270")
        with col2:
            id_selecionado = st.number_input("ID Integração", value=1031369, step=1)

        if st.button("Executar Batimento"):
            with st.spinner("Comparando registros..."):
                from auditoria import batimento_json
                
                # Executa a função robusta que criamos
                dif_folha, dif_json, pct_folha, pct_json, erro = batimento_json.processar_batimento_consolidado(conn, selecionados)

                # Tratamento de erro e exibição de resultados
                if erro:
                    st.error(f"Erro ao processar: {erro}")
                
                elif dif_folha.empty and dif_json.empty:
                    st.success("Tudo sincronizado! Nenhuma divergência encontrada.")
                
                else:
                    st.warning("Divergências encontradas no batimento:")
                    
                    # Uso de abas para organizar a visualização dos DataFrames
                    tab1, tab2 = st.tabs([
                        f"❌ Divergências na Folha ({len(dif_folha)})", 
                        f"❌ Divergências no JSON SEFAZ ({len(dif_json)})"
                    ])
                    
                    with tab1:
                        if not dif_folha.empty:
                            st.dataframe(dif_folha, use_container_width=True)
                        else:
                            st.info("Nenhum registro divergente na folha.")
                            
                    with tab2:
                        if not dif_json.empty:
                            st.dataframe(dif_json, use_container_width=True)
                        else:
                            st.info("Nenhum registro divergente no JSON SEFAZ.")


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
