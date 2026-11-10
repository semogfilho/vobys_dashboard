# -*- coding: utf-8 -*-
import streamlit as st
import requests
import urllib3
import pandas as pd

st.set_page_config(layout="wide")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def carregar_dados(ano):
    BASE_URL = "https://localhost:8443/siafe-api"
    try:
        r_auth = requests.post(f"{BASE_URL}/auth", 
                               json={"usuario": st.secrets.get("SIAFE_CPF", ""), 
                                     "senha": st.secrets.get("SIAFE_SENHA", "")}, verify=False)
        token = r_auth.json().get("token")
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        r = requests.post(f"{BASE_URL}/folha-pagamento/pendente/{ano}", json={}, headers=headers, verify=False)
        
        if r.status_code == 200:
            df = pd.DataFrame(r.json())
            df_explode = df.explode('itens').reset_index(drop=True)
            itens_norm = pd.json_normalize(df_explode['itens']).add_prefix('item_')
            df_final = pd.concat([df_explode.drop(columns=['itens']), itens_norm], axis=1)
            
            # Garantir colunas numéricas
            for col in ['item_valorBruto', 'item_valorLiquido']:
                df_final[col] = pd.to_numeric(df_final[col], errors='coerce').fillna(0.0)
            
            st.session_state['df_final'] = df_final
    except Exception as e:
        st.error(f"Erro: {e}")

def main():
    st.title("📊 Painel de Pagamentos - Master/Detail (Estruturado)")
    
    if st.button("🔄 Atualizar Base de Dados"):
        carregar_dados("2026")
        st.rerun()

    if 'df_final' not in st.session_state:
        st.info("Clique em atualizar para carregar os dados.")
        return

    df = st.session_state['df_final']

    col_esq, col_dir = st.columns([1, 3])

    with col_esq:
        st.subheader("Unidades Gestoras")
        # Agrupamento considerando as duas chaves
        resumo = df.groupby(['codigoUgSistemaExterno', 'codigoUg']).size().reset_index(name='QUANTIDADE')
        resumo.columns = ['CODIGO_SEFAZ', 'CODIGO_UG', 'QUANTIDADE']
        
        # Exibe a tabela selecionável
        evento = st.dataframe(
            resumo, 
            use_container_width=True, 
            hide_index=True, 
            selection_mode="single-row", 
            on_select="rerun"
        )
        
        # Lógica de seleção composta
        if len(evento.selection.rows) > 0:
            row = resumo.iloc[evento.selection.rows[0]]
            sefaz_sel = row['CODIGO_SEFAZ']
            ug_sel = row['CODIGO_UG']
        else:
            sefaz_sel = resumo.iloc[0]['CODIGO_SEFAZ']
            ug_sel = resumo.iloc[0]['CODIGO_UG']

    with col_dir:
        st.subheader(f"Detalhes - UG: {ug_sel} | SEFAZ: {sefaz_sel}")
        
        # FILTRO COMPOSTO: Filtra pelas duas colunas simultaneamente
        detalhes = df[
            (df['codigoUg'].astype(str) == str(ug_sel)) & 
            (df['codigoUgSistemaExterno'].astype(str) == str(sefaz_sel))
        ].copy()
        
        exibicao = detalhes.copy()
        exibicao['item_valorBruto'] = exibicao['item_valorBruto'].apply(lambda x: f"R$ {x:,.2f}")
        exibicao['item_valorLiquido'] = exibicao['item_valorLiquido'].apply(lambda x: f"R$ {x:,.2f}")
        
        st.table(exibicao[['item_nome', 'item_matricula', 'item_valorBruto', 'item_valorLiquido', 'item_statusPgto']])

if __name__ == "__main__":
    main()

