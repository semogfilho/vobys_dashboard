# -*- coding: utf-8 -*-
import streamlit as st
import requests
import urllib3
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

# Desabilita avisos de SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Mapa ROBUSTO
MAPA_MESES_ROBUSTO = {
    "Jan": "01", "Fev": "02", "Mar": "03", "Abr": "04", "Mai": "05", "Jun": "06",
    "Jul": "07", "Ago": "08", "Set": "09", "Out": "10", "Nov": "11", "Dez": "12",
    1: "01", 2: "02", 3: "03", 4: "04", 5: "05", 6: "06",
    7: "07", 8: "08", 9: "09", 10: "10", 11: "11", 12: "12",
    "1": "01", "2": "02", "3": "03", "4": "04", "5": "05", "6": "06",
    "7": "07", "8": "08", "9": "09", "10": "10", "11": "11", "12": "12"
}

def formatar_moeda_br(valor):
    try:
        return f"R$ {float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return valor

@st.cache_data(show_spinner="Sincronizando com a API...")
def buscar_dados_siafe(ano):
    BASE_URL = "https://127.0.0.1:8443/siafe-api"
    session = requests.Session()
    session.verify = False  
    session.timeout = 10
    session.headers.update({"Host": "tesouro.sefaz.pi.gov.br", "Content-Type": "application/json"})
    try:
        r_auth = session.post(f"{BASE_URL}/auth", json={"usuario": st.secrets.get("SIAFE_CPF", ""), "senha": st.secrets.get("SIAFE_SENHA", "")})
        r_auth.raise_for_status()
        token = r_auth.json().get("token")
        session.headers.update({"Authorization": f"Bearer {token}"})
        r = session.post(f"{BASE_URL}/folha-pagamento/pendente/{ano}", json={})
        r.raise_for_status()
        df = pd.DataFrame(r.json())
        df_explode = df.explode('itens').reset_index(drop=True)
        itens_norm = pd.json_normalize(df_explode['itens']).add_prefix('item_')
        df_final = pd.concat([df_explode.drop(columns=['itens']), itens_norm], axis=1)
        return df_final.rename(columns={'codigoUgSistemaExterno': 'Cod_Sefaz'})
    except Exception as e:
        st.error(f"⚠️ Erro na API SIAFE: {e}")
        return pd.DataFrame()

def main(conn, ano_selecionado, mes_chave, meses_lista):
    # CSS para forçar alinhamento de topo e remover espaços indesejados
    st.markdown("""
        <style>
            [data-testid="column"] { display: flex; flex-direction: column; align-items: flex-start !important; }
            div[data-testid="stHorizontalBlock"] { align-items: flex-start !important; }
            div[data-testid="stDataFrame"] { margin-top: 0px !important; }
        </style>
    """, unsafe_allow_html=True)

    mes_num_str = MAPA_MESES_ROBUSTO.get(mes_chave, "01")
    competencia_busca = f"{mes_num_str}/{ano_selecionado}"
    
    st.title(f"📊 Painel de Pagamentos Pendentes ({competencia_busca})")
    
    df_total = buscar_dados_siafe(ano_selecionado)
    if df_total.empty:
        st.warning("Nenhum dado encontrado.")
        return

    df_total['categoria'] = df_total['Cod_Sefaz'].apply(lambda x: "FOLHA" if str(x).isdigit() and int(x) <= 999 else "PPF")
    cat_selecionada = st.radio("Selecione a Categoria:", ["FOLHA", "PPF"], horizontal=True)
    df_mes = df_total[(df_total['competencia'].astype(str) == competencia_busca) & (df_total['categoria'] == cat_selecionada)].copy()

    col_esq, col_dir = st.columns([1, 4])

    with col_esq:
        st.subheader(f"Unidades Gestoras ({cat_selecionada})")
        resumo = df_mes.groupby(['Cod_Sefaz', 'codigoUg']).agg(
            QTD=('codigoUg', 'size'), VALOR_BRUTO=('item_valorBruto', 'sum')
        ).reset_index()
        
        linha_total = pd.DataFrame({'Cod_Sefaz': ['TOTAL'], 'codigoUg': [''], 
                                   'QTD': [resumo['QTD'].sum()], 'VALOR_BRUTO': [resumo['VALOR_BRUTO'].sum()]})
        df_display = pd.concat([resumo, linha_total], ignore_index=True)
        df_display['VALOR_BRUTO'] = df_display['VALOR_BRUTO'].apply(formatar_moeda_br)
        
        evento = st.dataframe(df_display, use_container_width=True, hide_index=True, 
                              selection_mode="multi-row", on_select="rerun")
        
        selected_rows = evento.selection.rows
        modo_filtro = "TOTAL" if (not selected_rows or len(resumo) in selected_rows) else "UNIDADE"
        sel_data = resumo.iloc[selected_rows]
        listas_sefaz = sel_data['Cod_Sefaz'].astype(str).tolist()
        listas_ug = sel_data['codigoUg'].astype(str).tolist()

    with col_dir:
        st.subheader(f"Detalhes - {modo_filtro}")
        detalhes = df_mes[df_mes.apply(lambda x: (str(x['Cod_Sefaz']), str(x['codigoUg'])) 
                                      in zip(listas_sefaz, listas_ug), axis=1)].copy() if modo_filtro == "UNIDADE" else df_mes.copy()
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Registros", len(detalhes))
        c2.metric("Total Bruto", formatar_moeda_br(detalhes['item_valorBruto'].sum()))
        c3.metric("Total Líquido", formatar_moeda_br(detalhes['item_valorLiquido'].sum()))

        df_exibicao = detalhes.copy()
        df_exibicao['item_valorBruto'] = df_exibicao['item_valorBruto'].apply(formatar_moeda_br)
        df_exibicao['item_valorLiquido'] = df_exibicao['item_valorLiquido'].apply(formatar_moeda_br)
        
# --- AQUI VOCÊ RENOMEIA A COLUNA ---
        #df_exibicao = df_exibicao.rename(columns={'item_matricula': 'Matricula'})
        #df_exibicao = df_exibicao.rename(columns={'item_valorBruto': 'ValorBruto'})
        #df_exibicao = df_exibicao.rename(columns={'item_valorLiquido': 'ValorLiquido'})
        #df_exibicao = df_exibicao.rename(columns={'item_nome': 'Nome'})
        #df_exibicao = df_exibicao.rename(columns={'item_descricaoStatusPgto': 'DescricaoStatusPgto'})
        #df_exibicao = df_exibicao.rename(columns={'item_dataPagamento': 'DataPagamento'})
            
        cols = ['codigo', 'codigoExterno', 'tipoProcessamento', 'item_nome', 'item_matricula', 
                'item_dataPagamento', 'item_descricaoStatusPgto', 'item_valorBruto', 'item_valorLiquido']
        st.dataframe(df_exibicao[[c for c in cols if c in df_exibicao.columns]], use_container_width=True, hide_index=True)
        
        with st.expander("🔍 Auditoria da Seleção"):
            st.json(detalhes.to_json(orient='records', force_ascii=False))

def render(conn, ano_selecionado, mes_chave, meses_disponiveis):
    # --- AJUSTES DE LAYOUT E ESTILIZAÇÃO ---
    st.markdown("""
        <style>
            .block-container { padding-top: 1.5rem !important; }
            div[data-testid="stVerticalBlock"] > div:first-child { margin-top: 0px !important; }
        </style>
    """, unsafe_allow_html=True)

    st.title(f"📊 Painel de Controle de Folhas")
    st.markdown(f"**Distribuição volumétrica:** {meses_disponiveis[mes_chave]}/{ano_selecionado}")
    st.markdown("---")

    cursor = conn.cursor()
    sql = f"""
        SELECT 
            CASE 
                WHEN STATUS_VOBYS = 'P' THEN 'PENDENTE'
                WHEN STATUS_VOBYS = 'T' THEN 'TRANSMITIDO'
                WHEN STATUS_VOBYS = 'A' THEN 'ABERTO'
                WHEN STATUS_VOBYS = 'F' THEN 'FECHADO'
                WHEN STATUS_VOBYS = 'I' THEN 'INCONSISTENCIA'
                WHEN STATUS_VOBYS = 'O' THEN 'OUTRAS'
                WHEN STATUS_VOBYS = 'E' THEN 'ERRO'
                ELSE 'ABERTO'
            END AS STATUS,
            COUNT(*) AS QTD
        FROM sw_publico.SIAFE_EVENTO_INTEGRACAO
        WHERE ANO = {ano_selecionado} AND MES = {int(mes_chave)}
        GROUP BY STATUS_VOBYS
    """

    try:
        cursor.execute(sql)
        rows = cursor.fetchall()
        
        if not rows:
            st.info("Nenhum dado encontrado para o período.")
            return
        
        df = pd.DataFrame(rows, columns=['STATUS', 'QTD'])
        total_geral = df['QTD'].sum()
        
        # --- LAYOUT EM COLUNAS ---
        col_grafico, col_metricas = st.columns([1.5, 1.0])
        
        with col_grafico:
            st.write("### Composição do Status")
            fig, ax = plt.subplots(figsize=(8, 4))
            ax.bar(df['STATUS'], df['QTD'], color='#1a73e8')
            ax.set_xticklabels(df['STATUS'], rotation=45, ha='right')
            st.pyplot(fig)

        with col_metricas:
            st.markdown("### 📋 Resumo Operacional")
            
            st.markdown(f"""
                <div style="background-color: #e8f0fe; padding: 15px; border-radius: 10px; border: 1px solid #d2e3fc;">
                    <small>Total Geral</small><br>
                    <span style="font-size: 24px; font-weight: bold;">{total_geral}</span>
                </div>
            """, unsafe_allow_html=True)
            
            st.markdown("<br>", unsafe_allow_html=True)
            
            total_falhas = df[df['STATUS'].isin(['ERRO', 'INCONSISTENCIA'])]['QTD'].sum()
            if total_falhas > 0:
                st.warning(f"⚠️ **{total_falhas} inconsistências detectadas.**")
            else:
                st.success("✅ **Saúde Operacional: 100%**")

    except Exception as e:
        st.error(f"Erro ao processar dados gráficos: {e}")
    finally:
        cursor.close()

