# -*- coding: utf-8 -*-
import streamlit as st
import requests
import pandas as pd
import urllib3
import re
from datetime import datetime

# Desabilita avisos de SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def consultar_credor_sefaz(ano, cpf_ou_credor):
    usuario = st.secrets["sefaz"]["SIAFE_CPF"]
    senha = st.secrets["sefaz"]["SIAFE_SENHA"]
    BASE_URL = st.secrets["sefaz"]["BASE_URL"]

    identificador_limpo = re.sub(r'\D', '', cpf_ou_credor)

    try:
        # Criamos a sessão mantendo o comportamento idêntico ao curl que funcionou
        session = requests.Session()
        session.verify = False
        
        session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            "User-Agent": "curl/7.29.0"  # Usando o mesmo user-agent do curl validado
        })

        # 1. Autenticação na API (armazena automaticamente os cookies do WAF e da aplicação)
        payload_auth = {"usuario": usuario, "senha": senha}
        r_auth = session.post(f"{BASE_URL}/auth", json=payload_auth, timeout=(10, 20))
        r_auth.raise_for_status()

        res_json = r_auth.json()
        token = res_json.get("token")
        
        if not token:
            return f"Erro: Token não retornado pela API. Resposta: {res_json}"

        # Atualiza o header com o Bearer token mantendo os cookies da sessão anterior
        session.headers.update({"Authorization": f"Bearer {token}"})

        # 2. Chamada ao endpoint de credor
        url = f"{BASE_URL}/apoio-geral/credor/{ano}/{identificador_limpo}"
        r = session.get(url, timeout=(10, 30))
        r.raise_for_status()

        return r.json()

    except requests.exceptions.ConnectionError as ce:
        return f"Erro de Conexão (RemoteDisconnected/WAF): O proxy da SEFAZ fechou a conexão. Detalhes: {str(ce)}"
    except requests.exceptions.Timeout:
        return "Erro: O tempo limite (timeout) de resposta da SEFAZ foi excedido."
    except Exception as e:
        return f"Erro na API (Status/Falha): {str(e)}"

def renderizar_consulta_credor(ano, mes):
    st.subheader(f"🔍 Consulta de Credor na SEFAZ (Exercício: {ano})")

    with st.expander("ℹ️ Detalhes da Consulta", expanded=False):
        st.caption(f"**Endpoint:** `/apoio-geral/credor/{ano}/{{codigo}}`")
        st.caption(f"**Última tentativa:** {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")

    cpf_input = st.text_input("Informe o CPF ou Código do Credor:", max_chars=20)

    if st.button("Consultar Credor", type="primary"):
        if not cpf_input.strip():
            st.warning("Por favor, informe um CPF ou código válido.")
            return

        with st.spinner(f"Buscando dados do credor para o exercício {ano}..."):
            data = consultar_credor_sefaz(ano, cpf_input.strip())

            if isinstance(data, (dict, list)) and not isinstance(data, str):
                tem_conteudo = False
                if isinstance(data, dict):
                    if data.get("codigo") or data.get("cpfCnpj") or data.get("nome"):
                        tem_conteudo = True
                elif isinstance(data, list) and len(data) > 0:
                    tem_conteudo = True

                if tem_conteudo:
                    st.success("Dados encontrados com sucesso!")
                    if isinstance(data, dict):
                        st.json(data)
                    else:
                        df = pd.DataFrame(data)
                        st.dataframe(df, use_container_width=True, hide_index=True)
                else:
                    st.warning("⚠️ Nenhum registro encontrado para o identificador informado neste exercício.")
            else:
                perfil_usuario = st.session_state.get("perfil_usuario")
                if perfil_usuario in ['a', 'g']:
                    st.error(f"⚠️ {data}")
                else:
                    st.warning("⚠️ O serviço de consulta de credor está temporariamente indisponível. Por favor, contate o suporte técnico.")

def render(conn, ano, mes, meses_lista=None):
    renderizar_consulta_credor(ano, mes)

