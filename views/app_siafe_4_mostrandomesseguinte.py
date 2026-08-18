# -*- coding: utf-8 -*-
import streamlit as st
import requests
import urllib3
import pandas as pd

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

@st.cache_data(show_spinner="Buscando dados...")
def buscar_dados_siafe(ano):
    BASE_URL = "https://localhost:8443/siafe-api"
    try:
        r_auth = requests.post(f"{BASE_URL}/auth", json={"usuario": st.secrets.get("SIAFE_CPF", ""), "senha": st.secrets.get("SIAFE_SENHA", "")}, verify=False)
        token = r_auth.json().get("token")
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        r = requests.post(f"{BASE_URL}/folha-pagamento/pendente/{ano}", json={}, headers=headers, verify=False)
        if r.status_code == 200:
            df = pd.DataFrame(r.json())
            df_explode = df.explode('itens').reset_index(drop=True)
            itens_norm = pd.json_normalize(df_explode['itens']).add_prefix('item_')
            df_final = pd.concat([df_explode.drop(columns=['itens']), itens_norm], axis=1)
            return df_final
        return pd.DataFrame()
    except Exception:
        return pd.DataFrame()

def main(conn, ano_selecionado, mes_chave, meses_lista):
    num_mes_busca = str(int(mes_chave) + 1).zfill(2)
    competencia_busca = f"{num_mes_busca}/{ano_selecionado}"
    
    st.title(f"📊 Painel de Pagamentos ({meses_lista[mes_chave]}/{ano_selecionado})")

    df_total = buscar_dados_siafe(ano_selecionado)
    if df_total.empty:
        st.warning("Nenhum dado encontrado.")
        return

    df_mes = df_total[df_total['competencia'].astype(str) == competencia_busca].copy()

    if df_mes.empty:
        st.info(f"Nenhum registro para {competencia_busca}.")
        return

    col_esq, col_dir = st.columns([1, 4])

    with col_esq:
        st.subheader("Unidades Gestoras")
        resumo = df_mes.groupby(['codigoUgSistemaExterno', 'codigoUg']).size().reset_index(name='QUANTIDADE')
        resumo.columns = ['CODIGO_SEFAZ', 'CODIGO_UG', 'QUANTIDADE']
        
        # --- INSPEÇÃO DA LISTA DE UGs ---
        with st.expander("🔍 JSON da Lista de Unidades Gestoras"):
            st.json(resumo.to_json(orient='records', force_ascii=False))
            
        evento = st.dataframe(resumo, use_container_width=True, hide_index=True, 
                              selection_mode="single-row", on_select="rerun")
        
        # Seleção lógica
        idx = evento.selection.rows[0] if len(evento.selection.rows) > 0 else 0
        sefaz_sel = str(resumo.iloc[idx]['CODIGO_SEFAZ'])
        ug_sel = str(resumo.iloc[idx]['CODIGO_UG'])

    with col_dir:
        st.subheader(f"Detalhes - UG: {ug_sel} | SEFAZ: {sefaz_sel}")
        
        detalhes = df_mes[
            (df_mes['codigoUg'].astype(str) == ug_sel) & 
            (df_mes['codigoUgSistemaExterno'].astype(str) == sefaz_sel)
        ].copy()
        
        st.table(detalhes[['item_nome', 'item_matricula', 'item_dataPagamento', 'item_valorBruto']])
        
        with st.expander("🔍 Auditoria da Seleção (UG/SEFAZ)"):
            st.write(f"Buscando por SEFAZ: '{sefaz_sel}' e UG: '{ug_sel}'")
            st.json(detalhes.to_json(orient='records', force_ascii=False))

