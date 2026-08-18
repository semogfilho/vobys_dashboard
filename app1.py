# -*- coding: utf-8 -*-
import streamlit as st
import oracledb

# Adicionada a importação do novo módulo arquivos
from views import inicio, grafico, pagamento, responsavel, arquivos

st.set_page_config(page_title="FOLHA - Operacao NTGD", layout="wide")

st.markdown("""
    <style>
        .block-container {
            padding-top: 3.5rem !important;
            padding-bottom: 1rem !important;
            padding-left: 2rem !important;
            padding-right: 2rem !important;
            margin-top: 0rem !important;
        }

        h1 {
            margin-top: 2rem !important;
            padding-top: 0rem !important;
            font-size: 36px !important;
            margin-bottom: 1.5rem !important;
        }

        .stTable, table, data-testid="stTable" {
            width: 100% !important;
            margin-bottom: 0rem !important;
        }

        div[data-testid="stTable"] table tbody tr td,
        div[data-testid="stTable"] td,
        .stTable td, 
        table td {
            font-size: 20px !important;
            font-weight: bold !important;
            line-height: 22px !important;
            padding-top: 2px !important;
            padding-bottom: 2px !important;
            height: 26px !important;
        }

        div[data-testid="stTable"] table thead tr th,
        div[data-testid="stTable"] th,
        .stTable th,
        table th {
            font-size: 18px !important;
            font-weight: 800 !important;
            line-height: 20px !important;
            padding-top: 4px !important;
            padding-bottom: 4px !important;
            background-color: #f9f9f9 !important;
        }

        div[data-testid="stDataFrame"] div {
            font-size: 20px !important;
        }

        section[data-testid="stSidebar"] div.st-emotion-cache-6qobrx {
            padding-top: 2rem !important;
            padding-left: 1rem !important;
            padding-right: 1rem !important;
        }

        div.stPlotlyChart {
            margin-top: 2rem !important;
            margin-left: auto;
            margin-right: auto;
            width: 100% !important;
        }

        div[data-testid="stRadio"] label {
            font-size: 20px !important;
        }
    </style>
""", unsafe_allow_html=True)

try:
    DB_USER = st.secrets["db_user"]
    DB_PASS = st.secrets["db_pass"]
    DB_DSN = st.secrets["db_dsn"]
except Exception as e:
    st.error(f"Erro Secrets: {e}")
    st.stop()

with st.sidebar:
    st.markdown("<h2 style='color: #015494; margin-top: -1rem;'>NTGD</h2>", unsafe_allow_html=True)
    st.divider()

    st.write("**Filtros do Periodo**")

    anos_disponiveis = [2024, 2025, 2026, 2027]
    ano_selecionado = st.selectbox("Selecione o Ano:", anos_disponiveis, index=2)

    meses_disponiveis = {
        "01": "Janeiro", "02": "Fevereiro", "03": "Marco", "04": "Abril",
        "05": "Maio", "06": "Junho", "07": "Julho", "08": "Agosto",
        "09": "Setembro", "10": "Outubro", "11": "Novembro", "12": "Dezembro"
    }

    mes_chave = st.selectbox(
        "Selecione o Mes:",
        list(meses_disponiveis.keys()),
        format_func=lambda x: meses_disponiveis[x],
        index=4
    )

    st.divider()
    st.write("**Navegacao**")

    # Incluído 'Arquivos/ID' na lista de opções do menu de navegação
    menu_opcao = st.radio("", ["Inicio", "Grafico", "Pagamento", "Responsavel", "Arquivos/ID"])

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

    # Tratamento da nova rota para acionar o nosso render isolado
    elif menu_opcao == "Arquivos/ID":
        arquivos.render(conn, ano_selecionado, mes_chave, meses_disponiveis)

    conn.close()

except Exception as e:
    st.error(f"Erro operacional: {e}")

st.markdown("---")
st.caption(f"Ambiente: SEADLNX | Versao: 7.3 ({meses_disponiveis[mes_chave]}/{ano_selecionado})")



