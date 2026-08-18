import streamlit as st
import pandas as pd
import json
import auth_ui
# Mantemos as importações originais que você já usa para as outras opções
st.cache_data.clear()

from auditoria import (
    tipo_folha_x_tipo_arquivo_sefaz,
    colaboradores_novatos,
    novos_dados_bancario
)

def render(conn, ano, mes):
    # Configuração do menu lateral
    #st.sidebar.subheader("Sub-menu de Auditoria")
    sub_opcao = st.sidebar.radio(
        "Selecione:", 
        ["Consistência Folha", "Dados Bancários (Controle SEFAZ)"], # <--- Lista fechada com ]
        key="sub_menu_auditoria_key"                                # <--- Argumento key separado por vírgula
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

    # Opção 2: Novos Colaboradores (Mantida a chamada original)
    elif sub_opcao == "Novos Colaboradores":
        st.subheader("👥 Novos Colaboradores")
        df = colaboradores_novatos.executar_auditoria_novatos(conn, ano, mes)
        st.dataframe(df)
# Opção 3: Controle SEFAZ
    elif sub_opcao == "Dados Bancários (Controle SEFAZ)":
        st.subheader("🏦 Controle de Envio de Dados Bancários")
        # Módulos que exigem autenticação SEFAZ
        # 1. Checagem de Segurança (Guarda-costas)
        if not auth_ui.verificar_credenciais_sefaz():
            st.stop() # Interrompe tudo se não estiver autenticado


        @st.cache_data(ttl=600)
        def carregar_dados_bancarios(ano, mes):
            return novos_dados_bancario.listar_novatos_bancario_com_status(conn, ano, mes)

        # 1. Carregamento e Cache
        if 'df_bancario' not in st.session_state or st.session_state.get('last_params') != (ano, mes):
            with st.spinner("Buscando dados no banco..."):
                df_temp = carregar_dados_bancarios(ano, mes)
                st.session_state.df_bancario = df_temp.sort_values(by=["ORGAO", "CPF"])
                st.session_state.last_params = (ano, mes)

        # 2. Filtro de Unicidade
        #if 'df_bancario' in st.session_state:
        #    st.session_state.df_bancario = st.session_state.df_bancario.drop_duplicates(
        #        subset=["CPF", "COD_INSTITUCIONAL"],
        #        keep='first'
        #    )

        # 3. Exibição do Formulário
        if not st.session_state.df_bancario.empty:
            if "ENVIAR" not in st.session_state.df_bancario.columns:
                st.session_state.df_bancario["ENVIAR"] = False

            df_exibicao = st.session_state.df_bancario.copy()
            df_exibicao['ENVIADO'] = df_exibicao['ENVIADO'].map({
                'SIM': '✅ SIM',
                 'ERRO': '❌ ERRO',
                 'NÃO': '⏳ NÃO'
            }).fillna('⏳ NÃO')

            with st.form("form_envio_bancario"):
                df_editado = st.data_editor(
                    df_exibicao, # Passamos o dataframe com os marcadores
                    column_config={
                        "ENVIAR": st.column_config.CheckboxColumn("Enviar?", default=False),
                        "ENVIADO": st.column_config.TextColumn(
                            "ENVIADO",
                            help="✅ Sim | ❌ Erro | ⏳ Não"
                        ),
                    },
                    disabled=["ENVIADO", "ORGAO", "COD_INSTITUCIONAL", "NOME_ATUAL", "CPF", "CHAVE_FOLHA"],
                    use_container_width=True,
                    hide_index=True
                )
                submit_button = st.form_submit_button("Confirmar Envio Selecionados")

            # 4. Ação do Formulário (Prepara o processamento)
            if submit_button:
                st.session_state.df_bancario = df_editado
                selecionados = st.session_state.df_bancario[st.session_state.df_bancario["ENVIAR"] == True]
                
                if selecionados.empty:
                    st.warning("Nenhum registro selecionado para envio!")
                else:
                    st.session_state.processamento_pendente = selecionados.to_dict('records')
                    st.rerun()

            # 5. Processamento (Executa fora do formulário)
            if 'processamento_pendente' in st.session_state:
                registros = st.session_state.processamento_pendente
                st.write(f"Processando {len(registros)} registros...")

                status_container = st.container()

                for registro in registros:
                    with status_container:

                        schema_dinamico = f"SW_{registro.get('ORGAO')}"
                        dados_busca = novos_dados_bancario.buscar_dados_completos(conn, schema_dinamico, registro['COD_INSTITUCIONAL'])

                        if dados_busca is None:
                            st.error(f"Dados não encontrados para {registro.get('NOME_ATUAL')}")
                            continue

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
                                # O servidor respondeu, mas indicou erro na validação/processamento
                                st.session_state.df_bancario.loc[mask, 'ENVIADO'] = 'ERRO'
                                st.error(f"Erro SEFAZ para {registro.get('NOME_ATUAL')}: {retorno}")
                            
                            # Atualiza a flag de envio para False após processar
                            st.session_state.df_bancario.loc[mask, 'ENVIAR'] = False
                            
                        except Exception as e:
                            # Erro de conexão ou exceção inesperada
                            mask = (st.session_state.df_bancario['CPF'] == registro['CPF']) & \
                                   (st.session_state.df_bancario['COD_INSTITUCIONAL'] == registro['COD_INSTITUCIONAL'])
                            st.session_state.df_bancario.loc[mask, 'ENVIADO'] = 'ERRO'
                            st.session_state.df_bancario.loc[mask, 'ENVIAR'] = False
                            st.error(f"Erro sistêmico em {registro.get('NOME_ATUAL')}: {e}")

                if st.button("Finalizar e Atualizar Tela"):
                    st.session_state.pop('processamento_pendente', None)
                    st.rerun()
        else:
            st.info("Nenhum registro encontrado para esta competência.")

