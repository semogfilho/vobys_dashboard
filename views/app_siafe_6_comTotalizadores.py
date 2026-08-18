# -*- coding: utf-8 -*-
import streamlit as st
import requests
import urllib3
import pandas as pd

# Desabilita avisos de SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Mapa ROBUSTO para evitar erros de índice
MAPA_MESES_ROBUSTO = {
    "Jan": "01", "Fev": "02", "Mar": "03", "Abr": "04", "Mai": "05", "Jun": "06",
    "Jul": "07", "Ago": "08", "Set": "09", "Out": "10", "Nov": "11", "Dez": "12",
    1: "01", 2: "02", 3: "03", 4: "04", 5: "05", 6: "06",
    7: "07", 8: "08", 9: "09", 10: "10", 11: "11", 12: "12",
    "1": "01", "2": "02", "3": "03", "4": "04", "5": "05", "6": "06",
    "7": "07", "8": "08", "9": "09", "10": "10", "11": "11", "12": "12"
}

def formatar_moeda_br(valor):
    """Formata float para o padrão brasileiro: R$ X.XXX,XX"""
    try:
        return f"R$ {float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return valor

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
    try:
        chave_formatada = int(mes_chave)
    except (ValueError, TypeError):
        chave_formatada = mes_chave

    mes_num_str = MAPA_MESES_ROBUSTO.get(chave_formatada, "01")
    competencia_busca = f"{mes_num_str}/{ano_selecionado}"
    
    st.title(f"📊 Painel de Pagamentos ({mes_num_str}/{ano_selecionado})")
    
    df_total = buscar_dados_siafe(ano_selecionado)
    if df_total.empty:
        st.warning("Nenhum dado encontrado.")
        return

    df_mes = df_total[df_total['competencia'].astype(str) == competencia_busca].copy()

    col_esq, col_dir = st.columns([1, 4])

    with col_esq:
        st.subheader("Unidades Gestoras")
        resumo = df_mes.groupby(['codigoUgSistemaExterno', 'codigoUg']).agg(
            QTD=('codigoUg', 'size'),
            VALOR_BRUTO=('item_valorBruto', 'sum')
        ).reset_index()
        
        total_qtd = resumo['QTD'].sum()
        total_valor = resumo['VALOR_BRUTO'].sum()
        linha_total_master = pd.DataFrame({
            'codigoUgSistemaExterno': ['TOTAL'],
            'codigoUg': [''],
            'QTD': [total_qtd],
            'VALOR_BRUTO': [total_valor]
        })
        
        df_display = pd.concat([resumo, linha_total_master], ignore_index=True)
        df_display['VALOR_BRUTO'] = df_display['VALOR_BRUTO'].apply(formatar_moeda_br)
        
        evento = st.dataframe(df_display, use_container_width=True, hide_index=True, 
                              selection_mode="single-row", on_select="rerun")
        
        idx = evento.selection.rows[0] if len(evento.selection.rows) > 0 else 0
        
        if idx < len(resumo):
            sefaz_sel = str(resumo.iloc[idx]['codigoUgSistemaExterno'])
            ug_sel = str(resumo.iloc[idx]['codigoUg'])
            modo_filtro = "UNIDADE"
        else:
            sefaz_sel, ug_sel = "", ""
            modo_filtro = "TOTAL"

    with col_dir:
        if modo_filtro == "UNIDADE":
            st.subheader(f"Detalhes - UG: {ug_sel} | SEFAZ: {sefaz_sel}")
            detalhes = df_mes[
                (df_mes['codigoUg'].astype(str) == ug_sel) & 
                (df_mes['codigoUgSistemaExterno'].astype(str) == sefaz_sel)
            ].copy()
        else:
            st.subheader("Detalhes - Todos os Registros do Mês")
            detalhes = df_mes.copy()
            
        detalhes['item_valorBruto'] = detalhes['item_valorBruto'].apply(formatar_moeda_br)
        detalhes['item_valorLiquido'] = detalhes['item_valorLiquido'].apply(formatar_moeda_br)
        
        # Reset no índice para evitar a coluna fantasma
        tabela_final = detalhes.reset_index(drop=True)
        
        colunas_exibicao = [
            'codigo', 'codigoExterno', 'tipoProcessamento', 'item_nome', 'item_matricula', 
            'item_dataPagamento', 'item_descricaoStatusPgto', 'item_valorBruto', 'item_valorLiquido'
        ]
        colunas_validas = [c for c in colunas_exibicao if c in tabela_final.columns]
        
        st.table(tabela_final[colunas_validas])
        
        with st.expander("🔍 Auditoria da Seleção"):
            st.json(detalhes.to_json(orient='records', force_ascii=False))

