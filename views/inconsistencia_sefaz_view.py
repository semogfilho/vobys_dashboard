# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
from datetime import datetime
from sefaz_client import requisitar_sefaz

def consultar_inconsistencia_sefaz(ano, mes):
    # Endpoint de inconsistências da folha de pagamento na SEFAZ
    endpoint = f"folha-pagamento/inconsistencia-pag/{ano}/{mes}"
    
    try:
        # Utiliza parâmetros nomeados para evitar conflitos na assinatura da função
        resultado = requisitar_sefaz(endpoint=endpoint, metodo="GET")
        return resultado
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

            # Validação unificada de retorno com erro do sefaz_client
            if isinstance(data, dict) and data.get("erro"):
                err_msg = data.get("mensagem", "Erro desconhecido na API")
                perfil_usuario = st.session_state.get("perfil_usuario")
                if perfil_usuario in ['a', 'g']:
                    st.error(f"⚠️ {err_msg}")
                else:
                    st.warning("⚠️ O serviço de integração SEFAZ está temporariamente indisponível. Por favor, contate o suporte técnico.")
                return

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


def render(conn, ano, mes, meses_lista=None, *args, **kwargs):
    import auth_ui
    renderizar_inconsistencia_sefaz(int(ano), int(mes), auth_ui)

