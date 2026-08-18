# -*- coding: utf-8 -*-
import streamlit as st
import requests
import pandas as pd
import urllib3
import json

# Silencia avisos de SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# URL apontando para o túnel local que validamos
BASE_URL = "https://localhost:8443/siafe-api"

def render(ano_selecionado, mes_chave):
    st.title("📊 Módulo de Pagamentos - SIAFE")
    
    @st.cache_data(ttl=3600)
    def obter_token_siafe():
        auth_url = f"{BASE_URL}/auth"
        cpf = st.secrets.get("SIAFE_CPF")
        senha = st.secrets.get("SIAFE_SENHA")
        
        headers = {
            "Content-Type": "application/json",
            "Host": "tesouro.sefaz.pi.gov.br",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        }
        
        payload = {"usuario": str(cpf).strip(), "senha": str(senha).strip()}
        
        try:
            # O timeout foi aumentado para dar tempo do túnel responder
            response = requests.post(auth_url, json=payload, headers=headers, timeout=30, verify=False)
            
            # LOG DE DEBUG: Essencial para descobrir por que a autenticação falha
            print(f"DEBUG: Status Code {response.status_code}")
            print(f"DEBUG: Resposta completa: {response.text}")
            
            if response.status_code == 200:
                return response.json().get("token")
            return None
        except Exception as e:
            print(f"DEBUG: Erro na requisição: {str(e)}")
            return None

    def buscar_dados_siafe(exercicio, token):
        url = f"{BASE_URL}/folha-pagamento/pendente/{str(exercicio).strip()}"
        headers = {
            "Authorization": f"Bearer {token}", 
            "Content-Type": "application/json",
            "Host": "tesouro.sefaz.pi.gov.br"
        }
        try:
            response = requests.post(url, json={}, headers=headers, timeout=30, verify=False)
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            print(f"DEBUG: Erro ao buscar dados: {str(e)}")
            return None

    with st.spinner("Autenticando..."):
        token_valido = obter_token_siafe()

    if token_valido:
        dados_brutos = buscar_dados_siafe(ano_selecionado, token_valido)
        if dados_brutos:
            st.success("Dados carregados!")
            df = pd.DataFrame(dados_brutos)
            st.dataframe(df)
        else:
            st.error("Erro ao buscar dados. Verifique o terminal para detalhes.")
    else:
        st.error("Falha na autenticação. Verifique o terminal para o erro detalhado.")

if __name__ == "__main__":
    render("2026", "FEV")

