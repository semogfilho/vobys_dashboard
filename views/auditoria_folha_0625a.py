import streamlit as st
import pandas as pd
import json
# Mantemos as importações originais que você já usa para as outras opções
st.cache_data.clear()

from auditoria import (
    tipo_folha_x_tipo_arquivo_sefaz,
    colaboradores_novatos,
    novos_dados_bancario
)

def render(conn, ano, mes):
    # Configuração do menu lateral
    st.sidebar.subheader("Sub-menu de Auditoria")
    sub_opcao = st.sidebar.radio("Selecione:", [
        "Consistência Folha",
        "Novos Colaboradores",
        "Dados Bancários (Controle SEFAZ)"
    ])

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

        @st.cache_data(ttl=600)
        def carregar_dados_bancarios(ano, mes):
            return novos_dados_bancario.listar_novatos_bancario_com_status(conn, ano, mes)

        # 1. Carregamento e Cache
        if 'df_bancario' not in st.session_state or st.session_state.get('last_params') != (ano, mes):
            with st.spinner("Buscando dados no banco..."):
                df_temp = carregar_dados_bancarios(ano, mes)
                st.session_state.df_bancario = df_temp.sort_values(by=["ORGAO", "CPF"])
                st.session_state.last_params = (ano, mes)

        # 2. Filtro de Unicidade (Remover duplicadas visualmente)
        if 'df_bancario' in st.session_state:
            st.session_state.df_bancario = st.session_state.df_bancario.drop_duplicates(
                subset=["CPF", "COD_INSTITUCIONAL"],
                keep='first'
            )

        if not st.session_state.df_bancario.empty:
            if "ENVIAR" not in st.session_state.df_bancario.columns:
                st.session_state.df_bancario["ENVIAR"] = False

           # 1. Checkbox Mestre (agora armazenado em uma variável de controle)
            #selecionar_todos = st.checkbox("Marcar/Desmarcar Todos")

           # 2. Lógica para alternar em massa apenas quando o usuário interagir com o checkbox
            #if 'ultima_selecao_mestra' not in st.session_state:
            #    st.session_state.ultima_selecao_mestra = False

            #if selecionar_todos != st.session_state.ultima_selecao_mestra:
            #    st.session_state.ultima_selecao_mestra = selecionar_todos
            #    st.session_state.df_bancario["ENVIAR"] = selecionar_todos
            #    st.rerun() # Força a atualização da tela com os novos estados


            # 3. Edição de dados
            df_editado = st.data_editor(
                st.session_state.df_bancario,
                column_config={"ENVIAR": st.column_config.CheckboxColumn("Enviar?", default=False)},
                disabled=["ENVIADO", "ORGAO", "COD_INSTITUCIONAL", "NOME_ATUAL", "CPF", "CHAVE_FOLHA"],
                use_container_width=True
            )
            st.session_state.df_bancario["ENVIAR"] = df_editado["ENVIAR"]

            # 4. Botão de Ação com suporte a reenvio
            if st.button("Confirmar Envio Selecionados"):
                selecionados = st.session_state.df_bancario[
                    st.session_state.df_bancario["ENVIAR"] == True
                ]

                if selecionados.empty:
                    st.warning("Nenhum registro selecionado para envio!")
                else:
                    st.session_state.processamento_pendente = selecionados.to_dict('records')
                    st.rerun()

            # 5. Lógica de Processamento
            if 'processamento_pendente' in st.session_state:
                registros = st.session_state.processamento_pendente
                st.write(f"Processando {len(registros)} registros...")

                status_container = st.container()

                for registro in registros:
                    with status_container:
                        schema_dinamico = f"SW_{registro.get('ORGAO')}"

                        # Busca
                        dados_busca = novos_dados_bancario.buscar_dados_completos(conn, schema_dinamico, registro['COD_INSTITUCIONAL'])

                        if dados_busca is None:
                            st.error(f"Dados não encontrados para {registro.get('NOME_ATUAL')}")
                            continue

                        # Montagem
                        payload = novos_dados_bancario.montar_json_sefaz(dados_busca)
                        st.subheader(f"Inspecionando: {registro.get('NOME_ATUAL')}")
                        st.json(payload)

                        # Gravação via MERGE (Upsert)
                        # 3. Gravação
                        try:
                            sucesso, json_str, retorno = novos_dados_bancario.enviar_para_sefaz(payload)
                            
                            # Grava no banco
                            novos_dados_bancario.registrar_envio(conn, [registro], json_str, retorno)
                            
                            # --- ATUALIZAÇÃO EM MEMÓRIA (SEM CONSULTAR O BANCO) ---
                            # Localiza o índice do registro que foi enviado no DataFrame de sessão
                            mask = (st.session_state.df_bancario['CPF'] == registro['CPF']) & \
                                   (st.session_state.df_bancario['COD_INSTITUCIONAL'] == registro['COD_INSTITUCIONAL'])
                            
                            # Atualiza a coluna ENVIADO para 'SIM' e limpa o check 'ENVIAR'
                            st.session_state.df_bancario.loc[mask, 'ENVIADO'] = 'SIM'
                            st.session_state.df_bancario.loc[mask, 'ENVIAR'] = False
                            # -----------------------------------------------------

                            st.success(f"Gravado e atualizado localmente: {registro.get('NOME_ATUAL')}")
                        except Exception as e:
                            st.error(f"Erro no envio de {registro.get('NOME_ATUAL')}: {e}")

                # Limpeza final
                st.session_state.pop('processamento_pendente', None)
                if st.button("Finalizar e Atualizar Tela"):
                    st.rerun()
        else:
            st.info("Nenhum registro encontrado para esta competência.")

