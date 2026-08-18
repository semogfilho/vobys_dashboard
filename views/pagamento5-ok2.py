# -*- coding: utf-8 -*-
import streamlit as st
import requests
import pandas as pd
import urllib3

# Silencia os avisos de SSL Inseguro devido ao uso do localhost no túnel
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def render(ano_selecionado, mes_chave):
    st.title("📊 Módulo de Pagamentos - SIAFE")
    st.info(f"Faturamento e processamento do período: {mes_chave}/{ano_selecionado}.")
    
    BASE_URL = "https://localhost:8443/siafe-api"
    
    # --- Função para Obter o Token de Autenticação ---
    @st.cache_data(ttl=3600)
    def obter_token_siafe():
        auth_url = f"{BASE_URL}/auth"
        cpf = st.secrets.get("SIAFE_CPF") or st.secrets.get("database", {}).get("SIAFE_CPF")
        senha = st.secrets.get("SIAFE_SENHA") or st.secrets.get("database", {}).get("SIAFE_SENHA")
        
        if not cpf or not senha:
            return "ERRO_CONFIG: Credenciais não encontradas no secrets.toml"
            
        payload = {"usuario": str(cpf).strip(), "senha": str(senha).strip()}
        headers = {"Content-Type": "application/json"}
        
        try:
            response = requests.post(auth_url, json=payload, headers=headers, timeout=30, verify=False)
            if response.status_code == 200:
                return response.json().get("token")
            else:
                return f"ERRO_API_{response.status_code}"
        except Exception as e:
            return f"ERRO_CONEXAO: {str(e)}"

    # --- Função para Buscar os Dados ---
    def buscar_dados_siafe(exercicio, token):
        url = f"{BASE_URL}/folha-pagamento/pendente/{str(exercicio).strip()}"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        try:
            response = requests.post(url, json={}, headers=headers, timeout=30, verify=False)
            return response.json() if response.status_code == 200 else None
        except:
            return None

    # --- Fluxo Principal ---
    token_resultado = obter_token_siafe()
    
    # Verifica se o resultado é um token válido (não começa com ERRO)
    if not token_resultado or str(token_resultado).startswith("ERRO"):
        st.error(f"Falha na autenticação: {token_resultado}")
        st.info("Verifique se o túnel SSH está ativo com 'ssh -N tunnel-siafe'.")
        return

    dados_brutos = buscar_dados_siafe(ano_selecionado, token_resultado)
    if not dados_brutos:
        st.error("O servidor não retornou dados para este período.")
        return

    df_bruto = pd.DataFrame(dados_brutos)
    
    # Limpeza
    for col in ['mes', 'codigoUg']:
        if col in df_bruto.columns: df_bruto[col] = df_bruto[col].astype(str).str.strip().str.upper()

    st.metric("Total de Ocorrências", len(df_bruto))
    
    # Tabela Resumo
    st.subheader("🏢 Resumo por Unidade Gestora (UG)")
    resumo = df_bruto.groupby(['codigoUg']).size().reset_index(name='Total')
    st.dataframe(resumo, use_container_width=True)

    # Detalhes Individuais
    st.subheader("🔍 Detalhes Individuais dos Colaboradores")
    lista_ugs = sorted(df_bruto['codigoUg'].unique())
    ug_selecionada = st.selectbox("Selecione uma Cód. UG:", lista_ugs)

    if ug_selecionada:
        df_detalhe = df_bruto[df_bruto['codigoUg'] == str(ug_selecionada).strip()].copy()
        
        df_analitico_final = pd.DataFrame()
        for idx, row in df_detalhe.iterrows():
            itens = row.get('itens')
            if isinstance(itens, list) and len(itens) > 0:
                df_temp = pd.json_normalize(itens)
                for col in df_detalhe.columns:
                    if col != 'itens': df_temp[col] = row[col]
                df_analitico_final = pd.concat([df_analitico_final, df_temp], ignore_index=True)

        df_exibicao = df_analitico_final if not df_analitico_final.empty else df_detalhe
        
        # Exibição na tela
        st.dataframe(df_exibicao, use_container_width=True, hide_index=True, height=500)

        # Exportação
        csv = df_exibicao.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig')
        st.download_button(label=f"📥 Exportar Registros da UG {ug_selecionada}", 
                           data=csv, file_name=f"UG_{ug_selecionada}.csv", mime="text/csv")

if __name__ == "__main__":
    render("2026", "Abr")

