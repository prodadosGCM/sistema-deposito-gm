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
    .section-box {
        background: #ffffff;
        padding: 16px;
        border-radius: 16px;
        border: 1px solid #e5e7eb;
        box-shadow: 0 3px 12px rgba(0,0,0,0.05);
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 10px;
        padding: 8px 14px;
    }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-title">🚓 Depósito Público – Controle de Veículos | GCM</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">Sistema de controle operacional, inventário e auditoria</div>', unsafe_allow_html=True)

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
        "placa", "marca", "modelo", "cor", "tipo",
        "motivo_apreensao", "motivo da apreensão", "motivo",
        "agente_entrada", "agente entrada",
        "status",
        "data_saida", "hora_saida", "agente_saida", "agente saída",
        "observacoes", "observações"
    ]

    for col in df.columns:
        if col in colunas_texto:
            df[col] = df[col].astype(str)

    if "id" in df.columns:
        df["id"] = pd.to_numeric(df["id"], errors="coerce")

    # Ajuste de aliases de colunas
    mapa_alias = {}
    if "motivo da apreensão" in df.columns and "motivo_apreensao" not in df.columns:
        mapa_alias["motivo da apreensão"] = "motivo_apreensao"
    if "agente entrada" in df.columns and "agente_entrada" not in df.columns:
        mapa_alias["agente entrada"] = "agente_entrada"
    if "agente saída" in df.columns and "agente_saida" not in df.columns:
        mapa_alias["agente saída"] = "agente_saida"
    if "observações" in df.columns and "observacoes" not in df.columns:
        mapa_alias["observações"] = "observacoes"

    if mapa_alias:
        df = df.rename(columns=mapa_alias)

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
            "🔐 Minha Conta",
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
        total_deposito = len(df[df["status"].astype(str).str.upper() == "NO_DEPÓSITO"]) if "status" in df.columns else 0
        total_liberados = len(df[df["status"].astype(str).str.upper() == "LIBERADO"]) if "status" in df.columns else 0
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

        c6, c7 = st.columns(2)
        with c6:
            card_metrica("Caminhões", total_caminhoes)
        with c7:
            saldo_operacional = total_deposito - total_liberados
            card_metrica("Saldo Operacional", saldo_operacional)

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

            with m1:
                st.markdown("**Quantidade de Entradas por Mês**")
                entradas_mes = (
                    df.dropna(subset=["mes_entrada"])
                      .groupby("mes_entrada")
                      .size()
                      .sort_index()
                )
                if not entradas_mes.empty:
                    st.line_chart(entradas_mes, use_container_width=True)
                    st.dataframe(
                        entradas_mes.reset_index().rename(columns={"mes_entrada": "Mês", 0: "Entradas"}),
                        use_container_width=True
                    )
                else:
                    st.info("Sem dados de entrada por mês.")

            with m2:
                st.markdown("**Quantidade de Saídas por Mês**")
                saidas_mes = (
                    df.dropna(subset=["mes_saida"])
                      .groupby("mes_saida")
                      .size()
                      .sort_index()
                )
                if not saidas_mes.empty:
                    st.line_chart(saidas_mes, use_container_width=True)
                    st.dataframe(
                        saidas_mes.reset_index().rename(columns={"mes_saida": "Mês", 0: "Saídas"}),
                        use_container_width=True
                    )
                else:
                    st.info("Sem dados de saída por mês.")

            st.markdown("**Comparativo de Entradas x Saídas por Mês**")
            entradas_df = entradas_mes.reset_index(name="Entradas") if not entradas_mes.empty else pd.DataFrame(columns=["mes_entrada", "Entradas"])
            saidas_df = saidas_mes.reset_index(name="Saídas") if not saidas_mes.empty else pd.DataFrame(columns=["mes_saida", "Saídas"])

            if not entradas_df.empty:
                entradas_df = entradas_df.rename(columns={"mes_entrada": "Mês"})
            if not saidas_df.empty:
                saidas_df = saidas_df.rename(columns={"mes_saida": "Mês"})

            comparativo = pd.merge(entradas_df, saidas_df, on="Mês", how="outer").fillna(0)

            if not comparativo.empty:
                comparativo = comparativo.sort_values("Mês")
                comparativo_chart = comparativo.set_index("Mês")[["Entradas", "Saídas"]]
                st.bar_chart(comparativo_chart, use_container_width=True)
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
# 👤 CADASTRO DE USUÁRIO - SOMENTE ADMIN
# =====================================================
elif menu == "👤 Cadastrar Usuário":
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
# 🔐 MINHA CONTA - SOMENTE ADMIN
# =====================================================
elif menu == "🔐 Minha Conta":
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
# 📤 SAÍDA DE VEÍCULO
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