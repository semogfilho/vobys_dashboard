# -*- coding: utf-8 -*-
import importlib
import datetime
import os
import sys
import pandas as pd
import streamlit as st

# Garante que a pasta views está no path para importar o auth_ui
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE_DIR, "views"))
sys.path.insert(0, os.path.join(BASE_DIR, ".streamlit"))

import auth_ui  # <-- Importação necessária

# 1. Configuração inicial do estado de autenticação
if "autenticado" not in st.session_state:
  st.session_state["autenticado"] = False

# 2. Se NÃO estiver autenticado, exibe a tela de login
# Se NÃO estiver autenticado, exibe a tela de login idêntica à do app.py
if not st.session_state.get("autenticado", False):
    st.markdown("""
        <style>
            /* Oculta a barra lateral no login */
            [data-testid="stSidebar"] { display: none !important; }
            [data-testid="collapsedControl"] { display: none !important; }

            /* Fundo da tela limpo e suave */
            .stApp {
                background-color: #f1f5f9 !important;
            }

            /* Container principal centralizado e compacto */
            .main .block-container, 
            [data-testid="stMainBlockContainer"],
            [data-testid="stAppViewBlockContainer"] {
                max-width: 380px !important;
                margin: 0 auto !important;
                padding-top: 4rem !important;
                padding-bottom: 2rem !important;
                padding-left: 1rem !important;
                padding-right: 1rem !important;
            }

            /* Retângulo central com tom suave */
            div[data-testid="stVerticalBlockBorderWrapper"] {
                background-color: #f0f4f8 !important;
                border: 1px solid #cbd5e1 !important;
                border-radius: 14px !important;
                box-shadow: 0 10px 20px rgba(0, 0, 0, 0.05) !important;
                padding: 1.2rem 1rem !important;
            }

            /* Cor e legibilidade dos textos internos do cartão */
            div[data-testid="stVerticalBlockBorderWrapper"] p,
            div[data-testid="stVerticalBlockBorderWrapper"] label,
            div[data-testid="stVerticalBlockBorderWrapper"] span {
                color: #334155 !important;
            }

            /* Título NTGD mantendo destaque */
            div[data-testid="stVerticalBlockBorderWrapper"] h1,
            div[data-testid="stVerticalBlockBorderWrapper"] h2,
            div[data-testid="stVerticalBlockBorderWrapper"] h3 {
                color: #d32f2f !important;
            }

            /* Espaçamentos verticais internos */
            div[data-testid="stVerticalBlock"] {
                gap: 0.5rem !important;
            }

            /* Inputs com fundo branco para contraste limpo */
            .stTextInput > div > div > input {
                border-radius: 6px !important;
                border: 1px solid #cbd5e1 !important;
                padding: 8px 10px !important;
                background-color: #ffffff !important;
                color: #0f172a !important;
                font-size: 0.88rem !important;
            }

            /* Estilo dos Botões para ocuparem largura total e tom vermelho */
            div.stButton > button {
                width: 100% !important;
                border-radius: 6px !important;
                font-size: 0.9rem !important;
                padding: 0.45rem !important;
            }

            /* Botão Entrar */
            div.stButton > button:first-of-type {
                background-color: #d32f2f !important;
                border: none !important;
                box-shadow: 0 4px 10px rgba(211, 47, 47, 0.25) !important;
            }
            div.stButton > button:first-of-type * {
                color: #ffffff !important;
                font-weight: 600 !important;
            }
            div.stButton > button:first-of-type:hover {
                background-color: #b71c1c !important;
            }
        </style>
    """, unsafe_allow_html=True)

    # Indicador superior
    st.markdown(
        "<div style='text-align: center; color: #64748b; font-size: 0.82rem; font-weight: 600; margin-bottom: 0.5rem; letter-spacing: 0.5px;'>"
        "🔒 SISTEMA NTGD"
        "</div>",
        unsafe_allow_html=True
    )

    # Bloco centralizado idêntico ao app.py
    _, col_center, _ = st.columns([0.01, 0.98, 0.01])
    with col_center:
        with st.container(border=True):
            auth_ui.gerenciar_sessao_fluxo()

    st.stop()

# ==============================================================================
# DAQUI PARA BAIXO FICA O CONTEÚDO NORMAL DO app_menu.py APÓS O LOGIN
# ==============================================================================
# Configuração da página em modo wide
st.set_page_config(
    page_title="NTGD - Gestão Dinâmica",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Garante que a pasta views esteja no path para importação correta
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE_DIR, "views"))

# ---------------------------------------------------------
# CONEXÃO COM O BANCO DE DADOS ORACLE
# ---------------------------------------------------------
try:
    from database import get_connection
except ImportError:
    def get_connection():
        return None


def obter_conexao():
    try:
        return get_connection()
    except Exception:
        return None


def obter_usuario_logado():
    """Retorna o usuário logado real associado ao perfil de Administrador."""
    return {"usuario": "jose.gomes", "perfil_id": 1, "perfil_nome": "Administrador"}



def carregar_modulos_do_banco(perfil_id):
    """Consulta no banco os módulos liberados para o perfil do usuário."""
    conn = obter_conexao()
    if not conn:
        st.error("Não foi possível estabelecer conexão com o banco de dados.")
        return []

    query = """
        SELECT m.id, m.nome_menu, m.arquivo_view, m.icone, m.ordem
        FROM josegomes.modulo m
        INNER JOIN josegomes.perfil_modulo pm ON m.id = pm.id_modulo
        WHERE pm.id_perfil = :perfil_id AND m.ativo = 1
        ORDER BY m.ordem ASC
    """
    try:
        df = pd.read_sql(query, conn, params={"perfil_id": perfil_id})
        conn.close()
        return df.to_dict('records')
    except Exception as e:
        st.error(f"Erro ao consultar módulos no banco: {e}")
        if conn:
            conn.close()
        return []


def carregar_todos_modulos():
    conn = obter_conexao()
    if not conn:
        return pd.DataFrame()
    query = "SELECT id, nome_menu, arquivo_view, ordem FROM josegomes.modulo ORDER BY ordem ASC"
    df = pd.read_sql(query, conn)
    conn.close()
    return df


def carregar_todos_perfis():
    conn = obter_conexao()
    if not conn:
        return pd.DataFrame()
    query = "SELECT id, descricao FROM josegomes.perfil ORDER BY id ASC"
    df = pd.read_sql(query, conn)
    conn.close()
    return df


def carregar_modulos_por_perfil_id(perfil_id):
    conn = obter_conexao()
    if not conn:
        return []
    query = "SELECT id_modulo FROM josegomes.perfil_modulo WHERE id_perfil = :perfil_id"
    cursor = conn.cursor()
    cursor.execute(query, {"perfil_id": perfil_id})
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return [r[0] for r in rows]


# ---------------------------------------------------------
# TELA DE GESTÃO DE PERFIS E MÓDULOS (CRUD Real)
# ---------------------------------------------------------
def render_gestao_perfil():
    st.title("⚙️ Gestão de Módulos, Perfis e Acessos")
    st.markdown("Gerencie os módulos do sistema, crie novos perfis e associe as permissões em tempo real.")

    tab1, tab2, tab3 = st.tabs(["📦 Cadastro de Módulos", "👤 Cadastro de Perfis", "🔗 Atribuição (Perfil x Módulos)"])

    # --- ABA 1: MÓDULOS ---
    with tab1:
        col_cad, col_list = st.columns([1, 1.5])
        
        with col_cad:
            st.subheader("Novo Módulo")
            with st.form("form_modulo"):
                nome_menu = st.text_input("Nome no Menu (ex: ⚙️ Gestão de Perfis)")
                arquivo_view = st.text_input("Caminho View (ex: gestao_perfil)")
                ordem = st.number_input("Ordem", min_value=1, value=10)
                
                submitted = st.form_submit_button("Salvar Módulo")
                if submitted:
                    if nome_menu and arquivo_view:
                        conn = obter_conexao()
                        if conn:
                            try:
                                cursor = conn.cursor()
                                cursor.execute(
                                    "INSERT INTO josegomes.modulo (nome_menu, arquivo_view, ordem, ativo) VALUES (:1, :2, :3, 1)",
                                    (nome_menu, arquivo_view, ordem)
                                )
                                conn.commit()
                                cursor.close()
                                conn.close()
                                st.success(f"Módulo '{nome_menu}' cadastrado com sucesso!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erro ao inserir módulo: {e}")
                        else:
                            st.error("Falha na conexão com o banco.")
                    else:
                        st.warning("Preencha todos os campos obrigatórios.")

        with col_list:
            st.subheader("Módulos Cadastrados")
            df_mod = carregar_todos_modulos()
            if not df_mod.empty:
                st.dataframe(df_mod, use_container_width=True, hide_index=True)
            else:
                st.info("Nenhum módulo cadastrado.")

    # --- ABA 2: PERFIS ---
    with tab2:
        col_cad_p, col_list_p = st.columns([1, 1.5])
        
        with col_cad_p:
            st.subheader("Novo Perfil")
            with st.form("form_perfil"):
                desc_perfil = st.text_input("Descrição (ex: Supervisor)")
                
                submitted_perfil = st.form_submit_button("Salvar Perfil")
                if submitted_perfil:
                    if desc_perfil:
                        conn = obter_conexao()
                        if conn:
                            try:
                                cursor = conn.cursor()
                                cursor.execute(
                                    "INSERT INTO josegomes.perfil (descricao) VALUES (:1)",
                                    (desc_perfil,)
                                )
                                conn.commit()
                                cursor.close()
                                conn.close()
                                st.success(f"Perfil '{desc_perfil}' cadastrado com sucesso!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erro ao inserir perfil: {e}")
                        else:
                            st.error("Falha na conexão com o banco.")
                    else:
                        st.warning("Informe a descrição do perfil.")

        with col_list_p:
            st.subheader("Perfis Existentes")
            df_perf = carregar_todos_perfis()
            if not df_perf.empty:
                st.dataframe(df_perf, use_container_width=True, hide_index=True)
            else:
                st.info("Nenhum perfil cadastrado.")

    # --- ABA 3: ATRIBUIÇÃO (PERFIL X MÓDULOS) ---
    with tab3:
        st.subheader("Vincular Módulos aos Perfis")
        df_perf = carregar_todos_perfis()
        df_mod = carregar_todos_modulos()

        if df_perf.empty or df_mod.empty:
            st.warning("Cadastre ao menos um perfil e um módulo antes de fazer associações.")
            return

        perfil_map = {row['DESCRICAO']: row['ID'] for _, row in df_perf.iterrows()}
        perfil_escolhido = st.selectbox("Selecione o Perfil:", options=list(perfil_map.keys()))
        id_perfil_sel = perfil_map[perfil_escolhido]

        modulos_atuais = carregar_modulos_por_perfil_id(id_perfil_sel)

        modulo_map = {f"{row['ID']} - {row['NOME_MENU']} ({row['ARQUIVO_VIEW']})": row['ID'] for _, row in df_mod.iterrows()}
        default_mod_labels = [k for k, v in modulo_map.items() if v in modulos_atuais]

        modulos_selecionados_labels = st.multiselect(
            "Selecione os módulos permitidos para este perfil:",
            options=list(modulo_map.keys()),
            default=default_mod_labels
        )

        if st.button("Salvar Permissões"):
            conn = obter_conexao()
            if conn:
                try:
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM josegomes.perfil_modulo WHERE id_perfil = :1", (id_perfil_sel,))
                    
                    for label in modulos_selecionados_labels:
                        id_mod = modulo_map[label]
                        cursor.execute(
                            "INSERT INTO josegomes.perfil_modulo (id_perfil, id_modulo) VALUES (:1, :2)",
                            (id_perfil_sel, id_mod)
                        )
                    
                    conn.commit()
                    cursor.close()
                    conn.close()
                    st.success("Permissões atualizadas com sucesso!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao salvar permissões: {e}")


# ---------------------------------------------------------
# FLUXO PRINCIPAL DO APP MENU
# ---------------------------------------------------------
def main():
    usuario_atual = obter_usuario_logado()

    st.sidebar.title("NTGD - Sandbox")
    st.sidebar.markdown(f"**Usuário:** {usuario_atual['usuario']}")
    st.sidebar.markdown(f"**Perfil:** {usuario_atual['perfil_nome']}")
    st.sidebar.divider()

    # --- SELETOR DE ANO E MÊS (Idêntico ao app.py) ---
    hoje = datetime.date.today()
    if hoje.day >= 21:
        if hoje.month == 12:
            mes_sugerido, ano_sugerido = 1, hoje.year + 1
        else:
            mes_sugerido, ano_sugerido = hoje.month + 1, hoje.year
    else:
        mes_sugerido, ano_sugerido = hoje.month, hoje.year

    lista_anos = [2026, 2025, 2024, 2023]
    if ano_sugerido not in lista_anos: 
        lista_anos.insert(0, ano_sugerido)
    
    ano = st.sidebar.selectbox("Ano:", lista_anos, index=lista_anos.index(ano_sugerido))
    meses_lista = {1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun", 7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez", 13: "13º"}
    mes = st.sidebar.selectbox("Mês:", list(meses_lista.keys()), index=mes_sugerido - 1, format_func=lambda x: meses_lista[x])
    st.sidebar.divider()
    # -----------------------------------------------

    # Carrega dinamicamente os módulos direto do banco
    modulos = carregar_modulos_do_banco(usuario_atual["perfil_id"])

    if not modulos:
        st.sidebar.warning("Nenhum módulo liberado para o seu perfil.")
        return

    opcoes_menu = {m["NOME_MENU"] if "NOME_MENU" in m else m["nome_menu"]: m for m in modulos}
    escolha_menu = st.sidebar.radio("Navegação", options=list(opcoes_menu.keys()))

    modulo_selecionado = opcoes_menu[escolha_menu]
    caminho_view = modulo_selecionado.get("ARQUIVO_VIEW") or modulo_selecionado.get("arquivo_view")

    if caminho_view == "views.gestao_perfil" or caminho_view == "gestao_perfil":
        render_gestao_perfil()
    else:
        try:
            nome_modulo_import = caminho_view.replace("views.", "")
            view_module = importlib.import_module(nome_modulo_import)
            
            if hasattr(view_module, "render"):
                try:
                    view_module.render(obter_conexao(), ano, mes, meses_lista)
                except TypeError:
                    try:
                        view_module.render(obter_conexao(), ano, mes)
                    except TypeError:
                        view_module.render(obter_conexao())
            else:
                st.info(f"Módulo **{escolha_menu}** carregado com sucesso.")
        except Exception as e:
            st.warning(f"Aviso ao carregar o arquivo físico ({caminho_view}): {e}")
            st.info(f"Acessando o módulo: **{escolha_menu}**.")


if __name__ == "__main__":
    main()

