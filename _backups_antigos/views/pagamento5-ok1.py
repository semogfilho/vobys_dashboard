# -*- coding: utf-8 -*-
import streamlit as st
import requests
import pandas as pd
import urllib3
import plotly.express as px

# Silencia avisos de SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def render(ano_selecionado, mes_chave):
    st.title("📊 Módulo de Pagamentos - SIAFE")
    st.info(f"Faturamento e processamento do período: {mes_chave}/{ano_selecionado}.")
    
    BASE_URL = "https://localhost:8443/siafe-api"
    
    @st.cache_data(ttl=3600)
    def obter_token_siafe():
        auth_url = f"{BASE_URL}/auth"
        cpf = st.secrets.get("SIAFE_CPF") or st.secrets.get("database", {}).get("SIAFE_CPF")
        senha = st.secrets.get("SIAFE_SENHA") or st.secrets.get("database", {}).get("SIAFE_SENHA")
        
        if not cpf or not senha:
            return None
            
        payload = {"usuario": str(cpf).strip(), "senha": str(senha).strip()}
        headers = {"Content-Type": "application/json"}
        
        try:
            # Timeout de 30s para garantir estabilidade no túnel
            response = requests.post(auth_url, json=payload, headers=headers, timeout=30, verify=False)
            return response.json().get("token") if response.status_code == 200 else None
        except Exception:
            return None

    def buscar_dados_siafe(exercicio, token):
        url = f"{BASE_URL}/folha-pagamento/pendente/{str(exercicio).strip()}"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        try:
            response = requests.post(url, json={}, headers=headers, timeout=30, verify=False)
            return response.json() if response.status_code == 200 else None
        except Exception:
            return None

    # --- Execução Principal com Proteção de Variável ---
    with st.spinner("Autenticando e buscando dados..."):
        token_valido = obter_token_siafe()

    if token_valido:
        dados_brutos = buscar_dados_siafe(ano_selecionado, token_valido)

        if dados_brutos:
            df_filtrado = pd.DataFrame(dados_brutos)
            
            # KPIs de Destaque
            col1, col2, col3 = st.columns(3)
            col1.metric("Total Registros", f"{len(df_filtrado):,}")
            # Verificação segura de colunas
            valor_total = df_filtrado['valorLiquido'].sum() if 'valorLiquido' in df_filtrado.columns else 0
            col2.metric("Valor Total", f"R$ {valor_total:,.2f}")
            erros = df_filtrado[df_filtrado.get('statusPtg') == 'ERRO_NO_PGTO'].shape[0] if 'statusPtg' in df_filtrado.columns else 0
            col3.metric("Erros", erros)
            st.markdown("---")

            # Treemap Visual
            st.subheader("🏢 Distribuição de Volume por UG")
            if not df_filtrado.empty and 'codigoUg' in df_filtrado.columns:
                fig = px.treemap(df_filtrado, path=['codigoUg'], values='valorLiquido' if 'valorLiquido' in df_filtrado.columns else None)
                st.plotly_chart(fig, use_container_width=True)

            # Tabela Analítica
            st.subheader("🔍 Detalhes Individuais")
            st.data_editor(df_filtrado, use_container_width=True, hide_index=True)
        else:
            st.error("Erro ao buscar dados. O servidor retornou vazio ou falhou.")
    else:
        st.error("Falha na autenticação. Verifique o seu túnel SSH (está rodando?) e suas credenciais.")

if __name__ == "__main__":
    render("2026", "04")

