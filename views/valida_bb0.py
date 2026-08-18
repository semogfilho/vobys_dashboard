import streamlit as st
import requests

# 1. Constantes de Autenticação
BASIC_AUTH = "ZXlKcFpDSTZJakJpT0dWa05EQXROVEJsWXkwMFpERmlMVGxsWkdZdFpUWmxNaUlzSW1OdlpHbG5iMUIxWW14cFkyRmtiM0lpT2pBc0ltTnZaR2xuYjFOdlpuUjNZWEpsSWpveE9UZzROVFVzSW5ObGNYVmxibU5wWVd4SmJuTjBZV3hoWTJGdklqb3hmUTpleUpwWkNJNklqZzVOalpqTlRNdE1EZzFNeTAwTXpReExUa3lZMlF0WVdJMk16Z3lNMlJoWkdReE1ERXhPR0psT0NJc0ltTnZaR2xuYjFCMVlteHBZMkZrYjNJaU9qQXNJbU52WkdsbmIxTnZablIzWVhKbElqb3hPVGc0TlRVc0luTmxjWFZsYm1OcFlXeEpibk4wWVd4aFkyRnZJam94TENKelpYRjFaVzVqYVdGc1EzSmxaR1Z1WTJsaGJDSTZNU3dpWVcxaWFXVnVkR1VpT2lKb2IyMXZiRzluWVdOaGJ5SXNJbWxoZENJNk1UYzRNelV6T0RNek56TTNOWDA="
DEVELOPER_KEY = "c17de8d857e54c9da66d5a0581040039"

TOKEN_URL = "https://oauth.hm.bb.com.br/oauth/token"
BASE_URL = "https://api.hm.bb.com.br/validacao-contas/v1/contas"

def obter_token():
    headers = {
        'Authorization': f'Basic {BASIC_AUTH}',
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    
    # O BB em homologação é sensível ao formato do payload
    payload = {
        'grant_type': 'client_credentials',
        'scope': 'validacao-contas.info'
    }
    
    # Adicionamos o 'data=' explícito e garantimos a codificação
    response = requests.post(TOKEN_URL, data=payload, headers=headers)
    
    if response.status_code == 200:
        return response.json().get('access_token')
    else:
        # Debug detalhado para o 400
        st.error(f"Erro na autenticação: {response.status_code}")
        st.text(f"Detalhe do erro: {response.text}")
        return None

def render(conn): # Nome alterado de volta para render
    st.subheader("🔍 Validação de Contas")
    
    # Valores do primeiro exemplo do BB
    # CPF: 993.919.161-80 | Agência: 0018 | Conta: 3.066-X
    # Nota: A API geralmente pede agência/conta sem o dígito verificador ou separadores
    with st.form("form_bb"):
        agencia = st.text_input("Agência (sem dígito):", value="0018")
        conta = st.text_input("Conta (sem dígito):", value="3066")
        cpf_cnpj = st.text_input("CPF ou CNPJ:", value="99391916180")
        submit = st.form_submit_button("Consultar")
        
    if submit:
        token = obter_token()
        if token:
            headers = {
                'Authorization': f'Bearer {token}',
                'gw-dev-app-key': DEVELOPER_KEY, # Nome do header conforme a especificação do BB
                'Content-Type': 'application/json'
            }
            # Ajuste de formatação: remova pontuações do CPF/CNPJ se necessário
            url = f"{BASE_URL}/{agencia}-{conta}/situacao"
            
            try:
                resp = requests.get(url, headers=headers, params={'cpfCnpj': cpf_cnpj})
                if resp.status_code == 200:
                    st.success("Consulta realizada!")
                    st.json(resp.json())
                elif resp.status_code == 404:
                    st.warning("Conta não encontrada. Verifique os dados.")
                else:
                    st.error(f"Erro {resp.status_code}")
                    st.json(resp.json())
            except Exception as e:
                st.error(f"Erro: {str(e)}")

if __name__ == "__main__":
    main()

