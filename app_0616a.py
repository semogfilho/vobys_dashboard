# -*- coding: utf-8 -*-
import os, sys, datetime, streamlit as st, oracledb
import json, importlib
import streamlit as st
import streamlit.components.v1 as components
def capturar_ip_via_js():
    # Se o IP já estiver na query_params, não faz nada
    if "ip_capturado" in st.query_params:
        return st.query_params["ip_capturado"]
    
    # Script para pegar IP e recarregar a página com ele na URL
    js_code = """
    <script>
        fetch('https://api.ipify.org?format=json')
        .then(response => response.json())
        .then(data => {
            const url = new URL(window.location.href);
            url.searchParams.set('ip_capturado', data.ip);
            window.location.href = url.toString();
        });
    </script>
    """
    components.html(js_code, height=0)
    #st.stop() # Para a execução enquanto o navegador recarrega

# Função que injeta um script para capturar o IP e atualizar o session_state
def capturar_ip_cliente():
    if "ip_cliente" not in st.session_state:
        # Script que busca o IP público e envia para o Streamlit via mensagem
        js_code = """
        <script>
            fetch('https://api.ipify.org?format=json')
            .then(response => response.json())
            .then(data => {
                const url = new URL(window.location.href);
                // Envia o IP de volta para o Python (via mecanismo de callback do streamlit)
                window.parent.postMessage({type: 'streamlit:setComponentValue', value: data.ip}, '*');
            });
        </script>
        """
        # Exibe o componente invisível
        valor = components.html(js_code, height=0)
        return valor
    return st.session_state["ip_cliente"]


# --- CONFIGURAÇÃO DE CAMINHOS ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE_DIR, "views"))
sys.path.insert(0, os.path.join(BASE_DIR, ".streamlit"))

# Importação com a view de auditoria
import auth_ui, inicio, grafico, app_siafe, responsavel, arquivos, usuarios, auditoria_integracao, auditoria_folha
# --- RECARREGAMENTO DINÂMICO ---
def reload_views():
    importlib.reload(auth_ui)
    importlib.reload(inicio)
    importlib.reload(grafico)
    importlib.reload(app_siafe)
    importlib.reload(responsavel)
    importlib.reload(arquivos)
    importlib.reload(usuarios)
    importlib.reload(auditoria_integracao)
    importlib.reload(auditoria_folha)

reload_views()

st.set_page_config(page_title="FOLHA - Operacao NTGD", layout="wide")

# --- DEFINIÇÃO DE OPÇÕES (Blindada como função) ---
def get_opcoes():
    opcoes_base = ["Inicio", "Grafico", "Pagto Pendente", "Responsavel", "Arquivos/ID", "Auditoria", "Auditoria Folha"]
    if st.session_state.get("perfil_usuario") in ['a', 'g']: 
        return opcoes_base + ["Usuários"]
    return opcoes_base

# Agora usamos a função para buscar a lista sempre que necessário
opcoes = get_opcoes()

if "menu_atual" not in st.session_state:
    st.session_state.menu_atual = "Inicio"
if st.session_state.menu_atual not in opcoes:
    st.session_state.menu_atual = "Inicio"


# --- 1. RESTAURAÇÃO DE SESSÃO ---
def restaurar_sessao():
    params = st.query_params
    token_url = params.get("s")
    if token_url:
        dados = auth_ui.decodificar_sessao(token_url)
        if dados and len(dados) == 3:
            nome, perfil, login = dados
            
            # --- TRAVA DE SEGURANÇA ---
            # Se o login que veio na URL for DIFERENTE do que está na sessão, 
            # é obrigatório destruir a sessão antiga completamente.
            if st.session_state.get("login_atual") != login:
                st.session_state.clear()
            
            # --- RESTAURAÇÃO ---
            st.session_state.autenticado = True
            st.session_state.nome_usuario = nome
            st.session_state.perfil_usuario = perfil
            st.session_state.login_atual = login
            
            return True
    return False

restaurar_sessao()

# ADICIONE O DEBUG AQUI:
#st.sidebar.write("--- DEBUG ---")
#st.sidebar.write(f"Autenticado: {st.session_state.get('autenticado')}")
#st.sidebar.write(f"Login Atual: {st.session_state.get('login_atual')}")
#st.sidebar.write(f"perfil Atual: {st.session_state.get('perfil_usuario')}")

# --- LOGICA DE PERSISTENCIA DO MENU ---
# Se não houver menu no estado, começa no 'Inicio'

# --- 2. TRAVA DE RESET DE SENHA ---
if st.session_state.get("autenticado", False):
    usuarios_db = auth_ui.carregar_usuarios()
    login = st.session_state.get("login_atual")
    if login in usuarios_db and usuarios_db[login].get("requer_reset") == "sim":
        with st.sidebar:
            st.warning("⚠️ **Atenção:** Alteração de senha obrigatória.")
            nova = st.text_input("Nova senha:", type="password")
            conf = st.text_input("Confirmar nova senha:", type="password")
            if st.button("Confirmar Alteração"):
                if nova == conf:
                    if auth_ui.processar_troca_senha(login, nova):
                        st.success("Senha atualizada!")
                        st.rerun()
                else:
                    st.error("As senhas não conferem.")
        st.stop()

# --- 3. TRAVA DE LOGIN ---
if not st.session_state.get("autenticado", False):
    with st.sidebar:
        auth_ui.gerenciar_sessao_fluxo()
    st.markdown("<h3 style='color: #666; font-weight: normal; margin-top: 5rem; text-align: center;'>🔒 Aguardando identificação no menu lateral...</h3>", unsafe_allow_html=True)
    st.stop()


# --- 4. SIDEBAR E MENU ---
# --- 4.5. SINCRONIZADOR DE ESTADO ---
# Força o perfil a ser o que está no estado atual, sem caches escondidos
if "perfil_usuario" in st.session_state:
    # Garante que o perfil no ambiente de execução seja o correto
    os.environ["CURRENT_USER_PROFILE"] = st.session_state.perfil_usuario

with st.sidebar:
# 1. Título do Projeto
    st.markdown("<h1 style='text-align: center; color: #d32f2f;'>NTGD</h1>", unsafe_allow_html=True)
    st.divider()

    # 2. Mova o nome do usuário para aqui (antes dos selects)
    st.markdown(f"### 👤 {st.session_state.get('nome_usuario', 'Usuário')}")
    #st.divider() # Opcional: para separar o nome dos selects

    # 3. Seletores de Ano e Mês

    # Lógica para definir o mês sugerido
    hoje = datetime.date.today()
    # Lógica para definir mês e ano padrão
    if hoje.day <= 12:
        if hoje.month == 1:
            mes_sugerido = 12
            ano_sugerido = hoje.year - 1
        else:
            mes_sugerido = hoje.month - 1
            ano_sugerido = hoje.year
    else:
        mes_sugerido = hoje.month
        ano_sugerido = hoje.year

    # Ajuste do Selectbox do Ano
    # Garantindo que o ano anterior esteja disponível na lista caso necessário
    lista_anos = [2026, 2025, 2024, 2023]
    if ano_sugerido not in lista_anos:
        lista_anos.insert(0, ano_sugerido)

    ano = st.selectbox("Ano:", lista_anos, index=lista_anos.index(ano_sugerido))

    meses_lista = {1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun", 
                   7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez"}
    mes = st.selectbox("Mês:", list(meses_lista.keys()), index=mes_sugerido - 1, format_func=lambda x: meses_lista[x])
    
    st.markdown("### " + st.session_state.get("nome_usuario", "Usuário"))
    
    # 1. Definição global das opções (fora de qualquer condição limitante)
    # Definimos sempre, para evitar o NameError
    opcoes_base = ["Inicio", "Grafico", "Pagto Pendente", "Responsavel", "Arquivos/ID", "Auditoria", "Auditoria Folha"]
    if st.session_state.get("perfil_usuario") in ['a', 'g']: 
        opcoes = opcoes_base + ["Usuários"]
    else:
        opcoes = opcoes_base

    # 2. Inicialização do estado do menu
    if "menu_atual" not in st.session_state:
        st.session_state.menu_atual = "Inicio"

    # 3. Correção de segurança: Se o valor no estado não for mais válido, resetamos
    if st.session_state.menu_atual not in opcoes:
        st.session_state.menu_atual = "Inicio"

    # 4. Renderização do Radio
    # Usamos o index seguro baseado na lista 'opcoes' já definida
    
# Esta é a ÚNICA instância do radio que deve existir no seu código
    menu = st.radio(
        "Menu:", 
        opcoes, 
        index=opcoes.index(st.session_state.menu_atual),
        key="menu_principal"
    )

    # 5. Atualização do estado
    st.session_state.menu_atual = menu

       # Certifique-se de que o botão esteja AQUI, dentro do bloco with
    if st.button("Sair"):
        # 1. Limpa todas as chaves do estado
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        
        # 2. Limpa os parâmetros da URL
        st.query_params.clear()
        
        # 3. Força uma reinicialização limpa
        st.rerun()
# --- 5. RENDERIZAÇÃO ---
try:
    db = st.secrets["database"]
    conn = oracledb.connect(user=db["db_user"], password=db["db_pass"], dsn=db["db_dsn"])

    # REGISTRO DE LOG SEM DEPENDER DE JS (Muito mais estável para um DBA)
    if st.session_state.get("autenticado") and not st.session_state.get("log_registrado"):
        login_usuario = st.session_state.get("login_atual")
        if login_usuario:
            from views.usuarios import registrar_log_acesso
            
            registrar_log_acesso(conn, login_usuario, "10.0.52.171")
            st.session_state["log_registrado"] = True
            #st.rerun()
# Use o st.session_state.menu_atual em vez da variável 'menu' que vem do radio
    menu_selecionado = st.session_state.menu_atual
 
    if menu_selecionado == "Inicio": inicio.render(conn, ano, mes, meses_lista)
    elif menu_selecionado == "Grafico": grafico.render(conn, ano, mes, meses_lista)
    elif menu_selecionado == "Pagto Pendente": app_siafe.main(conn, ano, mes, meses_lista, st.session_state.perfil_usuario)
    elif menu_selecionado == "Responsavel": responsavel.render(conn, ano, mes, meses_lista)
    elif menu_selecionado == "Arquivos/ID": arquivos.render(conn, ano, mes, meses_lista)
    elif menu_selecionado == "Auditoria": auditoria_integracao.render(conn, ano, mes) # Chamada corrigida
    elif menu_selecionado == "Auditoria Folha": auditoria_folha.render(conn, ano, mes) # Chamada corrigida
    elif menu_selecionado == "Usuários": usuarios.render(conn, st.session_state.perfil_usuario)
    
    conn.close()
except Exception as e:
    st.error("Erro na renderização: " + str(e))
# Logo abaixo do TRY no bloco 5
#st.sidebar.write("Status do Log:", st.session_state.get("log_registrado", "Não registrado"))

