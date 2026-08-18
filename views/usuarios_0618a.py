# -*- coding: utf-8 -*-
import streamlit as st
import os, toml, hashlib, pandas as pd, smtplib, random
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Configurações de Caminho
CAMINHO_ATUAL = os.path.dirname(__file__)
CAMINHO_USERS_TOML = os.path.abspath(os.path.join(CAMINHO_ATUAL, "..", ".streamlit", "users.toml"))

def exibir_feedback():
    if "mensagem_sucesso" in st.session_state:
        st.success(st.session_state.mensagem_sucesso)
        del st.session_state.mensagem_sucesso
        
    # Campo de Debug específico
    if "senha_debug" in st.session_state:
        if st.session_state.perfil_usuario in ['a']:
            st.info(f"🔍 [DEBUG] Senha temporária ativa: **{st.session_state.senha_debug}**")
        del st.session_state.senha_debug
        # Opcional: del st.session_state.senha_debug # Comente essa linha se quiser que ela fique visível por mais tempo
        
    if "mensagem_erro" in st.session_state:
        st.error(st.session_state.mensagem_erro)
        del st.session_state.mensagem_erro


# E no topo do seu script, basta chamar:
exibir_feedback()

def enviar_email_senha(email_destino, senha_temp, nome):
    remetente = st.secrets["email"]["remetente"]
    senha_app = st.secrets["email"]["senha_app"]
    smtp_server = st.secrets["email"]["smtp_server"]
    smtp_port = int(st.secrets["email"]["smtp_port"]) # Garante que é um número
 
    msg = MIMEMultipart()
    msg['From'] = remetente
    msg['To'] = email_destino
    msg['Subject'] = "NTGD - Senha Temporaria de Acesso"
    
    
    link = st.secrets["sistema"]["url_acesso"]
    
    corpo = f"""
Ola, {nome}!

Sua senha temporaria para o sistema NTGD foi gerada com sucesso.

Senha: {senha_temp}

Acesse o sistema pelo link abaixo:
{link}

Esta senha e valida apenas para o seu proximo acesso.
"""
    msg = MIMEMultipart()
    msg['From'] = remetente
    msg['To'] = email_destino
    msg['Subject'] = "NTGD - Senha Temporaria de Acesso"
    msg.attach(MIMEText(corpo, 'plain'))

    try:
        # Usa SMTP_SSL para a porta 465 (provado que funciona no seu servidor)
        server = smtplib.SMTP_SSL(smtp_server, smtp_port)
        server.login(remetente, senha_app)
        server.sendmail(remetente, email_destino, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        # Se falhar agora, a mensagem de erro será definitiva
        st.error(f"Erro de envio (SSL): {type(e).__name__} - {str(e)}")
        return False

def pode_ver_usuario(login_alvo):
    # Admins ('a') e Gestores ('g') veem tudo
    if st.session_state.perfil_usuario in ['a', 'g']:
        return True
    # Usuários comuns ('c') só veem a si mesmos
    return login_alvo == st.session_state.login_atual


def registrar_log_acesso(conn, login, ip_usuario="0.0.0.0"):
    cursor = conn.cursor()
    try:
        query = "INSERT INTO APP_LOG_ACESSO (USUARIO, IP_USUARIO, DATA_ACESSO) VALUES (:1, :2, SYSDATE)"
        cursor.execute(query, [login, ip_usuario])
        conn.commit()
    except Exception as e:
        print(f"Erro ao inserir log no banco: {e}")
    finally:
        cursor.close()

def carregar_usuarios():
    return toml.load(CAMINHO_USERS_TOML) if os.path.exists(CAMINHO_USERS_TOML) else {"usuario": {}}

def salvar_usuarios(dados):
    with open(CAMINHO_USERS_TOML, "w", encoding="utf-8") as f:
        toml.dump(dados, f)

def buscar_logs_usuario(conn, login):
    query = f"SELECT * FROM (SELECT TO_CHAR(DATA_ACESSO, 'DD/MM/YYYY HH24:MI:SS') AS DATA_HORA, IP_USUARIO FROM APP_LOG_ACESSO WHERE USUARIO = '{login}' ORDER BY DATA_ACESSO DESC) WHERE ROWNUM <= 10"
    return pd.read_sql(query, conn)

def render(conn, perfil_logado):
# DEBUG: Identificar o que está chegando
    #st.sidebar.info(f"DEBUG - Perfil Recebido: {perfil_logado}")
    #st.sidebar.info(f"DEBUG - Login Atual: {st.session_state.get('login_atual')}")

    # CSS para interface compacta
    st.markdown("""<style>[data-testid="stVerticalBlock"] { gap: 0px !important; } .stButton button { height: 30px !important; }</style>""", unsafe_allow_html=True)

    st.markdown("<h2>⚙️ Gerenciamento de Usuários</h2>", unsafe_allow_html=True)
    
    aba_listar, aba_cadastrar = st.tabs(["📋 Lista", "➕ Cadastro"])

    dados_toml = carregar_usuarios()
    usuarios_dict = dados_toml.get("usuario", {})

    with aba_listar:
	# 1. Defina a hierarquia de valores para comparação
	# Adm (a) = 3, Gerente (g) = 2, Comum (c) = 1
        hierarquia = {'a': 3, 'g': 2, 'c': 1}

        for login, info in usuarios_dict.items():
            tipo_user = info.get("tipo", "c")
            nome_user = info.get("nome", "Sem Nome")
            email_user = info.get("email", "")
            esta_resetado = str(info.get("requer_reset", "nao")).lower() in ["sim", "true", "1"]
            tipo_logado = st.session_state.perfil_usuario

            if not pode_ver_usuario(login):
                continue

            pode_interagir = (hierarquia[tipo_logado] >= hierarquia[tipo_user]) or (tipo_logado == 'a')

            with st.container(border=True):
                c1, c2, c3, c4, c5 = st.columns([3, 2, 2, 1.5, 1.5])
                with c1: st.markdown(f"**{nome_user}** ({login})")
                with c2: st.markdown(f"Perfil: {'Adm' if tipo_user=='a' else 'Gerente' if tipo_user=='g' else 'Comum'}")
                with c3: st.markdown(":red[🔴 Resetado]" if esta_resetado else ":green[✅ Ativo]")
                
                with c4:
		    # O botão de Logs agora respeita a mesma hierarquia do botão de Reset
                    if pode_interagir:
                        if st.button("📊 Logs", key=f"log_{login}", use_container_width=True):
                            st.session_state[f"show_log_{login}"] = True
                    else:
                        # Opcional: mostrar um ícone para indicar acesso negado ou deixar em branco
                        st.markdown("🚫")
                
                with c5:
                    if pode_interagir:
                        if esta_resetado and tipo_logado != 'a':
                            st.button("Solicitado", key=f"rst_{login}", disabled=True, use_container_width=True)
                        else:
                            with st.popover("🔑 Reset", use_container_width=True):
                                if st.button("Confirmar Reset", key=f"conf_{login}", type="primary"):
                                    senha_temp = str(random.randint(100000, 999999))
                                    nome_usuario = dados_toml["usuario"][login].get("nome", "Usuario")
                                    if enviar_email_senha(email_user, senha_temp, nome_usuario):
                                        dados_toml["usuario"][login].update({"requer_reset": "sim", "senha_hash": hashlib.sha256(senha_temp.encode()).hexdigest()})
                                        salvar_usuarios(dados_toml)
				        # Salva a mensagem no session_state para exibir após o rerun
                                        st.session_state.mensagem_sucesso = f"Senha resetada! E-mail enviado para {email_user}"
                                        # Opcional: st.session_state.senha_debug = senha_temp
                                        st.session_state.senha_debug = senha_temp
                                        st.rerun()
                    else:
                        # Se NÃO tem permissão, pode deixar vazio ou um ícone de bloqueado
                        st.markdown("🔒")

            if st.session_state.get(f"show_log_{login}"):
                st.dataframe(buscar_logs_usuario(conn, login), use_container_width=True)
                if st.button("Fechar", key=f"close_{login}"):
                    st.session_state[f"show_log_{login}"] = False
                    st.rerun()

    with aba_cadastrar:
        st.markdown("### Adicionar Novo Usuário")
        
        # AQUI COMEÇA A RESTRIÇÃO
        if st.session_state.perfil_usuario in ['a', 'g']:
            with st.form("form_cadastro"):
                novo_login = st.text_input("Login do Usuário")
                novo_nome = st.text_input("Nome Completo")
                novo_email = st.text_input("E-mail")
                novo_tipo = st.selectbox("Perfil", ["c", "g", "a"], format_func=lambda x: "Comum" if x=="c" else "Gerente" if x=="g" else "Administrador")

                if st.form_submit_button("Cadastrar"):
                    if novo_login in dados_toml.get("usuario", {}):
                        st.error("Usuário já existe!")
                    elif not novo_login or not novo_nome or not novo_email:
                        st.error("Preencha todos os campos!")
                    else:
                        dados_toml["usuario"][novo_login] = {
                            "nome": novo_nome,
                            "email": novo_email,
                            "tipo": novo_tipo,
                            "senha_hash": hashlib.sha256("sead@ntgd".encode()).hexdigest(),
                            "requer_reset": "sim"
                        }
                        salvar_usuarios(dados_toml)
                        st.success(f"Usuário {novo_login} cadastrado com sucesso!")
                        st.rerun()
        else:
            # Caso o usuário logado seja 'c', ele recebe este aviso
            st.warning("⚠️ Você não tem permissão para cadastrar novos usuários.")

