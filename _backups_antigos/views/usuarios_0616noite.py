# -*- coding: utf-8 -*-
import streamlit as st
import os
import toml
import hashlib
import pandas as pd

# Garante o caminho exato para encontrar o arquivo de usuários
CAMINHO_ATUAL = os.path.dirname(__file__)
if CAMINHO_ATUAL.endswith(".streamlit") or CAMINHO_ATUAL.endswith("views"):
    CAMINHO_USERS_TOML = os.path.abspath(os.path.join(CAMINHO_ATUAL, "..", ".streamlit", "users.toml"))
else:
    CAMINHO_USERS_TOML = os.path.abspath(os.path.join(CAMINHO_ATUAL, ".streamlit", "users.toml"))

# --- Funções de Log de Acesso ---

def registrar_log_acesso(conn, login, ip_usuario="0.0.0.0"):
    cursor = conn.cursor()
    try:
        # Usamos o INSERT simples. Se a tabela foi truncada, o próximo registro será o ID 1
        query = "INSERT INTO APP_LOG_ACESSO (USUARIO, IP_USUARIO, DATA_ACESSO) VALUES (:1, :2, SYSDATE)"
        cursor.execute(query, [login, ip_usuario])
        conn.commit()
    except Exception as e:
        # Se ocorrer erro, não trava o app, apenas registra no console para debug
        print(f"Erro ao inserir log no banco: {e}")
    finally:
        cursor.close()

def carregar_usuarios():
    if not os.path.exists(CAMINHO_USERS_TOML):
        return {"usuario": {}}
    return toml.load(CAMINHO_USERS_TOML)

def salvar_usuarios(dados):
    with open(CAMINHO_USERS_TOML, "w", encoding="utf-8") as f:
        toml.dump(dados, f)

# --- Funções de Log de Acesso ---
def buscar_logs_usuario(conn, login):
    query = f"""
    SELECT * FROM (
        SELECT TO_CHAR(DATA_ACESSO, 'DD/MM/YYYY HH24:MI:SS') AS DATA_HORA 
        ,IP_USUARIO
        FROM APP_LOG_ACESSO 
        WHERE USUARIO = '{login}' 
        ORDER BY DATA_ACESSO DESC
    ) WHERE ROWNUM <= 10
    """
    return pd.read_sql(query, conn)

def render(conn, perfil_logado):
    if "msg_sucesso_reset" not in st.session_state:
        st.session_state.msg_sucesso_reset = None

    st.markdown("<h2>⚙️ Gerenciamento de Usuários (Config TOML)</h2>", unsafe_allow_html=True)
    
    aba_listar, aba_cadastrar = st.tabs(["📋 Usuários Cadastrados", "➕ Cadastrar Novo Usuário"])
    
    dados_toml = carregar_usuarios()
    usuarios_dict = dados_toml.get("usuario", {})

    with aba_listar:
        st.write("### Lista de Acessos")
        
        if st.session_state.msg_sucesso_reset:
            st.success(st.session_state.msg_sucesso_reset)
            st.session_state.msg_sucesso_reset = None

        for login, info in usuarios_dict.items():
            tipo_user = info.get("tipo", "c")
            nome_user = info.get("nome", "Sem Nome")
            status_reset_bruto = info.get("requer_reset", "nao")
            esta_resetado = str(status_reset_bruto).strip().lower() in ["sim", "true", "1"]
            
            # Layout mais equilibrado: 4 colunas (Nome, Perfil, Logs, Reset)
            col1, col2, col3, col4 = st.columns([4, 2, 1.5, 2.5], gap="small")
            
            with col1:
                st.write(f"👤 **{nome_user}** *({login})*")
                
            with col2:
                label_perfil = "Administrador" if tipo_user == "a" else "Gerente" if tipo_user == "g" else "Comum"
                st.write(f"Perfil: *{label_perfil}*")
            
            with col3:
	        # Restrição: Gerente não vê logs de Administrador
                if perfil_logado == "g" and tipo_user == "a":
                    st.markdown("*🔒 Restrito*")
                else:
                    if st.button("📊 Logs", key=f"log_{login}"):
                        st.session_state[f"show_log_{login}"] = True

            with col4:
                # Lógica do Reset integrada com Popover
                if perfil_logado == "g" and tipo_user == "a":
                    st.markdown("*🔒 Restrito*")
                elif esta_resetado:
                    st.button("Reset solicitado", key=f"btn_rst_{login}", disabled=True, use_container_width=True)
                else:
                    # Popover de confirmação para evitar resets acidentais
                    with st.popover("🔄 Resetar Senha", use_container_width=True):
                        st.write(f"Confirmar reset de senha para **{nome_user}**?")
                        if st.button("Confirmar Reset", key=f"conf_rst_{login}", type="primary", use_container_width=True):
                            dados_toml["usuario"][login]["requer_reset"] = "sim"
                            senha_padrao = "sead@ntgd"
                            senha_padrao_hash = hashlib.sha256(senha_padrao.strip().encode('utf-8')).hexdigest()
                            dados_toml["usuario"][login]["senha_hash"] = senha_padrao_hash
                            
                            salvar_usuarios(dados_toml)
                            st.session_state.msg_sucesso_reset = f"Sucesso! Senha provisória: `{senha_padrao}`"
                            st.rerun()

            # Área de expansão dos logs (fica abaixo da linha do usuário)
            if st.session_state.get(f"show_log_{login}"):
                #with st.container(border=True):
                st.write(f"**Histórico de Acessos: {nome_user}**")
                df_logs = buscar_logs_usuario(conn, login)
                if not df_logs.empty:
                    st.dataframe(df_logs, use_container_width=True, hide_index=True, height=200)
                else:
                    st.info("Nenhum registro encontrado.")
                if st.button("Fechar Logs", key=f"close_{login}"):
                    st.session_state[f"show_log_{login}"] = False
                    st.rerun()

            
            st.write("")

    with aba_cadastrar:
        st.write("### Inserir Novo Usuário")
        novo_login = st.text_input("Login (Sem espaços):", key="nv_login").strip().lower()
        novo_nome = st.text_input("Nome Completo:", key="nv_nome").strip()

        opcoes_perfis = {"Administrador": "a", "Gerente": "g", "Comum": "c"} if perfil_logado == "a" else {"Gerente": "g", "Comum": "c"}

        perfil_selecionado_label = st.selectbox("Tipo de Perfil:", list(opcoes_perfis.keys()))
        perfil_final_sigla = opcoes_perfis[perfil_selecionado_label]

        if st.button("Salvar Novo Usuário", type="primary"):
            if not novo_login or not novo_nome:
                st.warning("⚠️ Preencha o login e o nome completo.")
            elif novo_login in usuarios_dict:
                st.error("❌ Este login já existe!")
            else:
                senha_inicial_hash = hashlib.sha256("sead@ntgd".strip().encode('utf-8')).hexdigest()
                dados_toml["usuario"][novo_login] = {
                    "nome": novo_nome,
                    "senha_hash": senha_inicial_hash,
                    "tipo": perfil_final_sigla,
                    "requer_reset": "sim"
                }
                salvar_usuarios(dados_toml)
                st.success(f"Usuário {novo_nome} cadastrado com sucesso!")
                st.rerun()


