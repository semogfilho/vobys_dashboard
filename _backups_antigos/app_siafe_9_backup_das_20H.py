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
    BASE_URL = "https://localhost:8443/siafe-api"
    try:
        # Aumentei a segurança incluindo um timeout para não travar o painel
        r_auth = requests.post(f"{BASE_URL}/auth", 
                               json={"usuario": st.secrets.get("SIAFE_CPF", ""), 
                                     "senha": st.secrets.get("SIAFE_SENHA", "")}, 
                               verify=False, timeout=5)
        
        token = r_auth.json().get("token")
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        r = requests.post(f"{BASE_URL}/folha-pagamento/pendente/{ano}", json={}, headers=headers, verify=False, timeout=10)
        
        if r.status_code == 200:
            df = pd.DataFrame(r.json())
            df_explode = df.explode('itens').reset_index(drop=True)
            itens_norm = pd.json_normalize(df_explode['itens']).add_prefix('item_')
            df_final = pd.concat([df_explode.drop(columns=['itens']), itens_norm], axis=1)
            return df_final
        return pd.DataFrame()

    except requests.exceptions.ConnectionError as e:
        st.error(f"⚠️ Erro de conexão detalhado: {e}")
        st.write(f"Verifique se o túnel SSH ainda está ativo com: ps aux | grep ssh")
        return pd.DataFrame()

    #except requests.exceptions.ConnectionError:
    #    st.error("⚠️ **Ops! Não conseguimos conectar ao servidor do SIAFE.**")
    #    st.info("Habilite o túnel SSH com o servidor para acessar o SIAFE. Verifique também se a sua VPN está ativa.")
    #    return pd.DataFrame()
        
    except Exception as e:
        st.error(f"Erro inesperado na comunicação com a API: {e}")
        return pd.DataFrame()

def main(conn, ano_selecionado, mes_chave, meses_lista):
    try:
        chave_formatada = int(mes_chave)
    except (ValueError, TypeError):
        chave_formatada = mes_chave

    mes_num_str = MAPA_MESES_ROBUSTO.get(chave_formatada, "01")
    competencia_busca = f"{mes_num_str}/{ano_selecionado}"
    
    st.title(f"📊 Painel de Pagamentos ({mes_num_str}/{ano_selecionado})")
    
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

    df_total['categoria'] = df_total['codigoUgSistemaExterno'].apply(categorizar)

    # Filtro de Categoria
    cat_selecionada = st.radio("Selecione a Categoria:", ["FOLHA", "PPF"], horizontal=True)
    df_mes = df_total[(df_total['competencia'].astype(str) == competencia_busca) & 
                      (df_total['categoria'] == cat_selecionada)].copy()

    col_esq, col_dir = st.columns([1, 4])

    with col_esq:
        st.subheader(f"Unidades Gestoras ({cat_selecionada})")
        resumo = df_mes.groupby(['codigoUgSistemaExterno', 'codigoUg']).agg(
            QTD=('codigoUg', 'size'),
            VALOR_BRUTO=('item_valorBruto', 'sum')
        ).reset_index()
        
        total_qtd = resumo['QTD'].sum()
        total_valor = resumo['VALOR_BRUTO'].sum()
        linha_total_master = pd.DataFrame({
            'codigoUgSistemaExterno': ['TOTAL'],
            'codigoUg': [''],
            'QTD': [total_qtd],
            'VALOR_BRUTO': [total_valor]
        })
        
        df_display = pd.concat([resumo, linha_total_master], ignore_index=True)
        df_display['VALOR_BRUTO'] = df_display['VALOR_BRUTO'].apply(formatar_moeda_br)
        
        evento = st.dataframe(df_display, use_container_width=True, hide_index=True, 
                              selection_mode="multi-row", on_select="rerun")
        
        selected_rows = evento.selection.rows
        if not selected_rows or len(resumo) in selected_rows:
            modo_filtro = "TOTAL"
        else:
            modo_filtro = "UNIDADE"
            sel_data = resumo.iloc[selected_rows]
            listas_sefaz = sel_data['codigoUgSistemaExterno'].astype(str).tolist()
            listas_ug = sel_data['codigoUg'].astype(str).tolist()

    with col_dir:
        if modo_filtro == "UNIDADE":
            st.subheader(f"Detalhes - Seleção Múltipla ({len(selected_rows)} UGs)")
            detalhes = df_mes[
                df_mes.apply(lambda x: (str(x['codigoUgSistemaExterno']), str(x['codigoUg'])) 
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
        
        st.dataframe(df_exibicao[colunas_validas], use_container_width=True, hide_index=True)
        
        with st.expander("🔍 Auditoria da Seleção"):
            st.json(detalhes.to_json(orient='records', force_ascii=False))

