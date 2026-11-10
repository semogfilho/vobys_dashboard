# -*- coding: utf-8 -*-
import streamlit as st
import hashlib, toml, os, base64
import usuarios

def carregar_usuarios():
    caminho = os.path.join(os.path.dirname(__file__), "users.toml")
    if not os.path.exists(caminho): return {}
    return toml.load(caminho).get("usuario", {})

def codificar_sessao(nome, perfil, login): # Adicione o login aqui
    payload = "{0}|{1}|{2}".format(nome, perfil, login) # Adicione o login no payload
    return base64.b64encode(payload.encode('utf-8')).decode('utf-8')

def decodificar_sessao(token):
    try:
        decoded = base64.b64decode(token.encode('utf-8')).decode('utf-8')
        return decoded.split("|")
    except:
        return None, None, None


def gerenciar_sessao_fluxo():
    # 1. Título do Projeto
    st.markdown("<h1 style='text-align: center; color: #d32f2f;'>NTGD</h1>", unsafe_allow_html=True)
    st.divider()

    st.write("### 🔐 Acesso ao Sistema")
    login = st.text_input("Usuário:").strip().lower()
    senha = st.text_input("Senha:", type="password")
    
    if st.button("Entrar"):
        usuarios_db = carregar_usuarios()
        if login in usuarios_db:
            user_data = usuarios_db[login]
            senha_hash = hashlib.sha256(senha.strip().encode('utf-8')).hexdigest()
            
            if user_data.get("senha_hash") == senha_hash:
                st.session_state.clear()
                st.session_state.autenticado = True
                st.session_state.login_atual = login
                st.session_state.nome_usuario = user_data.get("nome", login)
                st.session_state.perfil_usuario = user_data.get("tipo", "c")
                
                flag = user_data.get("requer_reset", "nao")
                st.session_state.precisa_resetar = (flag == "sim")
                
                st.query_params["s"] = codificar_sessao(st.session_state.nome_usuario, st.session_state.perfil_usuario, st.session_state.login_atual)
                st.rerun()
            else:
                st.error("❌ Senha incorreta.")
        else:
            st.error("❌ Usuário não encontrado.")

    # --- FLUXO: ESQUECI A SENHA ---
    st.divider()
    if st.button("Esqueci minha senha"):
        st.session_state.modo_recuperacao = True

    if st.session_state.get("modo_recuperacao"):
        login_rec = st.text_input("Digite seu login para recuperação:").strip().lower()
        dados_gerais = carregar_usuarios()
        
        if login_rec in dados_gerais:
            user_info = dados_gerais[login_rec]
            email_cadastrado = user_info.get("email", "")
            
            # Máscara para privacidade (ex: j***@mv.com.br)
            if "@" in email_cadastrado:
                prefixo, dominio = email_cadastrado.split("@")
                email_mascarado = f"{prefixo[0]}***@{dominio}"
                st.write(f"E-mail vinculado: **{email_mascarado}**")
            
            email_input = st.text_input("Confirme o e-mail cadastrado:")
            
            if st.button("Enviar E-mail de Recuperação"):
                if email_input.strip().lower() == email_cadastrado.lower():
                    senha_temp = str(random.randint(100000, 999999))
                    
                    # Usa a função existente em usuarios.py
                    if usuarios.enviar_email_senha(email_cadastrado, senha_temp, user_info["nome"]):
                        # Atualiza com HASH da senha e flag de reset
                        dados_gerais[login_rec].update({
                            "senha_hash": hashlib.sha256(senha_temp.encode()).hexdigest(),
                            "requer_reset": "sim"
                        })
                        usuarios.salvar_usuarios({"usuario": dados_gerais})
                        st.success("E-mail enviado! Verifique sua caixa de entrada.")
                        st.session_state.modo_recuperacao = False
                        st.rerun()
                else:
                    st.error("❌ O e-mail informado não confere com o registrado.")
        elif login_rec:
            st.error("❌ Usuário não encontrado.")

def processar_troca_senha(login, nova_senha):
    caminho = os.path.join(os.path.dirname(__file__), "users.toml")
    config = toml.load(caminho)
    config["usuario"][login]["senha_hash"] = hashlib.sha256(nova_senha.strip().encode('utf-8')).hexdigest()
    config["usuario"][login]["requer_reset"] = "nao"
    with open(caminho, "w") as f:
        toml.dump(config, f)
    return True

