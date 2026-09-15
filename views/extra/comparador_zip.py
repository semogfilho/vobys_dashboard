# -*- coding: utf-8 -*-
import zipfile
import pandas as pd
import streamlit as st


def carregar_dados_zip(file_zip):
  """Lê todos os arquivos Excel e CSV contidos em um arquivo ZIP em memória."""
  dfs = []
  if file_zip is None:
    return pd.DataFrame()

  try:
    with zipfile.ZipFile(file_zip, "r") as z:
      for filename in z.namelist():
        if filename.startswith("__MACOSX/") or filename.startswith("~$"):
          continue

        if filename.endswith((".xlsx", ".xls")):
          try:
            with z.open(filename) as f:
              df = pd.read_excel(f)
              df["__arquivo_origem__"] = filename
              dfs.append(df)
          except Exception as e:
            if "openpyxl" in str(e):
              st.error(
                  f"⚠️ Não foi possível ler o arquivo Excel '{filename}' dentro"
                  " do ZIP pois a biblioteca **openpyxl** não está instalada no"
                  " servidor."
              )
            else:
              st.error(f"Erro ao ler '{filename}': {e}")
        elif filename.endswith(".csv"):
          with z.open(filename) as f:
            try:
              df = pd.read_csv(f, sep=None, engine="python", encoding="utf-8")
            except Exception:
              f.seek(0)
              df = pd.read_csv(f, sep=";", encoding="latin1")
            df["__arquivo_origem__"] = filename
            dfs.append(df)

    if dfs:
      return pd.concat(dfs, ignore_index=True)
  except Exception as e:
    st.error(f"Erro ao processar o arquivo ZIP: {e}")

  return pd.DataFrame()


def render():
  st.subheader("🔍 Comparador de Remessas (ZIP x ZIP)")
  st.caption(
      "Identifique automaticamente novos itens/registros inseridos no arquivo"
      " ZIP mais recente em relação ao arquivo anterior."
  )

  col1, col2 = st.columns(2)

  with col1:
    st.markdown("### 📦 1. Arquivo ZIP Anterior (Base)")
    zip_antigo = st.file_uploader(
        "Selecione o ZIP antigo:", type=["zip"], key="zip_antigo"
    )

  with col2:
    st.markdown("### 📦 2. Arquivo ZIP Novo (Atual)")
    zip_novo = st.file_uploader(
        "Selecione o ZIP novo:", type=["zip"], key="zip_novo"
    )

  if zip_antigo and zip_novo:
    with st.spinner("Extraindo e comparando planilhas..."):
      df_antigo = carregar_dados_zip(zip_antigo)
      df_novo = carregar_dados_zip(zip_novo)

    if df_antigo.empty or df_novo.empty:
      st.warning(
          "⚠️ Não foi possível extrair planilhas válidas de um ou de ambos os"
          " arquivos ZIP."
      )
      return

    colunas_comuns = [
        c
        for c in df_novo.columns
        if c in df_antigo.columns and c != "__arquivo_origem__"
    ]

    st.divider()
    st.markdown("### ⚙️ Configuração da Comparação")

    opcao_chave = st.radio(
        "Critério de comparação:",
        ["Comparar por Chave Específica (ex: CPF, Matricula)", "Linha Completa"],
        horizontal=True,
    )

    if opcao_chave == "Comparar por Chave Específica (ex: CPF, Matricula)":
      chaves_selecionadas = st.multiselect(
          "Selecione a(s) coluna(s) identificadora(s):",
          options=colunas_comuns,
          default=[
              c
              for c in ["CPF", "MATRICULA", "ID", "ID_FOLHA"]
              if c in colunas_comuns
          ],
      )

      if not chaves_selecionadas:
        st.warning("Selecione pelo menos uma coluna para servir de chave.")
        return

      df_antigo["__chave__"] = (
          df_antigo[chaves_selecionadas].astype(str).agg("-".join, axis=1)
      )
      df_novo["__chave__"] = (
          df_novo[chaves_selecionadas].astype(str).agg("-".join, axis=1)
      )

      ineditos = df_novo[
          ~df_novo["__chave__"].isin(df_antigo["__chave__"])
      ].drop(columns=["__chave__"])
    else:
      merged = df_novo.merge(
          df_antigo[colunas_comuns],
          on=colunas_comuns,
          how="left",
          indicator=True,
      )
      ineditos = merged[merged["_merge"] == "left_only"].drop(
          columns=["_merge"]
      )

    m1, m2, m3 = st.columns(3)
    m1.metric("Registros no ZIP Antigo", len(df_antigo))
    m2.metric("Registros no ZIP Novo", len(df_novo))
    m3.metric("⚡ Novos Itens Inéditos", len(ineditos), delta=len(ineditos))

    st.divider()

    if not ineditos.empty:
      st.success(
          f"Encontrados **{len(ineditos)}** novos registros no arquivo"
          " recente!"
      )

      # Gera CSV formatado com Ponto e Vírgula e BOM para acentuação correta no Excel
      csv_bytes = ineditos.to_csv(
          index=False, sep=";", encoding="utf-8-sig"
      ).encode("utf-8-sig")

      st.download_button(
          label="📥 Baixar Itens Inéditos (CSV)",
          data=csv_bytes,
          file_name="relatorio_novos_itens_folha.csv",
          mime="text/csv",
      )

      st.dataframe(ineditos, width="stretch")
    else:
      st.info(
          "ℹ️ Nenhuma novidade encontrada. O ZIP novo possui exatamente os"
          " mesmos itens que o antigo."
      )

