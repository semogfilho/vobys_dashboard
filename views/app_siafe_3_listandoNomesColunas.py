# -*- coding: utf-8 -*-
import streamlit as st
import requests
import urllib3
import pandas as pd

st.set_page_config(layout="wide")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

@st.cache_data(show_spinner="Buscando dados no SIAFE...")
def buscar_dados_siafe(ano, mes):
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
            
            for col in ['item_valorBruto', 'item_valorLiquido']:
                df_final[col] = pd.to_numeric(df_final[col], errors='coerce').fillna(0.0)
            return df_final
    except Exception as e:
        st.error(f"Erro: {e}")
        return pd.DataFrame()

def main():
    ano = st.session_state.get('ano', '2026')
    mes = st.session_state.get('mes', 'JANEIRO')

    st.title(f"📊 Painel de Pagamentos ({ano}/{mes})")
    df = buscar_dados_siafe(ano, mes)

    if df.empty:
        st.warning("Nenhum dado encontrado.")
        return

    # Bloco para o DBA inspecionar os nomes das colunas
    with st.expander("🔍 Inspecionar Colunas do DataFrame (Use estes nomes abaixo)"):
        st.write(df.columns.tolist())

    col_esq, col_dir = st.columns([1, 4])

    with col_esq:
        st.subheader("Unidades Gestoras")
        resumo = df.groupby(['codigoUgSistemaExterno', 'codigoUg']).size().reset_index(name='QUANTIDADE')
        resumo.columns = ['CODIGO_SEFAZ', 'CODIGO_UG', 'QUANTIDADE']
        
        evento = st.dataframe(resumo, use_container_width=True, hide_index=True, 
                              selection_mode="single-row", on_select="rerun")
        
        if len(evento.selection.rows) > 0:
            row = resumo.iloc[evento.selection.rows[0]]
            sefaz_sel, ug_sel = row['CODIGO_SEFAZ'], row['CODIGO_UG']
        else:
            sefaz_sel, ug_sel = resumo.iloc[0]['CODIGO_SEFAZ'], resumo.iloc[0]['CODIGO_UG']

    with col_dir:
        st.subheader(f"Detalhes - UG: {ug_sel} | SEFAZ: {sefaz_sel}")
        
        detalhes = df[
            (df['codigoUg'].astype(str) == str(ug_sel)) & 
            (df['codigoUgSistemaExterno'].astype(str) == str(sefaz_sel))
        ].copy()
        
        exibicao = detalhes.copy()
        exibicao['item_valorBruto'] = exibicao['item_valorBruto'].apply(lambda x: f"R$ {x:,.2f}")
        exibicao['item_valorLiquido'] = exibicao['item_valorLiquido'].apply(lambda x: f"R$ {x:,.2f}")
        
        # AJUSTE ESTA LISTA ABAIXO COM OS NOMES QUE APARECEREM NO EXPANDER:
        colunas_exibicao = [
            'item_nome', 'item_matricula', 'item_mes', 'item_data', 
            'item_descricao', 'item_valorBruto', 'item_valorLiquido', 'item_statusPgto'
        ]
        
        st.table(exibicao[colunas_exibicao])

if __name__ == "__main__":
    main()

