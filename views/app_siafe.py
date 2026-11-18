# -*- coding: utf-8 -*-
import streamlit as st
import requests
import urllib3
import pandas as pd
from queries import GET_SIGLAS_EMPRESA
import sefaz_client

# Desabilita avisos de SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

MAPA_MESES_ROBUSTO = {
    1: "01", 2: "02", 3: "03", 4: "04", 5: "05", 6: "06",
    7: "07", 8: "08", 9: "09", 10: "10", 11: "11", 12: "12", 13: "13",
    "1": "01", "2": "02", "3": "03", "4": "04", "5": "05", "6": "06",
    "7": "07", "8": "08", "9": "09", "10": "10", "11": "11", "12": "12", "13": "13",
    "Jan": "01", "Fev": "02", "Mar": "03", "Abr": "04", "Mai": "05", "Jun": "06",
    "Jul": "07", "Ago": "08", "Set": "09", "Out": "10", "Nov": "11", "Dez": "12", "13º": "13"
}

@st.cache_data
def carregar_siglas(_conn):
    try:
        df = pd.read_sql(GET_SIGLAS_EMPRESA, _conn)
        if not df.empty:
            df.columns = [str(c).upper() for c in df.columns]
        return df
    except Exception as e:
        return pd.DataFrame(columns=['COD_SEFAZ', 'SIGLA'])

def formatar_moeda_br(valor):
    try:
        return f"R$ {float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return valor

@st.cache_data(show_spinner="Sincronizando com a API SEFAZ...")
def buscar_dados_siafe(ano):
    try:
        endpoint = f"folha-pagamento/pendente/{ano}"
        data = sefaz_client.requisitar_sefaz("POST", endpoint, payload={})
        
        if not data:
            return pd.DataFrame()

        df = pd.DataFrame(data)
        if df.empty:
            return pd.DataFrame()

        if 'itens' in df.columns:
            df_explode = df.explode('itens').reset_index(drop=True)
            df_explode = df_explode.dropna(subset=['itens'])
            if df_explode.empty:
                return pd.DataFrame()
            itens_norm = pd.json_normalize(df_explode['itens']).add_prefix('item_')
            df_final = pd.concat([df_explode.drop(columns=['itens']).reset_index(drop=True), itens_norm.reset_index(drop=True)], axis=1)
        else:
            df_final = df

        # Normaliza todas as colunas para maiúsculas
        df_final.columns = [str(c).upper() for c in df_final.columns]

        return df_final

    except Exception as e:
        return pd.DataFrame()

def render(conn, ano_selecionado, mes_chave=None, meses_disponiveis=None, **kwargs):
    try:
        st.markdown("""
            <style>
                .stApp { background-color: #f8fafc; }
                .block-container { padding-top: 2rem !important; padding-bottom: 2rem !important; padding-left: 2rem !important; padding-right: 2rem !important; }
                div[data-testid="stDataFrame"] { border-radius: 8px; box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.1); }
                .metric-card { background-color: #ffffff; border: 1px solid #e2e8f0; padding: 10px 14px; border-radius: 8px; box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05); margin-bottom: 0.5rem; }
            </style>
        """, unsafe_allow_html=True)

        st.markdown("## 📊 Painel de Pagamentos Pendentes")
        st.markdown("---")

        # --- LINHA 1 DE FILTROS ---
        col_c1, col_c2, col_c3 = st.columns([2, 2, 2])
        with col_c1:
            meses_opcoes = ["TODOS", 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13]
            default_idx = meses_opcoes.index(mes_chave) if mes_chave in meses_opcoes else 0
            mes_escolhido = st.selectbox("📅 Filtrar Mês:", options=meses_opcoes, index=default_idx)

        with col_c2:
            categorias_opcoes = ["TODAS", "FOLHA", "PPF"]
            cat_escolhida = st.selectbox("📁 Categoria:", options=categorias_opcoes, index=0)

        with col_c3:
            st.markdown("<br>", unsafe_allow_html=True)
            btn_atualizar = st.button("🔄 Recarregar Dados", use_container_width=True)

        # --- LINHA 2 DE FILTROS (Busca por Matrícula, CPF/CNPJ e Nome) ---
        col_b1, col_b2, col_b3 = st.columns(3)
        with col_b1:
            filtro_matricula = st.text_input("🔍 Matrícula:", placeholder="Digite a matrícula...")
        with col_b2:
            filtro_cpf = st.text_input("🔍 CPF / CNPJ:", placeholder="Digite o CPF ou CNPJ...")
        with col_b3:
            filtro_nome = st.text_input("🔍 Nome:", placeholder="Digite parte do nome...")

        if btn_atualizar:
            if "df_siafe_cache" in st.session_state:
                del st.session_state["df_siafe_cache"]
            st.cache_data.clear()
            st.rerun()

        if "df_siafe_cache" not in st.session_state:
            st.session_state["df_siafe_cache"] = buscar_dados_siafe(ano_selecionado)

        df_total = st.session_state.get("df_siafe_cache", pd.DataFrame())

        if df_total.empty:
            st.warning("⚠️ Não foi possível obter dados da API SEFAZ para o exercício selecionado no momento. Verifique a conexão ou tente novamente.")
            return

        # Padroniza coluna de unidade gestora para COD_SEFAZ
        encontrou_ug = False
        for col_cand in ['CODIGOUGSISTEMAEXTERNO', 'CODIGOUG', 'UG', 'ORGAO', 'CODIGO', 'CODIGOEXTERNO']:
            if col_cand in df_total.columns:
                df_total['COD_SEFAZ'] = df_total[col_cand]
                encontrou_ug = True
                break
        if not encontrou_ug and 'COD_SEFAZ' not in df_total.columns:
            df_total['COD_SEFAZ'] = "0"

        df_total['CATEGORIA_CALC'] = df_total['COD_SEFAZ'].apply(lambda x: "FOLHA" if str(x).isdigit() and int(str(x)) <= 999 else "PPF")

        # Mapeia ou unifica o campo de Data de Pagamento
        col_dt_pag = next((c for c in ['ITEM_DATAPAGAMENTO', 'ITEM_DATAPAGAMENT', 'DATAPAGAMENTO', 'DATA_PAGAMENTO'] if c in df_total.columns), None)
        if col_dt_pag:
            df_total['DATA_PAGAMENTO_EXIBE'] = df_total[col_dt_pag]
        else:
            df_total['DATA_PAGAMENTO_EXIBE'] = "N/D"

        # Identifica ou cria coluna de mês/competência
        col_comp = next((c for c in ['COMPETENCIA', 'MES', 'ITEM_MES', 'ITEM_COMPETENCIA'] if c in df_total.columns), None)
        if not col_comp:
            if col_dt_pag:
                df_total['COMPETENCIA_EXIBE'] = df_total[col_dt_pag].astype(str).str[5:7] + '/' + str(ano_selecionado)
            else:
                df_total['COMPETENCIA_EXIBE'] = "N/D"
        else:
            df_total['COMPETENCIA_EXIBE'] = df_total[col_comp]

        df_filtrado = df_total.copy()

        # Aplica filtro de Categoria
        if cat_escolhida != "TODAS":
            df_filtrado = df_filtrado[df_filtrado['CATEGORIA_CALC'] == cat_escolhida]

        # Aplica filtro de Mês
        if mes_escolhido != "TODOS":
            mes_str = MAPA_MESES_ROBUSTO.get(mes_escolhido, "10")
            competencia_alvo = f"{mes_str}/{ano_selecionado}"
            
            col_data_filtro = next((c for c in ['COMPETENCIA_EXIBE', 'COMPETENCIA', 'DATA_PAGAMENTO_EXIBE'] if c in df_filtrado.columns), None)
            if col_data_filtro:
                df_filtrado = df_filtrado[df_filtrado[col_data_filtro].astype(str).str.contains(competencia_alvo, na=False)]

        # Aplica filtros de texto dinâmicos (Matrícula, CPF, Nome)
        if filtro_matricula:
            col_mat = next((c for c in ['ITEM_MATRICULA', 'MATRICULA'] if c in df_filtrado.columns), None)
            if col_mat:
                df_filtrado = df_filtrado[df_filtrado[col_mat].astype(str).str.contains(filtro_matricula, case=False, na=False)]

        if filtro_cpf:
            col_cpf = next((c for c in ['ITEM_CPF', 'CPF', 'CNPJ', 'ITEM_CNPJ', 'ITEM_CPFCNPJ'] if c in df_filtrado.columns), None)
            if col_cpf:
                df_filtrado = df_filtrado[df_filtrado[col_cpf].astype(str).str.contains(filtro_cpf, case=False, na=False)]

        if filtro_nome:
            col_nome = next((c for c in ['ITEM_NOME', 'NOME', 'FAVORECIDO', 'ITEM_FAVORECIDO'] if c in df_filtrado.columns), None)
            if col_nome:
                df_filtrado = df_filtrado[df_filtrado[col_nome].astype(str).str.contains(filtro_nome, case=False, na=False)]

        st.markdown("---")

        df_siglas = carregar_siglas(conn)
        if not df_siglas.empty and 'COD_SEFAZ' in df_filtrado.columns and 'COD_SEFAZ' in df_siglas.columns:
            df_filtrado['COD_SEFAZ'] = df_filtrado['COD_SEFAZ'].astype(str)
            df_siglas['COD_SEFAZ'] = df_siglas['COD_SEFAZ'].astype(str)
            df_filtrado = pd.merge(df_filtrado, df_siglas, on='COD_SEFAZ', how='left')
            if 'SIGLA' in df_filtrado.columns:
                df_filtrado['SIGLA'] = df_filtrado['SIGLA'].fillna("N/D")
            else:
                df_filtrado['SIGLA'] = "N/D"
        else:
            df_filtrado['SIGLA'] = "N/D"

        # --- KPI CARDS EXECUTIVOS ---
        tot_reg = len(df_filtrado)
        col_bruto = next((c for c in ['ITEM_VALORBRUTO', 'VALORBRUTO', 'VALOR'] if c in df_filtrado.columns), None)
        val_bruto = df_filtrado[col_bruto].sum() if col_bruto else 0.0

        col_liq = next((c for c in ['ITEM_VALORLIQUIDO', 'VALOR LIQUIDO', 'VALORLIQUIDO'] if c in df_filtrado.columns), None)
        val_liq = df_filtrado[col_liq].sum() if col_liq else 0.0

        k1, k2, k3 = st.columns(3)
        k1.metric("📦 Total de Registros", f"{tot_reg:,}".replace(",", "."))
        k2.metric("💰 Valor Bruto Total", formatar_moeda_br(val_bruto))
        k3.metric("💵 Valor Líquido Total", formatar_moeda_br(val_liq))

        st.markdown("### 📋 Detalhamento Geral")

        colunas_padrao = [
            'CODIGO', 'COD_SEFAZ', 'SIGLA', 'TIPOPROCESSAMENTO', 
            'COMPETENCIA_EXIBE', 'DATA_PAGAMENTO_EXIBE', 'ITEM_NOME', 
            'ITEM_MATRICULA', 'ITEM_DESCRICAOSTATUSPGTO', 
            'ITEM_VALORBRUTO', 'ITEM_VALORLIQUIDO'
        ]
        colunas_existentes = [c for c in colunas_padrao if c in df_filtrado.columns]

        st.dataframe(
            df_filtrado[colunas_existentes] if colunas_existentes else df_filtrado,
            use_container_width=True,
            hide_index=True,
            height=550,
            column_config={
                "COD_SEFAZ": st.column_config.TextColumn("Cod SEFAZ"),
                "SIGLA": st.column_config.TextColumn("Órgão / Sigla"),
                "COMPETENCIA_EXIBE": st.column_config.TextColumn("Competência / Mês"),
                "DATA_PAGAMENTO_EXIBE": st.column_config.TextColumn("Data Pagamento"),
                "ITEM_VALORBRUTO": st.column_config.NumberColumn("Valor Bruto", format="R$ %.2f"),
                "ITEM_VALORLIQUIDO": st.column_config.NumberColumn("Valor Líquido", format="R$ %.2f")
            }
        )
    except Exception as e:
        st.error(f"Ocorreu um erro ao renderizar o painel: {e}")

