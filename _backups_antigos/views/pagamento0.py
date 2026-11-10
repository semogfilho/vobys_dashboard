# -*- coding: utf-8 -*-
import streamlit as st
import requests
import pandas as pd
import urllib3

# Silencia os avisos de SSL Inseguro no console devido ao uso do localhost no túnel
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def render(ano_selecionado, mes_chave):
    st.title("Modulo de Pagamentos")
    st.info(f"Faturamento e processamento do periodo {mes_chave}/{ano_selecionado}.")
    
    # --- Configuração do Túnel SSH Reverso ---
    BASE_URL = "https://localhost:8443/siafe-api"
    
    # --- Função para Obter o Token de Autenticação ---
    @st.cache_data(ttl=3600)
    def obter_token_siafe():
        auth_url = f"{BASE_URL}/auth"
        
        # Busca inteligente de credenciais no secrets.toml
        cpf = st.secrets.get("SIAFE_CPF") or st.secrets.get("database", {}).get("SIAFE_CPF")
        senha = st.secrets.get("SIAFE_SENHA") or st.secrets.get("database", {}).get("SIAFE_SENHA")
        
        if not cpf or not senha:
            st.error("Erro: Credenciais SIAFE_CPF ou SIAFE_SENHA não foram encontradas no secrets.toml.")
            return None
            
        payload = {
            "usuario": str(cpf).strip(),
            "senha": str(senha).strip()
        }
        headers = {"Content-Type": "application/json"}
        
        try:
            response = requests.post(auth_url, json=payload, headers=headers, timeout=10, verify=False)
            if response.status_code == 200:
                return response.json().get("token")
            else:
                st.error(f"Falha na Autenticação SIAFE: Status {response.status_code}")
                return None
        except Exception as e:
            st.error(f"Erro ao conectar no serviço de autenticação via Túnel: {e}")
            return None

    # --- Função para Buscar os Dados via POST ---
    def buscar_dados_siafe(exercicio, token):
        ano_formatado = str(exercicio).strip()
        url = f"{BASE_URL}/folha-pagamento/pendente/{ano_formatado}"
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        # Mapeamento do nome do mês para número caso a API use filtros numéricos no corpo
        meses_map = {
            "Jan": 1, "Fev": 2, "Mar": 3, "Abr": 4, "Mai": 5, "Jun": 6,
            "Jul": 7, "Ago": 8, "Set": 9, "Out": 10, "Nov": 11, "Dez": 12
        }
        mes_numero = meses_map.get(mes_chave, 5)

        # Como o método é POST, enviamos um payload de filtros no corpo da requisição.
        # Geralmente apis de folha aceitam filtros como 'mes' ou 'mesCompetencia'.
        # Se der erro, tentaremos enviar o objeto vazio {} para trazer tudo do ano.
        payload_filtro = {
            "mes": mes_numero
        }
        
        try:
            # Alterado para requests.post enviando json=payload_filtro
            response = requests.post(url, json=payload_filtro, headers=headers, timeout=20, verify=False)
            
            # Se falhar com o filtro de mês, tenta uma segunda vez enviando corpo vazio {} para garantir
            if response.status_code != 200:
                response = requests.post(url, json={}, headers=headers, timeout=20, verify=False)
            
            if response.status_code == 200:
                return response.json()
            else:
                print(f"\n--- ERRO DETALHADO SIAFE (POST Status {response.status_code}) ---")
                print(f"URL: {url}")
                print(f"Resposta: {response.text}\n-----------------------------------\n")
                
                st.error(f"Erro na consulta do relatório: Status {response.status_code}")
                st.warning("Retorno detalhado do servidor SEFAZ:")
                if response.text:
                    st.code(response.text, language="json")
                return None
                
        except Exception as e:
            st.error(f"Falha ao conectar no endpoint do relatório via Túnel: {e}")
            return None

    # --- Fluxo de Execução Principal ---
    with st.spinner("Autenticando na API do SIAFE via Túnel..."):
        token_valido = obter_token_siafe()

    if token_valido:
        with st.spinner("Carregando dados reais do relatório..."):
            dados_brutos = buscar_dados_siafe(ano_selecionado, token_valido)

        if dados_brutos:
            df = pd.DataFrame(dados_brutos)
            
            # Ajuste/Filtro local por mês caso venham dados adicionais
            coluna_mes = 'mes' if 'mes' in df.columns else ('mesCompetencia' if 'mesCompetencia' in df.columns else None)
            if coluna_mes:
                df[coluna_mes] = df[coluna_mes].astype(str)
                df_filtrado = df[df[coluna_mes] == str(mes_chave)]
            else:
                df_filtrado = df

            st.write("### ")
            st.subheader("Relatório de Pendências")

            if not df_filtrado.empty:
                st.dataframe(df_filtrado, use_container_width=True)
                st.download_button(
                    label="📥 Exportar para CSV",
                    data=df_filtrado.to_csv(index=False).encode('utf-8'),
                    file_name=f"pendencias_SIAFE_{mes_chave}_{ano_selecionado}.csv",
                    mime="text/csv"
                )
            else:
                st.warning(f"Nenhum pagamento pendente retornado para o período {mes_chave}/{ano_selecionado}.")
    else:
        st.error("A autenticação falhou.")

