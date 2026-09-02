import unicodedata
import pandas as pd
import streamlit as st


def remover_acentos(texto):
  """Remove acentos e caracteres especiais de uma string."""
  if not isinstance(texto, str):
    return str(texto)
  nfkd = unicodedata.normalize("NFKD", texto)
  return "".join([c for c in nfkd if not unicodedata.combining(c)])


def formatar_cpf(val):
  """Formata uma string numérica de 11 dígitos no padrão XXX.XXX.XXX-XX."""
  val_limpo = "".join(filter(str.isdigit, str(val))).zfill(11)
  if len(val_limpo) == 11:
    return (
        f"{val_limpo[:3]}.{val_limpo[3:6]}.{val_limpo[6:9]}-{val_limpo[9:]}"
    )
  return val


def limpar_id(val):
  """Padroniza IDs numéricos removendo .0 e espaçamentos."""
  if pd.isna(val) or val is None:
    return None
  val_str = str(val).strip()
  if val_str.endswith(".0"):
    val_str = val_str[:-2]
  if val_str in ["nan", "None", ""]:
    return None
  return val_str


def render(conn):
  st.title("⚡ Módulo Extra: Atualização de Dados Bancários (Modo Pandas)")
  st.markdown(
      "Carregue a planilha Excel/CSV para cruzar os dados em memória com o"
      " Oracle, tratar pontuações e gerar o arquivo final atualizado."
  )

  # 1. Área para carregar o arquivo de entrada
  uploaded_file = st.file_uploader(
      "Envie a planilha de entrada (.xlsx, .xls ou .csv)",
      type=["xlsx", "xls", "csv"],
  )

  if uploaded_file is not None:
    try:
      # Lendo a planilha de entrada forçando dtype string para preservar zeros à esquerda
      if uploaded_file.name.endswith(".csv"):
        try:
          df_entrada = pd.read_csv(
              uploaded_file,
              sep=None,
              engine="python",
              encoding="utf-8",
              dtype=str,
          )
        except UnicodeDecodeError:
          uploaded_file.seek(0)
          df_entrada = pd.read_csv(
              uploaded_file,
              sep=None,
              engine="python",
              encoding="latin-1",
              dtype=str,
          )
      else:
        df_entrada = pd.read_excel(uploaded_file, dtype=str)

      # Normalização robusta das colunas da planilha de entrada
      df_entrada.columns = [
          remover_acentos(str(col))
          .replace("\ufeff", "")
          .strip()
          .lower()
          .replace(" ", "_")
          for col in df_entrada.columns
      ]

      st.success("Planilha carregada com sucesso!")

      # 2. Botão para processar
      if st.button("Processar e Gerar Arquivo Final"):
        with st.spinner(
            "Lendo dados, consultando Oracle e realizando cruzamento em"
            " memória..."
        ):

          # Identifica as colunas de forma flexível
          col_mun = next(
              (c for c in df_entrada.columns if "municip" in c),
              df_entrada.columns[0],
          )
          col_nom = next(
              (c for c in df_entrada.columns if "nome" in c),
              df_entrada.columns[1],
          )
          col_ban = next(
              (c for c in df_entrada.columns if "banco" in c),
              df_entrada.columns[2],
          )
          col_cpf = next(
              (c for c in df_entrada.columns if "cpf" in c),
              df_entrada.columns[3],
          )

          # Tratamento e limpeza dos dados de entrada (com tratamento para NAN/None no município)
          df_entrada["MUNICIPIO"] = (
              df_entrada[col_mun]
              .astype(str)
              .str.strip()
              .str.upper()
              .replace(["NAN", "NONE", "NAT", ""], None)
          )
          df_entrada["NOME"] = (
              df_entrada[col_nom].astype(str).str.strip().str.upper()
          )
          df_entrada["DESCRICAO_BANCO"] = (
              df_entrada[col_ban].astype(str).str.strip()
          )

          # Limpeza rigorosa do CPF da entrada garantindo 11 dígitos numéricos (zfill)
          df_entrada["CPF_LIMPO"] = (
              df_entrada[col_cpf]
              .astype(str)
              .str.replace(r"[^\d]", "", regex=True)
              .str.strip()
              .str.zfill(11)
          )

          # Carregando as tabelas do Oracle
          df_doc = pd.read_sql(
              "SELECT id_pessoa, cpf_pessoa FROM SW_PUBLICO.pessoa_doc_cpf",
              con=conn,
          )
          df_doc.columns = [str(c).lower().strip() for c in df_doc.columns]
          df_doc = df_doc.drop_duplicates(subset=["cpf_pessoa"])

          # Padroniza id_pessoa e cpf_pessoa do doc
          df_doc["id_pessoa"] = df_doc["id_pessoa"].apply(limpar_id)
          df_doc["CPF_LIMPO"] = (
              df_doc["cpf_pessoa"]
              .astype(str)
              .str.replace(r"[^\d]", "", regex=True)
              .str.strip()
              .str.zfill(11)
          )

          df_vinculo = pd.read_sql(
              "SELECT id_pessoa, cod_institucional FROM SW_seduc.pessoa_vinculo",
              con=conn,
          )
          df_vinculo.columns = [str(c).lower().strip() for c in df_vinculo.columns]
          df_vinculo["id_pessoa"] = df_vinculo["id_pessoa"].apply(limpar_id)

          df_vinculo_agg = (
              df_vinculo.groupby("id_pessoa")["cod_institucional"]
              .apply(lambda x: ", ".join(x.dropna().astype(str).unique()))
              .reset_index(name="COD_INSTITUCIONAL")
          )

          df_banco = pd.read_sql(
              "SELECT id_pessoa, id_agencia, conta_corrente FROM"
              " SW_PUBLICO.Pessoa_Banco WHERE data_fim IS NULL",
              con=conn,
          )
          df_banco.columns = [str(c).lower().strip() for c in df_banco.columns]
          df_banco["id_pessoa"] = df_banco["id_pessoa"].apply(limpar_id)
          df_banco["id_agencia"] = df_banco["id_agencia"].apply(limpar_id)

          df_agencia = pd.read_sql(
              "SELECT id_agencia, id_banco, cod_agencia FROM"
              " SW_PUBLICO.RHB_BANCO_AGENCIA",
              con=conn,
          )
          df_agencia.columns = [str(c).lower().strip() for c in df_agencia.columns]
          df_agencia["id_agencia"] = df_agencia["id_agencia"].apply(limpar_id)
          df_agencia["id_banco"] = df_agencia["id_banco"].apply(limpar_id)

          df_bancos_ref = pd.read_sql(
              "SELECT id_banco, cod_banco FROM SW_PUBLICO.RHB_BANCO", con=conn
          )
          df_bancos_ref.columns = [
              str(c).lower().strip() for c in df_bancos_ref.columns
          ]
          df_bancos_ref["id_banco"] = df_bancos_ref["id_banco"].apply(limpar_id)

          # Formata o código do banco com zeros à esquerda (ex: 001) eliminando decimais .0
          df_bancos_ref["cod_banco"] = (
              df_bancos_ref["cod_banco"]
              .astype(str)
              .str.replace(r"\.0$", "", regex=True)
              .str.strip()
              .str.zfill(3)
          )

          # Montando a árvore de dados bancários via merge em memória com tipos idênticos
          df_banco_completo = df_banco.merge(
              df_agencia, on="id_agencia", how="left"
          )
          df_banco_completo = df_banco_completo.merge(
              df_bancos_ref, on="id_banco", how="left"
          )

          # Realizando os cruzamentos replicando fielmente o seu antigo_select
          # 1. Tabela doc (trazendo o id_pessoa através do CPF limpo)
          df_resultado = df_entrada.merge(
              df_doc[["id_pessoa", "CPF_LIMPO"]], on="CPF_LIMPO", how="left"
          )
          df_resultado["id_pessoa"] = df_resultado["id_pessoa"].apply(limpar_id)

          # 2. Tabela de vínculo institucional agrupada
          df_resultado = df_resultado.merge(
              df_vinculo_agg, on="id_pessoa", how="left"
          )

          # 3. Tabelas bancárias unidas por id_pessoa
          df_resultado = df_resultado.merge(
              df_banco_completo[
                  ["id_pessoa", "cod_banco", "cod_agencia", "conta_corrente"]
              ],
              on="id_pessoa",
              how="left",
          )

          # Aplica a máscara formatada no CPF final (XXX.XXX.XXX-XX)
          df_resultado["CPF_FORMATADO"] = df_resultado["CPF_LIMPO"].apply(
              formatar_cpf
          )

          # Renomeando colunas finais para manter o padrão exato esperado
          df_resultado = df_resultado.rename(
              columns={
                  "id_pessoa": "ID_PESSOA",
                  "cod_banco": "CODIGOBANCO",
                  "cod_agencia": "CODIGOAGENCIA",
                  "conta_corrente": "NUMEROCONTA",
                  "CPF_FORMATADO": "CPF",
          }
          )

          # Selecionando apenas as colunas finais desejadas na ordem correta
          colunas_finais = [
              "MUNICIPIO",
              "NOME",
              "DESCRICAO_BANCO",
              "CPF",
              "ID_PESSOA",
              "CODIGOBANCO",
              "CODIGOAGENCIA",
              "NUMEROCONTA",
              "COD_INSTITUCIONAL",
          ]

          # Garante que todas as colunas existam no dataframe final
          for col in colunas_finais:
            if col not in df_resultado.columns:
              df_resultado[col] = None

          df_saida = df_resultado[colunas_finais]

          # Estatística de cruzamento para feedback
          total_encontrados = (
              df_saida["ID_PESSOA"].notnull()
              & (df_saida["ID_PESSOA"] != "None")
              & (df_saida["ID_PESSOA"] != "")
          ).sum()
          st.info(
              f"Cruzamento concluído! {total_encontrados} de"
              f" {len(df_saida)} registros encontrados no Oracle."
          )

          # Convertendo o resultado para CSV em memória
          processed_data = df_saida.to_csv(
              index=False, sep=";", encoding="utf-8-sig"
          ).encode("utf-8-sig")

        st.success("Processamento e cruzamento em memória concluídos com êxito!")
        st.write("### Prévia do Resultado Gerado (Todos os registros):")

        # Exibe a tabela inteira com o ID_PESSOA visível
        st.dataframe(df_saida, use_container_width=True)

        # Botão de download do arquivo CSV final
        st.download_button(
            label="📥 Baixar Planilha Final (CSV)",
            data=processed_data,
            file_name="Dados_bancario_faltantes_trabalhada.csv",
            mime="text/csv",
        )

    except Exception as e:
      st.error(
          f"Ocorreu um erro ao processar o arquivo e cruzar os dados: {e}"
      )

