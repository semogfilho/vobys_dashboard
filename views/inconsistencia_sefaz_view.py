# -*- coding: utf-8 -*-
import streamlit as st
import requests
import pandas as pd
import urllib3
from datetime import datetime

# Desabilita avisos de SSL (mesmo padrão do SIAFE)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def consultar_inconsistencia_sefaz(ano, mes):
    # Recupera credenciais e URL base do secrets
    usuario = st.secrets["sefaz"]["SIAFE_CPF"]
    senha = st.secrets["sefaz"]["SIAFE_SENHA"]
    BASE_URL = st.secrets["sefaz"]["BASE_URL"]

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

        # 2. Chamada ao endpoint de inconsistências
        url = f"{BASE_URL}/folha-pagamento/inconsistencia-pag/{ano}/{mes}"
        r = session.get(url, timeout=15)
        r.raise_for_status()

        return r.json()

    except Exception as e:
        return f"Erro na API (Status/Falha): {str(e)}"

def renderizar_inconsistencia_sefaz(ano, mes, auth_ui):
    st.subheader(f"🔍 Inconsistência Cadastro SEFAZ ({mes:02d}/{ano})")

    # Exibição transparente do contexto de busca
    with st.expander("ℹ️ Detalhes da Consulta", expanded=False):
        col1, col2 = st.columns(2)
        col1.caption(f"**Endpoint:** `/folha-pagamento/inconsistencia-pag/{ano}/{mes}`")
        col2.caption(f"**Competência Consultada:** {mes:02d}/{ano}")
        st.caption(f"**Última tentativa:** {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")

    if st.button("Consultar Inconsistências na SEFAZ", type="primary"):
        with st.spinner(f"Buscando dados na SEFAZ para {mes:02d}/{ano}..."):
            data = consultar_inconsistencia_sefaz(ano, mes)

            if isinstance(data, list):
                if data:
                    df = pd.DataFrame(data)
                    
                    # Tratamento de normalização caso venha estrutura aninhada (similar ao padrão do sistema)
                    if 'itens' in df.columns:
                        df_explode = df.explode('itens').reset_index(drop=True)
                        itens_norm = pd.json_normalize(df_explode['itens']).add_prefix('item_')
                        df_final = pd.concat([df_explode.drop(columns=['itens']), itens_norm], axis=1)
                    else:
                        df_final = df

                    st.success(f"Foram encontradas {len(df_final)} ocorrências.")
                    st.dataframe(
                        df_final, 
                        use_container_width=True, 
                        hide_index=True,
                        column_config={
                            "codigoUG": "Código UG",
                            "codigo": "Código",
                            "codigoPagamento": "Cód. Pagamento",
                            "identidadeFuncional": "Id. Funcional",
                            "descricao": "Descrição",
                            "nomeArquivo": "Nome do Arquivo",
                            "cpf": "CPF"
                        }
                    )
                else:
                    st.info("Nenhuma inconsistência encontrada para esta competência.")
            else:
                # Tratamento diferenciado de erro para Administradores vs Usuários comuns
                perfil_usuario = st.session_state.get("perfil_usuario")
                if perfil_usuario in ['a', 'g']:
                    st.error(f"⚠️ {data}")
                else:
                    st.warning("⚠️ O serviço de integração SEFAZ está temporariamente indisponível. Por favor, contate o suporte técnico.")

