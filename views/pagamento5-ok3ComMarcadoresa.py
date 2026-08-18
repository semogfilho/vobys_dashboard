# -*- coding: utf-8 -*-
import streamlit as st
import requests
import urllib3
import pandas as pd

st.set_page_config(layout="wide")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def render(ano_selecionado, mes_chave):
    st.title("📊 Módulo de Pagamentos - Correção de Requisição")
    BASE_URL = "https://localhost:8443/siafe-api"
    
    try:
        # 1. Autenticação
        r_auth = requests.post(f"{BASE_URL}/auth", json={"usuario": st.secrets.get("SIAFE_CPF", ""), "senha": st.secrets.get("SIAFE_SENHA", "")}, verify=False)
        token = r_auth.json().get("token")
        
        # 2. Busca com o corpo correto (O erro estava aqui)
        # A API espera um objeto no body. Se o método não exige parâmetros específicos, 
        # enviamos um JSON vazio {}, mas precisamos garantir que o cabeçalho esteja correto.
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        
        # Ajuste: A API espera um objeto (JSON), tente enviar um JSON vazio com a estrutura correta
        body_da_requisicao = {} 
        
        r = requests.post(f"{BASE_URL}/folha-pagamento/pendente/{ano_selecionado}", 
                          json=body_da_requisicao, headers=headers, verify=False)
        
        # 3. Tratamento da Resposta
        if r.status_code != 200:
            st.error(f"Erro na API ({r.status_code}): {r.text}")
            return

        dados = r.json()
        
        # Aqui, como agora sabemos que a API pode retornar um objeto com chave de erro 
        # ou a lista diretamente, vamos validar:
        if isinstance(dados, dict) and 'erro' in dados:
            st.error(f"API retornou erro: {dados['erro']}")
            return

        st.success("Dados recebidos com sucesso!")
        st.dataframe(pd.DataFrame(dados))

    except Exception as e:
        st.error(f"Erro no código: {str(e)}")

if __name__ == "__main__":
    render("2026", "Mar")

