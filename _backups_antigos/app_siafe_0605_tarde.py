# -*- coding: utf-8 -*-
import streamlit as st
import requests
import urllib3
import pandas as pd

# Desabilita avisos de SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Mapa ROBUSTO
MAPA_MESES_ROBUSTO = {
    "Jan": "01", "Fev": "02", "Mar": "03", "Abr": "04", "Mai": "05", "Jun": "06",
    "Jul": "07", "Ago": "08", "Set": "09", "Out": "10", "Nov": "11", "Dez": "12",
    1: "01", 2: "02", 3: "03", 4: "04", 5: "05", 6: "06",
    7: "07", 8: "08", 9: "09", 10: "10", 11: "11", 12: "12",
    "1": "01", "2": "02", "3": "03", "4": "04", "5": "05", "6": "06",
    "7": "07", "8": "08", "9": "09", "10": "10", "11": "11", "12": "12"
}

def formatar_moeda_br(valor):
    try:
        return f"R$ {float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return valor

@st.cache_data(show_spinner="Sincronizando com a API...")

def buscar_dados_siafe(ano):
    BASE_URL = "https://127.0.0.1:8443/siafe-api"
    
    # Sessão para reaproveitar conexão TCP/SSL
    session = requests.Session()
    session.verify = False  
    session.timeout = 10    # Timeout unificado
    
# O Header 'Host' é OBRIGATÓRIO agora
    session.headers.update({
        "Host": "tesouro.sefaz.pi.gov.br",
        "Content-Type": "application/json"
    })

    try:
        # 1. Autenticação
        r_auth = session.post(f"{BASE_URL}/auth", 
                               json={
                                   "usuario": st.secrets.get("SIAFE_CPF", ""),
                                   "senha": st.secrets.get("SIAFE_SENHA", "")
                               })
        r_auth.raise_for_status() # Lança exceção se o status não for 2xx
        
        token = r_auth.json().get("token")
        session.headers.update({"Authorization": f"Bearer {token}"})
        
        # 2. Busca de dados
        r = session.post(f"{BASE_URL}/folha-pagamento/pendente/{ano}", json={})
        r.raise_for_status()
        
        # 3. Processamento de dados
        df = pd.DataFrame(r.json())
        df_explode = df.explode('itens').reset_index(drop=True)
        itens_norm = pd.json_normalize(df_explode['itens']).add_prefix('item_')
        df_final = pd.concat([df_explode.drop(columns=['itens']), itens_norm], axis=1)

	# Renomeação da coluna para um nome mais amigável
        df_final = df_final.rename(columns={'codigoUgSistemaExterno': 'Cod_Sefaz'})

        return df_final

    except requests.exceptions.HTTPError as e:
        st.error(f"⚠️ Erro na API SIAFE (HTTP {r.status_code if 'r' in locals() else 'N/A'}): {e}")
    except requests.exceptions.ConnectionError as e:
        st.error(f"⚠️ Túnel SSH/Rede indisponível: {e}")
    except Exception as e:
        st.error(f"⚠️ Erro inesperado: {e}")
        
    return pd.DataFrame()

def main(conn, ano_selecionado, mes_chave, meses_lista):
    try:
        chave_formatada = int(mes_chave)
    except (ValueError, TypeError):
        chave_formatada = mes_chave

    mes_num_str = MAPA_MESES_ROBUSTO.get(chave_formatada, "01")
    competencia_busca = f"{mes_num_str}/{ano_selecionado}"
    
    st.title(f"📊 Painel de Pagamentos  Pendentes ({mes_num_str}/{ano_selecionado})")
    
    df_total = buscar_dados_siafe(ano_selecionado)
    if df_total.empty:
        st.warning("Nenhum dado encontrado.")
        return

    # Lógica de Categorização
    def categorizar(codigo):
        try:
            val = int(codigo)
            return "FOLHA" if 1 <= val <= 999 else "PPF"
        except:
            return "PPF"

    df_total['categoria'] = df_total['Cod_Sefaz'].apply(categorizar)

    # Filtro de Categoria
    cat_selecionada = st.radio("Selecione a Categoria:", ["FOLHA", "PPF"], horizontal=True)
    df_mes = df_total[(df_total['competencia'].astype(str) == competencia_busca) & 
                      (df_total['categoria'] == cat_selecionada)].copy()

    col_esq, col_dir = st.columns([1, 4])

    with col_esq:
        st.subheader(f"Unidades Gestoras ({cat_selecionada})")
        resumo = df_mes.groupby(['Cod_Sefaz', 'codigoUg']).agg(
            QTD=('codigoUg', 'size'),
            VALOR_BRUTO=('item_valorBruto', 'sum')
        ).reset_index()
        
        total_qtd = resumo['QTD'].sum()
        total_valor = resumo['VALOR_BRUTO'].sum()
        linha_total_master = pd.DataFrame({
            'Cod_Sefaz': ['TOTAL'],
            'codigoUg': [''],
            'QTD': [total_qtd],
            'VALOR_BRUTO': [total_valor]
        })
        
        df_display = pd.concat([resumo, linha_total_master], ignore_index=True)
        df_display['VALOR_BRUTO'] = df_display['VALOR_BRUTO'].apply(formatar_moeda_br)
        
        evento = st.dataframe(df_display, width='stretch', hide_index=True, 
                              selection_mode="multi-row", on_select="rerun")
        
        selected_rows = evento.selection.rows
        if not selected_rows or len(resumo) in selected_rows:
            modo_filtro = "TOTAL"
        else:
            modo_filtro = "UNIDADE"
            sel_data = resumo.iloc[selected_rows]
            listas_sefaz = sel_data['Cod_Sefaz'].astype(str).tolist()
            listas_ug = sel_data['codigoUg'].astype(str).tolist()

    with col_dir:
        if modo_filtro == "UNIDADE":
            st.subheader(f"Detalhes - Seleção Múltipla ({len(selected_rows)} UGs)")
            detalhes = df_mes[
                df_mes.apply(lambda x: (str(x['Cod_Sefaz']), str(x['codigoUg'])) 
                             in zip(listas_sefaz, listas_ug), axis=1)
            ].copy()
        else:
            st.subheader(f"Detalhes - Todos os Registros {cat_selecionada}")
            detalhes = df_mes.copy()
            
        # CSS para compactar o layout
        st.markdown("""
            <style>
                div.stMetric { padding-top: 0px !important; }
                div[data-testid="stDataFrame"] { margin-top: -20px !important; }
            </style>
        """, unsafe_allow_html=True)

        c1, c2, c3 = st.columns(3)
        c1.metric("Registros", len(detalhes))
        c2.metric("Total Bruto", formatar_moeda_br(detalhes['item_valorBruto'].sum()))
        c3.metric("Total Líquido", formatar_moeda_br(detalhes['item_valorLiquido'].sum()))
            
        df_exibicao = detalhes.copy()
        df_exibicao['item_valorBruto'] = df_exibicao['item_valorBruto'].apply(formatar_moeda_br)
        df_exibicao['item_valorLiquido'] = df_exibicao['item_valorLiquido'].apply(formatar_moeda_br)
        
        colunas_exibicao = [
            'codigo', 'codigoExterno', 'tipoProcessamento', 'item_nome', 'item_matricula', 
            'item_dataPagamento', 'item_descricaoStatusPgto', 'item_valorBruto', 'item_valorLiquido'
        ]
        colunas_validas = [c for c in colunas_exibicao if c in df_exibicao.columns]
        
        st.dataframe(df_exibicao[colunas_validas], width='stretch', hide_index=True)
        
        with st.expander("🔍 Auditoria da Seleção"):
            st.json(detalhes.to_json(orient='records', force_ascii=False))

