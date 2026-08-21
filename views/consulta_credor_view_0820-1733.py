# -*- coding: utf-8 -*-
import streamlit as st
import requests
import pandas as pd
import urllib3
import re
from datetime import datetime

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def consultar_credor_sefaz(ano, cpf_ou_credor):
    usuario = st.secrets["sefaz"]["SIAFE_CPF"]
    senha = st.secrets["sefaz"]["SIAFE_SENHA"]
    BASE_URL = st.secrets["sefaz"]["BASE_URL"]

    # Limpa a string, mantendo apenas dígitos (caso seja CPF/CNPJ formatado)
    # Se for um código alfanumérico, ajuste conforme necessário, mas para CPF/CNPJ remove pontos e traços
    identificador_limpo = re.sub(r'\D', '', cpf_ou_credor)
    # Se o credor puder aceitar letras/códigos que não sejam só números, use:
    # identificador_limpo = cpf_ou_credor.replace('.', '').replace('-', '').replace('/', '').strip()

    try:
        session = requests.Session()
        session.verify = False
        session.headers.update({"Content-Type": "application/json"})

        # 1. Autenticação na API
        payload_auth = {"usuario": usuario, "senha": senha}
        r_auth = session.post(f"{BASE_URL}/auth", json=payload_auth, timeout=10)
        r_auth.raise_for_status()

        token = r_auth.json().get("token")
        session.headers.update({"Authorization": f"Bearer {token}"})

        # 2. Chamada ao endpoint utilizando o valor limpo
        url = f"{BASE_URL}/apoio-geral/credor/{ano}/{identificador_limpo}"
        r = session.get(url, timeout=15)
        r.raise_for_status()

        return r.json()

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
                if data:
                    st.success("Dados encontrados com sucesso!")
                    if isinstance(data, dict):
                        st.json(data)
                    else:
                        df = pd.DataFrame(data)
                        st.dataframe(df, use_container_width=True, hide_index=True)
                else:
                    st.info("Nenhum registro encontrado para o identificador informado.")
            else:
                perfil_usuario = st.session_state.get("perfil_usuario")
                if perfil_usuario in ['a', 'g']:
                    st.error(f"⚠️ {data}")
                else:
                    st.warning("⚠️ O serviço de consulta de credor está temporariamente indisponível.")

