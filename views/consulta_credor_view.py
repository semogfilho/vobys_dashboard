# -*- coding: utf-8 -*-
import streamlit as st
import requests
import pandas as pd
import urllib3
import re
from datetime import datetime

# Desabilita avisos de SSL (mesmo padrão do SIAFE)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def consultar_credor_sefaz(ano, cpf_ou_credor):
    # Recupera credenciais e URL base do secrets
    usuario = st.secrets["sefaz"]["SIAFE_CPF"]
    senha = st.secrets["sefaz"]["SIAFE_SENHA"]
    BASE_URL = st.secrets["sefaz"]["BASE_URL"]

    # Limpa a string, removendo pontos, traços e barras, mantendo apenas os dígitos
    identificador_limpo = re.sub(r'\D', '', cpf_ou_credor)

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

        # 2. Chamada ao endpoint correto mapeado no Swagger (/apoio-geral/credor/{exercicio}/{codigo})
        url = f"{BASE_URL}/apoio-geral/credor/{ano}/{identificador_limpo}"
        r = session.get(url, timeout=15)
        r.raise_for_status()

        return r.json()

    except Exception as e:
        return f"Erro na API (Status/Falha): {str(e)}"

def renderizar_consulta_credor(ano, mes):
    st.subheader(f"🔍 Consulta de Credor na SEFAZ (Exercício: {ano})")

    # Exibição transparente do contexto de busca
    with st.expander("ℹ️ Detalhes da Consulta", expanded=False):
        st.caption(f"**Endpoint:** `/apoio-geral/credor/{ano}/{{codigo}}`")
        st.caption(f"**Última tentativa:** {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")

    # Campo de entrada para o CPF ou código do credor
    cpf_input = st.text_input("Informe o CPF ou Código do Credor:", max_chars=20)

    if st.button("Consultar Credor", type="primary"):
        if not cpf_input.strip():
            st.warning("Por favor, informe um CPF ou código válido.")
            return

        with st.spinner(f"Buscando dados do credor para o exercício {ano}..."):
            data = consultar_credor_sefaz(ano, cpf_input.strip())

            if isinstance(data, (dict, list)) and not isinstance(data, str):
                # Valida se o dicionário possui conteúdo real (evita exibir tela vazia/nula)
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
                # Tratamento diferenciado de erro para Administradores vs Usuários comuns
                perfil_usuario = st.session_state.get("perfil_usuario")
                if perfil_usuario in ['a', 'g']:
                    st.error(f"⚠️ {data}")
                else:
                    st.warning("⚠️ O serviço de consulta de credor está temporariamente indisponível. Por favor, contate o suporte técnico.")

