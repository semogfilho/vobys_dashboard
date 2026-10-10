# -*- coding: utf-8 -*-
import datetime
import importlib
import os
import sys
import pandas as pd
import streamlit as st

# Garante que a pasta views e a .streamlit estão no path para importações
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE_DIR, "views"))
sys.path.insert(0, os.path.join(BASE_DIR, ".streamlit"))

import auth_ui

# 1. Configuração inicial do estado de autenticação
if "autenticado" not in st.session_state:
    st.session_state["autenticado"] = False

if "sub_menu_auditoria" not in st.session_state:
    st.session_state["sub_menu_auditoria"] = "Consistência Folha"

# 2. Se NÃO estiver autenticado, exibe a tela de login
if not st.session_state.get("autenticado", False):
    st.markdown("""
        <style>
            [data-testid="stSidebar"] { display: none !important; }
            [data-testid="collapsedControl"] { display: none !important; }
            .stApp { background-color: #f1f5f9 !important; }
            .main .block-container, 
            [data-testid="stMainBlockContainer"],
            [data-testid="stAppViewBlockContainer"] {
                max-width: 380px !important;
                margin: 0 auto !important;
                padding-top: 4rem !important;
                padding-bottom: 2rem !important;
                padding-left: 1rem !important;
                padding-right: 1rem !important;
            }
            div[data-testid="stVerticalBlockBorderWrapper"] {
                background-color: #f0f4f8 !important;
                border: 1px solid #cbd5e1 !important;
                border-radius: 14px !important;
                box-shadow: 0 10px 20px rgba(0, 0, 0, 0.05) !important;
                padding: 1.2rem 1rem !important;
            }
            div[data-testid="stVerticalBlockBorderWrapper"] p,
            div[data-testid="stVerticalBlockBorderWrapper"] label,
            div[data-testid="stVerticalBlockBorderWrapper"] span {
                color: #334155 !important;
            }
            div[data-testid="stVerticalBlockBorderWrapper"] h1,
            div[data-testid="stVerticalBlockBorderWrapper"] h2,
            div[data-testid="stVerticalBlockBorderWrapper"] h3 {
                color: #d32f2f !important;
            }
            div[data-testid="stVerticalBlock"] {
                gap: 0.5rem !important;
            }
            .stTextInput > div > div > input {
                border-radius: 6px !important;
                border: 1px solid #cbd5e1 !important;
                padding: 8px 10px !important;
                background-color: #ffffff !important;
                color: #0f172a !important;
                font-size: 0.88rem !important;
            }
            div.stButton > button {
                width: 100% !important;
                border-radius: 6px !important;
                font-size: 0.9rem !important;
                padding: 0.45rem !important;
            }
            div.stButton > button:first-of-type {
                background-color: #d32f2f !important;
                border: none !important;
                box-shadow: 0 4px 10px rgba(211, 47, 47, 0.25) !important;
            }
            div.stButton > button:first-of-type * {
                color: #ffffff !important;
                font-weight: 600 !important;
            }
            div.stButton > button:first-of-type:hover {
                background-color: #b71c1c !important;
            }
        </style>
    """, unsafe_allow_html=True)

    st.markdown(
        "<div style='text-align: center; color: #64748b; font-size: 0.82rem; font-weight: 600; margin-bottom: 0.5rem; letter-spacing: 0.5px;'>"
        "🔒 SISTEMA NTGD"
        "</div>",
        unsafe_allow_html=True
    )

    _, col_center, _ = st.columns([0.01, 0.98, 0.01])
    with col_center:
        with st.container(border=True):
            auth_ui.gerenciar_sessao_fluxo()

    st.stop()

# ==============================================================================
# CONFIGURAÇÃO DA PÁGINA APÓS A AUTENTICAÇÃO
# ==============================================================================
st.set_page_config(
    page_title="NTGD - Gestão Dinâmica",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------
# CONEXÃO COM O BANCO DE DADOS ORACLE
# ---------------------------------------------------------
try:
    from database import get_connection
except ImportError:
    def get_connection():
        return None

def obter_conexao():
    try:
        return get_connection()
    except Exception:
        return None

def obter_usuario_logado():
    nome = st.session_state.get("nome_usuario", "Usuário")
    login = st.session_state.get("login_atual", "jose.gomes")
    perfil = st.session_state.get("perfil_usuario", "a")
    
    perfis_nomes = {
        "1": "Administrador", "a": "Administrador",
        "2": "Gerente", "g": "Gerente",
        "3": "Consulta", "c": "Consulta",
        "4": "Supervisor", "s": "Supervisor",
        "comum": "Comum"
    }
    perfil_nome = perfis_nomes.get(str(perfil).lower(), "Administrador")
    
    return {
        "usuario": login,
        "nome": nome,
        "perfil_id": perfil,
        "perfil_nome": perfil_nome
    }

def carregar_modulos_do_banco(perfil_id, login_usuario=""):
    conn = obter_conexao()
    if not conn:
        return []

    p_str = str(perfil_id).lower()
    try:
        cursor = conn.cursor()
        
        # Se for admin master ou perfil 'a'/'1', traz todos os módulos ativos
        if p_str in ["a", "administrador", "1", "jose.gomes"] or login_usuario == "jose.gomes":
            sql_simples = """
                SELECT DISTINCT m.id, m.nome_menu, m.arquivo_view, m.icone, m.ordem
                FROM josegomes.modulo m
                WHERE m.ativo = 1
                ORDER BY m.ordem ASC
            """
            df = pd.read_sql(sql_simples, conn)
        else:
            # Consulta robusta que busca perfis vinculados na tabela perfil_modulo considerando id ou descrição
            query = """
                SELECT DISTINCT m.id, m.nome_menu, m.arquivo_view, m.icone, m.ordem
                FROM josegomes.modulo m
                INNER JOIN josegomes.perfil_modulo pm ON m.id = pm.id_modulo
                INNER JOIN josegomes.perfil p ON pm.id_perfil = p.id
                WHERE (LOWER(p.descricao) LIKE '%' || :p1 || '%' OR TO_CHAR(p.id) = :p2) AND m.ativo = 1
                ORDER BY m.ordem ASC
            """
            df = pd.read_sql(query, conn, params={"p1": p_str, "p2": p_str})
            
            # Se ainda vier vazio, busca diretamente pelo id_perfil cru da sessão na tabela perfil_modulo
            if df.empty:
                query_alt = """
                    SELECT DISTINCT m.id, m.nome_menu, m.arquivo_view, m.icone, m.ordem
                    FROM josegomes.modulo m
                    INNER JOIN josegomes.perfil_modulo pm ON m.id = pm.id_modulo
                    WHERE pm.id_perfil = :p1 AND m.ativo = 1
                    ORDER BY m.ordem ASC
                """
                df = pd.read_sql(query_alt, conn, params={"p1": str(perfil_id)})

        conn.close()
        return df.to_dict('records')
    except Exception as e:
        if conn:
            conn.close()
        return []

# ---------------------------------------------------------
# FLUXO PRINCIPAL DO APP MENU
# ---------------------------------------------------------
def main():
    usuario_atual = obter_usuario_logado()

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
                .botao-sair-container {
                    margin-top: 0.5rem !important;
                }
                /* Botão Sair compacto, alinhado e com cantos sutis */
                [data-testid="stSidebar"] div.stButton > button {
                    background-color: transparent !important;
                    border: 1px solid rgba(49, 51, 63, 0.2) !important;
                    color: rgb(49, 51, 63) !important;
                    border-radius: 8px !important;
                    box-shadow: none !important;
                    width: auto !important;
                    padding: 0.35rem 1.25rem !important;
                }
                [data-testid="stSidebar"] div.stButton > button:hover {
                    border-color: rgb(49, 51, 63) !important;
                    color: rgb(49, 51, 63) !important;
                    background-color: rgba(49, 51, 63, 0.02) !important;
                }
            </style>
        """, unsafe_allow_html=True)

        st.markdown("<h1 class='titulo-ntgd' style='text-align: center; color: #d32f2f;'>NTGD</h1>", unsafe_allow_html=True)
        st.divider()

        st.markdown(f"### 👤 {usuario_atual.get('nome', 'Usuário')}")
        
        sefaz_autenticado = st.session_state.get("sefaz_auth", False)
        if sefaz_autenticado:
            st.markdown("🟢 **SEFAZ:** Conectado")
            if st.button("Desconectar SEFAZ", key="btn_desconectar_sefaz"):
                st.session_state["sefaz_auth"] = False
                st.session_state["sefaz_cpf"] = ""
                st.session_state["sefaz_pass"] = ""
                st.rerun()
        else:
            st.markdown("🔴 **SEFAZ:** Desconectado")
        st.divider()

        hoje = datetime.date.today()
        if hoje.day >= 21:
            if hoje.month == 12:
                mes_sugerido, ano_sugerido = 1, hoje.year + 1
            else:
                mes_sugerido, ano_sugerido = hoje.month + 1, hoje.year
        else:
            mes_sugerido, ano_sugerido = hoje.month, hoje.year

        lista_anos = [2026, 2025, 2024, 2023]
        if ano_sugerido not in lista_anos: 
            lista_anos.insert(0, ano_sugerido)
        
        ano = st.selectbox("Ano:", lista_anos, index=lista_anos.index(ano_sugerido))
        meses_lista = {1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun", 7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez", 13: "13º"}
        mes = st.selectbox("Mês:", list(meses_lista.keys()), index=mes_sugerido - 1, format_func=lambda x: meses_lista[x])
        st.divider()

        modulos = carregar_modulos_do_banco(usuario_atual["perfil_id"], usuario_atual["usuario"])
        
        opcoes_menu = {}
        if modulos:
            opcoes_menu = {m["NOME_MENU"] if "NOME_MENU" in m else m["nome_menu"]: m for m in modulos}
            
            if "menu_atual" not in st.session_state or st.session_state.menu_atual not in opcoes_menu:
                st.session_state.menu_atual = list(opcoes_menu.keys())[0]

            escolha_menu = st.sidebar.radio("Menu:", options=list(opcoes_menu.keys()), index=list(opcoes_menu.keys()).index(st.session_state.menu_atual), key="menu_principal")
            st.session_state.menu_atual = escolha_menu

            if "auditoria" in escolha_menu.lower() and "folha" in escolha_menu.lower():
                with st.container(border=True):
                    st.caption("Subopções de Auditoria:")
                    st.radio(
                        "Selecione a Auditoria:",
                        [
                           "Consistência Folha",
                           "Dados Bancários",
                           "Auditoria de Integridade"
                        ],
                        index=["Consistência Folha", "Dados Bancários", "Auditoria de Integridade"].index(st.session_state.get("sub_menu_auditoria", "Consistência Folha")),
                        label_visibility="collapsed",
                        key="sub_menu_auditoria"
                    )
        else:
            st.warning("⚠️ Nenhum módulo liberado para o seu perfil.")
            escolha_menu = None

        st.divider()
        st.markdown('<div class="botao-sair-container">', unsafe_allow_html=True)
        if st.button("Sair"):
            for key in list(st.session_state.keys()): del st.session_state[key]
            st.query_params.clear()
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    if not opcoes_menu or not escolha_menu:
        st.info("Por favor, contate o administrador para associar módulos ao seu perfil de acesso.")
        return

    modulo_selecionado = opcoes_menu[escolha_menu]
    caminho_view = modulo_selecionado.get("ARQUIVO_VIEW") or modulo_selecionado.get("arquivo_view")

    try:
        nome_modulo_import = str(caminho_view).replace("views.", "")
        view_module = importlib.import_module(nome_modulo_import)
        
        if hasattr(view_module, "render"):
            try:
                if "auditoria" in escolha_menu.lower() and "folha" in escolha_menu.lower():
                    view_module.render(obter_conexao(), ano, mes, st.session_state.sub_menu_auditoria)
                else:
                    view_module.render(obter_conexao(), ano, mes, meses_lista)
            except TypeError:
                try:
                    view_module.render(obter_conexao(), ano, mes)
                except TypeError:
                    view_module.render(obter_conexao())
        else:
            st.info(f"Módulo **{escolha_menu}** carregado com sucesso.")
    except Exception as e:
        st.warning(f"Aviso ao carregar o arquivo físico ({caminho_view}): {e}")
        st.info(f"Acessando o módulo: **{escolha_menu}**.")

if __name__ == "__main__":
    main()

