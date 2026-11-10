# -*- coding: utf-8 -*-
import os, sys, datetime, streamlit as st, oracledb

# --- CONFIGURAÇÃO DE CAMINHOS ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE_DIR, "views"))
sys.path.insert(0, os.path.join(BASE_DIR, ".streamlit"))

import auth_ui, inicio, grafico, pagamento, responsavel, arquivos, usuarios

st.set_page_config(page_title="FOLHA - Operacao NTGD", layout="wide")

# --- 1. RESTAURAÇÃO DE SESSÃO ---
def restaurar_sessao():
    if st.session_state.get("autenticado", False): return True
    params = st.query_params
    if "s" in params:
        nome, perfil = auth_ui.decodificar_sessao(params["s"])
        if nome:
            st.session_state.autenticado = True
            st.session_state.nome_usuario = nome
            st.session_state.perfil_usuario = perfil
            st.session_state.login_atual = nome
            return True
    return False

restaurar_sessao()

# --- 2. TRAVA DE RESET DE SENHA ---
if st.session_state.get("autenticado", False):
    usuarios_db = auth_ui.carregar_usuarios()
    login = st.session_state.get("login_atual")
    if login in usuarios_db and usuarios_db[login].get("requer_reset") == "sim":
        with st.sidebar:
            st.warning("⚠️ **Atenção:** Alteração de senha obrigatória.")
            nova = st.text_input("Nova senha:", type="password")
            conf = st.text_input("Confirmar nova senha:", type="password")
            if st.button("Confirmar Alteração"):
                if nova == conf:
                    if auth_ui.processar_troca_senha(login, nova):
                        st.success("Senha atualizada!")
                        st.rerun()
                else:
                    st.error("As senhas não conferem.")
        st.markdown("<h3 style='color: #c62828; font-weight: normal; margin-top: 5rem; text-align: center;'>⚠️ Acesso bloqueado até a troca de senha.</h3>", unsafe_allow_html=True)
        st.stop()

# --- 3. TRAVA DE LOGIN ---
if not st.session_state.get("autenticado", False):
    with st.sidebar:
        auth_ui.gerenciar_sessao_fluxo()
    st.markdown("<h3 style='color: #666; font-weight: normal; margin-top: 5rem; text-align: center;'>🔒 Aguardando identificação no menu lateral...</h3>", unsafe_allow_html=True)
    st.stop()

# --- 4. SIDEBAR E MENU (Com seleção automática) ---
with st.sidebar:
    st.markdown("### " + st.session_state.get("nome_usuario", ""))
    
    # Datas Correntes
    hoje = datetime.date.today()
    ano = st.selectbox("Ano:", [2026, 2025], index=0)
    
    meses_lista = {1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun", 
                   7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez"}
    mes = st.selectbox("Mês:", list(meses_lista.keys()), index=hoje.month - 1, format_func=lambda x: meses_lista[x])
    
    opcoes = ["Inicio", "Grafico", "Pagamento", "Responsavel", "Arquivos/ID"]
    if st.session_state.get("perfil_usuario") in ['a', 'g']: opcoes.append("Usuários")
    menu = st.radio("Menu:", opcoes)
    
    if st.button("Sair"):
        st.session_state.clear()
        st.query_params.clear()
        st.rerun()

# --- 5. RENDERIZAÇÃO ---
try:
    db = st.secrets["database"]
    conn = oracledb.connect(user=db["db_user"], password=db["db_pass"], dsn=db["db_dsn"])
    
    if menu == "Inicio": inicio.render(conn, ano, mes, meses_lista)
    elif menu == "Grafico": grafico.render(conn, ano, mes, meses_lista)
    elif menu == "Pagamento": pagamento.render(ano, mes)
    elif menu == "Responsavel": responsavel.render(conn, ano, mes, meses_lista)
    elif menu == "Arquivos/ID": arquivos.render(conn, ano, mes, meses_lista)
    elif menu == "Usuários": usuarios.render(conn, st.session_state.perfil_usuario)
    
    conn.close()
except Exception as e:
    st.error("Erro na renderização: " + str(e))

