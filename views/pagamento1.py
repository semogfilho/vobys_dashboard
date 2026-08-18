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
            st.error("Erro: Credenciais SIAFE_CPF ou SIAFE_SENHA não configuradas no secrets.toml.")
            return None
            
        payload = {"usuario": str(cpf).strip(), "senha": str(senha).strip()}
        headers = {"Content-Type": "application/json"}
        
        try:
            response = requests.post(auth_url, json=payload, headers=headers, timeout=10, verify=False)
            if response.status_code == 200:
                return response.json().get("token")
            return None
        except Exception:
            return None

    # --- Função para Buscar os Dados via POST ---
    def buscar_dados_siafe(exercicio, token):
        ano_formatado = str(exercicio).strip()
        url = f"{BASE_URL}/folha-pagamento/pendente/{ano_formatado}"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        
        try:
            response = requests.post(url, json={}, headers=headers, timeout=25, verify=False)
            if response.status_code == 200:
                return response.json()
            return None
        except Exception:
            return None

    # --- Fluxo de Execução Principal ---
    with st.spinner("Buscando dados da Folha no SIAFE..."):
        token_valido = obter_token_siafe()

    if token_valido:
        dados_brutos = buscar_dados_siafe(ano_selecionado, token_valido)

        if dados_brutos:
            df_bruto = pd.DataFrame(dados_brutos)
            
            # --- Força a conversão e limpeza de tipos para evitar quebras ---
            for col in ['mes', 'competencia', 'codigoUg', 'anoExercicioOrigem']:
                if col in df_bruto.columns:
                    df_bruto[col] = df_bruto[col].astype(str).str.strip()
            
            if 'mes' in df_bruto.columns:
                df_bruto['mes'] = df_bruto['mes'].str.upper()

            # Mapeamento dinâmico que aceita tanto chaves por extenso quanto numéricas (Ex: "Jan", "1" ou "01")
            meses_map_texto = {
                "Jan": "JANEIRO", "Fev": "FEVEREIRO", "Mar": "MARCO", "Abr": "ABRIL",
                "Mai": "MAIO", "Jun": "JUNHO", "Jul": "JULHO", "Ago": "AGOSTO",
                "Set": "SETEMBRO", "Out": "OUTUBRO", "Nov": "NOVEMBRO", "Dez": "DEZEMBRO",
                "1": "JANEIRO", "2": "FEVEREIRO", "3": "MARCO", "4": "ABRIL",
                "5": "MAIO", "6": "JUNHO", "7": "JULHO", "8": "AGOSTO",
                "9": "SETEMBRO", "10": "OUTUBRO", "11": "NOVEMBRO", "12": "DEZEMBRO"
            }
            
            meses_map_num = {
                "Jan": "01", "Fev": "02", "Mar": "03", "Abr": "04", "Mai": "05", "Jun": "06",
                "Jul": "07", "Ago": "08", "Set": "09", "Out": "10", "Nov": "11", "Dez": "12",
                "1": "01", "2": "02", "3": "03", "4": "04", "5": "05", "6": "06",
                "7": "07", "8": "08", "9": "09", "10": "10", "11": "11", "12": "12"
            }
            
            # Converte o valor que vem do componente lateral para string pura
            chave_busca = str(mes_chave).strip()
            txt_mes = meses_map_texto.get(chave_busca, chave_busca.upper())
            num_comp = f"{meses_map_num.get(chave_busca, chave_busca.zfill(2))}/{ano_selecionado}"
            
            # Executa o filtro inteligente na massa de dados
            condicao_mes = (df_bruto['mes'] == txt_mes) if 'mes' in df_bruto.columns else False
            condicao_comp = (df_bruto['competencia'] == num_comp) if 'competencia' in df_bruto.columns else False
            
            df_filtrado = df_bruto[condicao_mes | condicao_comp].copy()

            if not df_filtrado.empty:
                # Quantidade de registros pendentes encontrados para o mês selecionado
                total_registros = len(df_filtrado)
                st.metric(f"Total de Registros em {txt_mes}", f"{total_registros:,}".replace(',', '.'))
                st.markdown("---")

                # TELA 1: Visão Geral por Unidade Gestora
                st.subheader("🏢 Resumo por Unidade Gestora (UG)")
                col_tp = 'tipoProcessamento' if 'tipoProcessamento' in df_filtrado.columns else ('tipoFolha' if 'tipoFolha' in df_filtrado.columns else None)
                
                if col_tp:
                    df_resumo = df_filtrado.groupby(['anoExercicioOrigem', 'codigoUg', col_tp]).size().reset_index(name='Total')
                    df_resumo.columns = ['Exercício Origem', 'Cód. UG', 'Tipo de Processamento', 'Total de Registros']
                else:
                    df_resumo = df_filtrado.groupby(['anoExercicioOrigem', 'codigoUg']).size().reset_index(name='Total')
                    df_resumo.columns = ['Exercício Origem', 'Cód. UG', 'Total de Registros']
                
                st.dataframe(df_resumo, use_container_width=True, hide_index=True)
                st.markdown("---")

                # TELA 2: Listagem Detalhada
                st.subheader("🔍 Listagem Analítica Detalhada")
                lista_ugs = sorted(df_filtrado['codigoUg'].unique())
                ug_selecionada = st.selectbox("Selecione uma Cód. UG:", lista_ugs)

                if ug_selecionada:
                    df_detalhe = df_filtrado[df_filtrado['codigoUg'] == str(ug_selecionada).strip()].copy()
                    
                    colunas_traducao = {
                        'anoExercicioOrigem': 'Exercício Origem',
                        'codigoUg': 'Cód. UG',
                        'mes': 'Mês',
                        'competencia': 'Competência',
                        'tipoProcessamento': 'Tipo do Processamento',
                        'tipoFolha': 'Tipo da Folha'
                    }
                    
                    cols_presentes = {k: v for k, v in colunas_traducao.items() if k in df_detalhe.columns}
                    df_detalhe_final = df_detalhe[list(cols_presentes.keys())].rename(columns=cols_presentes)
                    
                    st.dataframe(df_detalhe_final, use_container_width=True, hide_index=True)
            else:
                st.warning(f"Nenhum faturamento pendente foi encontrado para o período {mes_chave}/{ano_selecionado}.")
        else:
            st.error("O servidor SIAFE não retornou dados para o ano selecionado.")
    else:
        st.error("A autenticação falhou. Verifique o seu túnel SSH.")

