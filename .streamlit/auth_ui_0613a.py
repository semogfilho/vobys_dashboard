# -*- coding: utf-8 -*-
import streamlit as st
import hashlib, toml, os, base64

def carregar_usuarios():
    caminho = os.path.join(os.path.dirname(__file__), "users.toml")
    if not os.path.exists(caminho): return {}
    return toml.load(caminho).get("usuario", {})

def codificar_sessao(nome, perfil):
    payload = "{0}|{1}".format(nome, perfil)
    return base64.b64encode(payload.encode('utf-8')).decode('utf-8')

def decodificar_sessao(token):
    try:
        decoded = base64.b64decode(token.encode('utf-8')).decode('utf-8')
        return decoded.split("|")
    except:
        return None, None

def gerenciar_sessao_fluxo():
    st.write("### 🔐 Acesso ao Sistema")
    login = st.text_input("Usuário:").strip().lower()
    senha = st.text_input("Senha:", type="password")
    
    if st.button("Entrar"):
        usuarios = carregar_usuarios()
        if login in usuarios:
            user_data = usuarios[login]
            senha_hash = hashlib.sha256(senha.strip().encode('utf-8')).hexdigest()
            
            if user_data.get("senha_hash") == senha_hash:
                st.session_state.autenticado = True
                st.session_state.login_atual = login
                st.session_state.nome_usuario = user_data.get("nome", login)
                st.session_state.perfil_usuario = user_data.get("tipo", "c")
                
                # Flag de reset
                flag = user_data.get("requer_reset", "nao")
                st.session_state.precisa_resetar = (flag == "sim")
                
                # Mascarando na URL
                st.query_params["s"] = codificar_sessao(st.session_state.nome_usuario, st.session_state.perfil_usuario)
                st.rerun()
            else:
                st.error("❌ Senha incorreta.")
        else:
            st.error("❌ Usuário não encontrado.")

def processar_troca_senha(login, nova_senha):
    caminho = os.path.join(os.path.dirname(__file__), "users.toml")
    config = toml.load(caminho)
    config["usuario"][login]["senha_hash"] = hashlib.sha256(nova_senha.strip().encode('utf-8')).hexdigest()
    config["usuario"][login]["requer_reset"] = "nao"
    with open(caminho, "w") as f:
        toml.dump(config, f)
    return True

