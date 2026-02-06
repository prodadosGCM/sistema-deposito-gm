import streamlit as st
import gspread
import pandas as pd
from google.oauth2.service_account import Credentials
from datetime import datetime


st.write(st.secrets.keys())


# ---------------- TESTE DE CONEXÃO COM A PLANILHA ----------------

sheet = conectar_planilha()
st.success("Conectado à planilha com sucesso!")


# ---------------- CONFIG STREAMLIT ----------------
st.set_page_config(page_title="Controle de Veículos - Depósito GCM", layout="wide")
st.title("🚓 Depósito Público – Controle de Veículos | GCM")

# ---------------- CONEXÃO GOOGLE SHEETS ----------------
def conectar_planilha():
    scope = ["https://www.googleapis.com/auth/spreadsheets"]

    creds = Credentials.from_service_account_info(
        st.secrets["google_service_account"],
        
        scopes=scope
    )

    client = gspread.authorize(creds)
    sheet = client.open("depositopython").worksheet("veiculos")
    return sheet


# ---------------- FUNÇÕES AUXILIARES ----------------
d@st.cache_data(ttl=60)
def carregar_dados():
    dados = sheet.get_all_records()
    return pd.DataFrame(dados)


def gerar_id(df):
    return 1 if df.empty or "id" not in df.columns else int(df["id"].max()) + 1


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
        agente = st.text_input("Agente Responsável")

        if st.form_submit_button("Registrar Entrada"):
            df = carregar_dados()
            novo_id = gerar_id(df)
            agora = datetime.now()

            sheet.append_row([
                novo_id,
                placa.upper(),
                marca,
                modelo,
                cor,
                tipo,
                motivo,
                agora.strftime("%d/%m/%Y"),
                agora.strftime("%H:%M"),
                agente,
                "NO_DEPÓSITO",
                "",
                "",
                "",
                ""
            ])

            st.success("✅ Veículo registrado com sucesso!")

# =====================================================
# 📤 SAÍDA DE VEÍCULO
# =====================================================
elif menu == "📤 Saída de Veículo":
    st.subheader("Registro de Saída de Veículo")

    df = carregar_dados()
    df_ativos = df[df["status"] == "NO_DEPÓSITO"]

    if df_ativos.empty:
        st.info("Nenhum veículo no depósito.")
    else:
        veiculo = st.selectbox(
            "Selecione o veículo",
            df_ativos["id"].astype(str) + " - " + df_ativos["placa"]
        )

        agente_saida = st.text_input("Agente Responsável pela Liberação")
        obs = st.text_area("Observações")

        if st.button("Registrar Saída"):
            vid = int(veiculo.split(" - ")[0])
            linha = df.index[df["id"] == vid][0] + 2  # ajuste Google Sheets

            agora = datetime.now()
            sheet.update(f"K{linha}:O{linha}", [[
                "LIBERADO",
                agora.strftime("%d/%m/%Y"),
                agora.strftime("%H:%M"),
                agente_saida,
                obs
            ]])

            st.success("🚗 Veículo liberado com sucesso!")

# =====================================================
# 🔎 CONSULTA / INVENTÁRIO
# =====================================================
elif menu == "🔎 Consulta / Inventário":
    st.subheader("Consulta de Veículos")

    df = carregar_dados()

    col1, col2, col3 = st.columns(3)
    placa = col1.text_input("Placa")
    marca = col2.text_input("Marca")
    data = col3.text_input("Data de Entrada (dd/mm/aaaa)")

    if placa:
        df = df[df["placa"].str.contains(placa.upper(), na=False)]
    if marca:
        df = df[df["marca"].str.contains(marca, case=False, na=False)]
    if data:
        df = df[df["data_entrada"] == data]

    st.dataframe(df, use_container_width=True)
