import streamlit as st
import gspread
import pandas as pd
from zoneinfo import ZoneInfo
from google.oauth2.service_account import Credentials
from datetime import datetime
import hashlib

# =====================================================
# CONFIG STREAMLIT
# =====================================================
st.set_page_config(page_title="Controle de Veículos - Depósito GCM", layout="wide")

# =====================================================
# CONEXÃO GOOGLE SHEETS
# =====================================================
def conectar_planilha():
    scope = ["https://www.googleapis.com/auth/spreadsheets"]

    creds = Credentials.from_service_account_info(
        st.secrets["google_service_account"],
        scopes=scope
    )

    client = gspread.authorize(creds)
    planilha = client.open_by_key("1p4eVJjnubslCc5mmxj8aHApC6ZTPraD2mvKkD8gBOEI")
    return planilha

planilha = conectar_planilha()
sheet = planilha.worksheet("veiculos")

# =====================================================
# SEGURANÇA / HASH
# =====================================================
def hash_senha(senha):
    return hashlib.sha256(senha.encode()).hexdigest()

def verificar_senha(senha_digitada, senha_hash):
    return hash_senha(senha_digitada) == senha_hash

# =====================================================
# USUÁRIOS
# =====================================================
def carregar_usuarios():
    aba = planilha.worksheet("usuarios")
    df = pd.DataFrame(aba.get_all_records())
    df.columns = df.columns.str.strip().str.lower()
    return aba, df

# =====================================================
# LOGIN
# =====================================================
if "logado" not in st.session_state:
    st.session_state.logado = False

if not st.session_state.logado:
    st.title("🔐 Acesso ao Sistema – Depósito GCM")

    usuario = st.text_input("Usuário")
    senha = st.text_input("Senha", type="password")

    if st.button("Entrar"):
        aba_users, df_users = carregar_usuarios()

        user = df_users[
            (df_users["usuario"] == usuario) &
            (df_users["ativo"] == "SIM")
        ]

        if user.empty:
            st.error("Usuário inválido ou inativo")
            st.stop()

        user = user.iloc[0]

        if not verificar_senha(senha, user["senha_hash"]):
            st.error("Senha incorreta")
            st.stop()

        st.session_state.logado = True
        st.session_state.usuario = user["usuario"]
        st.session_state.perfil = user["perfil"]
        st.session_state.primeiro_acesso = user["primeiro_acesso"]

        st.rerun()

# =====================================================
# TROCA DE SENHA OBRIGATÓRIA
# =====================================================
if st.session_state.primeiro_acesso == "SIM":
    st.warning("⚠️ Primeiro acesso — altere sua senha")

    nova = st.text_input("Nova senha", type="password")
    confirmar = st.text_input("Confirmar senha", type="password")

    if st.button("Alterar senha"):
        if nova != confirmar or len(nova) < 6:
            st.error("Senha inválida")
            st.stop()

        nova_hash = hash_senha(nova)
        aba_users, df_users = carregar_usuarios()

        linha = df_users.index[
            df_users["usuario"] == st.session_state.usuario
        ][0] + 2

        aba_users.update(f"C{linha}:E{linha}", [[
            nova_hash,
            st.session_state.perfil,
            "NAO"
        ]])

        st.session_state.primeiro_acesso = "NAO"
        st.success("Senha alterada com sucesso")
        st.rerun()

# =====================================================
# FUNÇÕES AUXILIARES
# =====================================================
@st.cache_data(ttl=60)
def carregar_dados():
    df = pd.DataFrame(sheet.get_all_records())
    df.columns = df.columns.str.strip().str.lower()
    return df

def gerar_id(df):
    if df.empty or "id" not in df.columns:
        return 1
    df["id"] = pd.to_numeric(df["id"], errors="coerce")
    return int(df["id"].max()) + 1

def registrar_log(usuario, acao, detalhes=""):
    agora = datetime.now(ZoneInfo("America/Sao_Paulo"))
    log_sheet = planilha.worksheet("log_auditoria")

    log_sheet.append_row([
        agora.strftime("%d/%m/%Y"),
        agora.strftime("%H:%M:%S"),
        usuario.upper(),
        acao.upper(),
        detalhes.upper()
    ])

# =====================================================
# INTERFACE PRINCIPAL
# =====================================================
st.title("🚓 Depósito Público – Controle de Veículos | GCM")

menu = st.sidebar.radio(
    "Menu",
    ["🚗 Entrada de Veículo", "📤 Saída de Veículo", "🔎 Consulta"]
)

# =====================================================
# ENTRADA
# =====================================================
if menu == "🚗 Entrada de Veículo":
    with st.form("entrada"):
        placa = st.text_input("Placa")
        marca = st.text_input("Marca")
        modelo = st.text_input("Modelo")
        cor = st.text_input("Cor")
        tipo = st.selectbox("Tipo", ["Automóvel", "Motocicleta", "Caminhão", "Outro"])
        motivo = st.text_area("Motivo")
        agente = st.session_state.usuario

        if st.form_submit_button("Registrar"):
            df = carregar_dados()
            novo_id = gerar_id(df)
            agora = datetime.now(ZoneInfo("America/Sao_Paulo"))

            sheet.append_row([
                novo_id,
                placa.upper(),
                marca.upper(),
                modelo.upper(),
                cor.upper(),
                tipo.upper(),
                motivo.upper(),
                agora.strftime("%d/%m/%Y"),
                agora.strftime("%H:%M"),
                agente.upper(),
                "NO_DEPÓSITO",
                "",
                "",
                "",
                ""
            ])

            registrar_log(agente, "ENTRADA", f"PLACA {placa}")
            st.success("Veículo registrado")

# =====================================================
# SAÍDA
# =====================================================
elif menu == "📤 Saída de Veículo":
    df = carregar_dados()
    ativos = df[df["status"] == "NO_DEPÓSITO"]

    veiculo = st.selectbox(
        "Veículo",
        ativos["id"].astype(str) + " - " + ativos["placa"]
    )

    if st.button("Liberar"):
        vid = int(veiculo.split(" - ")[0])
        linha = df.index[df["id"] == vid][0] + 2
        agora = datetime.now(ZoneInfo("America/Sao_Paulo"))

        sheet.update(f"K{linha}:O{linha}", [[
            "LIBERADO",
            agora.strftime("%d/%m/%Y"),
            agora.strftime("%H:%M"),
            st.session_state.usuario,
            ""
        ]])

        registrar_log(st.session_state.usuario, "SAIDA", f"ID {vid}")
        st.success("Veículo liberado")

# =====================================================
# CONSULTA
# =====================================================
elif menu == "🔎 Consulta":
    df = carregar_dados()
    st.dataframe(df, use_container_width=True)
