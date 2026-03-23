import streamlit as st
import gspread
import pandas as pd
import sqlite3
from zoneinfo import ZoneInfo
from google.oauth2.service_account import Credentials
from datetime import datetime
import hashlib
import time

# ---------------- CONFIG STREAMLIT ----------------
st.set_page_config(page_title="Controle de Veículos - Depósito GCM", layout="wide")
st.title("🚓 Depósito Público – Controle de Veículos | GCM")

# =====================================================
# ---------------- FUNÇÕES DE LOGIN -------------------
# =====================================================

def make_hashes(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def check_hashes(password, hashed_text):
    return make_hashes(password) == hashed_text

if 'logado' not in st.session_state:
    st.session_state['logado'] = False
    st.session_state['usuario_id'] = None
    st.session_state['tipo_usuario'] = None
    st.session_state['primeiro_acesso'] = False
    st.session_state['nome_usuario'] = ""

def logout():
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

def get_connection():
    return sqlite3.connect('usuarios_deposito.db', check_same_thread=False)

def init_db():
    conn = get_connection()
    c = conn.cursor()

    c.execute('''
        CREATE TABLE IF NOT EXISTS agentes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            matricula TEXT UNIQUE,
            nome TEXT,
            senha TEXT,
            primeiro_acesso INTEGER DEFAULT 0
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS administradores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT UNIQUE,
            senha TEXT,
            primeiro_acesso INTEGER DEFAULT 1
        )
    ''')

    # Admin padrão
    try:
        senha_hash = make_hashes('admin123')
        c.execute(
            "INSERT INTO administradores (usuario, senha, primeiro_acesso) VALUES (?, ?, ?)",
            ('admin', senha_hash, 1)
        )
    except sqlite3.IntegrityError:
        pass

    conn.commit()
    conn.close()

init_db()

def login_admin(usuario, senha):
    conn = get_connection()
    user = conn.execute(
        "SELECT id, senha, primeiro_acesso FROM administradores WHERE usuario = ?",
        (usuario,)
    ).fetchone()
    conn.close()

    if user and check_hashes(senha, user[1]):
        return True, user[0], user[2]
    return False, None, None

def login_agente(matricula, senha):
    conn = get_connection()
    user = conn.execute(
        "SELECT id, nome, senha, primeiro_acesso FROM agentes WHERE matricula = ?",
        (matricula,)
    ).fetchone()
    conn.close()

    if user and check_hashes(senha, user[2]):
        return True, user[0], user[1], user[3]
    return False, None, None, None

def cadastrar_agente_self(matricula, nome, senha):
    conn = get_connection()
    try:
        senha_cripto = make_hashes(senha)
        conn.execute(
            "INSERT INTO agentes (matricula, nome, senha, primeiro_acesso) VALUES (?, ?, ?, 0)",
            (matricula, nome, senha_cripto)
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def alterar_senha(tipo_usuario, id_usuario, nova_senha):
    conn = get_connection()
    nova_senha_hash = make_hashes(nova_senha)
    tabela = "administradores" if tipo_usuario == 'admin' else "agentes"
    conn.execute(
        f"UPDATE {tabela} SET senha = ?, primeiro_acesso = 0 WHERE id = ?",
        (nova_senha_hash, id_usuario)
    )
    conn.commit()
    conn.close()


# =====================================================
# ---------------- TELA DE LOGIN ----------------------
# =====================================================

if not st.session_state['logado']:
    col1, col2, col3 = st.columns([1, 2, 1])

    with col2:
        st.subheader("🔐 Acesso ao Sistema")

        tab_login, tab_cadastro = st.tabs(["Login", "Cadastro de Agente"])

        with tab_login:
            tipo = st.radio("Entrar como:", ["Agente", "Administrador"], horizontal=True)

            if tipo == "Administrador":
                usuario_input = st.text_input("Usuário do Admin")
            else:
                usuario_input = st.text_input("Matrícula do Agente")

            senha_input = st.text_input("Senha", type="password")

            if st.button("Entrar"):
                if tipo == "Administrador":
                    sucesso, uid, p_acesso = login_admin(usuario_input, senha_input)
                    if sucesso:
                        st.session_state['logado'] = True
                        st.session_state['tipo_usuario'] = 'admin'
                        st.session_state['usuario_id'] = uid
                        st.session_state['nome_usuario'] = usuario_input
                        st.session_state['primeiro_acesso'] = bool(p_acesso)
                        st.rerun()
                    else:
                        st.error("Usuário ou senha inválidos.")

                else:
                    sucesso, uid, nome, p_acesso = login_agente(usuario_input, senha_input)
                    if sucesso:
                        st.session_state['logado'] = True
                        st.session_state['tipo_usuario'] = 'agente'
                        st.session_state['usuario_id'] = uid
                        st.session_state['nome_usuario'] = nome
                        st.session_state['primeiro_acesso'] = bool(p_acesso)
                        st.rerun()
                    else:
                        st.error("Matrícula ou senha incorretos.")

        with tab_cadastro:
            st.write("Cadastro de novo agente")
            new_mat = st.text_input("Matrícula")
            new_nome = st.text_input("Nome Completo")
            new_pass = st.text_input("Crie uma Senha", type="password")
            new_pass_conf = st.text_input("Confirme a Senha", type="password")

            if st.button("Criar Conta"):
                if new_pass != new_pass_conf:
                    st.error("As senhas não coincidem.")
                elif new_mat and new_nome and new_pass:
                    if cadastrar_agente_self(new_mat, new_nome, new_pass):
                        st.success("Conta criada com sucesso.")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("Matrícula já cadastrada.")
                else:
                    st.warning("Preencha todos os campos.")

    st.stop()

# =====================================================
# ----------- TROCA DE SENHA NO PRIMEIRO ACESSO -------
# =====================================================

if st.session_state['primeiro_acesso']:
    st.warning("⚠️ Por segurança, altere sua senha inicial.")
    with st.form("form_troca_senha"):
        nova_s1 = st.text_input("Nova Senha", type="password")
        nova_s2 = st.text_input("Confirme a Nova Senha", type="password")

        if st.form_submit_button("Atualizar Senha"):
            if nova_s1 == nova_s2 and len(nova_s1) > 3:
                alterar_senha(
                    st.session_state['tipo_usuario'],
                    st.session_state['usuario_id'],
                    nova_s1
                )
                st.session_state['primeiro_acesso'] = False
                st.success("Senha atualizada com sucesso.")
                time.sleep(1)
                st.rerun()
            else:
                st.error("As senhas não coincidem ou são muito curtas.")
    st.stop()

# =====================================================
# ---------------- SIDEBAR LOGADO ---------------------
# =====================================================

st.sidebar.success(f"Logado como: {st.session_state['nome_usuario']}")
st.sidebar.write(f"Perfil: {st.session_state['tipo_usuario'].upper()}")

if st.sidebar.button("Sair / Logout"):
    logout()

# ---------------- CONEXÃO GOOGLE SHEETS ----------------

def conectar_planilha():
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets"]

        creds = Credentials.from_service_account_info(
            st.secrets["google_service_account"],
            scopes=scope
        )

        client = gspread.authorize(creds)
        planilha = client.open_by_key("1p4eVJjnubslCc5mmxj8aHApC6ZTPraD2mvKkD8gBOEI")
        aba = planilha.worksheet("veiculos")

        return aba

    except Exception as e:
        st.error(f"Erro ao conectar com a planilha: {e}")
        st.stop()

# ---------------- TESTE DE CONEXÃO COM A PLANILHA ----------------
sheet = conectar_planilha()
st.success("Conectado à planilha com sucesso!")

# ---------------- FUNÇÕES AUXILIARES ----------------

@st.cache_data(ttl=60)
def carregar_dados():
    dados = sheet.get_all_records()
    df = pd.DataFrame(dados)

    if not df.empty:
        df.columns = df.columns.str.strip().str.lower()

    return df

def gerar_id(df):
    if df.empty or "id" not in df.columns:
        return 1

    df["id"] = pd.to_numeric(df["id"], errors="coerce")
    df_ids_validos = df["id"].dropna()

    if df_ids_validos.empty:
        return 1

    return int(df_ids_validos.max()) + 1

def registrar_log(usuario, acao, detalhes=""):
    agora = datetime.now(ZoneInfo("America/Sao_Paulo"))
    log_sheet = sheet.spreadsheet.worksheet("log_auditoria")

    log_sheet.append_row([
        agora.strftime("%d/%m/%Y"),
        agora.strftime("%H:%M:%S"),
        str(usuario).upper(),
        str(acao).upper(),
        str(detalhes).upper()
    ])

# ---------------- MENU ----------------
menu = st.sidebar.radio(
    "Menu",
    ["🚗 Entrada de Veículo", "📤 Saída de Veículo", "🔎 Consulta / Inventário"]
)

# =====================================================
# 🚗 ENTRADA DE VEÍCULO
# =====================================================
if menu == "🚗 Entrada de Veículo":
    st.subheader("Registro de Entrada de Veículo")

    with st.form("entrada"):
        placa = st.text_input("Placa")
        marca = st.text_input("Marca")
        modelo = st.text_input("Modelo")
        cor = st.text_input("Cor")
        tipo = st.selectbox("Tipo", ["Automóvel", "Motocicleta", "Caminhão", "Outro"])
        motivo = st.text_area("Motivo da Apreensão")
        agente = st.text_input("Agente Responsável", value=st.session_state['nome_usuario'])

        if st.form_submit_button("Registrar Entrada"):
            df = carregar_dados()
            novo_id = gerar_id(df)
            agora = datetime.now(ZoneInfo("America/Sao_Paulo"))

            sheet.append_row([
                novo_id,
                placa.strip().upper(),
                marca.strip().upper(),
                modelo.strip().upper(),
                cor.strip().upper(),
                tipo.strip().upper(),
                motivo.strip().upper(),
                agora.strftime("%d/%m/%Y"),
                agora.strftime("%H:%M"),
                agente.strip().upper(),
                "NO_DEPÓSITO",
                "",
                "",
                "",
                ""
            ])

            registrar_log(
                usuario=agente,
                acao="ENTRADA DE VEICULO",
                detalhes=f"PLACA {placa}"
            )

            st.cache_data.clear()
            st.success("✅ Veículo registrado com sucesso!")

# =====================================================
# 📤 SAÍDA DE VEÍCULO
# =====================================================
elif menu == "📤 Saída de Veículo":
    st.subheader("Registro de Saída de Veículo")

    df = carregar_dados()

    if df.empty or "status" not in df.columns:
        st.info("Nenhum veículo no depósito.")
    else:
        df_ativos = df[df["status"] == "NO_DEPÓSITO"]

        if df_ativos.empty:
            st.info("Nenhum veículo no depósito.")
        else:
            veiculo = st.selectbox(
                "Selecione o veículo",
                df_ativos["id"].astype(str) + " - " + df_ativos["placa"]
            )

            agente_saida = st.text_input(
                "Agente Responsável pela Liberação",
                value=st.session_state['nome_usuario']
            )
            obs = st.text_area("Observações")

            if st.button("Registrar Saída"):
                vid = int(veiculo.split(" - ")[0])
                linha = df.index[df["id"] == vid][0] + 2  # ajuste Google Sheets
                agora = datetime.now(ZoneInfo("America/Sao_Paulo"))

                sheet.update(f"K{linha}:O{linha}", [[
                    "LIBERADO",
                    agora.strftime("%d/%m/%Y"),
                    agora.strftime("%H:%M"),
                    agente_saida.strip().upper(),
                    obs.strip().upper()
                ]])

                registrar_log(
                    usuario=agente_saida,
                    acao="SAIDA DE VEICULO",
                    detalhes=f"PLACA {df.loc[df['id'] == vid, 'placa'].values[0]}"
                )

                st.cache_data.clear()
                st.success("🚗 Veículo liberado com sucesso!")

# =====================================================
# 🔎 CONSULTA / INVENTÁRIO
# =====================================================
elif menu == "🔎 Consulta / Inventário":
    st.subheader("Consulta de Veículos")

    df = carregar_dados()

    if df.empty:
        st.info("Nenhum registro encontrado.")
    else:
        col1, col2, col3 = st.columns(3)
        placa = col1.text_input("Placa")
        marca = col2.text_input("Marca")
        data = col3.text_input("Data de Entrada (dd/mm/aaaa)")

        if placa and "placa" in df.columns:
            df = df[df["placa"].astype(str).str.contains(placa.upper(), na=False)]

        if marca and "marca" in df.columns:
            df = df[df["marca"].astype(str).str.contains(marca, case=False, na=False)]

        if data and "data_entrada" in df.columns:
            df = df[df["data_entrada"].astype(str) == data]

        st.dataframe(df, use_container_width=True)