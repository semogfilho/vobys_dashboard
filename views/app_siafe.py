# -*- coding: utf-8 -*-
import streamlit as st
import requests
import urllib3
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from queries import GET_SIGLAS_EMPRESA

# Desabilita avisos de SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

MAPA_MESES_ROBUSTO = {
    "Jan": "01", "Fev": "02", "Mar": "03", "Abr": "04", "Mai": "05", "Jun": "06",
    "Jul": "07", "Ago": "08", "Set": "09", "Out": "10", "Nov": "11", "Dez": "12",
    1: "01", 2: "02", 3: "03", 4: "04", 5: "05", 6: "06",
    7: "07", 8: "08", 9: "09", 10: "10", 11: "11", 12: "12",
    "1": "01", "2": "02", "3": "03", "4": "04", "5": "05", "6": "06",
    "7": "07", "8": "08", "9": "09", "10": "10", "11": "11", "12": "12"
}

@st.cache_data
def carregar_siglas(_conn):
    return pd.read_sql(GET_SIGLAS_EMPRESA, _conn)

def formatar_moeda_br(valor):
    try:
        return f"R$ {float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return valor

@st.cache_data(show_spinner="Sincronizando com a API...")
def buscar_dados_siafe(ano, perfil_usuario):
    usuario = st.session_state.get("sefaz_cpf", st.secrets["sefaz"]["SIAFE_CPF"])
    senha = st.session_state.get("sefaz_pass", st.secrets["sefaz"]["SIAFE_SENHA"])
    BASE_URL = st.secrets["sefaz"]["BASE_URL"]

    try:
        session = requests.Session()
        session.verify = False
        session.headers.update({"Content-Type": "application/json"})

        payload_auth = {"usuario": usuario, "senha": senha}
        r_auth = session.post(f"{BASE_URL}/auth", json=payload_auth, timeout=10)
        r_auth.raise_for_status()

        token = r_auth.json().get("token")
        session.headers.update({"Authorization": f"Bearer {token}"})

        r = session.post(f"{BASE_URL}/folha-pagamento/pendente/{ano}", json={}, timeout=15)
        r.raise_for_status()

        data = r.json()
        if not data:
            return pd.DataFrame()

        df = pd.DataFrame(data)
        df_explode = df.explode('itens').reset_index(drop=True)
        itens_norm = pd.json_normalize(df_explode['itens']).add_prefix('item_')
        df_final = pd.concat([df_explode.drop(columns=['itens']), itens_norm], axis=1)

        return df_final.rename(columns={'codigoUgSistemaExterno': 'Cod_Sefaz'})

    except Exception as e:
        eh_admin = perfil_usuario in ['a', 'g']
        if eh_admin:
            st.error(f"⚠️ Erro na API SIAFE: {e}")
        else:
            st.warning("⚠️ O serviço de integração SIAFE está temporariamente indisponível. Por favor, contate o suporte técnico.")
        return pd.DataFrame()

def main(conn, ano_selecionado, mes_chave, meses_lista, perfil_usuario):
    # CSS Customizado para estilização corporativa moderna
    st.markdown("""
        <style>
            .stApp {
                background-color: #f8fafc;
            }
            [data-testid="column"] { 
                display: flex; 
                flex-direction: column; 
                align-items: flex-start !important; 
            }
            div[data-testid="stHorizontalBlock"] { 
                align-items: flex-start !important; 
            }
            div[data-testid="stDataFrame"] { 
                margin-top: 0px !important;
                border-radius: 8px;
                box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.1);
            }
            .metric-card {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                padding: 16px 20px;
                border-radius: 10px;
                box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
                margin-bottom: 1rem;
            }
            .metric-title {
                font-size: 0.85rem;
                color: #64748b;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.05em;
            }
            .metric-value {
                font-size: 1.5rem;
                color: #0f172a;
                font-weight: 700;
                margin-top: 4px;
            }
        </style>
    """, unsafe_allow_html=True)

    mes_num_str = MAPA_MESES_ROBUSTO.get(mes_chave, "01")
    competencia_busca = f"{mes_num_str}/{ano_selecionado}"

    st.title(f"📊 Painel de Pagamentos Pendentes ({competencia_busca})")
    st.markdown("---")

    df_total = buscar_dados_siafe(ano_selecionado, perfil_usuario)
    if df_total.empty:
        st.warning("Nenhum dado encontrado.")
        return

    df_total['categoria'] = df_total['Cod_Sefaz'].apply(lambda x: "FOLHA" if str(x).isdigit() and int(x) <= 999 else "PPF")
    
    # Seletor com visual mais integrado
    cat_selecionada = st.radio("Selecione a Categoria:", ["FOLHA", "PPF"], horizontal=True)
    st.markdown("<div style='margin-bottom: 15px;'></div>", unsafe_allow_html=True)

    df_mes = df_total[(df_total['competencia'].astype(str) == competencia_busca) & (df_total['categoria'] == cat_selecionada)].copy()

    col_esq, col_dir = st.columns([1, 4])

    with col_esq:
        st.subheader(f"Unidades Gestoras ({cat_selecionada})")
        resumo = df_mes.groupby(['Cod_Sefaz', 'codigoUg']).agg(
            QTD=('codigoUg', 'size'),
            VALOR_BRUTO=('item_valorBruto', 'sum')
        ).reset_index()

        df_siglas = carregar_siglas(conn)
        df_siglas.columns = ['Cod_Sefaz', 'Sigla']

        resumo['Cod_Sefaz'] = resumo['Cod_Sefaz'].astype(str)
        df_siglas['Cod_Sefaz'] = df_siglas['Cod_Sefaz'].astype(str)

        resumo = resumo.merge(df_siglas, on='Cod_Sefaz', how='left')
        resumo['Sigla'] = resumo['Sigla'].fillna("N/D")

        resumo = resumo[['Cod_Sefaz', 'Sigla', 'codigoUg', 'QTD', 'VALOR_BRUTO']]

        linha_total = pd.DataFrame({
            'Cod_Sefaz': ['TOTAL'], 'Sigla': [''], 'codigoUg': [''],
            'QTD': [resumo['QTD'].sum()], 'VALOR_BRUTO': [resumo['VALOR_BRUTO'].sum()]
        })

        df_display = pd.concat([resumo, linha_total], ignore_index=True)

        evento = st.dataframe(
            df_display, use_container_width=True, hide_index=True,
            selection_mode="multi-row", on_select="rerun",
            column_config={
                "QTD": st.column_config.NumberColumn("QTD", format="%d"),
                "VALOR_BRUTO": st.column_config.NumberColumn("VALOR BRUTO", format="R$ %.2f")
            }
        )

        selected_rows = evento.selection.rows
        indices_validos = [i for i in selected_rows if i < len(resumo)]
        modo_filtro = "TOTAL" if (not selected_rows or len(resumo) in selected_rows) else "UNIDADE"

        if modo_filtro == "UNIDADE":
            sel_data = resumo.iloc[indices_validos]
            listas_sefaz = sel_data['Cod_Sefaz'].astype(str).tolist()
            listas_ug = sel_data['codigoUg'].astype(str).tolist()
        else:
            listas_sefaz = resumo['Cod_Sefaz'].astype(str).tolist()
            listas_ug = resumo['codigoUg'].astype(str).tolist()

    with col_dir:
        st.subheader(f"Detalhes - {modo_filtro}")
        detalhes = df_mes[df_mes.apply(lambda x: (str(x['Cod_Sefaz']), str(x['codigoUg']))
                                    in zip(listas_sefaz, listas_ug), axis=1)].copy() if modo_filtro == "UNIDADE" else df_mes.copy()

        detalhes['Cod_Sefaz'] = detalhes['Cod_Sefaz'].astype(str)
        df_siglas['Cod_Sefaz'] = df_siglas['Cod_Sefaz'].astype(str)
        detalhes = detalhes.merge(df_siglas, on='Cod_Sefaz', how='left')
        detalhes['Sigla'] = detalhes['Sigla'].fillna("N/D")

        # Cartões de Métricas Estilizados (Substituindo o .metric() simples por HTML customizado)
        m1, m2, m3 = st.columns(3)
        
        with m1:
            st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-title">Registros</div>
                    <div class="metric-value">{len(detalhes):,}</div>
                </div>
            """, unsafe_allow_html=True)
            
        with m2:
            st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-title">Total Bruto</div>
                    <div class="metric-value">{formatar_moeda_br(detalhes['item_valorBruto'].sum())}</div>
                </div>
            """, unsafe_allow_html=True)
            
        with m3:
            st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-title">Total Líquido</div>
                    <div class="metric-value">{formatar_moeda_br(detalhes['item_valorLiquido'].sum())}</div>
                </div>
            """, unsafe_allow_html=True)

        df_exibicao = detalhes.copy()
        
        cols = ['codigo', 'codigoExterno', 'Cod_Sefaz', 'Sigla', 'tipoProcessamento', 'item_nome', 'item_matricula',
                'item_dataPagamento', 'item_descricaoStatusPgto', 'item_valorBruto', 'item_valorLiquido']

        st.dataframe(
            df_exibicao[[c for c in cols if c in df_exibicao.columns]],
            use_container_width=True,
            hide_index=True,
            column_config={
                "Cod_Sefaz": st.column_config.TextColumn("Cod SEFAZ"),
                "Sigla": st.column_config.TextColumn("Órgão / Sigla"),
                "item_valorBruto": st.column_config.NumberColumn("Valor Bruto", format="R$ %.2f"),
                "item_valorLiquido": st.column_config.NumberColumn("Valor Líquido", format="R$ %.2f")
            }
        )

