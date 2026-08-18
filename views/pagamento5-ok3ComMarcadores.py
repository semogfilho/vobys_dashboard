# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import requests
import urllib3

st.set_page_config(layout="wide")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def render(ano_selecionado, mes_chave):
    st.title("📊 Diagnóstico SIAFE: Rastreamento de Fluxo")
    BASE_URL = "https://localhost:8443/siafe-api"
    
    # MARCADOR 1: Autenticação
    try:
        r = requests.post(f"{BASE_URL}/auth", json={"usuario": st.secrets.get("SIAFE_CPF", ""), "senha": st.secrets.get("SIAFE_SENHA", "")}, timeout=30, verify=False)
        token = r.json().get("token") if r.status_code == 200 else None
        st.write("MARCADOR 1: Autenticação realizada.")
    except Exception as e:
        st.error(f"MARCADOR 1 - Falha na Autenticação: {e}")
        return

    # MARCADOR 2: Requisição com CORPO (Body)
    try:
        st.write(f"MARCADOR 2: Tentando buscar dados para o ano {ano_selecionado} com corpo de requisição...")
        
        # O erro indicava que falta um ParamConsultaFolhaPagamentoPendenteDTO
        # Enviamos um objeto vazio para satisfazer a exigência da API
        payload = {} 
        
        r = requests.post(f"{BASE_URL}/folha-pagamento/pendente/{ano_selecionado}", 
                          json=payload, 
                          headers={"Authorization": f"Bearer {token}"}, 
                          timeout=60, verify=False)
        
        st.write(f"MARCADOR 2.0: Status da resposta = {r.status_code}")
        
        if r.status_code == 200:
            dados = r.json()
        else:
            st.error(f"MARCADOR 2 - Erro HTTP {r.status_code}: {r.text}")
            return
            
    except Exception as e:
        st.error(f"MARCADOR 2 - Falha de conexão: {e}")
        return

    # MARCADOR 2.1: Verificação de conteúdo
    if not dados:
        st.warning("MARCADOR 2.1 - API retornou lista vazia.")
        return
    else:
        st.success("MARCADOR 2.2 - Dados recebidos com sucesso!")
        st.write(f"Quantidade de registros: {len(dados)}")

    # MARCADOR 3, 4 e 5 seguem igual...
    df = pd.DataFrame(dados)
    st.write("MARCADOR 3 - DataFrame criado.")
    
    df['mes'] = df['mes'].apply(lambda x: str(x).strip().upper())
    st.write("MARCADOR 4 - Normalização concluída.")
    
    st.success("MARCADOR 5 - Processamento finalizado!")
    st.dataframe(df.head())

if __name__ == "__main__":
    render("2026", "Jan")

