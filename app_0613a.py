# -*- coding: utf-8 -*-
import os, sys, datetime, streamlit as st, oracledb

# --- CONFIGURAÇÃO DE CAMINHOS ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE_DIR, "views"))
sys.path.insert(0, os.path.join(BASE_DIR, ".streamlit"))

# Importação com a view de auditoria
import auth_ui, inicio, grafico, app_siafe, responsavel, arquivos, usuarios, auditoria_integracao, auditoria_folha

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
        st.stop()

# --- 3. TRAVA DE LOGIN ---
if not st.session_state.get("autenticado", False):
    with st.sidebar:
        auth_ui.gerenciar_sessao_fluxo()
    st.markdown("<h3 style='color: #666; font-weight: normal; margin-top: 5rem; text-align: center;'>🔒 Aguardando identificação no menu lateral...</h3>", unsafe_allow_html=True)
    st.stop()

# --- 4. SIDEBAR E MENU ---
with st.sidebar:
    st.markdown("### " + st.session_state.get("nome_usuario", ""))
    
    # Lógica para definir o mês sugerido
    hoje = datetime.date.today()
    # Lógica para definir mês e ano padrão
    if hoje.day <= 12:
        if hoje.month == 1:
            mes_sugerido = 12
            ano_sugerido = hoje.year - 1
        else:
            mes_sugerido = hoje.month - 1
            ano_sugerido = hoje.year
    else:
        mes_sugerido = hoje.month
        ano_sugerido = hoje.year

    # Ajuste do Selectbox do Ano
    # Garantindo que o ano anterior esteja disponível na lista caso necessário
    lista_anos = [2026, 2025, 2024, 2023]
    if ano_sugerido not in lista_anos:
        lista_anos.insert(0, ano_sugerido)
        
    ano = st.selectbox("Ano:", lista_anos, index=lista_anos.index(ano_sugerido))

    meses_lista = {1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun", 
                   7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez"}
    mes = st.selectbox("Mês:", list(meses_lista.keys()), index=mes_sugerido - 1, format_func=lambda x: meses_lista[x])
    
    #opcoes = ["Inicio", "Grafico", "Pagto Pendente", "Responsavel", "Arquivos/ID", "Auditoria"]
    opcoes = ["Inicio", "Grafico", "Pagto Pendente", "Responsavel", "Arquivos/ID", "Auditoria", "Auditoria Folha"]
    if st.session_state.get("perfil_usuario") in ['a', 'g']: opcoes.append("Usuários")

    #menu = st.radio("Menu:", opcoes)
    menu = st.sidebar.radio("Menu:", opcoes)
    
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
    elif menu == "Pagto Pendente": app_siafe.main(conn, ano, mes, meses_lista)
    elif menu == "Responsavel": responsavel.render(conn, ano, mes, meses_lista)
    elif menu == "Arquivos/ID": arquivos.render(conn, ano, mes, meses_lista)
    elif menu == "Auditoria": auditoria_integracao.render(conn, ano, mes) # Chamada corrigida
    elif menu == "Auditoria Folha": auditoria_folha.render(conn, ano, mes) # Chamada corrigida
    elif menu == "Usuários": usuarios.render(conn, st.session_state.perfil_usuario)
    
    conn.close()
except Exception as e:
    st.error("Erro na renderização: " + str(e))

