# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import re
from datetime import datetime

import sefaz_client

def consultar_credor_sefaz(ano, cpf_ou_credor):
    identificador_limpo = re.sub(r'\D', '', cpf_ou_credor)
    endpoint = f"apoio-geral/credor/{ano}/{identificador_limpo}"
    
    # O sefaz_client já devolve o JSON de sucesso ou um dicionário estruturado de erro
    return sefaz_client.requisitar_sefaz("GET", endpoint)

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
            resultado = consultar_credor_sefaz(ano, cpf_input.strip())

            # Verifica se o resultado veio com a estrutura de erro tratada pelo cliente
            if isinstance(resultado, dict) and resultado.get("erro"):
                perfil_usuario = st.session_state.get("perfil_usuario")
                if perfil_usuario in ['a', 'g']:
                    st.error(f"⚠️ {resultado.get('mensagem')}")
                else:
                    st.warning("⚠️ O serviço de consulta de credor está temporariamente indisponível. Por favor, contate o suporte técnico.")
            else:
                # Trata o sucesso (dicionário ou lista de dados do credor)
                tem_conteudo = False
                if isinstance(resultado, dict):
                    if resultado.get("codigo") or resultado.get("cpfCnpj") or resultado.get("nome"):
                        tem_conteudo = True
                elif isinstance(resultado, list) and len(resultado) > 0:
                    tem_conteudo = True

                if tem_conteudo:
                    st.success("Dados encontrados com sucesso!")
                    if isinstance(resultado, dict):
                        st.json(resultado)
                    else:
                        df = pd.DataFrame(resultado)
                        st.dataframe(df, use_container_width=True, hide_index=True)
                else:
                    st.warning("⚠️ Nenhum registro encontrado para o identificador informado neste exercício.")

def render(conn, ano, mes, meses_lista=None):
    renderizar_consulta_credor(ano, mes)

