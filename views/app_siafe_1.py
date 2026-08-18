# -*- coding: utf-8 -*-
import streamlit as st
import requests
import urllib3
import pandas as pd

# Configuração e Segurança
st.set_page_config(layout="wide")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def carregar_dados(ano):
    """Extrai, normaliza e armazena os dados no session_state."""
    BASE_URL = "https://localhost:8443/siafe-api"
    try:
        r_auth = requests.post(f"{BASE_URL}/auth", 
                               json={"usuario": st.secrets.get("SIAFE_CPF", ""), 
                                     "senha": st.secrets.get("SIAFE_SENHA", "")}, verify=False)
        token = r_auth.json().get("token")
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        
        r = requests.post(f"{BASE_URL}/folha-pagamento/pendente/{ano}", 
                          json={}, headers=headers, verify=False)
        
        if r.status_code == 200:
            dados = r.json()
            df = pd.DataFrame(dados)
            # Normalização (Flattening)
            df_explode = df.explode('itens').reset_index(drop=True)
            itens_norm = pd.json_normalize(df_explode['itens']).add_prefix('item_')
            df_final = pd.concat([df_explode.drop(columns=['itens']), itens_norm], axis=1)
            
            # Conversão financeira
            cols_fin = ['item_valorBruto', 'item_valorLiquido']
            for col in cols_fin:
                df_final[col] = pd.to_numeric(df_final[col], errors='coerce').fillna(0.0)
            
            st.session_state['df_final'] = df_final
            st.session_state['dados_carregados'] = True
        else:
            st.error(f"Erro na API: {r.status_code}")
    except Exception as e:
        st.error(f"Erro de conexão: {e}")

def main():
    """Função principal sem argumentos para evitar o erro de 'positional arguments'."""
    st.title("📊 Painel de Pagamentos - Mestre/Detalhe")
    
    if st.button("Atualizar Dados da API"):
        carregar_dados("2026")
        st.rerun()

    if 'df_final' not in st.session_state:
        st.info("Clique em 'Atualizar Dados da API' para carregar as informações.")
        return

    df = st.session_state['df_final']

    # --- VISÃO MESTRE ---
    st.subheader("Seleção de Folha (Mestre)")
    lista_folhas = df[['codigoRelatorioFolhaPagamento', 'status', 'competencia']].drop_duplicates()
    folha_selecionada = st.selectbox(
        "Selecione o Relatório para detalhar:",
        lista_folhas['codigoRelatorioFolhaPagamento'].unique()
    )

    # --- VISÃO DETALHE ---
    st.divider()
    st.subheader(f"Colaboradores - Relatório: {folha_selecionada}")
    
    detalhes = df[df['codigoRelatorioFolhaPagamento'] == folha_selecionada].copy()
    
    exibicao = detalhes.copy()
    exibicao['item_valorBruto'] = exibicao['item_valorBruto'].apply(lambda x: f"R$ {x:,.2f}")
    exibicao['item_valorLiquido'] = exibicao['item_valorLiquido'].apply(lambda x: f"R$ {x:,.2f}")
    
    colunas_exibicao = ['item_nome', 'item_matricula', 'item_valorBruto', 'item_valorLiquido', 'item_statusPgto']
    st.table(exibicao[colunas_exibicao])

if __name__ == "__main__":
    main()

