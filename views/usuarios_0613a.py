# -*- coding: utf-8 -*-
import streamlit as st
import os
import toml
import hashlib

# Garante o caminho exato para encontrar o arquivo de usuários
CAMINHO_ATUAL = os.path.dirname(__file__)
if CAMINHO_ATUAL.endswith(".streamlit") or CAMINHO_ATUAL.endswith("views"):
    CAMINHO_USERS_TOML = os.path.abspath(os.path.join(CAMINHO_ATUAL, "..", ".streamlit", "users.toml"))
else:
    CAMINHO_USERS_TOML = os.path.abspath(os.path.join(CAMINHO_ATUAL, ".streamlit", "users.toml"))

def carregar_usuarios():
    if not os.path.exists(CAMINHO_USERS_TOML):
        return {"usuario": {}}
    return toml.load(CAMINHO_USERS_TOML)

def salvar_usuarios(dados):
    with open(CAMINHO_USERS_TOML, "w", encoding="utf-8") as f:
        toml.dump(dados, f)

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
            
            col1, col2, col3 = st.columns([3, 2, 2])
            
            with col1:
                if esta_resetado:
                    st.write(f"👤 **{nome_user}** ({login}) 🔴 *(Senha Resetada)*")
                else:
                    st.write(f"👤 **{nome_user}** ({login})")
                    
            with col2:
                label_perfil = "Administrador" if tipo_user == "a" else "Gerente" if tipo_user == "g" else "Comum"
                st.write(f"Perfil: *{label_perfil}*")
                
            with col3:
                if perfil_logado == "g" and tipo_user == "a":
                    st.markdown("<span style='color: #666; font-style: italic;'>🔒 Acesso Restrito</span>", unsafe_allow_html=True)
                else:
                    if esta_resetado:
                        st.button("Reset já Solicitado", key=f"btn_rst_{login}", disabled=True, width='stretch')
                    else:
                        # Popover simplificado: foco total na confirmação
                        with st.popover("Forçar Reset Senha", width='stretch'):
                            st.write(f"Confirmar reset de senha para **{nome_user}**?")
                            if st.button("Confirmar Reset", key=f"conf_rst_{login}", type="primary", width='stretch'):
                                dados_toml["usuario"][login]["requer_reset"] = "sim"
                                senha_padrao = "sead@ntgd"
                                senha_padrao_hash = hashlib.sha256(senha_padrao.strip().encode('utf-8')).hexdigest()
                                dados_toml["usuario"][login]["senha_hash"] = senha_padrao_hash
                                
                                salvar_usuarios(dados_toml)
                                st.session_state.msg_sucesso_reset = f"Sucesso! Senha provisória: `{senha_padrao}`"
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



