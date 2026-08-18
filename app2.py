# -*- coding: utf-8 -*-
import os
import sys
import streamlit as st
import oracledb

# Resolve caminhos internos da pasta oculta .streamlit
PASTA_STREAMLIT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".streamlit"))
if PASTA_STREAMLIT not in sys.path:
    sys.path.append(PASTA_STREAMLIT)

import auth_ui

# FORÇA A BARRA LATERAL A FICAR ABERTA LOGO DE CARA (initial_sidebar_state="expanded")
st.set_page_config(
    page_title="FOLHA - Operacao NTGD", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# =========================================================================
# TRAVA DE SEGURANÇA NA BARRA LATERAL
# =========================================================================
if auth_ui.gerenciar_sessao_fluxo():

    # ------------------------------------------------------------------------------
    # ESTILOS CSS (Só carregam depois do login para manter o layout limpo)
    # ------------------------------------------------------------------------------
    st.markdown("""
        <style>
            .block-container { padding-top: 3.5rem !important; padding-bottom: 1rem !important; padding-left: 2rem !important; padding-right: 2rem !important; }
            h1 { margin-top: 2rem !important; font-size: 36px !important; margin-bottom: 1.5rem !important; }
            .stTable, table, data-testid="stTable" { width: 100% !important; }
            div[data-testid="stTable"] td, .stTable td { font-size: 20px !important; font-weight: bold !important; padding-top: 2px !important; padding-bottom: 2px !important; }
            div[data-testid="stTable"] th, .stTable th { font-size: 18px !important; font-weight: 800 !important; background-color: #f9f9f9 !important; }
            section[data-testid="stSidebar"] div.st-emotion-cache-6qobrx { padding-top: 2rem !important; padding-left: 1rem !important; padding-right: 1rem !important; }
            div[data-testid="stRadio"] label { font-size: 20px !important; }
        </style>
    """, unsafe_allow_html=True)

    # ------------------------------------------------------------------------------
    # CREDENCIAIS DO BANCO DE DADOS
    # ------------------------------------------------------------------------------
    try:
        DB_USER = st.secrets["database"]["db_user"]
        DB_PASS = st.secrets["database"]["db_pass"]
        DB_DSN = st.secrets["database"]["db_dsn"]
    except Exception as e:
        st.error(f"Erro ao carregar credenciais do secrets.toml: {e}")
        st.stop()

    # Importação das views do sistema
    from views import inicio, grafico, pagamento, responsavel, arquivos

    # ------------------------------------------------------------------------------
    # MENU LATERAL DO SISTEMA (Substitui o formulário de login após o acesso)
    # ------------------------------------------------------------------------------
    with st.sidebar:
        st.markdown("<h2 style='color: #015494; margin-top: -1rem;'>NTGD</h2>", unsafe_allow_html=True)
        st.write(f"👤 ` {st.session_state.get('usuario_logado', 'Usuário')} `")
        
        if st.button("Sair (Logout)", use_container_width=True):
            st.session_state.autenticado = False
            st.session_state.usuario_logado = ""
            st.rerun()
            
        st.divider()
        st.write("**Filtros do Periodo**")

        anos_disponiveis = [2024, 2025, 2026, 2027]
        ano_selecionado = st.selectbox("Selecione o Ano:", anos_disponiveis, index=2)

        meses_disponiveis = {
            "01": "Janeiro", "02": "Fevereiro", "03": "Marco", "04": "Abril",
            "05": "Maio", "06": "Junho", "07": "Julho", "08": "Agosto",
            "09": "Setembro", "10": "Outubro", "11": "Novembro", "12": "Dezembro"
        }

        mes_chave = st.selectbox("Selecione o Mes:", list(meses_disponiveis.keys()), format_func=lambda x: meses_disponiveis[x], index=4)

        st.divider()
        st.write("**Navegacao**")
        menu_opcao = st.radio("", ["Inicio", "Grafico", "Pagamento", "Responsavel", "Arquivos/ID"])

    # ------------------------------------------------------------------------------
    # EXECUÇÃO DO BANCO ORACLE
    # ------------------------------------------------------------------------------
    try:
        conn = oracledb.connect(user=DB_USER, password=DB_PASS, dsn=DB_DSN)

        if menu_opcao == "Inicio":
            inicio.render(conn, ano_selecionado, mes_chave, meses_disponiveis)
        elif menu_opcao == "Grafico":
            grafico.render(conn, ano_selecionado, mes_chave, meses_disponiveis)
        elif menu_opcao == "Pagamento":
            pagamento.render(ano_selecionado, mes_chave)
        elif menu_opcao == "Responsavel":
            responsavel.render(conn, ano_selecionado, mes_chave, meses_disponiveis)
        elif menu_opcao == "Arquivos/ID":
            arquivos.render(conn, ano_selecionado, mes_chave, meses_disponiveis)

        conn.close()

    except Exception as e:
        st.error(f"Erro operacional no banco: {e}")

    st.markdown("---")
    st.caption(f"Ambiente: SEADLNX | Versao: 7.3 ({meses_disponiveis[mes_chave]}/{ano_selecionado})")

