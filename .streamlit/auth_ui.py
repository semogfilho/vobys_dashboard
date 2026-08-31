# -*- coding: utf-8 -*-
import streamlit as st
import hashlib, toml, os, base64, random
import usuarios
import requests

def garantir_autenticacao_sefaz(servico_nome):
    # Se já estiver autenticado, não faz nada
    if "sefaz_cpf" in st.session_state:
        return True
    
    # Se não, dispara o modal
    modal_autenticacao_sefaz(servico_nome)
    st.stop() # Isso PARA a execução aqui, forçando o usuário a interagir com o modal

# O "Porteiro" - Decido se mostra o diálogo ou libera o acesso
def verificar_credenciais_sefaz():
    if st.session_state.get('sefaz_auth'):
        st.sidebar.success("✅ Conectado à SEFAZ")
        if st.sidebar.button("Desconectar SEFAZ"):
            for key in ['sefaz_auth', 'sefaz_cpf', 'sefaz_pass']:
                st.session_state.pop(key, None)
            st.rerun()
        return True
    
    # Se não está logado, abre o diálogo e retorna False
    modal_autenticacao_sefaz()
    return False

# O "Diálogo" - A parte visual que você queria "estilosa"
@st.dialog("Acesso SEFAZ")
def modal_autenticacao_sefaz():
    # Estilização CSS para um visual compacto e direto
    st.markdown("""
        <style>
        /* Removi a linha de background-color para ficar transparente/padrão */
        div[data-testid="stDialog"] { 
            width: 350px; 
        }
        div.stButton > button {
            background-color: #f0f0f0;
            border: 1px solid #999;
            color: #000;
            padding: 5px 20px;
            float: right;
        }
        </style>
    """, unsafe_allow_html=True)

    with st.form("form_sefaz_login"):
        user_cpf = st.text_input("* Usuário")
        user_pass = st.text_input("* Senha", type="password")
        
        # Espaçador para organizar o layout
        st.write("") 
        
        # Botão Ok alinhado
        if st.form_submit_button("✅ Ok"):
            if testar_conexao_sefaz(user_cpf, user_pass):
                st.session_state.sefaz_auth = True
                st.session_state.sefaz_cpf = user_cpf
                st.session_state.sefaz_pass = user_pass
                st.rerun()
            else:
                st.error("Credenciais inválidas.")

def testar_conexao_sefaz(cpf, senha):
    """
    Testa se as credenciais fornecidas são válidas tentando autenticar na API.
    """
    # Acessa o BASE_URL do seu secrets
    BASE_URL = st.secrets["sefaz"]["BASE_URL"]
    try:
        session = requests.Session()
        session.verify = False # Conforme seu padrão de conexão

        # Tenta a autenticação real
        payload = {"usuario": cpf, "senha": senha}
        r_auth = session.post(f"{BASE_URL}/auth", json=payload, timeout=5)

        # Retorna True se o status for 200 (OK)
        return r_auth.status_code == 200
    except Exception as e:
        st.error(f"Erro ao conectar com SEFAZ: {e}")
        return False


def carregar_usuarios():
    caminho = os.path.join(os.path.dirname(__file__), "users.toml")
    if not os.path.exists(caminho): return {}
    return toml.load(caminho).get("usuario", {})

def codificar_sessao(nome, perfil, login):
    payload = "{0}|{1}|{2}".format(nome, perfil, login)
    return base64.b64encode(payload.encode('utf-8')).decode('utf-8')

def decodificar_sessao(token):
    try:
        decoded = base64.b64decode(token.encode('utf-8')).decode('utf-8')
        return decoded.split("|")
    except:
        return None, None, None

def gerenciar_sessao_fluxo():
    st.markdown("<h1 style='text-align: center; color: #d32f2f;'>NTGD</h1>", unsafe_allow_html=True)
    st.divider()

    st.write("### 🔐 Acesso ao Sistema")
    login = st.text_input("Usuário:").strip().lower()
    senha = st.text_input("Senha:", type="password")
    
    if st.button("Entrar"):
        usuarios_db = carregar_usuarios()
        if login in usuarios_db:
            user_data = usuarios_db[login]
            senha_hash = hashlib.sha256(senha.strip().encode('utf-8')).hexdigest()
            
            if user_data.get("senha_hash") == senha_hash:
                st.session_state.clear()
                st.session_state.autenticado = True
                st.session_state.login_atual = login
                st.session_state.nome_usuario = user_data.get("nome", login)
                st.session_state.perfil_usuario = user_data.get("tipo", "c")
                flag = user_data.get("requer_reset", "nao")
                st.session_state.precisa_resetar = (flag == "sim")
                st.query_params["s"] = codificar_sessao(st.session_state.nome_usuario, st.session_state.perfil_usuario, st.session_state.login_atual)
                st.rerun()
            else:
                st.error("❌ Senha incorreta.")
        else:
            st.error("❌ Usuário não encontrado.")
#[usuario.comum2]
#nome = "Usuário Comum2"
#email = "jose.filho@mv.com.br"
#tipo = "c"
#senha_hash = "d4735e3a265e16eee03f59718b9b5d03019c07d8b6c51f90da3a666eec13ab35"
#requer_reset = "nao"


    # --- FLUXO: ESQUECI A SENHA ---
    st.divider()
    if st.button("Esqueci minha senha"):
        st.session_state.modo_recuperacao = True

    if st.session_state.get("modo_recuperacao"):
        st.markdown("### 🔄 Recuperação de Acesso")
        st.info("Informe seu login ou e-mail cadastrado para iniciarmos o processo.")
        
        identificador = st.text_input("Identificador:", placeholder="login ou e-mail@dominio.com").strip().lower()
        dados_gerais = carregar_usuarios()
        
        usuarios_encontrados = []
        if identificador:
            for login, info in dados_gerais.items():
                if login == identificador or info.get("email", "").lower() == identificador:
                    usuarios_encontrados.append({"login": login, "info": info})
        
        if identificador and not usuarios_encontrados:
            st.error("❌ Usuário ou e-mail não encontrado.")
        
        elif usuarios_encontrados:
            # Estilização com Container para separar o fluxo
            with st.container(border=True):
                if len(usuarios_encontrados) > 1:
                    st.warning("⚠️ Múltiplas contas encontradas. Selecione o login desejado:")
                    escolha = st.selectbox("Contas vinculadas:", [u["login"] for u in usuarios_encontrados])
                    usuario_final = next(u for u in usuarios_encontrados if u["login"] == escolha)
                else:
                    usuario_final = usuarios_encontrados[0]
                    st.success(f"Conta encontrada: **{usuario_final['login']}**")

                login_chave = usuario_final["login"]
                info = usuario_final["info"]
                email_cadastrado = info.get("email", "")

                # Máscara elegante
                prefixo, dominio = email_cadastrado.split("@")
                mascara = f"{prefixo[0]}{'*' * (len(prefixo)-1)}@{dominio}"
                
                st.write(f"Para sua segurança, confirme o e-mail: ` {mascara} `")
                email_input = st.text_input("Confirmação de e-mail:")
                
                if st.button("🚀 Enviar Instruções"):
                    if email_input.strip().lower() == email_cadastrado.lower():
                        import random
                        senha_temp = str(random.randint(100000, 999999))
                        
                        if usuarios.enviar_email_senha(email_cadastrado, senha_temp, info["nome"], login_chave):
                            dados_gerais[login_chave].update({
                                "senha_hash": hashlib.sha256(senha_temp.encode()).hexdigest(),
                                "requer_reset": "sim"
                            })
                            usuarios.salvar_usuarios({"usuario": dados_gerais})
                            st.toast("E-mail enviado com sucesso!", icon="✅")
                            st.session_state.mensagem_sucesso = f"E-mail enviado com sucesso!"

                            st.session_state.modo_recuperacao = False
                            st.rerun()
                    else:
                        st.error("❌ E-mail de confirmação inválido.")
        
        if st.button("Cancelar"):
            st.session_state.modo_recuperacao = False
            st.rerun()

def processar_troca_senha(login, nova_senha):
    caminho = os.path.join(os.path.dirname(__file__), "users.toml")
    config = toml.load(caminho)
    config["usuario"][login]["senha_hash"] = hashlib.sha256(nova_senha.strip().encode('utf-8')).hexdigest()
    config["usuario"][login]["requer_reset"] = "nao"
    with open(caminho, "w") as f:
        toml.dump(config, f)
    return True

