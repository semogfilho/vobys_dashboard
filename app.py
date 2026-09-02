# -*- coding: utf-8 -*-
# 1. Page Config deve ser a PRIMEIRA coisa
import streamlit as st
st.set_page_config(page_title="FOLHA - Operacao NTGD", layout="wide")

# 2. Importações e Inicializações
import os, sys, datetime, oracledb, json, importlib
import streamlit.components.v1 as components

# 1. INICIALIZAÇÃO OBRIGATÓRIA E IMEDIATA
def inicializar_estado():
    defaults = {
        "menu_atual": "Inicio",
        "autenticado": False,
        "log_registrado": False,
        "login_atual": None,
        "perfil_usuario": None,
        "sub_menu_auditoria": "Consistência Folha"
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

inicializar_estado()


def capturar_ip_cliente():
    if "ip_cliente" not in st.session_state:
        js_code = """
        <script>
            fetch('https://api.ipify.org?format=json')
            .then(response => response.json())
            .then(data => {
                window.parent.postMessage({type: 'streamlit:setComponentValue', value: data.ip}, '*');
            });
        </script>
        """
        valor = components.html(js_code, height=0)
        return valor
    return st.session_state["ip_cliente"]

# --- CONFIGURAÇÃO DE CAMINHOS ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE_DIR, "views"))
sys.path.insert(0, os.path.join(BASE_DIR, ".streamlit"))

import auth_ui, inicio, grafico, app_siafe, responsavel, arquivos, usuarios, auditoria_integracao, auditoria_folha, valida_bb, inconsistencia_sefaz_view, consulta_credor_view, extra

def reload_views():
    importlib.reload(auth_ui)
    importlib.reload(inicio)
    importlib.reload(grafico)
    importlib.reload(app_siafe)
    importlib.reload(responsavel)
    importlib.reload(arquivos)
    importlib.reload(usuarios)
    importlib.reload(auditoria_integracao)
    importlib.reload(auditoria_folha)
    importlib.reload(valida_bb)
    importlib.reload(inconsistencia_sefaz_view)
    importlib.reload(consulta_credor_view)
    importlib.reload(extra)

reload_views()


# 5. Validação final de menu
def get_opcoes():
  opcoes_base = [
      "Inicio",
      "Grafico",
      "Pagto Pendente",
      "Responsavel",
      "Arquivos/ID",
      "Auditoria",
      "Auditoria Folha",
      "Consulta Credor SEFAZ",
      "Relatório de Inconsistências SEFAZ",
  ]

  if st.session_state.get("perfil_usuario") in ["a", "g", "c"]:
    opcoes_base.append("Usuários")

  # --- RESTRIÇÃO DA OPÇÃO EXTRA ---
  # Liberado para o Valdiano (por login) ou para qualquer Admin (perfil 'a')
  login_bruto = st.session_state.get("login_atual")
  login_atual = str(login_bruto).lower() if login_bruto else ""

  if (
      login_atual == "valdiano"
      or st.session_state.get("perfil_usuario") == "a"
  ):
    opcoes_base.append("Extra")

  return opcoes_base


def restaurar_sessao():
    params = st.query_params
    token_url = params.get("s")
    if token_url:
        dados = auth_ui.decodificar_sessao(token_url)
        if dados and len(dados) == 3:
            nome, perfil, login = dados

            if st.session_state.get("login_atual") != login:
                st.session_state.autenticado = True
                st.session_state.nome_usuario = nome
                st.session_state.perfil_usuario = perfil
                st.session_state.login_atual = login
                st.session_state.menu_atual = "Inicio"
                return True
            return True
    return False

restaurar_sessao()

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

if not st.session_state.get("autenticado", False):
    with st.sidebar:
        auth_ui.gerenciar_sessao_fluxo()
    st.markdown("<h3 style='color: #666; font-weight: normal; margin-top: 5rem; text-align: center;'>🔒 Aguardando identificação...</h3>", unsafe_allow_html=True)
    st.stop()

if "perfil_usuario" in st.session_state:
    os.environ["CURRENT_USER_PROFILE"] = st.session_state.perfil_usuario

with st.sidebar:
    st.markdown("""
        <style>
            [data-testid="stSidebar"] > div:first-child {
                padding-top: 0.5rem !important;
            }
            .titulo-ntgd {
                font-size: 2rem !important;
                margin-top: -1.5rem !important;
                margin-bottom: -0.5rem !important;
            }
            div[data-testid="stMarkdown"] hr {
                margin-top: 0.5rem !important;
                margin-bottom: 0.5rem !important;
            }
        </style>
    """, unsafe_allow_html=True)

    st.markdown("<h1 class='titulo-ntgd' style='text-align: center; color: #d32f2f;'>NTGD</h1>", unsafe_allow_html=True)
    st.divider()

    st.markdown(f"### 👤 {st.session_state.get('nome_usuario', 'Usuário')}")
    hoje = datetime.date.today()

    if hoje.day >= 21:
        if hoje.month == 12:
            mes_sugerido, ano_sugerido = 1, hoje.year + 1
        else:
            mes_sugerido, ano_sugerido = hoje.month + 1, hoje.year
    else:
        mes_sugerido, ano_sugerido = hoje.month, hoje.year

    lista_anos = [2026, 2025, 2024, 2023]
    if ano_sugerido not in lista_anos: lista_anos.insert(0, ano_sugerido)
    ano = st.selectbox("Ano:", lista_anos, index=lista_anos.index(ano_sugerido))
    meses_lista = {1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun", 7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez", 13: "13º"}
    mes = st.selectbox("Mês:", list(meses_lista.keys()), index=mes_sugerido - 1, format_func=lambda x: meses_lista[x])

    opcoes = get_opcoes()
    if st.session_state.menu_atual not in opcoes: st.session_state.menu_atual = "Inicio"
    menu = st.radio("Menu:", opcoes, index=opcoes.index(st.session_state.menu_atual), key="menu_principal")
    st.session_state.menu_atual = menu

    if st.session_state.menu_atual == "Auditoria Folha":
        with st.container(border=True):
            st.caption("Subopções de Auditoria:")
            st.radio(
                "Selecione a Auditoria:",
                [
                   "Consistência Folha",
                   "Dados Bancários",
                   "Auditoria de Integridade"
                ],
                index=["Consistência Folha", "Dados Bancários", "Auditoria de Integridade"].index(st.session_state.sub_menu_auditoria),
                label_visibility="collapsed",
                key="sub_menu_auditoria"
            )

    st.markdown('<div class="botao-sair-container">', unsafe_allow_html=True)
    if st.button("Sair"):
        for key in list(st.session_state.keys()): del st.session_state[key]
        st.query_params.clear()
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

try:
    db = st.secrets["database"]
    conn = oracledb.connect(user=db["db_user"], password=db["db_pass"], dsn=db["db_dsn"])

    if st.session_state.get("autenticado") and not st.session_state.get("log_registrado"):
        login_usuario = st.session_state.get("login_atual")
        if login_usuario:
            usuarios.registrar_log_acesso(conn, login_usuario, "10.0.52.171")
            st.session_state["log_registrado"] = True

    menu_selecionado = st.session_state.menu_atual

    if menu_selecionado == "Inicio": inicio.render(conn, ano, mes, meses_lista)
    elif menu_selecionado == "Grafico": grafico.render(conn, ano, mes, meses_lista)
    elif menu_selecionado == "Pagto Pendente": app_siafe.main(conn, ano, mes, meses_lista, st.session_state.perfil_usuario)
    elif menu_selecionado == "Responsavel": responsavel.render(conn, ano, mes, meses_lista)
    elif menu_selecionado == "Arquivos/ID": arquivos.render(conn, ano, mes, meses_lista)
    elif menu_selecionado == "Auditoria": auditoria_integracao.render(conn, ano, mes)
    elif menu_selecionado == "Auditoria Folha": auditoria_folha.render(conn, ano, mes, st.session_state.sub_menu_auditoria)
    elif menu_selecionado == "Usuários": usuarios.render(conn, st.session_state.perfil_usuario)
    elif menu_selecionado == "Relatório de Inconsistências SEFAZ": inconsistencia_sefaz_view.renderizar_inconsistencia_sefaz(ano, mes, auth_ui)
    elif menu_selecionado == "Consulta Credor SEFAZ": consulta_credor_view.renderizar_consulta_credor(ano, mes)
    elif menu_selecionado == "Extra": extra.render(conn)
    elif menu_selecionado == "Validação BB":
       if st.session_state.perfil_usuario == 'a': valida_bb.render(conn)
       else:
            st.error("Acesso negado.")

    conn.close()
except Exception as e:
    st.error("Erro na renderização: " + str(e))

