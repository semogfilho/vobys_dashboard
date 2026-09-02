import io
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
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


def gerar_xlsx_nativo(df):
  """Gera um arquivo .xlsx real usando apenas bibliotecas padrão do Python (zipfile),

  forçando a coluna CODIGOBANCO a ser texto puro com zeros à esquerda.
  """
  output = io.BytesIO()

  headers = list(df.columns)
  rows = df.values.tolist()

  col_banco_idx = -1
  for i, h in enumerate(headers):
    if h == "CODIGOBANCO":
      col_banco_idx = i
      break

  content_types_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
    <Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
        <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
        <Default Extension="xml" ContentType="application/xml"/>
        <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
        <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
        <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
    </Types>"""

  rels_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
    <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
        <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
    </Relationships>"""

  workbook_rels_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
    <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
        <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
    </Relationships>"""

  workbook_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
    <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
        <sheets>
            <sheet name="Dados Bancarios" sheetId="1" r:id="rId1"/>
        </sheets>
    </workbook>"""

  styles_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
    <styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
        <fonts count="1">
            <font><sz val="11"/><name val="Calibri"/></font>
        </fonts>
        <fills count="2">
            <fill><patternFill patternType="none"/></fill>
            <fill><patternFill patternType="gray125"/></fill>
        </fills>
        <borders count="1">
            <border><left/><right/><top/><bottom/><diagonal/></border>
        </borders>
        <cellStyleXfs count="1">
            <xf numFmtId="0" fontId="0" fillId="0" borderId="0"/>
        </cellStyleXfs>
        <cellXfs count="1">
            <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
        </cellXfs>
        <cellStyles count="1">
            <cellStyle name="Normal" xfId="0" builtinId="0"/>
        </cellStyles>
    </styleSheet>"""

  def escape_xml(val):
    if val is None:
      return ""
    return (
        str(val)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )

  sheet_data = []
  sheet_data.append('<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">')
  sheet_data.append("<sheetData>")

  sheet_data.append('<row r="1">')
  for col_idx, h in enumerate(headers, start=1):
    col_letter = chr(64 + col_idx) if col_idx <= 26 else "I"
    sheet_data.append(
        f'<c r="{col_letter}1" t="inlineStr"><is><t>{escape_xml(h)}</t></is></c>'
    )
  sheet_data.append("</row>")

  for row_idx, row_values in enumerate(rows, start=2):
    sheet_data.append(f'<row r="{row_idx}">')
    for col_idx, val in enumerate(row_values, start=1):
      col_letter = chr(64 + col_idx) if col_idx <= 26 else "I"
      val_str = "" if pd.isna(val) else str(val).strip()

      if col_idx - 1 == col_banco_idx and val_str != "":
        val_str = val_str.zfill(3)

      sheet_data.append(
          f'<c r="{col_letter}{row_idx}"'
          f' t="inlineStr"><is><t>{escape_xml(val_str)}</t></is></c>'
      )
    sheet_data.append("</row>")

  sheet_data.append("</sheetData>")
  sheet_data.append("</worksheet>")
  worksheet_xml = "".join(sheet_data)

  with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
    zf.writestr("[Content_Types].xml", content_types_xml)
    zf.writestr("_rels/.rels", rels_xml)
    zf.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml)
    zf.writestr("xl/workbook.xml", workbook_xml)
    zf.writestr("xl/styles.xml", styles_xml)
    zf.writestr("xl/worksheets/sheet1.xml", worksheet_xml)

  return output.getvalue()


def render(conn):
  st.title("⚡ Módulo Extra: Atualização de Dados Bancários")
  st.markdown(
      "Carregue a planilha de entrada (preferencialmente no formato **CSV**)"
      " para cruzar os dados em memória com o Oracle e gerar o arquivo"
      " atualizado."
  )

  uploaded_file = st.file_uploader(
      "Envie a planilha de entrada (.csv)", type=["csv", "xlsx", "xls"]
  )

  if uploaded_file is not None:
    try:
      # Lendo o arquivo de entrada
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
        try:
          df_entrada = pd.read_excel(uploaded_file, dtype=str)
        except Exception as excel_err:
          if "openpyxl" in str(excel_err):
            st.error(
                "⚠️ Não foi possível ler arquivos do Excel (.xlsx/.xls) por"
                " falta de uma dependência opcional no ambiente. Por favor,"
                " **salve e envie sua planilha no formato CSV** para prosseguir"
                " sem problemas!"
            )
            return
          else:
            raise excel_err

      df_entrada.columns = [
          remover_acentos(str(col))
          .replace("\ufeff", "")
          .strip()
          .lower()
          .replace(" ", "_")
          for col in df_entrada.columns
      ]

      st.success("Planilha carregada com sucesso!")

      if st.button("Processar e Gerar Arquivo Final"):
        with st.spinner(
            "Lendo dados, consultando Oracle e realizando cruzamento em"
            " memória..."
        ):

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

          df_entrada["MUNICIPIO"] = (
              df_entrada[col_mun]
              .astype(str)
              .str.strip()
              .str.upper()
              .replace(["NAN", "NONE", "NAT", ""], "")
          )
          df_entrada["NOME"] = (
              df_entrada[col_nom].astype(str).str.strip().str.upper()
          )
          df_entrada["DESCRICAO_BANCO"] = (
              df_entrada[col_ban].astype(str).str.strip()
          )

          df_entrada["CPF_LIMPO"] = (
              df_entrada[col_cpf]
              .astype(str)
              .str.replace(r"[^\d]", "", regex=True)
              .str.strip()
              .str.zfill(11)
          )

          df_doc = pd.read_sql(
              "SELECT id_pessoa, cpf_pessoa FROM SW_PUBLICO.pessoa_doc_cpf",
              con=conn,
          )
          df_doc.columns = [str(c).lower().strip() for c in df_doc.columns]
          df_doc = df_doc.drop_duplicates(subset=["cpf_pessoa"])

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
          df_agencia["id_banco"] = df_banco["id_banco"].apply(limpar_id)

          df_bancos_ref = pd.read_sql(
              "SELECT id_banco, cod_banco FROM SW_PUBLICO.RHB_BANCO", con=conn
          )
          df_bancos_ref.columns = [
              str(c).lower().strip() for c in df_bancos_ref.columns
          ]
          df_bancos_ref["id_banco"] = df_bancos_ref["id_banco"].apply(limpar_id)

          def formatar_banco(val):
            if pd.isna(val) or val is None:
              return ""
            val_str = (
                str(val)
                .replace(".0", "")
                .strip()
                .replace("nan", "")
                .replace("None", "")
            )
            if val_str == "":
              return ""
            return val_str.zfill(3)

          df_bancos_ref["cod_banco"] = df_bancos_ref["cod_banco"].apply(
              formatar_banco
          )

          df_banco_completo = df_banco.merge(
              df_agencia, on="id_agencia", how="left"
          )
          df_banco_completo = df_banco_completo.merge(
              df_bancos_ref, on="id_banco", how="left"
          )

          df_resultado = df_entrada.merge(
              df_doc[["id_pessoa", "CPF_LIMPO"]], on="CPF_LIMPO", how="left"
          )
          df_resultado["id_pessoa"] = df_resultado["id_pessoa"].apply(limpar_id)

          df_resultado = df_resultado.merge(
              df_vinculo_agg, on="id_pessoa", how="left"
          )

          df_resultado = df_resultado.merge(
              df_banco_completo[
                  ["id_pessoa", "cod_banco", "cod_agencia", "conta_corrente"]
              ],
              on="id_pessoa",
              how="left",
          )

          df_resultado["CPF_FORMATADO"] = df_resultado["CPF_LIMPO"].apply(
              formatar_cpf
          )

          df_resultado = df_resultado.rename(
              columns={
                  "id_pessoa": "ID_PESSOA",
                  "cod_banco": "CODIGOBANCO",
                  "cod_agencia": "CODIGOAGENCIA",
                  "conta_corrente": "NUMEROCONTA",
                  "CPF_FORMATADO": "CPF",
          }
          )

          df_resultado["CODIGOBANCO"] = df_resultado["CODIGOBANCO"].apply(
              formatar_banco
          )

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

          for col in colunas_finais:
            if col not in df_resultado.columns:
              df_resultado[col] = ""
            else:
              df_resultado[col] = (
                  df_resultado[col]
                  .fillna("")
                  .replace(["nan", "None", "NAT"], "")
                  .astype(str)
              )

          df_saida = df_resultado[colunas_finais]

          total_encontrados = (
              (df_saida["ID_PESSOA"] != "")
              & (df_saida["ID_PESSOA"].notnull())
          ).sum()
          st.info(
              f"Cruzamento concluído! {total_encontrados} de"
              f" {len(df_saida)} registros encontrados no Oracle."
          )

          processed_data = gerar_xlsx_nativo(df_saida)

        st.success("Processamento e cruzamento em memória concluídos com êxito!")
        st.write("### Prévia do Resultado Gerado (Todos os registros):")

        st.dataframe(df_saida, use_container_width=True)

        st.download_button(
            label="📥 Baixar Planilha Final (Excel)",
            data=processed_data,
            file_name="Dados_bancario_faltantes_trabalhada.xlsx",
            mime=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
        )

    except Exception as e:
      if "openpyxl" in str(e):
        st.error(
            "⚠️ Não foi possível ler arquivos do Excel (.xlsx/.xls) por falta de"
            " uma dependência opcional no ambiente. Por favor, **salve e envie"
            " sua planilha no formato CSV** para prosseguir sem problemas!"
        )
      else:
        st.error(
            f"Ocorreu um erro ao processar o arquivo e cruzar os dados: {e}"
        )

