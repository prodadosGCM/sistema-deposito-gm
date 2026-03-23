import streamlit as st
import gspread
import pandas as pd
import sqlite3
from zoneinfo import ZoneInfo
from google.oauth2.service_account import Credentials
from datetime import datetime, date
import hashlib
import time

# ---------------- CONFIG STREAMLIT ----------------
st.set_page_config(
    page_title="Controle de Veículos - Depósito GCM",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ---------------- CSS ----------------
st.markdown("""
<style>
    .main-title {
        font-size: 2rem;
        font-weight: 800;
        margin-bottom: 0.2rem;
    }
    .sub-title {
        color: #6b7280;
        margin-bottom: 1.2rem;
    }
    .metric-card {
        background: linear-gradient(135deg, #0f172a, #1e293b);
        padding: 18px;
        border-radius: 18px;
        color: white;
        box-shadow: 0 4px 18px rgba(0,0,0,0.15);
        border: 1px solid rgba(255,255,255,0.08);
        min-height: 110px;
    }
    .metric-card h4 {
        margin: 0;
        font-size: 0.95rem;
        color: #cbd5e1;
        font-weight: 600;
    }
    .metric-card h2 {
        margin: 8px 0 0 0;
        font-size: 2rem;
        font-weight: 800;
        color: #ffffff;
    }
    .mini-card {
        background: #ffffff;
        border: 1px solid #e5e7eb;
        border-radius: 16px;
        padding: 16px;
        box-shadow: 0 3px 10px rgba(0,0,0,0.06);
        margin-bottom: 10px;
    }
    .mini-card h4 {
        margin: 0;
        font-size: 0.95rem;
        color: #475569;
        font-weight: 600;
    }
    .mini-card h2 {
        margin: 8px 0 0 0;
        font-size: 1.7rem;
        color: #0f172a;
        font-weight: 800;
    }
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0f172a 0%, #1e293b 100%);
    }
    section[data-testid="stSidebar"] * {
        color: white !important;
    }
    .sidebar-card {
        background: rgba(255,255,255,0.08);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 14px;
        padding: 12px;
        margin-bottom: 12px;
    }
    .sidebar-title {
        font-size: 0.95rem;
        font-weight: 700;
        margin-bottom: 6px;
        color: #e2e8f0;
    }
    .section-title {
        font-size: 1.1rem;
        font-weight: 700;
        margin: 6px 0 12px 0;
    }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-title">🚓 Depósito Público – Controle de Veículos | GCM</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">Sistema de controle operacional, inventário, retirada de pertences, delegacia e auditoria</div>', unsafe_allow_html=True)

# =====================================================
# ---------------- CONSTANTES -------------------------
# =====================================================

STATUS_PATIO = "DEPÓSITO"
STATUS_LIBERADO = "LIBERADO"

HEADERS_VEICULOS = [
    "id",
    "numero_grv",
    "placa",
    "marca",
    "modelo",
    "cor",
    "tipo",
    "motivo_apreensao",
    "data_entrada",
    "hora_entrada",
    "agente_entrada",
    "status",
    "data_saida",
    "hora_saida",
    "agente_saida",
    "observacoes"
]

HEADERS_DELEGACIA = [
    "id",
    "numero_grv",
    "placa",
    "marca",
    "modelo",
    "cor",
    "tipo",
    "procedencia",
    "data_entrada",
    "hora_entrada",
    "agente_entrada",
    "status",
    "data_saida",
    "hora_saida",
    "agente_saida",
    "observacoes"
]

HEADERS_RETIRADAS = [
    "id_retirada",
    "id_veiculo",
    "placa",
    "data_retirada",
    "hora_retirada",
    "nome_retirante",
    "documento_retirante",
    "itens_retirados",
    "observacao_retirada",
    "agente_responsavel"
]

HEADERS_LOG = [
    "data",
    "hora",
    "usuario",
    "acao",
    "detalhes"
]

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
    col1, col2, col3 = st.columns([1, 1.4, 1])

    with col2:
        st.subheader("🔐 Acesso ao Sistema")

        tipo = st.radio("Entrar como:", ["Agente", "Administrador"], horizontal=True)

        if tipo == "Administrador":
            usuario_input = st.text_input("Usuário do Admin")
        else:
            usuario_input = st.text_input("Matrícula do Agente")

        senha_input = st.text_input("Senha", type="password")

        if st.button("Entrar", use_container_width=True):
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

st.sidebar.markdown("""
<div class="sidebar-card">
    <div class="sidebar-title">Usuário logado</div>
</div>
""", unsafe_allow_html=True)

st.sidebar.write(f"**Nome:** {st.session_state['nome_usuario']}")
st.sidebar.write(f"**Perfil:** {st.session_state['tipo_usuario'].upper()}")

if st.sidebar.button("Sair do Sistema", use_container_width=True):
    logout()

st.sidebar.markdown("---")

# =====================================================
# ------------- CONEXÃO GOOGLE SHEETS -----------------
# =====================================================

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

def conectar_aba_retiradas():
    try:
        return sheet.spreadsheet.worksheet("retirada_pertences")
    except Exception:
        nova_aba = sheet.spreadsheet.add_worksheet(title="retirada_pertences", rows=1000, cols=10)
        nova_aba.append_row(HEADERS_RETIRADAS)
        return nova_aba

def conectar_aba_log():
    try:
        return sheet.spreadsheet.worksheet("log_auditoria")
    except Exception:
        nova_aba = sheet.spreadsheet.add_worksheet(title="log_auditoria", rows=2000, cols=5)
        nova_aba.append_row(HEADERS_LOG)
        return nova_aba

def conectar_aba_delegacia():
    try:
        return sheet.spreadsheet.worksheet("veiculos_delegacia")
    except Exception:
        nova_aba = sheet.spreadsheet.add_worksheet(title="veiculos_delegacia", rows=2000, cols=16)
        nova_aba.append_row(HEADERS_DELEGACIA)
        return nova_aba

retirada_sheet = conectar_aba_retiradas()
log_sheet = conectar_aba_log()
delegacia_sheet = conectar_aba_delegacia()

def validar_headers_worksheet(worksheet, headers_esperados, nome_aba):
    headers_atuais = worksheet.row_values(1)
    headers_atuais = [str(h).strip().lower() for h in headers_atuais]
    headers_esperados = [str(h).strip().lower() for h in headers_esperados]

    if headers_atuais != headers_esperados:
        st.error(
            f"A aba '{nome_aba}' está com a estrutura diferente do esperado.\n\n"
            f"Esperado: {headers_esperados}\n\n"
            f"Atual: {headers_atuais}"
        )
        st.stop()

validar_headers_worksheet(sheet, HEADERS_VEICULOS, "veiculos")
validar_headers_worksheet(delegacia_sheet, HEADERS_DELEGACIA, "veiculos_delegacia")
validar_headers_worksheet(retirada_sheet, HEADERS_RETIRADAS, "retirada_pertences")
validar_headers_worksheet(log_sheet, HEADERS_LOG, "log_auditoria")

# =====================================================
# ---------------- FUNÇÕES AUXILIARES -----------------
# =====================================================

@st.cache_data(ttl=60)
def carregar_dados():
    dados = sheet.get_all_records()
    df = pd.DataFrame(dados)
    if not df.empty:
        df.columns = df.columns.str.strip().str.lower()
    return df

@st.cache_data(ttl=60)
def carregar_retiradas():
    dados = retirada_sheet.get_all_records()
    df = pd.DataFrame(dados)
    if not df.empty:
        df.columns = df.columns.str.strip().str.lower()
    return df

@st.cache_data(ttl=60)
def carregar_logs():
    dados = log_sheet.get_all_records()
    df = pd.DataFrame(dados)
    if not df.empty:
        df.columns = df.columns.str.strip().str.lower()
    return df

@st.cache_data(ttl=60)
def carregar_dados_delegacia():
    dados = delegacia_sheet.get_all_records()
    df = pd.DataFrame(dados)
    if not df.empty:
        df.columns = df.columns.str.strip().str.lower()
    return df

def gerar_id(df):
    if df.empty or "id" not in df.columns:
        return 1
    df = df.copy()
    df["id"] = pd.to_numeric(df["id"], errors="coerce")
    df_ids_validos = df["id"].dropna()
    if df_ids_validos.empty:
        return 1
    return int(df_ids_validos.max()) + 1

def gerar_id_retirada(df):
    if df.empty or "id_retirada" not in df.columns:
        return 1
    df = df.copy()
    df["id_retirada"] = pd.to_numeric(df["id_retirada"], errors="coerce")
    ids_validos = df["id_retirada"].dropna()
    if ids_validos.empty:
        return 1
    return int(ids_validos.max()) + 1

def registrar_log(usuario, acao, detalhes=""):
    agora = datetime.now(ZoneInfo("America/Sao_Paulo"))
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

    mapa_alias = {}
    if "motivo da apreensão" in df.columns and "motivo_apreensao" not in df.columns:
        mapa_alias["motivo da apreensão"] = "motivo_apreensao"
    if "agente entrada" in df.columns and "agente_entrada" not in df.columns:
        mapa_alias["agente entrada"] = "agente_entrada"
    if "agente saída" in df.columns and "agente_saida" not in df.columns:
        mapa_alias["agente saída"] = "agente_saida"
    if "observações" in df.columns and "observacoes" not in df.columns:
        mapa_alias["observações"] = "observacoes"
    if "número_grv" in df.columns and "numero_grv" not in df.columns:
        mapa_alias["número_grv"] = "numero_grv"

    if mapa_alias:
        df = df.rename(columns=mapa_alias)

    for col in df.columns:
        if col != "id":
            df[col] = df[col].astype(str)

    if "id" in df.columns:
        df["id"] = pd.to_numeric(df["id"], errors="coerce")

    return df

def montar_coluna_mes(df, coluna_data, nome_coluna_mes):
    if coluna_data in df.columns:
        df[nome_coluna_mes] = pd.to_datetime(df[coluna_data], format="%d/%m/%Y", errors="coerce")
        df[nome_coluna_mes] = df[nome_coluna_mes].dt.to_period("M").astype(str)
    else:
        df[nome_coluna_mes] = None
    return df

def montar_coluna_data_real(df, coluna_data, nome_coluna):
    if coluna_data in df.columns:
        df[nome_coluna] = pd.to_datetime(df[coluna_data], format="%d/%m/%Y", errors="coerce")
    else:
        df[nome_coluna] = pd.NaT
    return df

def filtrar_por_periodo(df, coluna_data, data_inicio, data_fim):
    if df.empty or coluna_data not in df.columns:
        return df
    df = df.copy()
    df = montar_coluna_data_real(df, coluna_data, "__data_filtro__")
    if pd.notna(data_inicio):
        df = df[df["__data_filtro__"] >= pd.Timestamp(data_inicio)]
    if pd.notna(data_fim):
        df = df[df["__data_filtro__"] <= pd.Timestamp(data_fim)]
    return df.drop(columns=["__data_filtro__"], errors="ignore")

def card_metrica(titulo, valor):
    st.markdown(f"""
        <div class="metric-card">
            <h4>{titulo}</h4>
            <h2>{valor}</h2>
        </div>
    """, unsafe_allow_html=True)

def mini_card(titulo, valor):
    st.markdown(f"""
        <div class="mini-card">
            <h4>{titulo}</h4>
            <h2>{valor}</h2>
        </div>
    """, unsafe_allow_html=True)

def estilizar_status(df):
    if df.empty or "status" not in df.columns:
        return df

    def cor_status(valor):
        valor = str(valor).upper().strip()
        if valor == STATUS_PATIO:
            return "background-color: #fff3cd; color: #7a4b00; font-weight: 700;"
        if valor == STATUS_LIBERADO:
            return "background-color: #d1e7dd; color: #0f5132; font-weight: 700;"
        return ""

    styler = df.style.map(cor_status, subset=["status"])
    return styler

def exibir_tabela(df):
    if df.empty:
        st.dataframe(df, use_container_width=True)
    elif "status" in df.columns:
        st.dataframe(estilizar_status(df), use_container_width=True)
    else:
        st.dataframe(df, use_container_width=True)

def registrar_retirada_pertence(
    id_veiculo,
    placa,
    data_retirada,
    hora_retirada,
    nome_retirante,
    documento_retirante,
    itens_retirados,
    observacao_retirada,
    agente_responsavel
):
    df_retiradas = carregar_retiradas()
    novo_id = gerar_id_retirada(df_retiradas)

    retirada_sheet.append_row([
        novo_id,
        id_veiculo,
        str(placa).upper(),
        str(data_retirada),
        str(hora_retirada),
        str(nome_retirante).upper(),
        str(documento_retirante).upper(),
        str(itens_retirados).upper(),
        str(observacao_retirada).upper(),
        str(agente_responsavel).upper()
    ])

    registrar_log(
        usuario=agente_responsavel,
        acao="RETIRADA DE PERTENCE",
        detalhes=f"PLACA {placa} | RETIRANTE {nome_retirante} | DOC {documento_retirante}"
    )

    st.cache_data.clear()

def registrar_entrada_patio(numero_grv, placa, marca, modelo, cor, tipo, motivo, agente):
    df = carregar_dados()
    novo_id = gerar_id(df)
    agora = datetime.now(ZoneInfo("America/Sao_Paulo"))

    sheet.append_row([
        novo_id,
        str(numero_grv).upper(),
        str(placa).upper(),
        str(marca).upper(),
        str(modelo).upper(),
        str(cor).upper(),
        str(tipo).upper(),
        str(motivo).upper(),
        agora.strftime("%d/%m/%Y"),
        agora.strftime("%H:%M"),
        str(agente).upper(),
        STATUS_PATIO,
        "",
        "",
        "",
        ""
    ])

    registrar_log(
        usuario=agente,
        acao="ENTRADA DE VEICULO",
        detalhes=f"GRV {numero_grv} | PLACA {placa}"
    )

    st.cache_data.clear()

def registrar_saida_patio(id_veiculo, agente_saida, observacoes=""):
    df = carregar_dados()
    df = preparar_dataframe(df)

    linha = df.index[df["id"] == id_veiculo][0] + 2
    agora = datetime.now(ZoneInfo("America/Sao_Paulo"))

    sheet.update(f"L{linha}:P{linha}", [[
        STATUS_LIBERADO,
        agora.strftime("%d/%m/%Y"),
        agora.strftime("%H:%M"),
        str(agente_saida).upper(),
        str(observacoes).upper()
    ]])

    placa = df.loc[df["id"] == id_veiculo, "placa"].values[0]
    numero_grv = df.loc[df["id"] == id_veiculo, "numero_grv"].values[0] if "numero_grv" in df.columns else ""

    registrar_log(
        usuario=agente_saida,
        acao="SAIDA DE VEICULO",
        detalhes=f"GRV {numero_grv} | PLACA {placa}"
    )

    st.cache_data.clear()

def registrar_entrada_delegacia(numero_grv, placa, marca, modelo, cor, tipo, procedencia, agente_entrada):
    df = carregar_dados_delegacia()
    novo_id = gerar_id(df)
    agora = datetime.now(ZoneInfo("America/Sao_Paulo"))

    delegacia_sheet.append_row([
        novo_id,
        str(numero_grv).upper(),
        str(placa).upper(),
        str(marca).upper(),
        str(modelo).upper(),
        str(cor).upper(),
        str(tipo).upper(),
        str(procedencia).upper(),
        agora.strftime("%d/%m/%Y"),
        agora.strftime("%H:%M"),
        str(agente_entrada).upper(),
        STATUS_PATIO,
        "",
        "",
        "",
        ""
    ])

    registrar_log(
        usuario=agente_entrada,
        acao="ENTRADA VEICULO DELEGACIA",
        detalhes=f"GRV {numero_grv} | PLACA {placa} | PROCEDENCIA {procedencia}"
    )

    st.cache_data.clear()

def registrar_saida_delegacia(id_veiculo, agente_saida, observacoes=""):
    df = carregar_dados_delegacia()
    df = preparar_dataframe(df)

    linha = df.index[df["id"] == id_veiculo][0] + 2
    agora = datetime.now(ZoneInfo("America/Sao_Paulo"))

    delegacia_sheet.update(f"L{linha}:P{linha}", [[
        STATUS_LIBERADO,
        agora.strftime("%d/%m/%Y"),
        agora.strftime("%H:%M"),
        str(agente_saida).upper(),
        str(observacoes).upper()
    ]])

    placa = df.loc[df["id"] == id_veiculo, "placa"].values[0]
    numero_grv = df.loc[df["id"] == id_veiculo, "numero_grv"].values[0] if "numero_grv" in df.columns else ""

    registrar_log(
        usuario=agente_saida,
        acao="SAIDA VEICULO DELEGACIA",
        detalhes=f"GRV {numero_grv} | PLACA {placa}"
    )

    st.cache_data.clear()

# =====================================================
# ---------------- MENU -------------------------------
# =====================================================

st.sidebar.markdown("## Navegação")

if st.session_state['tipo_usuario'] == 'admin':
    menu = st.sidebar.radio(
        "Módulos",
        [
            "📊 Dashboard",
            "🚗 Operação de Pátio",
            "🚔 Delegacia",
            "👥 Administração",
            "🔎 Consulta / Inventário",
            "📜 Log de Auditoria"
        ],
        label_visibility="collapsed"
    )
else:
    menu = st.sidebar.radio(
        "Módulos",
        [
            "📊 Dashboard",
            "🚗 Operação de Pátio",
            "🚔 Delegacia",
            "🔎 Consulta / Inventário"
        ],
        label_visibility="collapsed"
    )

submenu_operacao = None
submenu_delegacia = None
submenu_admin = None

if menu == "🚗 Operação de Pátio":
    st.sidebar.markdown("""
    <div class="sidebar-card">
        <div class="sidebar-title">Operação de Pátio</div>
    </div>
    """, unsafe_allow_html=True)

    submenu_operacao = st.sidebar.radio(
        "Operação de Pátio",
        [
            "Entrada de Veículo",
            "Saída de Veículo",
            "Retirada de Pertences"
        ],
        label_visibility="collapsed"
    )

if menu == "🚔 Delegacia":
    st.sidebar.markdown("""
    <div class="sidebar-card">
        <div class="sidebar-title">Módulo Delegacia</div>
    </div>
    """, unsafe_allow_html=True)

    submenu_delegacia = st.sidebar.radio(
        "Delegacia",
        [
            "Dashboard Delegacia",
            "Entrada de Veículo",
            "Saída de Veículo",
            "Consulta de Veículos"
        ],
        label_visibility="collapsed"
    )

if menu == "👥 Administração" and st.session_state['tipo_usuario'] == 'admin':
    st.sidebar.markdown("""
    <div class="sidebar-card">
        <div class="sidebar-title">Administração</div>
    </div>
    """, unsafe_allow_html=True)

    submenu_admin = st.sidebar.radio(
        "Administração",
        [
            "Cadastrar Usuário",
            "Gerenciar Usuários",
            "Minha Conta"
        ],
        label_visibility="collapsed"
    )

# =====================================================
# 📊 DASHBOARD PRINCIPAL
# =====================================================
if menu == "📊 Dashboard":
    st.subheader("Dashboard Operacional")

    df_patio = preparar_dataframe(carregar_dados())
    df_del = preparar_dataframe(carregar_dados_delegacia())

    c1, c2 = st.columns(2)
    data_inicio = c1.date_input("Período inicial", value=date(date.today().year, 1, 1), key="dash_inicio")
    data_fim = c2.date_input("Período final", value=date.today(), key="dash_fim")

    if data_inicio > data_fim:
        st.error("A data inicial não pode ser maior que a data final.")
        st.stop()

    if not df_patio.empty:
        df_patio = filtrar_por_periodo(df_patio, "data_entrada", data_inicio, data_fim)
    if not df_del.empty:
        df_del = filtrar_por_periodo(df_del, "data_entrada", data_inicio, data_fim)

    bloco1, bloco2 = st.columns(2)

    with bloco1:
        st.markdown("### 🚗 Pátio Normal")

        if df_patio.empty:
            st.info("Sem dados do pátio normal no período selecionado.")
        else:
            df_patio = montar_coluna_mes(df_patio, "data_entrada", "mes_entrada")
            df_patio = montar_coluna_mes(df_patio, "data_saida", "mes_saida")

            total_registros = len(df_patio)
            total_deposito = len(df_patio[df_patio["status"].astype(str).str.upper() == STATUS_PATIO]) if "status" in df_patio.columns else 0
            total_liberados = len(df_patio[df_patio["status"].astype(str).str.upper() == STATUS_LIBERADO]) if "status" in df_patio.columns else 0
            total_motos = len(df_patio[df_patio["tipo"].astype(str).str.upper() == "MOTOCICLETA"]) if "tipo" in df_patio.columns else 0
            total_automoveis = len(df_patio[df_patio["tipo"].astype(str).str.upper() == "AUTOMÓVEL"]) if "tipo" in df_patio.columns else 0

            a1, a2 = st.columns(2)
            with a1:
                mini_card("Total", total_registros)
            with a2:
                mini_card("No Depósito", total_deposito)

            a3, a4 = st.columns(2)
            with a3:
                mini_card("Liberados", total_liberados)
            with a4:
                mini_card("Motocicletas", total_motos)

            mini_card("Automóveis", total_automoveis)

            st.markdown("**Status**")
            if "status" in df_patio.columns:
                st.bar_chart(df_patio["status"].astype(str).str.upper().value_counts(), use_container_width=True)

            st.markdown("**Entradas por mês**")
            entradas_mes = (
                df_patio.dropna(subset=["mes_entrada"])
                .groupby("mes_entrada")
                .size()
                .sort_index()
            )
            if not entradas_mes.empty:
                st.line_chart(entradas_mes, use_container_width=True)
            else:
                st.info("Sem entradas no período.")

    with bloco2:
        st.markdown("### 🚔 Delegacia")

        if df_del.empty:
            st.info("Sem dados da delegacia no período selecionado.")
        else:
            df_del = montar_coluna_mes(df_del, "data_entrada", "mes_entrada")
            df_del = montar_coluna_mes(df_del, "data_saida", "mes_saida")

            total_registros = len(df_del)
            total_deposito = len(df_del[df_del["status"].astype(str).str.upper() == STATUS_PATIO]) if "status" in df_del.columns else 0
            total_liberados = len(df_del[df_del["status"].astype(str).str.upper() == STATUS_LIBERADO]) if "status" in df_del.columns else 0
            total_motos = len(df_del[df_del["tipo"].astype(str).str.upper() == "MOTOCICLETA"]) if "tipo" in df_del.columns else 0
            total_automoveis = len(df_del[df_del["tipo"].astype(str).str.upper() == "AUTOMÓVEL"]) if "tipo" in df_del.columns else 0

            b1, b2 = st.columns(2)
            with b1:
                mini_card("Total", total_registros)
            with b2:
                mini_card("No Depósito", total_deposito)

            b3, b4 = st.columns(2)
            with b3:
                mini_card("Liberados", total_liberados)
            with b4:
                mini_card("Motocicletas", total_motos)

            mini_card("Automóveis", total_automoveis)

            st.markdown("**Status**")
            if "status" in df_del.columns:
                st.bar_chart(df_del["status"].astype(str).str.upper().value_counts(), use_container_width=True)

            st.markdown("**Entradas por mês**")
            entradas_mes = (
                df_del.dropna(subset=["mes_entrada"])
                .groupby("mes_entrada")
                .size()
                .sort_index()
            )
            if not entradas_mes.empty:
                st.line_chart(entradas_mes, use_container_width=True)
            else:
                st.info("Sem entradas no período.")

    st.markdown("---")
    st.markdown("### Comparativos Consolidados")

    tab1, tab2, tab3 = st.tabs(["Movimentação Mensal", "Tipos e Procedência", "Produtividade"])

    with tab1:
        p1, p2 = st.columns(2)

        with p1:
            st.markdown("**Pátio Normal - Entradas x Saídas por Mês**")
            if not df_patio.empty:
                df_tmp = df_patio.copy()
                df_tmp = montar_coluna_mes(df_tmp, "data_entrada", "mes_entrada")
                df_tmp = montar_coluna_mes(df_tmp, "data_saida", "mes_saida")

                entradas = df_tmp.dropna(subset=["mes_entrada"]).groupby("mes_entrada").size().sort_index()
                saidas = df_tmp.dropna(subset=["mes_saida"]).groupby("mes_saida").size().sort_index()

                entradas_df = entradas.reset_index(name="Entradas").rename(columns={"mes_entrada": "Mês"}) if not entradas.empty else pd.DataFrame(columns=["Mês", "Entradas"])
                saidas_df = saidas.reset_index(name="Saídas").rename(columns={"mes_saida": "Mês"}) if not saidas.empty else pd.DataFrame(columns=["Mês", "Saídas"])
                comparativo = pd.merge(entradas_df, saidas_df, on="Mês", how="outer").fillna(0)

                if not comparativo.empty:
                    st.bar_chart(comparativo.set_index("Mês")[["Entradas", "Saídas"]], use_container_width=True)
                    st.dataframe(comparativo, use_container_width=True)
                else:
                    st.info("Sem dados suficientes.")
            else:
                st.info("Sem dados.")

        with p2:
            st.markdown("**Delegacia - Entradas x Saídas por Mês**")
            if not df_del.empty:
                df_tmp = df_del.copy()
                df_tmp = montar_coluna_mes(df_tmp, "data_entrada", "mes_entrada")
                df_tmp = montar_coluna_mes(df_tmp, "data_saida", "mes_saida")

                entradas = df_tmp.dropna(subset=["mes_entrada"]).groupby("mes_entrada").size().sort_index()
                saidas = df_tmp.dropna(subset=["mes_saida"]).groupby("mes_saida").size().sort_index()

                entradas_df = entradas.reset_index(name="Entradas").rename(columns={"mes_entrada": "Mês"}) if not entradas.empty else pd.DataFrame(columns=["Mês", "Entradas"])
                saidas_df = saidas.reset_index(name="Saídas").rename(columns={"mes_saida": "Mês"}) if not saidas.empty else pd.DataFrame(columns=["Mês", "Saídas"])
                comparativo = pd.merge(entradas_df, saidas_df, on="Mês", how="outer").fillna(0)

                if not comparativo.empty:
                    st.bar_chart(comparativo.set_index("Mês")[["Entradas", "Saídas"]], use_container_width=True)
                    st.dataframe(comparativo, use_container_width=True)
                else:
                    st.info("Sem dados suficientes.")
            else:
                st.info("Sem dados.")

    with tab2:
        p1, p2 = st.columns(2)
        with p1:
            st.markdown("**Pátio Normal - Tipos de Veículo**")
            if not df_patio.empty and "tipo" in df_patio.columns:
                st.bar_chart(df_patio["tipo"].astype(str).str.upper().value_counts(), use_container_width=True)
            else:
                st.info("Sem dados.")

        with p2:
            st.markdown("**Delegacia - Procedência**")
            if not df_del.empty and "procedencia" in df_del.columns:
                st.bar_chart(df_del["procedencia"].astype(str).str.upper().value_counts().head(10), use_container_width=True)
            else:
                st.info("Sem dados.")

    with tab3:
        p1, p2 = st.columns(2)
        with p1:
            st.markdown("**Pátio Normal - Entradas por Agente**")
            if not df_patio.empty and "agente_entrada" in df_patio.columns:
                st.bar_chart(df_patio["agente_entrada"].astype(str).str.upper().value_counts().head(10), use_container_width=True)
            else:
                st.info("Sem dados.")

        with p2:
            st.markdown("**Delegacia - Entradas por Agente**")
            if not df_del.empty and "agente_entrada" in df_del.columns:
                st.bar_chart(df_del["agente_entrada"].astype(str).str.upper().value_counts().head(10), use_container_width=True)
            else:
                st.info("Sem dados.")

# =====================================================
# 👥 ADMINISTRAÇÃO
# =====================================================
elif menu == "👥 Administração" and submenu_admin == "Cadastrar Usuário":
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

elif menu == "👥 Administração" and submenu_admin == "Gerenciar Usuários":
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

elif menu == "👥 Administração" and submenu_admin == "Minha Conta":
    st.subheader("Minha Conta")
    st.info("Área para alteração manual da senha do administrador.")

    with st.form("form_troca_senha_admin_manual"):
        senha_atual = st.text_input("Senha Atual", type="password")
        nova_senha = st.text_input("Nova Senha", type="password")
        confirmar_nova = st.text_input("Confirmar Nova Senha", type="password")

        if st.form_submit_button("Alterar Senha"):
            sucesso, uid, _ = login_admin(st.session_state['nome_usuario'], senha_atual)

            if not sucesso:
                st.error("Senha atual incorreta.")
            elif nova_senha != confirmar_nova:
                st.error("A nova senha e a confirmação não coincidem.")
            elif len(nova_senha) < 4:
                st.error("A nova senha deve ter pelo menos 4 caracteres.")
            else:
                alterar_senha("admin", st.session_state['usuario_id'], nova_senha)
                st.success("Senha alterada com sucesso.")

# =====================================================
# 🚗 OPERAÇÃO DE PÁTIO
# =====================================================
elif menu == "🚗 Operação de Pátio" and submenu_operacao == "Entrada de Veículo":
    st.subheader("Registro de Entrada de Veículo")

    with st.form("entrada"):
        numero_grv = st.text_input("Número da GRV")
        placa = st.text_input("Placa")
        marca = st.text_input("Marca")
        modelo = st.text_input("Modelo")
        cor = st.text_input("Cor")
        tipo = st.selectbox("Tipo", ["AUTOMÓVEL", "MOTOCICLETA", "CAMINHÃO", "OUTRO"])
        motivo = st.text_area("Motivo da Apreensão")
        agente = st.text_input("Agente Responsável", value=st.session_state['nome_usuario'])

        if st.form_submit_button("Registrar Entrada"):
            if not numero_grv or not placa or not marca or not modelo or not cor or not motivo or not agente:
                st.warning("Preencha todos os campos obrigatórios.")
            else:
                registrar_entrada_patio(
                    numero_grv=numero_grv.strip(),
                    placa=placa.strip(),
                    marca=marca.strip(),
                    modelo=modelo.strip(),
                    cor=cor.strip(),
                    tipo=tipo.strip(),
                    motivo=motivo.strip(),
                    agente=agente.strip()
                )
                st.success("✅ Veículo registrado com sucesso!")

elif menu == "🚗 Operação de Pátio" and submenu_operacao == "Saída de Veículo":
    st.subheader("Registro de Saída de Veículo")

    df = carregar_dados()
    df = preparar_dataframe(df)

    if df.empty or "status" not in df.columns:
        st.info("Nenhum veículo no depósito.")
    else:
        df_ativos = df[df["status"].astype(str).str.upper() == STATUS_PATIO]

        if df_ativos.empty:
            st.info("Nenhum veículo no depósito.")
        else:
            veiculo = st.selectbox(
                "Selecione o veículo",
                df_ativos["id"].astype(str) + " - GRV " + df_ativos["numero_grv"].astype(str) + " - " + df_ativos["placa"].astype(str)
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
                    registrar_saida_patio(
                        id_veiculo=vid,
                        agente_saida=agente_saida.strip(),
                        observacoes=obs.strip()
                    )
                    st.success("🚗 Veículo liberado com sucesso!")

elif menu == "🚗 Operação de Pátio" and submenu_operacao == "Retirada de Pertences":
    st.subheader("Retirada de Pertences do Veículo Apreendido")

    df = carregar_dados()
    df = preparar_dataframe(df)

    if df.empty or "status" not in df.columns:
        st.info("Nenhum veículo cadastrado.")
    else:
        df_ativos = df[df["status"].astype(str).str.upper() == STATUS_PATIO]

        if df_ativos.empty:
            st.info("Não há veículos atualmente no depósito para retirada de pertences.")
        else:
            veiculo = st.selectbox(
                "Selecione o veículo",
                df_ativos["id"].astype(str) + " - GRV " +
                df_ativos["numero_grv"].astype(str) + " - " +
                df_ativos["placa"].astype(str) + " - " +
                df_ativos["marca"].astype(str) + " - " +
                df_ativos["modelo"].astype(str)
            )

            col1, col2 = st.columns(2)
            agora_sp = datetime.now(ZoneInfo("America/Sao_Paulo"))
            data_retirada = col1.date_input("Data da Retirada", value=agora_sp.date())
            hora_retirada = col2.time_input("Hora da Retirada", value=agora_sp.time().replace(second=0, microsecond=0))

            nome_retirante = st.text_input("Nome Completo da Pessoa que Retirou o Pertence")
            documento_retirante = st.text_input("Documento da Pessoa que Retirou")
            itens_retirados = st.text_area("Itens Retirados do Veículo")
            observacao_retirada = st.text_area("Observação da Retirada")
            agente_responsavel = st.text_input("Agente Responsável", value=st.session_state['nome_usuario'])

            if st.button("Registrar Retirada de Pertences"):
                if not nome_retirante or not documento_retirante or not itens_retirados or not agente_responsavel:
                    st.warning("Preencha todos os campos obrigatórios.")
                else:
                    id_veiculo = int(veiculo.split(" - ")[0])
                    placa_veiculo = veiculo.split(" - ")[2]

                    registrar_retirada_pertence(
                        id_veiculo=id_veiculo,
                        placa=placa_veiculo,
                        data_retirada=data_retirada.strftime("%d/%m/%Y"),
                        hora_retirada=hora_retirada.strftime("%H:%M"),
                        nome_retirante=nome_retirante.strip(),
                        documento_retirante=documento_retirante.strip(),
                        itens_retirados=itens_retirados.strip(),
                        observacao_retirada=observacao_retirada.strip(),
                        agente_responsavel=agente_responsavel.strip()
                    )

                    st.success("✅ Retirada de pertences registrada com sucesso.")

# =====================================================
# 🚔 DELEGACIA
# =====================================================
elif menu == "🚔 Delegacia" and submenu_delegacia == "Dashboard Delegacia":
    st.subheader("Dashboard - Veículos da Delegacia")

    df_del = carregar_dados_delegacia()
    df_del = preparar_dataframe(df_del)

    c1, c2 = st.columns(2)
    data_inicio = c1.date_input("Período inicial", value=date(date.today().year, 1, 1), key="dash_del_inicio")
    data_fim = c2.date_input("Período final", value=date.today(), key="dash_del_fim")

    if data_inicio > data_fim:
        st.error("A data inicial não pode ser maior que a data final.")
        st.stop()

    if df_del.empty:
        st.info("Ainda não há dados de veículos da delegacia para exibir.")
    else:
        df_del = filtrar_por_periodo(df_del, "data_entrada", data_inicio, data_fim)
        df_del = montar_coluna_mes(df_del, "data_entrada", "mes_entrada")
        df_del = montar_coluna_mes(df_del, "data_saida", "mes_saida")

        total_registros = len(df_del)
        total_deposito = len(df_del[df_del["status"].astype(str).str.upper() == STATUS_PATIO]) if "status" in df_del.columns else 0
        total_liberados = len(df_del[df_del["status"].astype(str).str.upper() == STATUS_LIBERADO]) if "status" in df_del.columns else 0
        total_motos = len(df_del[df_del["tipo"].astype(str).str.upper() == "MOTOCICLETA"]) if "tipo" in df_del.columns else 0
        total_automoveis = len(df_del[df_del["tipo"].astype(str).str.upper() == "AUTOMÓVEL"]) if "tipo" in df_del.columns else 0
        total_caminhoes = len(df_del[df_del["tipo"].astype(str).str.upper() == "CAMINHÃO"]) if "tipo" in df_del.columns else 0

        c1, c2, c3, c4, c5 = st.columns(5)
        with c1:
            card_metrica("Total Delegacia", total_registros)
        with c2:
            card_metrica("No Depósito", total_deposito)
        with c3:
            card_metrica("Liberados", total_liberados)
        with c4:
            card_metrica("Motocicletas", total_motos)
        with c5:
            card_metrica("Automóveis", total_automoveis)

        c6, c7 = st.columns(2)
        with c6:
            card_metrica("Caminhões", total_caminhoes)
        with c7:
            card_metrica("Saldo Operacional", total_deposito - total_liberados)

        st.markdown("---")

        tab1, tab2, tab3 = st.tabs(["Visão Geral", "Movimentação Mensal", "Origem e Produtividade"])

        with tab1:
            g1, g2