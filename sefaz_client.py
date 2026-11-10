# sefaz_client.py
import requests
import urllib3
import streamlit as st

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def _obter_credenciais_padrao():
    try:
        return (
            st.secrets['sefaz']['SIAFE_CPF'],
            st.secrets['sefaz']['SIAFE_SENHA']
        )
    except Exception:
        return None, None

def criar_sessao_sefaz():
    session = requests.Session()
    session.verify = False
    session.headers.update({
        'Content-Type': 'application/json',
        'Accept': 'application/json, text/plain, */*',
        'User-Agent': 'curl/7.29.0'
    })
    return session

def obter_token_sefaz(usuario=None, senha=None):
    BASE_URL = st.secrets['sefaz']['BASE_URL']
    
    if not usuario or not senha:
        usuario, senha = _obter_credenciais_padrao()
        
    if not usuario or not senha:
        raise ValueError('Credenciais da SEFAZ não fornecidas nem encontradas no secrets.')

    session = criar_sessao_sefaz()
    payload_auth = {'usuario': usuario, 'senha': senha}
    
    r_auth = session.post(f'{BASE_URL}/auth', json=payload_auth, timeout=(10, 20))
    r_auth.raise_for_status()
    
    return r_auth.json().get('token')

def requisitar_sefaz(metodo, endpoint, payload=None, usuario=None, senha=None):
    BASE_URL = st.secrets['sefaz']['BASE_URL'].rstrip('/')
    url = f'{BASE_URL}/{endpoint.lstrip("/")}'
    
    try:
        session = criar_sessao_sefaz()
        token = obter_token_sefaz(usuario, senha)
        session.headers.update({'Authorization': f'Bearer {token}'})
        
        metodo_upper = metodo.upper()
        if metodo_upper == 'POST':
            response = session.post(url, json=payload, timeout=(10, 30))
        elif metodo_upper == 'PUT':
            response = session.put(url, json=payload, timeout=(10, 30))
        else:
            response = session.get(url, timeout=(10, 30))
            
        response.raise_for_status()
        return response.json()

    except requests.exceptions.ConnectionError as ce:
        return {'erro': True, 'tipo': 'conexao', 'mensagem': f'Erro de Conexão (RemoteDisconnected/WAF): O proxy da SEFAZ fechou a conexão. Detalhes: {str(ce)}'}
    except requests.exceptions.Timeout:
        return {'erro': True, 'tipo': 'timeout', 'mensagem': 'Erro: O tempo limite (timeout) de resposta da SEFAZ foi excedido.'}
    except requests.exceptions.HTTPError as he:
        status = he.response.status_code if he.response else 'Desconhecido'
        return {'erro': True, 'tipo': 'http', 'mensagem': f'Erro HTTP {status}: {str(he)}'}
    except Exception as e:
        return {'erro': True, 'tipo': 'geral', 'mensagem': f'Erro na API (Status/Falha): {str(e)}'}
