# -*- coding: utf-8 -*-
import streamlit as st
import requests
import urllib3
import pandas as pd

# Desabilita avisos de SSL para chamadas internas
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Mapa ROBUSTO que aceita tanto texto quanto números (int e str)
# Isso corrige o erro de deslocamento de índice (off-by-one)
MAPA_MESES_ROBUSTO = {
    "Jan": "01", "Fev": "02", "Mar": "03", "Abr": "04", "Mai": "05", "Jun": "06",
    "Jul": "07", "Ago": "08", "Set": "09", "Out": "10", "Nov": "11", "Dez": "12",
    1: "01", 2: "02", 3: "03", 4: "04", 5: "05", 6: "06",
    7: "07", 8: "08", 9: "09", 10: "10", 11: "11", 12: "12",
    "1": "01", "2": "02", "3": "03", "4": "04", "5": "05", "6": "06",
    "7": "07", "8": "08", "9": "09", "10": "10", "11": "11", "12": "12"
}

@st.cache_data(show_spinner="Sincronizando com a API...")
def buscar_dados_siafe(ano):
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
            return df_final
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Erro na comunicação com a API: {e}")
        return pd.DataFrame()

def main(conn, ano_selecionado, mes_chave, meses_lista):
    # Tratamento para converter mes_chave de string numérica para int, se necessário
    try:
        chave_formatada = int(mes_chave)
    except (ValueError, TypeError):
        chave_formatada = mes_chave

    # Conversão segura usando o mapa robusto
    mes_num_str = MAPA_MESES_ROBUSTO.get(chave_formatada, "01")
    competencia_busca = f"{mes_num_str}/{ano_selecionado}"
    
    st.title(f"📊 Painel de Pagamentos ({mes_num_str}/{ano_selecionado})")
    st.sidebar.info(f"Seleção: {mes_chave} → Buscando: {competencia_busca}")

    df_total = buscar_dados_siafe(ano_selecionado)
    if df_total.empty:
        st.warning("Nenhum dado encontrado na base para este ano.")
        return

    # Filtro rígido pela competência calculada
    df_mes = df_total[df_total['competencia'].astype(str) == competencia_busca].copy()

    if df_mes.empty:
        st.info(f"Nenhum registro para a competência {competencia_busca}.")
        return

    col_esq, col_dir = st.columns([1, 4])

    with col_esq:
        st.subheader("Unidades Gestoras")
        resumo = df_mes.groupby(['codigoUgSistemaExterno', 'codigoUg']).size().reset_index(name='QTD')
        resumo.columns = ['CODIGO_SEFAZ', 'CODIGO_UG', 'QTD']
        
        evento = st.dataframe(resumo, use_container_width=True, hide_index=True, 
                              selection_mode="single-row", on_select="rerun")
        
        # Seleção de UG
        idx = evento.selection.rows[0] if len(evento.selection.rows) > 0 else 0
        sefaz_sel = str(resumo.iloc[idx]['CODIGO_SEFAZ'])
        ug_sel = str(resumo.iloc[idx]['CODIGO_UG'])

    with col_dir:
        st.subheader(f"Detalhes - UG: {ug_sel} | SEFAZ: {sefaz_sel}")
        detalhes = df_mes[
            (df_mes['codigoUg'].astype(str) == ug_sel) & 
            (df_mes['codigoUgSistemaExterno'].astype(str) == sefaz_sel)
        ].copy()
        
        st.table(detalhes[['item_nome', 'item_matricula', 'item_dataPagamento', 
                           'item_descricaoStatusPgto', 'item_valorBruto', 'item_valorLiquido']])
        
        with st.expander("🔍 Auditoria da Seleção"):
            st.json(detalhes.to_json(orient='records', force_ascii=False))

