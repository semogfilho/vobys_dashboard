# -*- coding: utf-8 -*-
import streamlit as st
import hashlib
import toml
import os

CAMINHO_ATUAL = os.path.dirname(__file__)
CAMINHO_USERS_TOML = os.path.abspath(os.path.join(CAMINHO_ATUAL, ".streamlit", "users.toml"))

def verificar_credenciais(usuario, senha):
    if not os.path.exists(CAMINHO_USERS_TOML): return None
    dados = toml.load(CAMINHO_USERS_TOML)
    usuarios_dict = dados.get("usuario", {})
    
    usuario_limpo = usuario.strip().lower()
    senha_hash_digitada = hashlib.sha256(senha.strip().encode('utf-8')).hexdigest()
    
    # DEBUG: Remova estas linhas após confirmar o problema
    # st.write(f"DEBUG: Buscando {usuario_limpo} | Hash Digitado: {senha_hash_digitada}")
    
    if usuario_limpo in usuarios_dict:
        user_data = usuarios_dict[usuario_limpo]
        # Comparação direta dos hashes
        if senha_hash_digitada == user_data.get("senha_hash"):
            return (usuario_limpo, user_data.get("nome", ""), user_data.get("tipo"), str(user_data.get("requer_reset", "nao")))
    return None

def gerenciar_sessao_fluxo():
    st.markdown("<h3 style='color: #015494;'>🔒 Entrar</h3>", unsafe_allow_html=True)
    
    # Usando key única para evitar conflitos no Streamlit
    usuario_input = st.text_input("Username:", key="login_user").strip()
    senha_input = st.text_input("Password:", type="password", key="login_pass")
    
    if st.button("Login", key="btn_login_exec", use_container_width=True):
        dados = verificar_credenciais(usuario_input, senha_input)
        if dados:
            login_bd, nome_bd, tipo_bd, flag_reset = dados
            st.session_state.usuario_logado = login_bd
            st.session_state.nome_usuario = str(nome_bd)
            st.session_state.perfil_usuario = str(tipo_bd).lower().strip()
            st.session_state.autenticado = True
            st.rerun() 
        else:
            st.error("Usuário ou senha incorretos.")

