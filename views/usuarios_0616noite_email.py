# -*- coding: utf-8 -*-
import streamlit as st
import os
import toml
import hashlib
import pandas as pd

# Caminho do arquivo de usuários
CAMINHO_ATUAL = os.path.dirname(__file__)
if CAMINHO_ATUAL.endswith(".streamlit") or CAMINHO_ATUAL.endswith("views"):
    CAMINHO_USERS_TOML = os.path.abspath(os.path.join(CAMINHO_ATUAL, "..", ".streamlit", "users.toml"))
else:
    CAMINHO_USERS_TOML = os.path.abspath(os.path.join(CAMINHO_ATUAL, ".streamlit", "users.toml"))

# --- Funções de Banco e Arquivos ---

def registrar_log_acesso(conn, login, ip_usuario="0.0.0.0"):
    cursor = conn.cursor()
    try:
        query = "INSERT INTO APP_LOG_ACESSO (USUARIO, IP_USUARIO, DATA_ACESSO) VALUES (:1, :2, SYSDATE)"
        cursor.execute(query, [login, ip_usuario])
        conn.commit()
    except Exception as e:
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

def buscar_logs_usuario(conn, login):
    query = f"""
    SELECT * FROM (
        SELECT TO_CHAR(DATA_ACESSO, 'DD/MM/YYYY HH24:MI:SS') AS DATA_HORA, IP_USUARIO 
        FROM APP_LOG_ACESSO 
        WHERE USUARIO = '{login}' 
        ORDER BY DATA_ACESSO DESC
    ) WHERE ROWNUM <= 10
    """
    return pd.read_sql(query, conn)

# --- Renderização ---

def render(conn, perfil_logado):
    # CSS para forçar a compactação da altura
    st.markdown("""
        <style>
        [data-testid="stVerticalBlockBorderWrapper"] { padding: 5px !important; }
        [data-testid="stVerticalBlock"] { gap: 0px !important; }
        .stButton button { padding: 0px 5px !important; height: 30px !important; }
        </style>
    """, unsafe_allow_html=True)

    if "msg_sucesso_reset" not in st.session_state:
        st.session_state.msg_sucesso_reset = None

    st.markdown("<h2>⚙️ Gerenciamento de Usuários</h2>", unsafe_allow_html=True)
    aba_listar, aba_cadastrar = st.tabs(["📋 Lista", "➕ Cadastro"])

    dados_toml = carregar_usuarios()
    usuarios_dict = dados_toml.get("usuario", {})

    with aba_listar:
        if st.session_state.msg_sucesso_reset:
            st.success(st.session_state.msg_sucesso_reset)
            st.session_state.msg_sucesso_reset = None

        for login, info in usuarios_dict.items():
            tipo_user = info.get("tipo", "c")
            nome_user = info.get("nome", "Sem Nome")
            esta_resetado = str(info.get("requer_reset", "nao")).strip().lower() in ["sim", "true", "1"]
            label_perfil = "Administrador" if tipo_user == "a" else "Gerente" if tipo_user == "g" else "Comum"

            with st.container(border=True):
                c1, c2, c3, c4, c5 = st.columns([3, 2, 2, 1.5, 1.5])
                with c1: st.markdown(f"**{nome_user}** ({login})")
                with c2: st.markdown(f"Perfil: {label_perfil}")
                with c3: st.markdown(":red[🔴 Resetado]" if esta_resetado else ":green[✅ Ativo]")
                
                with c4:
                    if perfil_logado == "g" and tipo_user == "a": st.caption("🔒 Restrito")
                    elif st.button("📊 Logs", key=f"log_{login}", use_container_width=True):
                        st.session_state[f"show_log_{login}"] = True
                
                with c5:
                    if perfil_logado == "g" and tipo_user == "a": st.caption("🔒 Restrito")
                    elif esta_resetado: st.button("Solicitado", key=f"rst_{login}", disabled=True, use_container_width=True)
                    else:
                        with st.popover("🔑 Reset", use_container_width=True):
                            if st.button("Confirmar Reset", key=f"conf_rst_{login}", type="primary"):
                                dados_toml["usuario"][login]["requer_reset"] = "sim"
                                dados_toml["usuario"][login]["senha_hash"] = hashlib.sha256("sead@ntgd".encode()).hexdigest()
                                salvar_usuarios(dados_toml)
                                st.session_state.msg_sucesso_reset = "Senha resetada!"
                                st.rerun()

            if st.session_state.get(f"show_log_{login}"):
                with st.container(border=True):
                    st.dataframe(buscar_logs_usuario(conn, login), use_container_width=True, hide_index=True)
                    if st.button("Fechar", key=f"close_{login}"):
                        st.session_state[f"show_log_{login}"] = False
                        st.rerun()
    
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

