import streamlit as st
import requests

# 1. Constantes de Autenticação
BASIC_AUTH = "ZXlKcFpDSTZJakJpT0dWa05EQXROVEJsWXkwMFpERmlMVGxsWkdZdFpUWmxNaUlzSW1OdlpHbG5iMUIxWW14cFkyRmtiM0lpT2pBc0ltTnZaR2xuYjFOdlpuUjNZWEpsSWpveE9UZzROVFVzSW5ObGNYVmxibU5wWVd4SmJuTjBZV3hoWTJGdklqb3hmUTpleUpwWkNJNklqZzVOalpqTlRNdE1EZzFNeTAwTXpReExUa3lZMlF0WVdJMk16Z3lNMlJoWkdReE1ERXhPR0psT0NJc0ltTnZaR2xuYjFCMVlteHBZMkZrYjNJaU9qQXNJbU52WkdsbmIxTnZablIzWVhKbElqb3hPVGc0TlRVc0luTmxjWFZsYm1OcFlXeEpibk4wWVd4aFkyRnZJam94TENKelpYRjFaVzVqYVdGc1EzSmxaR1Z1WTJsaGJDSTZNU3dpWVcxaWFXVnVkR1VpT2lKb2IyMXZiRzluWVdOaGJ5SXNJbWxoZENJNk1UYzRNelV6T0RNek56TTNOWDA="
DEVELOPER_KEY = "c17de8d857e54c9da66d5a0581040039"

TOKEN_URL = "https://oauth.hm.bb.com.br/oauth/token"
BASE_URL = "https://api.hm.bb.com.br/validacao-contas/v1/contas"

# 2. Dados de Teste
DADOS_TESTE_BB = [
    {"cpf": "99391916180", "agencia": "0018", "conta": "3066"},
    {"cpf": "98801072171", "agencia": "0018", "conta": "35745"},
    {"cpf": "42441521990", "agencia": "0018", "conta": "35789"},
    {"cpf": "79060319540", "agencia": "0018", "conta": "310841"},
    {"cpf": "93496603186", "agencia": "0018", "conta": "318581"},
    {"cpf": "20585714801", "agencia": "0551", "conta": "71000"},
    {"cpf": "684526081000158", "agencia": "0551", "conta": "760840"},
    {"cpf": "93983472000192", "agencia": "0551", "conta": "731771"},
    {"cpf": "6059151000194", "agencia": "0551", "conta": "712803"},
    {"cpf": "197678083000104", "agencia": "0551", "conta": "714669"},
    {"cpf": "293809477000101", "agencia": "0551", "conta": "762114"}
]

def obter_token():
    headers = {
        'Authorization': f'Basic {BASIC_AUTH}',
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    payload = {'grant_type': 'client_credentials', 'scope': 'validacao-contas.info'}
    response = requests.post(TOKEN_URL, data=payload, headers=headers)
    if response.status_code == 200:
        return response.json().get('access_token')
    else:
        st.error(f"Erro na autenticação: {response.status_code}")
        st.text(f"Detalhe do erro: {response.text}")
        return None

import streamlit as st
import requests

# ... (Mantenha as constantes e a lista DADOS_TESTE_BB iguais)

def render(conn):
    st.subheader("🔍 Validação de Contas - Auditoria de Retorno")
    
    idx = st.selectbox("Escolha um cenário de teste:", range(len(DADOS_TESTE_BB)), 
                       format_func=lambda i: f"CPF: {DADOS_TESTE_BB[i]['cpf']} | Ag: {DADOS_TESTE_BB[i]['agencia']} Cc: {DADOS_TESTE_BB[i]['conta']}")
    
    with st.form("form_bb"):
        agencia = st.text_input("Agência:", value=DADOS_TESTE_BB[idx]['agencia'])
        conta = st.text_input("Conta:", value=DADOS_TESTE_BB[idx]['conta'])
        cpf_cnpj = st.text_input("CPF ou CNPJ:", value=DADOS_TESTE_BB[idx]['cpf'])
        submit = st.form_submit_button("Consultar")

    if submit:
        token = obter_token()
        if token:
            headers = {
                'Authorization': f'Bearer {token}',
                'gw-dev-app-key': DEVELOPER_KEY,
                'Content-Type': 'application/json'
            }
            url = f"{BASE_URL}/{agencia}-{conta}/situacao"
            try:
                resp = requests.get(url, headers=headers, params={'cpfCnpj': cpf_cnpj})
                
                # Exibição de todo o conteúdo da resposta
                st.write(f"### Status Code: {resp.status_code}")
                
                if resp.status_code == 200:
                    st.success("Resposta completa recebida:")
                    # Exibe o JSON bruto para você mapear todos os campos disponíveis
                    st.json(resp.json())
                    
                    # Debug: Verifique se existe algum campo que não estamos vendo
                    dados = resp.json()
                    st.write("---")
                    st.write("Campos disponíveis no JSON:")
                    st.write(list(dados.keys()))
                else:
                    st.error("Erro na requisição:")
                    st.json(resp.json())
                    
            except Exception as e:
                st.error(f"Erro na conexão: {str(e)}")

