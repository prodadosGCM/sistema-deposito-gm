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
            primeiro_acesso INTEGER DEFAULT 1
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

def cadastrar_agente_admin(matricula, nome, senha_inicial):
    conn = get_connection()
    try:
        senha_cripto = make_hashes(senha_inicial)
        conn.execute(
            "INSERT INTO agentes (matricula, nome, senha, primeiro_acesso) VALUES (?, ?, ?, ?)",
            (matricula, nome, senha_cripto, 1)
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

def listar_agentes():
    conn = get_connection()
    df = pd.read_sql("SELECT id, matricula, nome, primeiro_acesso FROM agentes ORDER BY nome", conn)
    conn.close()
    return df

def excluir_agente(id_agente):
    conn = get_connection()
    conn.execute("DELETE FROM agentes WHERE id = ?", (id_agente,))
    conn.commit()
    conn.close()

def resetar_senha_agente(id_agente, nova_senha="1234"):
    conn = get_connection()
    senha_hash = make_hashes(nova_senha)
    conn.execute(
        "UPDATE agentes SET senha = ?, primeiro_acesso = 1 WHERE id = ?",
        (senha_hash, id_agente)
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

sheet = conectar_planilha()

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

def preparar_dataframe(df):
    if df.empty:
        return df

    df = df.copy()
    df.columns = df.columns.str.strip().str.lower()

    colunas_texto = [
        "placa", "marca", "modelo", "cor", "tipo", "motivo_apreensao",
        "agente_entrada", "status", "data_saida", "hora_saida",
        "agente_saida", "observacoes"
    ]

    for col in colunas_texto:
        if col in df.columns:
            df[col] = df[col].astype(str)

    if "id" in df.columns:
        df["id"] = pd.to_numeric(df["id"], errors="coerce")

    return df

# =====================================================
# ---------------- MENU -------------------------------
# =====================================================

if st.session_state['tipo_usuario'] == 'admin':
    menu = st.sidebar.radio(
        "Menu",
        [
            "📊 Dashboard",
            "👤 Cadastrar Usuário",
            "📋 Gerenciar Usuários",
            "🚗 Entrada de Veículo",
            "📤 Saída de Veículo",
            "🔎 Consulta / Inventário"
        ]
    )
else:
    menu = st.sidebar.radio(
        "Menu",
        [
            "📊 Dashboard",
            "🚗 Entrada de Veículo",
            "📤 Saída de Veículo",
            "🔎 Consulta / Inventário"
        ]
    )

# =====================================================
# 📊 DASHBOARD - TODOS VISUALIZAM
# =====================================================
if menu == "📊 Dashboard":
    st.subheader("Dashboard Operacional do Depósito")

    df = carregar_dados()
    df = preparar_dataframe(df)

    if df.empty:
        st.info("Ainda não há dados para exibir no dashboard.")
    else:
        total_registros = len(df)

        if "status" in df.columns:
            total_deposito = len(df[df["status"].astype(str).str.upper() == "NO_DEPÓSITO"])
            total_liberados = len(df[df["status"].astype(str).str.upper() == "LIBERADO"])
        else:
            total_deposito = 0
            total_liberados = 0

        if "tipo" in df.columns:
            total_motos = len(df[df["tipo"].astype(str).str.upper() == "MOTOCICLETA"])
            total_automoveis = len(df[df["tipo"].astype(str).str.upper() == "AUTOMÓVEL"])
            total_caminhoes = len(df[df["tipo"].astype(str).str.upper() == "CAMINHÃO"])
        else:
            total_motos = 0
            total_automoveis = 0
            total_caminhoes = 0

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total de Registros", total_registros)
        c2.metric("No Depósito", total_deposito)
        c3.metric("Liberados", total_liberados)
        c4.metric("Motocicletas", total_motos)

        c5, c6 = st.columns(2)
        c5.metric("Automóveis", total_automoveis)
        c6.metric("Caminhões", total_caminhoes)

        st.markdown("---")

        col_g1, col_g2 = st.columns(2)

        with col_g1:
            if "status" in df.columns:
                st.markdown("**Veículos por Status**")
                status_count = df["status"].astype(str).str.upper().value_counts()
                st.bar_chart(status_count)

        with col_g2:
            if "tipo" in df.columns:
                st.markdown("**Veículos por Tipo**")
                tipo_count = df["tipo"].astype(str).str.upper().value_counts()
                st.bar_chart(tipo_count)

        st.markdown("---")

        col_g3, col_g4 = st.columns(2)

        with col_g3:
            if "marca" in df.columns:
                st.markdown("**Top 10 Marcas**")
                marca_count = df["marca"].astype(str).str.upper().value_counts().head(10)
                st.bar_chart(marca_count)

        with col_g4:
            if "agente_entrada" in df.columns:
                st.markdown("**Entradas por Agente**")
                agente_count = df["agente_entrada"].astype(str).str.upper().value_counts().head(10)
                st.bar_chart(agente_count)

        st.markdown("---")

        if "data_entrada" in df.columns:
            st.markdown("**Entradas por Data**")
            df_datas = df.copy()
            df_datas["data_entrada_dt"] = pd.to_datetime(df_datas["data_entrada"], format="%d/%m/%Y", errors="coerce")
            entradas_por_data = (
                df_datas.dropna(subset=["data_entrada_dt"])
                .groupby("data_entrada_dt")
                .size()
                .sort_index()
            )
            if not entradas_por_data.empty:
                st.line_chart(entradas_por_data)
            else:
                st.info("Sem datas válidas para o gráfico de entradas.")

# =====================================================
# 👤 CADASTRO DE USUÁRIO - SOMENTE ADMIN
# =====================================================
elif menu == "👤 Cadastrar Usuário":
    if st.session_state['tipo_usuario'] != 'admin':
        st.error("Acesso restrito ao administrador.")
        st.stop()

    st.subheader("Cadastro de Usuário")

    with st.form("form_cadastro_usuario"):
        matricula = st.text_input("Matrícula")
        nome = st.text_input("Nome Completo")
        senha_inicial = st.text_input("Senha Inicial", value="1234", type="password")

        if st.form_submit_button("Cadastrar Usuário"):
            if not matricula or not nome or not senha_inicial:
                st.warning("Preencha todos os campos.")
            else:
                if cadastrar_agente_admin(matricula.strip(), nome.strip(), senha_inicial.strip()):
                    st.success("Usuário cadastrado com sucesso. No primeiro acesso ele deverá trocar a senha.")
                else:
                    st.error("Matrícula já cadastrada.")

# =====================================================
# 📋 GERENCIAR USUÁRIOS - SOMENTE ADMIN
# =====================================================
elif menu == "📋 Gerenciar Usuários":
    if st.session_state['tipo_usuario'] != 'admin':
        st.error("Acesso restrito ao administrador.")
        st.stop()

    st.subheader("Gerenciamento de Usuários")

    df_agentes = listar_agentes()

    if df_agentes.empty:
        st.info("Nenhum usuário cadastrado.")
    else:
        st.dataframe(df_agentes, use_container_width=True)

        opcoes = df_agentes["matricula"].astype(str) + " - " + df_agentes["nome"]
        selecionado = st.selectbox("Selecione um usuário", opcoes)

        matricula_sel = selecionado.split(" - ")[0]
        agente_sel = df_agentes[df_agentes["matricula"].astype(str) == matricula_sel].iloc[0]
        id_agente_sel = int(agente_sel["id"])

        col1, col2 = st.columns(2)

        with col1:
            if st.button("Resetar Senha para 1234"):
                resetar_senha_agente(id_agente_sel, "1234")
                st.success("Senha resetada com sucesso. O usuário deverá trocar no próximo login.")
                time.sleep(1)
                st.rerun()

        with col2:
            if st.button("Excluir Usuário", type="primary"):
                excluir_agente(id_agente_sel)
                st.success("Usuário excluído com sucesso.")
                time.sleep(1)
                st.rerun()

# =====================================================
# 🚗 ENTRADA DE VEÍCULO
# =====================================================
elif menu == "🚗 Entrada de Veículo":
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
            if not placa or not marca or not modelo or not cor or not motivo or not agente:
                st.warning("Preencha todos os campos obrigatórios.")
            else:
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
# 📤 SAÍDA DE VEÍCULO - ADMIN E AGENTE
# =====================================================
elif menu == "📤 Saída de Veículo":
    st.subheader("Registro de Saída de Veículo")

    df = carregar_dados()
    df = preparar_dataframe(df)

    if df.empty or "status" not in df.columns:
        st.info("Nenhum veículo no depósito.")
    else:
        df_ativos = df[df["status"].astype(str).str.upper() == "NO_DEPÓSITO"]

        if df_ativos.empty:
            st.info("Nenhum veículo no depósito.")
        else:
            veiculo = st.selectbox(
                "Selecione o veículo",
                df_ativos["id"].astype(str) + " - " + df_ativos["placa"].astype(str)
            )

            agente_saida = st.text_input(
                "Agente Responsável pela Liberação",
                value=st.session_state['nome_usuario']
            )
            obs = st.text_area("Observações")

            if st.button("Registrar Saída"):
                if not agente_saida:
                    st.warning("Informe o agente responsável pela liberação.")
                else:
                    vid = int(veiculo.split(" - ")[0])
                    linha = df.index[df["id"] == vid][0] + 2

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
    df = preparar_dataframe(df)

    if df.empty:
        st.info("Nenhum registro encontrado.")
    else:
        col1, col2, col3, col4 = st.columns(4)
        placa = col1.text_input("Placa")
        marca = col2.text_input("Marca")
        data = col3.text_input("Data de Entrada (dd/mm/aaaa)")
        status = col4.selectbox("Status", ["Todos", "NO_DEPÓSITO", "LIBERADO"])

        if placa and "placa" in df.columns:
            df = df[df["placa"].astype(str).str.contains(placa.upper(), na=False)]

        if marca and "marca" in df.columns:
            df = df[df["marca"].astype(str).str.contains(marca, case=False, na=False)]

        if data and "data_entrada" in df.columns:
            df = df[df["data_entrada"].astype(str) == data]

        if status != "Todos" and "status" in df.columns:
            df = df[df["status"].astype(str).str.upper() == status]

        st.dataframe(df, use_container_width=True)