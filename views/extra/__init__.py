# -*- coding: utf-8 -*-
import importlib
import streamlit as st
from . import atualiza_seduc, comparador_zip


def render(conn):
  # Recarrega os módulos para refletir edições sem precisar reiniciar o app
  importlib.reload(atualiza_seduc)
  importlib.reload(comparador_zip)

  st.title("📌 Módulo Extra")

  sub_opcao = st.radio(
      "Selecione a ferramenta:",
      ["Atualiza dados SEDUC", "Comparador de Remessas ZIP"],
      horizontal=True,
  )

  st.divider()

  if sub_opcao == "Atualiza dados SEDUC":
    atualiza_seduc.render(conn)
  elif sub_opcao == "Comparador de Remessas ZIP":
    comparador_zip.render()
