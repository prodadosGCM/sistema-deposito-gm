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
st.set_page_config(
    page_title="Controle de Veículos - Depósito GCM",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ---------------- CSS MODERNO ----------------
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
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-title">🚓 Depósito Público – Controle de Veículos | GCM</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">Sistema de controle operacional, inventário, retirada de pertences, delegacia e auditoria</div>', unsafe_allow_html=True)

TZ = ZoneInfo("America/Sao_Paulo")
STATUS_DEPOSITO = "DEPÓSITO"
STATUS_LIBERADO = "LIBERADO"

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

    c.execute('''
        CREATE TABLE IF NOT EXISTS gestores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT UNIQUE,
            nome TEXT,
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

def login_gestor(usuario, senha):
    conn = get_connection()
    user = conn.execute(
        "SELECT id, nome, senha, primeiro_acesso FROM gestores WHERE usuario = ?",
        (usuario,)
    ).fetchone()
    conn.close()

    if user and check_hashes(senha, user[2]):
        return True, user[0], user[1], user[3]
    return False, None, None, None

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

def cadastrar_gestor_admin(usuario, nome, senha_inicial):
    conn = get_connection()
    try:
        senha_cripto = make_hashes(senha_inicial)
        conn.execute(
            "INSERT INTO gestores (usuario, nome, senha, primeiro_acesso) VALUES (?, ?, ?, ?)",
            (usuario, nome, senha_cripto, 1)
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

    if tipo_usuario == 'admin':
        tabela = "administradores"
    elif tipo_usuario == 'gestor':
        tabela = "gestores"
    else:
        tabela = "agentes"

    conn.execute(
        f"UPDATE {tabela} SET senha = ?, primeiro_acesso = 0 WHERE id = ?",
        (nova_senha_hash, id_usuario)
    )
    conn.commit()
    conn.close()

def validar_senha_gestor_por_id(id_usuario, senha):
    conn = get_connection()
    user = conn.execute(
        "SELECT senha FROM gestores WHERE id = ?",
        (id_usuario,)
    ).fetchone()
    conn.close()

    if user and check_hashes(senha, user[0]):
        return True
    return False

def listar_agentes():
    conn = get_connection()
    df = pd.read_sql("SELECT id, matricula, nome, primeiro_acesso FROM agentes ORDER BY nome", conn)
    conn.close()
    return df

def listar_gestores():
    conn = get_connection()
    df = pd.read_sql("SELECT id, usuario, nome, primeiro_acesso FROM gestores ORDER BY nome", conn)
    conn.close()
    return df

def excluir_agente(id_agente):
    conn = get_connection()
    conn.execute("DELETE FROM agentes WHERE id = ?", (id_agente,))
    conn.commit()
    conn.close()

def excluir_gestor(id_gestor):
    conn = get_connection()
    conn.execute("DELETE FROM gestores WHERE id = ?", (id_gestor,))
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

def resetar_senha_gestor(id_gestor, nova_senha="1234"):
    conn = get_connection()
    senha_hash = make_hashes(nova_senha)
    conn.execute(
        "UPDATE gestores SET senha = ?, primeiro_acesso = 1 WHERE id = ?",
        (senha_hash, id_gestor)
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

        tipo = st.radio("Entrar como:", ["Agente", "Gestor", "Administrador"], horizontal=True)

        if tipo == "Administrador":
            usuario_input = st.text_input("Usuário do Admin")
        elif tipo == "Gestor":
            usuario_input = st.text_input("Usuário do Gestor")
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

            elif tipo == "Gestor":
                sucesso, uid, nome, p_acesso = login_gestor(usuario_input, senha_input)
                if sucesso:
                    st.session_state['logado'] = True
                    st.session_state['tipo_usuario'] = 'gestor'
                    st.session_state['usuario_id'] = uid
                    st.session_state['nome_usuario'] = nome
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
    with st.form("form_troca_senha", clear_on_submit=True):
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
        nova_aba.append_row([
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
        ])
        return nova_aba

def conectar_aba_log():
    try:
        return sheet.spreadsheet.worksheet("log_auditoria")
    except Exception:
        nova_aba = sheet.spreadsheet.add_worksheet(title="log_auditoria", rows=2000, cols=5)
        nova_aba.append_row([
            "data",
            "hora",
            "usuario",
            "acao",
            "detalhes"
        ])
        return nova_aba

def conectar_aba_delegacia():
    try:
        return sheet.spreadsheet.worksheet("veiculos_delegacia")
    except Exception:
        nova_aba = sheet.spreadsheet.add_worksheet(title="veiculos_delegacia", rows=2000, cols=16)
        nova_aba.append_row([
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
        ])
        return nova_aba

retirada_sheet = conectar_aba_retiradas()
log_sheet = conectar_aba_log()
delegacia_sheet = conectar_aba_delegacia()

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
    agora = datetime.now(TZ)
    log_sheet.append_row([
        agora.strftime("%d/%m/%Y"),
        agora.strftime("%H:%M:%S"),
        str(usuario).upper(),
        str(acao).upper(),
        str(detalhes).upper()
    ])

def validar_hora_manual(hora_str):
    try:
        hora_obj = datetime.strptime(hora_str.strip(), "%H:%M")
        return True, hora_obj.strftime("%H:%M")
    except:
        return False, None

def validar_data_manual(data_str):
    try:
        data_obj = datetime.strptime(data_str.strip(), "%d/%m/%Y")
        return True, data_obj
    except:
        return False, None

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
    if "número grv" in df.columns and "numero_grv" not in df.columns:
        mapa_alias["número grv"] = "numero_grv"
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

def card_metrica(titulo, valor):
    st.markdown(f"""
        <div class="metric-card">
            <h4>{titulo}</h4>
            <h2>{valor}</h2>
        </div>
    """, unsafe_allow_html=True)

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

def registrar_entrada_delegacia(numero_grv, placa, marca, modelo, cor, tipo, procedencia, data_entrada, hora_entrada, agente_entrada):
    df = carregar_dados_delegacia()
    novo_id = gerar_id(df)

    delegacia_sheet.append_row([
        novo_id,
        str(numero_grv).upper(),
        str(placa).upper(),
        str(marca).upper(),
        str(modelo).upper(),
        str(cor).upper(),
        str(tipo).upper(),
        str(procedencia).upper(),
        data_entrada.strftime("%d/%m/%Y"),
        str(hora_entrada),
        str(agente_entrada).upper(),
        STATUS_DEPOSITO,
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

def registrar_saida_delegacia(id_veiculo, data_saida, hora_saida, agente_saida, observacoes=""):
    df = carregar_dados_delegacia()
    df = preparar_dataframe(df)

    linha = df.index[df["id"] == id_veiculo][0] + 2

    delegacia_sheet.update(f"L{linha}:P{linha}", [[
        STATUS_LIBERADO,
        data_saida.strftime("%d/%m/%Y"),
        str(hora_saida),
        str(agente_saida).upper(),
        str(observacoes).upper()
    ]])

    placa = df.loc[df["id"] == id_veiculo, "placa"].values[0]
    numero_grv = df.loc[df["id"] == id_veiculo, "numero_grv"].values[0]

    registrar_log(
        usuario=agente_saida,
        acao="SAIDA VEICULO DELEGACIA",
        detalhes=f"GRV {numero_grv} | PLACA {placa}"
    )

    st.cache_data.clear()

def registrar_entrada_patio(numero_grv, placa, marca, modelo, cor, tipo, motivo, data_entrada, hora_entrada, agente):
    df = carregar_dados()
    novo_id = gerar_id(df)

    sheet.append_row([
        novo_id,
        str(numero_grv).upper(),
        str(placa).upper(),
        str(marca).upper(),
        str(modelo).upper(),
        str(cor).upper(),
        str(tipo).upper(),
        str(motivo).upper(),
        data_entrada.strftime("%d/%m/%Y"),
        str(hora_entrada),
        str(agente).upper(),
        STATUS_DEPOSITO,
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

def registrar_saida_patio(id_veiculo, data_saida, hora_saida, agente_saida, observacoes=""):
    df = carregar_dados()
    df = preparar_dataframe(df)

    linha = df.index[df["id"] == id_veiculo][0] + 2

    sheet.update(f"L{linha}:P{linha}", [[
        STATUS_LIBERADO,
        data_saida.strftime("%d/%m/%Y"),
        str(hora_saida),
        str(agente_saida).upper(),
        str(observacoes).upper()
    ]])

    registrar_log(
        usuario=agente_saida,
        acao="SAIDA DE VEICULO",
        detalhes=f"GRV {df.loc[df['id'] == id_veiculo, 'numero_grv'].values[0]} | PLACA {df.loc[df['id'] == id_veiculo, 'placa'].values[0]}"
    )

    st.cache_data.clear()

# =====================================================
# ---------------- MENU -------------------------------
# =====================================================

if st.session_state['tipo_usuario'] in ['admin', 'gestor']:
    menu = st.sidebar.radio(
        "Menu Principal",
        [
            "📊 Dashboard",
            "👤 Cadastrar Usuário",
            "📋 Gerenciar Usuários",
            "🔐 Minha Conta",
            "🚗 Entrada de Veículo",
            "📤 Saída de Veículo",
            "🧾 Retirada de Pertences",
            "🚔 Delegacia",
            "🔎 Consulta / Inventário",
            "📜 Log de Auditoria"
        ]
    )
else:
    menu = st.sidebar.radio(
        "Menu Principal",
        [
            "📊 Dashboard",
            "🚗 Entrada de Veículo",
            "📤 Saída de Veículo",
            "🧾 Retirada de Pertences",
            "🚔 Delegacia",
            "🔎 Consulta / Inventário"
        ]
    )

submenu_delegacia = None

if menu == "🚔 Delegacia":
    st.sidebar.markdown("---")
    st.sidebar.markdown("### Submenu Delegacia")
    submenu_delegacia = st.sidebar.radio(
        "Escolha uma opção",
        [
            "Entrada de Veículo",
            "Saída de Veículo",
            "Consulta de Veículos"
        ]
    )

# =====================================================
# 📊 DASHBOARD
# =====================================================

if menu == "📊 Dashboard":
    st.subheader("Dashboard Operacional")

    df = carregar_dados()
    df = preparar_dataframe(df)

    if df.empty:
        st.info("Ainda não há dados para exibir no dashboard.")
    else:
        df = montar_coluna_mes(df, "data_entrada", "mes_entrada")
        df = montar_coluna_mes(df, "data_saida", "mes_saida")

        total_registros = len(df)
        total_deposito = len(df[df["status"].astype(str).str.upper() == STATUS_DEPOSITO]) if "status" in df.columns else 0
        total_liberados = len(df[df["status"].astype(str).str.upper() == STATUS_LIBERADO]) if "status" in df.columns else 0
        total_motos = len(df[df["tipo"].astype(str).str.upper() == "MOTOCICLETA"]) if "tipo" in df.columns else 0
        total_automoveis = len(df[df["tipo"].astype(str).str.upper() == "AUTOMÓVEL"]) if "tipo" in df.columns else 0
        total_caminhoes = len(df[df["tipo"].astype(str).str.upper() == "CAMINHÃO"]) if "tipo" in df.columns else 0

        c1, c2, c3, c4, c5 = st.columns(5)
        with c1:
            card_metrica("Total de Registros", total_registros)
        with c2:
            card_metrica("No Depósito", total_deposito)
        with c3:
            card_metrica("Liberados", total_liberados)
        with c4:
            card_metrica("Motocicletas", total_motos)
        with c5:
            card_metrica("Automóveis", total_automoveis)

        st.markdown("")
        st.columns(1)[0].markdown(f"""
            <div class="metric-card">
                <h4>Caminhões</h4>
                <h2>{total_caminhoes}</h2>
            </div>
        """, unsafe_allow_html=True)

        st.markdown("---")

        tab1, tab2, tab3 = st.tabs(["Visão Geral", "Movimentação Mensal", "Produtividade"])

        with tab1:
            g1, g2 = st.columns(2)

            with g1:
                st.markdown("**Veículos por Status**")
                if "status" in df.columns:
                    status_count = df["status"].astype(str).str.upper().value_counts()
                    st.bar_chart(status_count, use_container_width=True)

            with g2:
                st.markdown("**Veículos por Tipo**")
                if "tipo" in df.columns:
                    tipo_count = df["tipo"].astype(str).str.upper().value_counts()
                    st.bar_chart(tipo_count, use_container_width=True)

            g3, g4 = st.columns(2)

            with g3:
                st.markdown("**Top 10 Marcas**")
                if "marca" in df.columns:
                    marca_count = df["marca"].astype(str).str.upper().value_counts().head(10)
                    st.bar_chart(marca_count, use_container_width=True)

            with g4:
                st.markdown("**Entradas por Agente**")
                if "agente_entrada" in df.columns:
                    agente_count = df["agente_entrada"].astype(str).str.upper().value_counts().head(10)
                    st.bar_chart(agente_count, use_container_width=True)

        with tab2:
            m1, m2 = st.columns(2)

            entradas_mes = (
                df.dropna(subset=["mes_entrada"])
                  .groupby("mes_entrada")
                  .size()
                  .sort_index()
            )

            saidas_mes = (
                df.dropna(subset=["mes_saida"])
                  .groupby("mes_saida")
                  .size()
                  .sort_index()
            )

            with m1:
                st.markdown("**Quantidade de Entradas por Mês**")
                if not entradas_mes.empty:
                    st.line_chart(entradas_mes, use_container_width=True)
                    st.dataframe(
                        entradas_mes.reset_index(name="Entradas").rename(columns={"mes_entrada": "Mês"}),
                        use_container_width=True
                    )
                else:
                    st.info("Sem dados de entrada por mês.")

            with m2:
                st.markdown("**Quantidade de Saídas por Mês**")
                if not saidas_mes.empty:
                    st.line_chart(saidas_mes, use_container_width=True)
                    st.dataframe(
                        saidas_mes.reset_index(name="Saídas").rename(columns={"mes_saida": "Mês"}),
                        use_container_width=True
                    )
                else:
                    st.info("Sem dados de saída por mês.")

            st.markdown("**Comparativo de Entradas x Saídas por Mês**")
            entradas_df = entradas_mes.reset_index(name="Entradas").rename(columns={"mes_entrada": "Mês"}) if not entradas_mes.empty else pd.DataFrame(columns=["Mês", "Entradas"])
            saidas_df = saidas_mes.reset_index(name="Saídas").rename(columns={"mes_saida": "Mês"}) if not saidas_mes.empty else pd.DataFrame(columns=["Mês", "Saídas"])
            comparativo = pd.merge(entradas_df, saidas_df, on="Mês", how="outer").fillna(0)

            if not comparativo.empty:
                comparativo = comparativo.sort_values("Mês")
                st.bar_chart(comparativo.set_index("Mês")[["Entradas", "Saídas"]], use_container_width=True)
                st.dataframe(comparativo, use_container_width=True)
            else:
                st.info("Sem dados suficientes para o comparativo mensal.")

        with tab3:
            p1, p2 = st.columns(2)

            with p1:
                st.markdown("**Saídas por Agente**")
                if "agente_saida" in df.columns:
                    saida_agente = (
                        df[df["agente_saida"].astype(str).str.strip() != ""]
                        ["agente_saida"]
                        .astype(str)
                        .str.upper()
                        .value_counts()
                        .head(10)
                    )
                    if not saida_agente.empty:
                        st.bar_chart(saida_agente, use_container_width=True)
                    else:
                        st.info("Sem registros de saída por agente.")

            with p2:
                st.markdown("**Entradas por Data**")
                if "data_entrada" in df.columns:
                    df_datas = df.copy()
                    df_datas["data_entrada_dt"] = pd.to_datetime(df_datas["data_entrada"], format="%d/%m/%Y", errors="coerce")
                    entradas_por_data = (
                        df_datas.dropna(subset=["data_entrada_dt"])
                        .groupby("data_entrada_dt")
                        .size()
                        .sort_index()
                    )
                    if not entradas_por_data.empty:
                        st.line_chart(entradas_por_data, use_container_width=True)
                    else:
                        st.info("Sem datas válidas para o gráfico.")

# =====================================================
# 👤 CADASTRO DE USUÁRIO - ADMIN E GESTOR
# =====================================================

elif menu == "👤 Cadastrar Usuário":
    st.subheader("Cadastro de Usuário")

    tipo_novo_usuario = st.selectbox("Tipo de Usuário", ["Agente", "Gestor"])

    with st.form("form_cadastro_usuario", clear_on_submit=True):
        if tipo_novo_usuario == "Agente":
            identificador = st.text_input("Matrícula")
        else:
            identificador = st.text_input("Usuário do Gestor")

        nome = st.text_input("Nome Completo")
        senha_inicial = st.text_input("Senha Inicial", value="1234", type="password")

        if st.form_submit_button("Cadastrar Usuário"):
            if not identificador or not nome or not senha_inicial:
                st.warning("Preencha todos os campos.")
            else:
                if tipo_novo_usuario == "Agente":
                    ok = cadastrar_agente_admin(
                        identificador.strip(),
                        nome.strip(),
                        senha_inicial.strip()
                    )
                else:
                    ok = cadastrar_gestor_admin(
                        identificador.strip(),
                        nome.strip(),
                        senha_inicial.strip()
                    )

                if ok:
                    st.success(f"{tipo_novo_usuario} cadastrado com sucesso. No primeiro acesso deverá trocar a senha.")
                else:
                    st.error("Usuário/Matrícula já cadastrado.")

# =====================================================
# 📋 GERENCIAR USUÁRIOS - ADMIN E GESTOR
# =====================================================

elif menu == "📋 Gerenciar Usuários":
    st.subheader("Gerenciamento de Usuários")

    aba1, aba2 = st.tabs(["Agentes", "Gestores"])

    with aba1:
        df_agentes = listar_agentes()

        if df_agentes.empty:
            st.info("Nenhum agente cadastrado.")
        else:
            st.dataframe(df_agentes, use_container_width=True)

            opcoes = df_agentes["matricula"].astype(str) + " - " + df_agentes["nome"]
            selecionado = st.selectbox("Selecione um agente", opcoes, key="sel_agente")

            matricula_sel = selecionado.split(" - ")[0]
            agente_sel = df_agentes[df_agentes["matricula"].astype(str) == matricula_sel].iloc[0]
            id_agente_sel = int(agente_sel["id"])

            col1, col2 = st.columns(2)

            with col1:
                if st.button("Resetar Senha do Agente para 1234", key="reset_agente"):
                    resetar_senha_agente(id_agente_sel, "1234")
                    st.success("Senha resetada com sucesso.")
                    time.sleep(1)
                    st.rerun()

            with col2:
                if st.button("Excluir Agente", type="primary", key="exc_agente"):
                    excluir_agente(id_agente_sel)
                    st.success("Agente excluído com sucesso.")
                    time.sleep(1)
                    st.rerun()

    with aba2:
        df_gestores = listar_gestores()

        if df_gestores.empty:
            st.info("Nenhum gestor cadastrado.")
        else:
            st.dataframe(df_gestores, use_container_width=True)

            opcoes = df_gestores["usuario"].astype(str) + " - " + df_gestores["nome"]
            selecionado = st.selectbox("Selecione um gestor", opcoes, key="sel_gestor")

            usuario_sel = selecionado.split(" - ")[0]
            gestor_sel = df_gestores[df_gestores["usuario"].astype(str) == usuario_sel].iloc[0]
            id_gestor_sel = int(gestor_sel["id"])

            col1, col2 = st.columns(2)

            with col1:
                if st.button("Resetar Senha do Gestor para 1234", key="reset_gestor"):
                    resetar_senha_gestor(id_gestor_sel, "1234")
                    st.success("Senha resetada com sucesso.")
                    time.sleep(1)
                    st.rerun()

            with col2:
                if st.button("Excluir Gestor", type="primary", key="exc_gestor"):
                    excluir_gestor(id_gestor_sel)
                    st.success("Gestor excluído com sucesso.")
                    time.sleep(1)
                    st.rerun()

# =====================================================
# 🔐 MINHA CONTA - ADMIN E GESTOR
# =====================================================

elif menu == "🔐 Minha Conta":
    st.subheader("Minha Conta")

    if st.session_state['tipo_usuario'] == 'admin':
        st.info("Área para alteração manual da senha do administrador.")

        with st.form("form_troca_senha_admin_manual", clear_on_submit=True):
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

    elif st.session_state['tipo_usuario'] == 'gestor':
        st.info("Área para alteração da senha do gestor.")

        with st.form("form_troca_senha_gestor_manual", clear_on_submit=True):
            senha_atual = st.text_input("Senha Atual", type="password")
            nova_senha = st.text_input("Nova Senha", type="password")
            confirmar_nova = st.text_input("Confirmar Nova Senha", type="password")

            if st.form_submit_button("Alterar Senha"):
                if not validar_senha_gestor_por_id(st.session_state['usuario_id'], senha_atual):
                    st.error("Senha atual incorreta.")
                elif nova_senha != confirmar_nova:
                    st.error("A nova senha e a confirmação não coincidem.")
                elif len(nova_senha) < 4:
                    st.error("A nova senha deve ter pelo menos 4 caracteres.")
                else:
                    alterar_senha("gestor", st.session_state['usuario_id'], nova_senha)
                    st.success("Senha alterada com sucesso.")

# =====================================================
# 🚗 ENTRADA DE VEÍCULO
# =====================================================

elif menu == "🚗 Entrada de Veículo":
    st.subheader("Registro de Entrada de Veículo")

    agora = datetime.now(TZ)

    with st.form("entrada", clear_on_submit=True):
        numero_grv = st.text_input("Número da GRV")
        placa = st.text_input("Placa")
        marca = st.text_input("Marca")
        modelo = st.text_input("Modelo")
        cor = st.text_input("Cor")
        tipo = st.selectbox("Tipo", ["AUTOMÓVEL", "MOTOCICLETA", "CAMINHÃO", "OUTRO"])
        motivo = st.text_area("Motivo da Apreensão")
        data_entrada = st.text_input("Data da Entrada (DD/MM/AAAA)", value=agora.strftime("%d/%m/%Y"))
        hora_entrada = st.text_input("Hora da Entrada (HH:MM)", value=agora.strftime("%H:%M"))
        agente = st.text_input("Agente Responsável", value=st.session_state['nome_usuario'])

        if st.form_submit_button("Registrar Entrada"):
            data_ok, data_formatada = validar_data_manual(data_entrada)
            hora_ok, hora_formatada = validar_hora_manual(hora_entrada)

            if not numero_grv or not placa or not marca or not modelo or not cor or not motivo or not agente:
                st.warning("Preencha todos os campos obrigatórios.")
            elif not data_ok:
                st.error("Data inválida. Use o formato DD/MM/AAAA, por exemplo 23/03/2026.")
            elif not hora_ok:
                st.error("Hora inválida. Use o formato HH:MM, por exemplo 14:35.")
            else:
                registrar_entrada_patio(
                    numero_grv=numero_grv.strip(),
                    placa=placa.strip(),
                    marca=marca.strip(),
                    modelo=modelo.strip(),
                    cor=cor.strip(),
                    tipo=tipo.strip(),
                    motivo=motivo.strip(),
                    data_entrada=data_formatada,
                    hora_entrada=hora_formatada,
                    agente=agente.strip()
                )
                st.success("✅ Veículo registrado com sucesso!")

# =====================================================
# 📤 SAÍDA DE VEÍCULO
# =====================================================

elif menu == "📤 Saída de Veículo":
    st.subheader("Registro de Saída de Veículo")

    df = carregar_dados()
    df = preparar_dataframe(df)

    if df.empty or "status" not in df.columns:
        st.info("Nenhum veículo no depósito.")
    else:
        df_ativos = df[df["status"].astype(str).str.upper() == STATUS_DEPOSITO]

        if df_ativos.empty:
            st.info("Nenhum veículo no depósito.")
        else:
            agora = datetime.now(TZ)

            with st.form("form_saida_veiculo", clear_on_submit=True):
                veiculo = st.selectbox(
                    "Selecione o veículo",
                    df_ativos["id"].astype(str) + " - GRV " + df_ativos["numero_grv"].astype(str) + " - " + df_ativos["placa"].astype(str)
                )
                data_saida = st.text_input("Data da Saída (DD/MM/AAAA)", value=agora.strftime("%d/%m/%Y"), key="data_saida_patio")
                hora_saida = st.text_input("Hora da Saída (HH:MM)", value=agora.strftime("%H:%M"), key="hora_saida_patio")
                agente_saida = st.text_input(
                    "Agente Responsável pela Liberação",
                    value=st.session_state['nome_usuario']
                )
                obs = st.text_area("Observações")

                if st.form_submit_button("Registrar Saída"):
                    data_ok, data_formatada = validar_data_manual(data_saida)
                    hora_ok, hora_formatada = validar_hora_manual(hora_saida)

                    if not agente_saida:
                        st.warning("Informe o agente responsável pela liberação.")
                    elif not data_ok:
                        st.error("Data inválida. Use o formato DD/MM/AAAA.")
                    elif not hora_ok:
                        st.error("Hora inválida. Use o formato HH:MM, por exemplo 16:20.")
                    else:
                        vid = int(veiculo.split(" - ")[0])
                        registrar_saida_patio(
                            id_veiculo=vid,
                            data_saida=data_formatada,
                            hora_saida=hora_formatada,
                            agente_saida=agente_saida.strip(),
                            observacoes=obs.strip()
                        )
                        st.success("🚗 Veículo liberado com sucesso!")

# =====================================================
# 🧾 RETIRADA DE PERTENCES
# =====================================================

elif menu == "🧾 Retirada de Pertences":
    st.subheader("Retirada de Pertences do Veículo Apreendido")

    df = carregar_dados()
    df = preparar_dataframe(df)

    if df.empty or "status" not in df.columns:
        st.info("Nenhum veículo cadastrado.")
    else:
        df_ativos = df[df["status"].astype(str).str.upper() == STATUS_DEPOSITO]

        if df_ativos.empty:
            st.info("Não há veículos atualmente no depósito para retirada de pertences.")
        else:
            agora_sp = datetime.now(TZ)

            with st.form("form_retirada_pertences", clear_on_submit=True):
                veiculo = st.selectbox(
                    "Selecione o veículo",
                    df_ativos["id"].astype(str) + " - GRV " +
                    df_ativos["numero_grv"].astype(str) + " - " +
                    df_ativos["placa"].astype(str) + " - " +
                    df_ativos["marca"].astype(str) + " - " +
                    df_ativos["modelo"].astype(str)
                )

                data_retirada = st.text_input("Data da Retirada (DD/MM/AAAA)", value=agora_sp.strftime("%d/%m/%Y"))
                hora_retirada = st.text_input("Hora da Retirada (HH:MM)", value=agora_sp.strftime("%H:%M"))

                nome_retirante = st.text_input("Nome Completo da Pessoa que Retirou o Pertence")
                documento_retirante = st.text_input("Documento da Pessoa que Retirou")
                itens_retirados = st.text_area("Itens Retirados do Veículo")
                observacao_retirada = st.text_area("Observação da Retirada")
                agente_responsavel = st.text_input("Agente Responsável", value=st.session_state['nome_usuario'])

                if st.form_submit_button("Registrar Retirada de Pertences"):
                    data_ok, data_formatada = validar_data_manual(data_retirada)
                    hora_ok, hora_formatada = validar_hora_manual(hora_retirada)

                    if not nome_retirante or not documento_retirante or not itens_retirados or not agente_responsavel:
                        st.warning("Preencha todos os campos obrigatórios.")
                    elif not data_ok:
                        st.error("Data inválida. Use o formato DD/MM/AAAA.")
                    elif not hora_ok:
                        st.error("Hora inválida. Use o formato HH:MM.")
                    else:
                        id_veiculo = int(veiculo.split(" - ")[0])
                        placa_veiculo = veiculo.split(" - ")[2]

                        registrar_retirada_pertence(
                            id_veiculo=id_veiculo,
                            placa=placa_veiculo,
                            data_retirada=data_formatada.strftime("%d/%m/%Y"),
                            hora_retirada=hora_formatada,
                            nome_retirante=nome_retirante.strip(),
                            documento_retirante=documento_retirante.strip(),
                            itens_retirados=itens_retirados.strip(),
                            observacao_retirada=observacao_retirada.strip(),
                            agente_responsavel=agente_responsavel.strip()
                        )

                        st.success("✅ Retirada de pertences registrada com sucesso.")

# =====================================================
# 🚔 ENTRADA DE VEÍCULO DA DELEGACIA
# =====================================================

elif menu == "🚔 Delegacia" and submenu_delegacia == "Entrada de Veículo":
    st.subheader("Registro de Entrada de Veículo - Delegacia")

    agora = datetime.now(TZ)

    with st.form("entrada_delegacia", clear_on_submit=True):
        numero_grv = st.text_input("Número da GRV")
        placa = st.text_input("Placa")
        marca = st.text_input("Marca")
        modelo = st.text_input("Modelo")
        cor = st.text_input("Cor")
        tipo = st.selectbox("Tipo", ["AUTOMÓVEL", "MOTOCICLETA", "CAMINHÃO", "OUTRO"], key="tipo_delegacia")
        procedencia = st.text_input("Procedência / Delegacia de Origem")
        data_entrada = st.text_input("Data da Entrada (DD/MM/AAAA)", value=agora.strftime("%d/%m/%Y"), key="data_entrada_del")
        hora_entrada = st.text_input("Hora da Entrada (HH:MM)", value=agora.strftime("%H:%M"), key="hora_entrada_del")
        agente = st.text_input("Agente Responsável", value=st.session_state['nome_usuario'])

        if st.form_submit_button("Registrar Entrada - Delegacia"):
            data_ok, data_formatada = validar_data_manual(data_entrada)
            hora_ok, hora_formatada = validar_hora_manual(hora_entrada)

            if not numero_grv or not placa or not marca or not modelo or not cor or not procedencia or not agente:
                st.warning("Preencha todos os campos obrigatórios.")
            elif not data_ok:
                st.error("Data inválida. Use o formato DD/MM/AAAA.")
            elif not hora_ok:
                st.error("Hora inválida. Use o formato HH:MM.")
            else:
                registrar_entrada_delegacia(
                    numero_grv=numero_grv.strip(),
                    placa=placa.strip(),
                    marca=marca.strip(),
                    modelo=modelo.strip(),
                    cor=cor.strip(),
                    tipo=tipo.strip(),
                    procedencia=procedencia.strip(),
                    data_entrada=data_formatada,
                    hora_entrada=hora_formatada,
                    agente_entrada=agente.strip()
                )
                st.success("✅ Veículo da delegacia registrado com sucesso.")

# =====================================================
# 🚔 SAÍDA DE VEÍCULO DA DELEGACIA
# =====================================================

elif menu == "🚔 Delegacia" and submenu_delegacia == "Saída de Veículo":
    st.subheader("Registro de Saída de Veículo - Delegacia")

    df_del = carregar_dados_delegacia()
    df_del = preparar_dataframe(df_del)

    if df_del.empty or "status" not in df_del.columns:
        st.info("Nenhum veículo da delegacia registrado.")
    else:
        df_ativos = df_del[df_del["status"].astype(str).str.upper() == STATUS_DEPOSITO]

        if df_ativos.empty:
            st.info("Nenhum veículo da delegacia no depósito.")
        else:
            agora = datetime.now(TZ)

            with st.form("form_saida_delegacia", clear_on_submit=True):
                veiculo = st.selectbox(
                    "Selecione o veículo da delegacia",
                    df_ativos["id"].astype(str) + " - GRV " + df_ativos["numero_grv"].astype(str) + " - " + df_ativos["placa"].astype(str) + " - " + df_ativos["procedencia"].astype(str)
                )
                data_saida = st.text_input("Data da Saída (DD/MM/AAAA)", value=agora.strftime("%d/%m/%Y"), key="data_saida_del")
                hora_saida = st.text_input("Hora da Saída (HH:MM)", value=agora.strftime("%H:%M"), key="hora_saida_del")
                agente_saida = st.text_input(
                    "Agente Responsável pela Liberação",
                    value=st.session_state['nome_usuario'],
                    key="agente_saida_delegacia"
                )
                obs = st.text_area("Observações", key="obs_saida_delegacia")

                if st.form_submit_button("Registrar Saída - Delegacia"):
                    data_ok, data_formatada = validar_data_manual(data_saida)
                    hora_ok, hora_formatada = validar_hora_manual(hora_saida)

                    if not agente_saida:
                        st.warning("Informe o agente responsável pela liberação.")
                    elif not data_ok:
                        st.error("Data inválida. Use o formato DD/MM/AAAA.")
                    elif not hora_ok:
                        st.error("Hora inválida. Use o formato HH:MM.")
                    else:
                        id_veiculo = int(veiculo.split(" - ")[0])

                        registrar_saida_delegacia(
                            id_veiculo=id_veiculo,
                            data_saida=data_formatada,
                            hora_saida=hora_formatada,
                            agente_saida=agente_saida.strip(),
                            observacoes=obs.strip()
                        )

                        st.success("✅ Saída de veículo da delegacia registrada com sucesso.")

# =====================================================
# 🚔 CONSULTA DE VEÍCULOS DA DELEGACIA
# =====================================================

elif menu == "🚔 Delegacia" and submenu_delegacia == "Consulta de Veículos":
    st.subheader("Consulta de Veículos Vindos da Delegacia")

    df_del = carregar_dados_delegacia()
    df_del = preparar_dataframe(df_del)

    if df_del.empty:
        st.info("Nenhum veículo da delegacia registrado.")
    else:
        c1, c2, c3, c4 = st.columns(4)
        placa_del = c1.text_input("Placa", key="placa_del")
        marca_del = c2.text_input("Marca", key="marca_del")
        procedencia_del = c3.text_input("Procedência", key="procedencia_del")
        status_del = c4.selectbox("Status", ["Todos", STATUS_DEPOSITO, STATUS_LIBERADO], key="status_del")

        if placa_del and "placa" in df_del.columns:
            df_del = df_del[df_del["placa"].astype(str).str.contains(placa_del.upper(), na=False)]

        if marca_del and "marca" in df_del.columns:
            df_del = df_del[df_del["marca"].astype(str).str.contains(marca_del, case=False, na=False)]

        if procedencia_del and "procedencia" in df_del.columns:
            df_del = df_del[df_del["procedencia"].astype(str).str.contains(procedencia_del, case=False, na=False)]

        if status_del != "Todos" and "status" in df_del.columns:
            df_del = df_del[df_del["status"].astype(str).str.upper() == status_del]

        st.dataframe(df_del, use_container_width=True)

# =====================================================
# 🔎 CONSULTA / INVENTÁRIO
# =====================================================

elif menu == "🔎 Consulta / Inventário":
    st.subheader("Consulta de Veículos")

    tab1, tab2 = st.tabs(["Veículos", "Histórico de Retirada de Pertences"])

    with tab1:
        df = carregar_dados()
        df = preparar_dataframe(df)

        if df.empty:
            st.info("Nenhum registro encontrado.")
        else:
            col1, col2, col3, col4 = st.columns(4)
            placa = col1.text_input("Placa")
            marca = col2.text_input("Marca")
            data = col3.text_input("Data de Entrada (dd/mm/aaaa)")
            status = col4.selectbox("Status", ["Todos", STATUS_DEPOSITO, STATUS_LIBERADO])

            if placa and "placa" in df.columns:
                df = df[df["placa"].astype(str).str.contains(placa.upper(), na=False)]

            if marca and "marca" in df.columns:
                df = df[df["marca"].astype(str).str.contains(marca, case=False, na=False)]

            if data and "data_entrada" in df.columns:
                df = df[df["data_entrada"].astype(str) == data]

            if status != "Todos" and "status" in df.columns:
                df = df[df["status"].astype(str).str.upper() == status]

            st.dataframe(df, use_container_width=True)

    with tab2:
        st.subheader("Histórico de Retirada de Pertences")

        df_ret = carregar_retiradas()

        if df_ret.empty:
            st.info("Nenhuma retirada de pertences registrada.")
        else:
            colr1, colr2, colr3 = st.columns(3)
            filtro_placa = colr1.text_input("Filtrar por placa")
            filtro_nome = colr2.text_input("Filtrar por nome do retirante")
            filtro_doc = colr3.text_input("Filtrar por documento")

            if filtro_placa and "placa" in df_ret.columns:
                df_ret = df_ret[df_ret["placa"].astype(str).str.contains(filtro_placa.upper(), na=False)]

            if filtro_nome and "nome_retirante" in df_ret.columns:
                df_ret = df_ret[df_ret["nome_retirante"].astype(str).str.contains(filtro_nome, case=False, na=False)]

            if filtro_doc and "documento_retirante" in df_ret.columns:
                df_ret = df_ret[df_ret["documento_retirante"].astype(str).str.contains(filtro_doc, case=False, na=False)]

            st.dataframe(df_ret, use_container_width=True)

# =====================================================
# 📜 LOG DE AUDITORIA - ADMIN E GESTOR
# =====================================================

elif menu == "📜 Log de Auditoria":
    st.subheader("Log de Auditoria do Sistema")

    df_log = carregar_logs()

    if df_log.empty:
        st.info("Nenhum log registrado.")
    else:
        c1, c2, c3 = st.columns(3)
        filtro_usuario = c1.text_input("Filtrar por usuário")
        filtro_acao = c2.text_input("Filtrar por ação")
        filtro_data = c3.text_input("Filtrar por data (dd/mm/aaaa)")

        if filtro_usuario and "usuario" in df_log.columns:
            df_log = df_log[df_log["usuario"].astype(str).str.contains(filtro_usuario, case=False, na=False)]

        if filtro_acao and "acao" in df_log.columns:
            df_log = df_log[df_log["acao"].astype(str).str.contains(filtro_acao, case=False, na=False)]

        if filtro_data and "data" in df_log.columns:
            df_log = df_log[df_log["data"].astype(str) == filtro_data]

        st.dataframe(df_log, use_container_width=True)