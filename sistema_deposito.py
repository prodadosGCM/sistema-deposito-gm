import streamlit as st
import gspread
import pandas as pd
from zoneinfo import ZoneInfo
from google.oauth2.service_account import Credentials
from datetime import datetime
import hashlib
import time
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import simpleSplit


# =====================================================
# CONFIGURAÇÃO INICIAL DO STREAMLIT
# =====================================================
st.set_page_config(
    page_title="Controle de Veículos - Depósito GCM",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =====================================================
# CSS PERSONALIZADO DA INTERFACE
# =====================================================
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
    div[data-testid="stCaptionContainer"] p {
        font-size: 0.85rem;
        color: #475569;
    }
</style>
""", unsafe_allow_html=True)

st.markdown(
    '<div class="main-title">🚓 Depósito Público – Controle de Veículos | GCM</div>',
    unsafe_allow_html=True
)
st.markdown(
    '<div class="sub-title">Sistema de controle operacional, inventário, retirada de pertences, delegacia, relatórios e auditoria. Criado em 24/03/2026.</div>',
    unsafe_allow_html=True
)

# =====================================================
# CONSTANTES GERAIS DO SISTEMA
# =====================================================
TZ = ZoneInfo("America/Sao_Paulo")
STATUS_DEPOSITO = "DEPÓSITO"
STATUS_LIBERADO = "LIBERADO"


# =====================================================
# FUNÇÕES DE SEGURANÇA / LOGIN
# =====================================================
def make_hashes(password):
    return hashlib.sha256(str.encode(password)).hexdigest()


def check_hashes(password, hashed_text):
    return make_hashes(password) == hashed_text


# =====================================================
# CONTROLE DE SESSÃO
# =====================================================
def init_session():
    valores_padrao = {
        "logado": False,
        "usuario_id": None,
        "tipo_usuario": None,
        "primeiro_acesso": False,
        "nome_usuario": "",
        "login_usuario": "",
    }

    for chave, valor in valores_padrao.items():
        if chave not in st.session_state:
            st.session_state[chave] = valor


init_session()


# =====================================================
# FUNÇÃO DE LOGOUT
# =====================================================
def logout():
    st.session_state["logado"] = False
    st.session_state["usuario_id"] = None
    st.session_state["tipo_usuario"] = None
    st.session_state["primeiro_acesso"] = False
    st.session_state["nome_usuario"] = ""
    st.session_state["login_usuario"] = ""
    st.rerun()


# =====================================================
# CONEXÃO COM GOOGLE SHEETS
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


# =====================================================
# CONEXÃO / CRIAÇÃO DA ABA DE USUÁRIOS
# =====================================================
def conectar_aba_usuarios():
    try:
        aba = sheet.spreadsheet.worksheet("usuarios")
    except Exception:
        aba = sheet.spreadsheet.add_worksheet(title="usuarios", rows=2000, cols=10)
        aba.append_row([
            "id",
            "tipo_usuario",
            "login",
            "nome",
            "senha",
            "primeiro_acesso",
            "status"
        ])

    try:
        registros = aba.get_all_records()
        df = pd.DataFrame(registros)

        if df.empty or "login" not in df.columns:
            senha_hash = make_hashes("admin123")
            aba.append_row([
                1,
                "admin",
                "admin",
                "ADMINISTRADOR",
                senha_hash,
                1,
                "ATIVO"
            ])
        else:
            df.columns = df.columns.str.strip().str.lower()

            admin_existe = not df[
                (df["tipo_usuario"].astype(str).str.lower() == "admin") &
                (df["login"].astype(str).str.lower() == "admin") &
                (df["status"].astype(str).str.upper() == "ATIVO")
            ].empty

            if not admin_existe:
                ids = pd.to_numeric(df["id"], errors="coerce").dropna()
                novo_id = int(ids.max()) + 1 if not ids.empty else 1
                senha_hash = make_hashes("admin123")
                aba.append_row([
                    novo_id,
                    "admin",
                    "admin",
                    "ADMINISTRADOR",
                    senha_hash,
                    1,
                    "ATIVO"
                ])
    except Exception:
        pass

    return aba


# =====================================================
# CONEXÃO / CRIAÇÃO DA ABA DE RETIRADAS DE PERTENCES
# =====================================================
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


# =====================================================
# CONEXÃO / CRIAÇÃO DA ABA DE LOG DE AUDITORIA
# =====================================================
def conectar_aba_log():
    try:
        return sheet.spreadsheet.worksheet("log_auditoria")
    except Exception:
        nova_aba = sheet.spreadsheet.add_worksheet(title="log_auditoria", rows=5000, cols=5)
        nova_aba.append_row([
            "data",
            "hora",
            "usuario",
            "acao",
            "detalhes"
        ])
        return nova_aba


# =====================================================
# CONEXÃO / CRIAÇÃO DA ABA DE VEÍCULOS DA DELEGACIA
# =====================================================
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


usuarios_sheet = conectar_aba_usuarios()
retirada_sheet = conectar_aba_retiradas()
log_sheet = conectar_aba_log()
delegacia_sheet = conectar_aba_delegacia()


# =====================================================
# FUNÇÕES DE LEITURA DE DADOS COM CACHE
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


@st.cache_data(ttl=60)
def carregar_usuarios():
    dados = usuarios_sheet.get_all_records()
    df = pd.DataFrame(dados)
    if not df.empty:
        df.columns = df.columns.str.strip().str.lower()
        for col in ["id", "primeiro_acesso"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


# =====================================================
# LIMPEZA CONTROLADA DE CACHE
# =====================================================
def limpar_cache_modulos(
    usuarios=False,
    veiculos=False,
    retiradas=False,
    logs=False,
    delegacia=False
):
    if usuarios:
        carregar_usuarios.clear()
    if veiculos:
        carregar_dados.clear()
    if retiradas:
        carregar_retiradas.clear()
    if logs:
        carregar_logs.clear()
    if delegacia:
        carregar_dados_delegacia.clear()


# =====================================================
# GERAÇÃO DE IDs AUTOMÁTICOS
# =====================================================
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


def gerar_id_usuario(df):
    if df.empty or "id" not in df.columns:
        return 1
    ids = pd.to_numeric(df["id"], errors="coerce").dropna()
    if ids.empty:
        return 1
    return int(ids.max()) + 1


# =====================================================
# REGISTRO DE LOGS DO SISTEMA
# =====================================================
def registrar_log(usuario, acao, detalhes=""):
    agora = datetime.now(TZ)
    log_sheet.append_row([
        agora.strftime("%d/%m/%Y"),
        agora.strftime("%H:%M:%S"),
        str(usuario).upper(),
        str(acao).upper(),
        str(detalhes).upper()
    ])
    carregar_logs.clear()


def registrar_log_impressao(usuario, tipo_relatorio, referencia=""):
    registrar_log(
        usuario=usuario,
        acao="IMPRESSAO_RELATORIO",
        detalhes=f"{tipo_relatorio} | {referencia}"
    )


# =====================================================
# FUNÇÕES DE USUÁRIOS VIA PLANILHA
# =====================================================
def localizar_linha_usuario_por_id(id_usuario):
    df = carregar_usuarios()
    if df.empty:
        return None, None

    df = df.copy()
    df["id"] = pd.to_numeric(df["id"], errors="coerce")
    resultado = df[df["id"] == int(id_usuario)]

    if resultado.empty:
        return None, None

    idx = resultado.index[0]
    linha_planilha = idx + 2
    return linha_planilha, resultado.iloc[0]


def buscar_usuario_login(tipo_usuario, login):
    df = carregar_usuarios()

    if df.empty:
        return None

    filtros = (
        (df["tipo_usuario"].astype(str).str.strip().str.lower() == str(tipo_usuario).strip().lower()) &
        (df["login"].astype(str).str.strip().str.lower() == str(login).strip().lower()) &
        (df["status"].astype(str).str.strip().str.upper() == "ATIVO")
    )

    resultado = df[filtros]
    if resultado.empty:
        return None

    return resultado.iloc[0]


def login_usuario_planilha(tipo_usuario, login, senha):
    user = buscar_usuario_login(tipo_usuario, login)

    if user is not None and check_hashes(senha, str(user["senha"])):
        primeiro_acesso_val = user.get("primeiro_acesso", 0)
        primeiro_acesso_bool = False
        try:
            primeiro_acesso_bool = bool(int(primeiro_acesso_val))
        except Exception:
            primeiro_acesso_bool = False

        return {
            "sucesso": True,
            "id": int(user["id"]),
            "nome": str(user["nome"]),
            "login": str(user["login"]),
            "primeiro_acesso": primeiro_acesso_bool
        }

    return {
        "sucesso": False,
        "id": None,
        "nome": None,
        "login": None,
        "primeiro_acesso": None
    }


def cadastrar_usuario_planilha(tipo_usuario, login, nome, senha_inicial):
    df = carregar_usuarios()

    if not df.empty:
        existe = df[
            (df["tipo_usuario"].astype(str).str.lower() == str(tipo_usuario).strip().lower()) &
            (df["login"].astype(str).str.lower() == str(login).strip().lower()) &
            (df["status"].astype(str).str.upper() == "ATIVO")
        ]

        if not existe.empty:
            return False

    novo_id = gerar_id_usuario(df)
    senha_hash = make_hashes(senha_inicial)

    usuarios_sheet.append_row([
        novo_id,
        str(tipo_usuario).strip().lower(),
        str(login).strip(),
        str(nome).strip().upper(),
        senha_hash,
        1,
        "ATIVO"
    ])

    registrar_log(
        usuario=st.session_state.get("nome_usuario", "SISTEMA"),
        acao="CADASTRO_USUARIO",
        detalhes=f"TIPO {tipo_usuario} | LOGIN {login} | NOME {nome}"
    )

    limpar_cache_modulos(usuarios=True, logs=True)
    return True


def alterar_senha_usuario_planilha(id_usuario, nova_senha):
    linha, user = localizar_linha_usuario_por_id(id_usuario)
    if linha is None:
        return False

    nova_senha_hash = make_hashes(nova_senha)
    usuarios_sheet.update(f"E{linha}:F{linha}", [[nova_senha_hash, 0]])

    registrar_log(
        usuario=user.get("nome", "USUARIO"),
        acao="ALTERACAO_SENHA",
        detalhes=f"ID_USUARIO {id_usuario}"
    )

    limpar_cache_modulos(usuarios=True, logs=True)
    return True


def validar_senha_usuario_por_id(id_usuario, senha):
    _, user = localizar_linha_usuario_por_id(id_usuario)
    if user is None:
        return False

    return check_hashes(senha, str(user["senha"]))


def listar_usuarios_por_tipo(tipo_usuario):
    df = carregar_usuarios()

    if df.empty:
        return pd.DataFrame(columns=["id", "login", "nome", "primeiro_acesso"])

    df = df[
        (df["tipo_usuario"].astype(str).str.lower() == str(tipo_usuario).strip().lower()) &
        (df["status"].astype(str).str.upper() == "ATIVO")
    ].copy()

    if df.empty:
        return pd.DataFrame(columns=["id", "login", "nome", "primeiro_acesso"])

    return df[["id", "login", "nome", "primeiro_acesso"]].sort_values("nome")


def excluir_usuario_planilha(id_usuario):
    linha, user = localizar_linha_usuario_por_id(id_usuario)
    if linha is None:
        return False

    usuarios_sheet.update(f"G{linha}", [["INATIVO"]])

    registrar_log(
        usuario=st.session_state.get("nome_usuario", "SISTEMA"),
        acao="INATIVACAO_USUARIO",
        detalhes=f"ID {id_usuario} | LOGIN {user.get('login', '')} | NOME {user.get('nome', '')}"
    )

    limpar_cache_modulos(usuarios=True, logs=True)
    return True


def resetar_senha_usuario_planilha(id_usuario, nova_senha="1234"):
    linha, user = localizar_linha_usuario_por_id(id_usuario)
    if linha is None:
        return False

    senha_hash = make_hashes(nova_senha)
    usuarios_sheet.update(f"E{linha}:F{linha}", [[senha_hash, 1]])

    registrar_log(
        usuario=st.session_state.get("nome_usuario", "SISTEMA"),
        acao="RESET_SENHA_USUARIO",
        detalhes=f"ID {id_usuario} | LOGIN {user.get('login', '')}"
    )

    limpar_cache_modulos(usuarios=True, logs=True)
    return True


# =====================================================
# VALIDAÇÃO DE HORA DIGITADA MANUALMENTE
# =====================================================
def validar_hora_manual(hora_str):
    try:
        hora_str = str(hora_str).strip().replace(".", "").replace("-", "").replace(" ", "")

        if ":" not in hora_str:
            if len(hora_str) == 4:
                hora_str = f"{hora_str[:2]}:{hora_str[2:]}"
            elif len(hora_str) == 3:
                hora_str = f"0{hora_str[:1]}:{hora_str[1:]}"
            else:
                return False, None

        hora_obj = datetime.strptime(hora_str, "%H:%M")
        return True, hora_obj.strftime("%H:%M")
    except Exception:
        return False, None


# =====================================================
# VALIDAÇÃO DE DATA DIGITADA MANUALMENTE
# =====================================================
def validar_data_manual(data_str):
    try:
        data_str = str(data_str).strip().replace("-", "/").replace(".", "/").replace("\\", "/")

        if "/" not in data_str:
            somente_num = "".join(ch for ch in data_str if ch.isdigit())

            if len(somente_num) == 8:
                data_str = f"{somente_num[:2]}/{somente_num[2:4]}/{somente_num[4:]}"
            elif len(somente_num) == 6:
                dia = somente_num[:2]
                mes = somente_num[2:4]
                ano = f"20{somente_num[4:]}"
                data_str = f"{dia}/{mes}/{ano}"
            else:
                return False, None
        else:
            partes = data_str.split("/")
            if len(partes) != 3:
                return False, None

            dia, mes, ano = partes

            if len(dia) == 1:
                dia = f"0{dia}"
            if len(mes) == 1:
                mes = f"0{mes}"
            if len(ano) == 2:
                ano = f"20{ano}"

            data_str = f"{dia}/{mes}/{ano}"

        data_obj = datetime.strptime(data_str, "%d/%m/%Y")
        return True, data_obj
    except Exception:
        return False, None


# =====================================================
# FUNÇÕES DE NORMALIZAÇÃO DE TEXTO DE DATA/HORA
# =====================================================
def normalizar_hora_texto(hora_str):
    ok, hora_formatada = validar_hora_manual(hora_str)
    if ok:
        return hora_formatada
    return ""


def normalizar_data_texto(data_str):
    ok, data_formatada = validar_data_manual(data_str)
    if ok:
        return data_formatada.strftime("%d/%m/%Y")
    return ""


# =====================================================
# PADRONIZAÇÃO DE COLUNAS DO DATAFRAME
# =====================================================
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


# =====================================================
# CRIA COLUNA AUXILIAR DE MÊS PARA RELATÓRIOS E GRÁFICOS
# =====================================================
def montar_coluna_mes(df, coluna_data, nome_coluna_mes):
    if coluna_data in df.columns:
        df[nome_coluna_mes] = pd.to_datetime(df[coluna_data], format="%d/%m/%Y", errors="coerce")
        df[nome_coluna_mes] = df[nome_coluna_mes].dt.to_period("M").astype(str)
    else:
        df[nome_coluna_mes] = None
    return df


# =====================================================
# CARTÃO VISUAL DE MÉTRICA
# =====================================================
def card_metrica(titulo, valor):
    st.markdown(f"""
        <div class="metric-card">
            <h4>{titulo}</h4>
            <h2>{valor}</h2>
        </div>
    """, unsafe_allow_html=True)


# =====================================================
# MOSTRA AO USUÁRIO COMO O SISTEMA ENTENDEU DATA E HORA
# =====================================================
def mostrar_preview_data_hora(data_txt, hora_txt):
    data_preview = normalizar_data_texto(data_txt)
    hora_preview = normalizar_hora_texto(hora_txt)

    col_prev1, col_prev2 = st.columns(2)
    with col_prev1:
        st.caption(f"Data reconhecida: {data_preview if data_preview else 'inválida'}")
    with col_prev2:
        st.caption(f"Hora reconhecida: {hora_preview if hora_preview else 'inválida'}")


# =====================================================
# GERA NOME DE ARQUIVO SEGURO
# =====================================================
def obter_nome_arquivo_seguro(texto_base):
    texto_base = str(texto_base).strip().replace(" ", "_").replace("/", "-").replace("\\", "-")
    texto_base = texto_base.replace(":", "-").replace("*", "").replace("?", "").replace('"', "")
    return texto_base


# =====================================================
# MONTA RELATÓRIO TEXTUAL COMPLETO DE VEÍCULO
# =====================================================
def montar_relatorio_veiculo(df_veiculo, df_retiradas=None, origem="DEPÓSITO"):
    if df_veiculo.empty:
        return "Nenhum dado encontrado para este veículo."

    row = df_veiculo.iloc[0]

    linhas = []
    linhas.append("RELATÓRIO COMPLETO DO VEÍCULO")
    linhas.append("=" * 80)
    linhas.append(f"ORIGEM: {origem}")
    linhas.append(f"ID: {row.get('id', '')}")
    linhas.append(f"NÚMERO GRV: {row.get('numero_grv', '')}")
    linhas.append(f"PLACA: {row.get('placa', '')}")
    linhas.append(f"MARCA: {row.get('marca', '')}")
    linhas.append(f"MODELO: {row.get('modelo', '')}")
    linhas.append(f"COR: {row.get('cor', '')}")
    linhas.append(f"TIPO: {row.get('tipo', '')}")

    if origem == "DEPÓSITO":
        linhas.append(f"MOTIVO APREENSÃO: {row.get('motivo_apreensao', '')}")
    else:
        linhas.append(f"PROCEDÊNCIA: {row.get('procedencia', '')}")

    linhas.append(f"DATA ENTRADA: {row.get('data_entrada', '')}")
    linhas.append(f"HORA ENTRADA: {row.get('hora_entrada', '')}")
    linhas.append(f"AGENTE ENTRADA: {row.get('agente_entrada', '')}")
    linhas.append(f"STATUS: {row.get('status', '')}")
    linhas.append(f"DATA SAÍDA: {row.get('data_saida', '')}")
    linhas.append(f"HORA SAÍDA: {row.get('hora_saida', '')}")
    linhas.append(f"AGENTE SAÍDA: {row.get('agente_saida', '')}")
    linhas.append(f"OBSERVAÇÕES: {row.get('observacoes', '')}")
    linhas.append("")

    if df_retiradas is not None and not df_retiradas.empty:
        linhas.append("HISTÓRICO DE RETIRADA DE PERTENCES")
        linhas.append("-" * 80)
        for _, ret in df_retiradas.iterrows():
            linhas.append(f"DATA: {ret.get('data_retirada', '')} | HORA: {ret.get('hora_retirada', '')}")
            linhas.append(f"RETIRANTE: {ret.get('nome_retirante', '')}")
            linhas.append(f"DOCUMENTO: {ret.get('documento_retirante', '')}")
            linhas.append(f"ITENS: {ret.get('itens_retirados', '')}")
            linhas.append(f"OBSERVAÇÃO: {ret.get('observacao_retirada', '')}")
            linhas.append(f"AGENTE RESPONSÁVEL: {ret.get('agente_responsavel', '')}")
            linhas.append("-" * 80)
    else:
        linhas.append("SEM REGISTROS DE RETIRADA DE PERTENCES.")

    return "\n".join(linhas)


# =====================================================
# MONTA RELATÓRIO TEXTUAL DOS LOGS DO SISTEMA
# =====================================================
def montar_relatorio_logs(df_logs):
    linhas = []
    linhas.append("RELATÓRIO COMPLETO DE LOGS DO SISTEMA")
    linhas.append("=" * 100)

    if df_logs.empty:
        linhas.append("Nenhum log encontrado.")
        return "\n".join(linhas)

    for _, row in df_logs.iterrows():
        linhas.append(
            f"DATA: {row.get('data', '')} | HORA: {row.get('hora', '')} | "
            f"USUÁRIO: {row.get('usuario', '')} | AÇÃO: {row.get('acao', '')}"
        )
        linhas.append(f"DETALHES: {row.get('detalhes', '')}")
        linhas.append("-" * 100)

    return "\n".join(linhas)


# =====================================================
# GERA PDF A PARTIR DE TEXTO
# =====================================================
def gerar_pdf_texto(titulo, conteudo, usuario_emissor):
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    largura, altura = A4

    y = altura - 40
    margem_esq = 40
    largura_texto = largura - 80

    def nova_pagina():
        nonlocal y
        pdf.showPage()
        y = altura - 40
        pdf.setFont("Helvetica", 10)

    pdf.setTitle(titulo)

    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(margem_esq, y, "GUARDA CIVIL MUNICIPAL")
    y -= 20
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(margem_esq, y, titulo)
    y -= 20

    pdf.setFont("Helvetica", 9)
    pdf.drawString(
        margem_esq,
        y,
        f"Emitido em: {datetime.now(TZ).strftime('%d/%m/%Y %H:%M:%S')} | Usuário: {usuario_emissor}"
    )
    y -= 25

    pdf.setFont("Helvetica", 10)

    for paragrafo in conteudo.split("\n"):
        linhas = simpleSplit(paragrafo, "Helvetica", 10, largura_texto)
        if not linhas:
            y -= 14
            if y < 50:
                nova_pagina()
            continue

        for linha in linhas:
            if y < 50:
                nova_pagina()
            pdf.drawString(margem_esq, y, linha)
            y -= 14

    pdf.save()
    buffer.seek(0)
    return buffer.getvalue()


# =====================================================
# REGISTRA RETIRADA DE PERTENCES
# =====================================================
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

    limpar_cache_modulos(retiradas=True, logs=True)


# =====================================================
# REGISTRA ENTRADA DE VEÍCULO NA DELEGACIA
# =====================================================
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

    limpar_cache_modulos(delegacia=True, logs=True)


# =====================================================
# REGISTRA SAÍDA DE VEÍCULO DA DELEGACIA
# =====================================================
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

    limpar_cache_modulos(delegacia=True, logs=True)


# =====================================================
# REGISTRA ENTRADA DE VEÍCULO NO PÁTIO
# =====================================================
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

    limpar_cache_modulos(veiculos=True, logs=True)


# =====================================================
# REGISTRA SAÍDA DE VEÍCULO DO PÁTIO
# =====================================================
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

    limpar_cache_modulos(veiculos=True, logs=True)


# =====================================================
# TELA DE LOGIN
# =====================================================
if not st.session_state["logado"]:
    col1, col2, col3 = st.columns([1, 1.4, 1])

    with col2:
        st.subheader("🔐 Acesso ao Sistema")

        with st.form("form_login"):
            tipo = st.radio("Entrar como:", ["Agente", "Gestor", "Administrador"], horizontal=True)

            if tipo == "Administrador":
                usuario_input = st.text_input("Usuário do Admin")
            elif tipo == "Gestor":
                usuario_input = st.text_input("Usuário do Gestor")
            else:
                usuario_input = st.text_input("Matrícula do Agente")

            senha_input = st.text_input("Senha", type="password")

            entrar = st.form_submit_button("Entrar", use_container_width=True)

        if entrar:
            tipo_mapa = {
                "Administrador": "admin",
                "Gestor": "gestor",
                "Agente": "agente"
            }

            tipo_login = tipo_mapa[tipo]
            resultado = login_usuario_planilha(tipo_login, usuario_input.strip(), senha_input)

            if resultado["sucesso"]:
                st.session_state["logado"] = True
                st.session_state["tipo_usuario"] = tipo_login
                st.session_state["usuario_id"] = resultado["id"]
                st.session_state["nome_usuario"] = resultado["nome"]
                st.session_state["login_usuario"] = resultado["login"]
                st.session_state["primeiro_acesso"] = resultado["primeiro_acesso"]
                st.rerun()
            else:
                st.error("Usuário ou senha inválidos.")

    st.stop()


# =====================================================
# TROCA DE SENHA NO PRIMEIRO ACESSO
# =====================================================
if st.session_state["primeiro_acesso"]:
    st.warning("⚠️ Por segurança, altere sua senha inicial.")
    with st.form("form_troca_senha", clear_on_submit=True):
        nova_s1 = st.text_input("Nova Senha", type="password")
        nova_s2 = st.text_input("Confirme a Nova Senha", type="password")

        if st.form_submit_button("Atualizar Senha"):
            if nova_s1 == nova_s2 and len(nova_s1) > 3:
                ok = alterar_senha_usuario_planilha(
                    st.session_state["usuario_id"],
                    nova_s1
                )
                if ok:
                    st.session_state["primeiro_acesso"] = False
                    st.success("Senha atualizada com sucesso.")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("Não foi possível atualizar a senha.")
            else:
                st.error("As senhas não coincidem ou são muito curtas.")
    st.stop()


# =====================================================
# SIDEBAR DO USUÁRIO LOGADO
# =====================================================
st.sidebar.success(f"Logado como: {st.session_state['nome_usuario']}")
st.sidebar.write(f"Perfil: {str(st.session_state['tipo_usuario']).upper()}")

if st.sidebar.button("Sair / Logout"):
    logout()


# =====================================================
# MENU PRINCIPAL
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
            "🖨️ Relatórios",
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
            "🖨️ Relatórios",
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
# DASHBOARD
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
        st.markdown(f"""
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
# CADASTRO DE USUÁRIO
# =====================================================
elif menu == "👤 Cadastrar Usuário":
    st.subheader("Cadastro de Usuário")

    tipo_novo_usuario = st.selectbox("Tipo de Usuário", ["Agente", "Gestor"])

    with st.form("form_cadastro_usuario", clear_on_submit=True):
        if tipo_novo_usuario == "Agente":
            identificador = st.text_input("Matrícula")
        else:
            identificador = st.text_input("Usuário do Gestor")

        nome = st.text_input("Nome de guerra")
        senha_inicial = st.text_input("Senha Inicial", value="1234", type="password")

        if st.form_submit_button("Cadastrar Usuário"):
            if not identificador or not nome or not senha_inicial:
                st.warning("Preencha todos os campos.")
            else:
                tipo_bd = "agente" if tipo_novo_usuario == "Agente" else "gestor"

                ok = cadastrar_usuario_planilha(
                    tipo_usuario=tipo_bd,
                    login=identificador.strip(),
                    nome=nome.strip(),
                    senha_inicial=senha_inicial.strip()
                )

                if ok:
                    st.success(f"{tipo_novo_usuario} cadastrado com sucesso. No primeiro acesso deverá trocar a senha.")
                else:
                    st.error("Usuário/Matrícula já cadastrado.")


# =====================================================
# GERENCIAR USUÁRIOS
# =====================================================
elif menu == "📋 Gerenciar Usuários":
    st.subheader("Gerenciamento de Usuários")

    aba1, aba2 = st.tabs(["Agentes", "Gestores"])

    with aba1:
        df_agentes = listar_usuarios_por_tipo("agente")
        if not df_agentes.empty:
            df_agentes = df_agentes.rename(columns={"login": "matricula"})

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
                    resetar_senha_usuario_planilha(id_agente_sel, "1234")
                    st.success("Senha resetada com sucesso.")
                    time.sleep(1)
                    st.rerun()

            with col2:
                if st.button("Excluir Agente", type="primary", key="exc_agente"):
                    excluir_usuario_planilha(id_agente_sel)
                    st.success("Agente excluído com sucesso.")
                    time.sleep(1)
                    st.rerun()

    with aba2:
        df_gestores = listar_usuarios_por_tipo("gestor")
        if not df_gestores.empty:
            df_gestores = df_gestores.rename(columns={"login": "usuario"})

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
                    resetar_senha_usuario_planilha(id_gestor_sel, "1234")
                    st.success("Senha resetada com sucesso.")
                    time.sleep(1)
                    st.rerun()

            with col2:
                if st.button("Excluir Gestor", type="primary", key="exc_gestor"):
                    excluir_usuario_planilha(id_gestor_sel)
                    st.success("Gestor excluído com sucesso.")
                    time.sleep(1)
                    st.rerun()


# =====================================================
# MINHA CONTA
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
                if not validar_senha_usuario_por_id(st.session_state['usuario_id'], senha_atual):
                    st.error("Senha atual incorreta.")
                elif nova_senha != confirmar_nova:
                    st.error("A nova senha e a confirmação não coincidem.")
                elif len(nova_senha) < 4:
                    st.error("A nova senha deve ter pelo menos 4 caracteres.")
                else:
                    alterar_senha_usuario_planilha(st.session_state['usuario_id'], nova_senha)
                    st.success("Senha alterada com sucesso.")

    elif st.session_state['tipo_usuario'] == 'gestor':
        st.info("Área para alteração da senha do gestor.")

        with st.form("form_troca_senha_gestor_manual", clear_on_submit=True):
            senha_atual = st.text_input("Senha Atual", type="password")
            nova_senha = st.text_input("Nova Senha", type="password")
            confirmar_nova = st.text_input("Confirmar Nova Senha", type="password")

            if st.form_submit_button("Alterar Senha"):
                if not validar_senha_usuario_por_id(st.session_state['usuario_id'], senha_atual):
                    st.error("Senha atual incorreta.")
                elif nova_senha != confirmar_nova:
                    st.error("A nova senha e a confirmação não coincidem.")
                elif len(nova_senha) < 4:
                    st.error("A nova senha deve ter pelo menos 4 caracteres.")
                else:
                    alterar_senha_usuario_planilha(st.session_state['usuario_id'], nova_senha)
                    st.success("Senha alterada com sucesso.")


# =====================================================
# ENTRADA DE VEÍCULO
# =====================================================
elif menu == "🚗 Entrada de Veículo":
    st.subheader("Registro de Entrada de Veículo")

    with st.form("entrada", clear_on_submit=True):
        numero_grv = st.text_input("Número da GRV")
        placa = st.text_input("Placa/Chassi/Nr do motor")
        marca = st.text_input("Marca")
        modelo = st.text_input("Modelo")
        cor = st.text_input("Cor")
        tipo = st.selectbox("Tipo", ["AUTOMÓVEL", "MOTOCICLETA", "CAMINHÃO", "OUTRO"])
        motivo = st.text_area("Motivo da Apreensão/Observações adicionais")

        data_entrada = st.text_input(
            "Data da Entrada",
            value="",
            placeholder="Ex: 23/03/2026 ou 23032026",
            help="Aceita: 23/03/2026, 23-03-2026, 23032026, 230326"
        )
        hora_entrada = st.text_input(
            "Hora da Entrada",
            value="",
            placeholder="Ex: 14:00 ou 1400",
            help="Aceita: 14:00, 1400, 930"
        )


        agente = st.text_input("Agente Responsável", value=st.session_state['nome_usuario'])

        if st.form_submit_button("Registrar Entrada"):
            data_ok, data_formatada = validar_data_manual(data_entrada)
            hora_ok, hora_formatada = validar_hora_manual(hora_entrada)

            if not numero_grv or not placa or not marca or not modelo or not cor or not motivo or not agente:
                st.warning("Preencha todos os campos obrigatórios.")
            elif not data_ok:
                st.error("Data inválida. Use DD/MM/AAAA ou 23032026.")
            elif not hora_ok:
                st.error("Hora inválida. Use HH:MM ou 1400.")
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
# SAÍDA DE VEÍCULO
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
            with st.form("form_saida_veiculo", clear_on_submit=True):
                veiculo = st.selectbox(
                    "Selecione o veículo",
                    df_ativos["id"].astype(str) + " - GRV " + df_ativos["numero_grv"].astype(str) + " - " + df_ativos["placa"].astype(str)
                )

                data_saida = st.text_input(
                    "Data da Saída",
                    value="",
                    key="data_saida_patio",
                    placeholder="Ex: 23/03/2026 ou 23032026",
                    help="Aceita: 23/03/2026, 23-03-2026, 23032026, 230326"
                )
                hora_saida = st.text_input(
                    "Hora da Saída",
                    value="",
                    key="hora_saida_patio",
                    placeholder="Ex: 14:00 ou 1400",
                    help="Aceita: 14:00, 1400, 930"
                )


                agente_saida = st.text_input(
                    "Agente Responsável pela Liberação",
                    value=st.session_state['nome_usuario']
                )
                obs = st.text_area("Observações adicionais, se necessário")

                if st.form_submit_button("Registrar Saída"):
                    data_ok, data_formatada = validar_data_manual(data_saida)
                    hora_ok, hora_formatada = validar_hora_manual(hora_saida)

                    if not agente_saida:
                        st.warning("Informe o agente responsável pela liberação.")
                    elif not data_ok:
                        st.error("Data inválida. Use DD/MM/AAAA ou 23032026.")
                    elif not hora_ok:
                        st.error("Hora inválida. Use HH:MM ou 1400.")
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
# RETIRADA DE PERTENCES
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
            with st.form("form_retirada_pertences", clear_on_submit=True):
                veiculo = st.selectbox(
                    "Selecione o veículo",
                    df_ativos["id"].astype(str) + " - GRV " +
                    df_ativos["numero_grv"].astype(str) + " - " +
                    df_ativos["placa"].astype(str) + " - " +
                    df_ativos["marca"].astype(str) + " - " +
                    df_ativos["modelo"].astype(str)
                )

                data_retirada = st.text_input(
                    "Data da Retirada",
                    value="",
                    placeholder=""
                )

                hora_retirada = st.text_input(
                    "Hora da Retirada",
                    value="",
                    placeholder=""
                )


                nome_retirante = st.text_input("Nome Completo da Pessoa que Retirou o Pertence")
                documento_retirante = st.text_input("Documento da Pessoa que Retirou")
                itens_retirados = st.text_area("Itens Retirados do Veículo")
                observacao_retirada = st.text_area("Observação da Retirada")
                agente_responsavel = st.text_input(
                    "Agente Responsável",
                    value=st.session_state['nome_usuario']
                )

                submit_retirada = st.form_submit_button("Registrar Retirada de Pertences")

                if submit_retirada:
                    data_ok, data_formatada = validar_data_manual(data_retirada)
                    hora_ok, hora_formatada = validar_hora_manual(hora_retirada)

                    if not nome_retirante or not documento_retirante or not itens_retirados or not agente_responsavel:
                        st.warning("Preencha todos os campos obrigatórios.")
                    elif not data_ok:
                        st.error("Data inválida. Use DD/MM/AAAA ou 23032026.")
                    elif not hora_ok:
                        st.error("Hora inválida. Use HH:MM ou 1400.")
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

                        st.success("✅ Retirada de pertences registrada com sucesso!")


# =====================================================
# DELEGACIA - ENTRADA DE VEÍCULO
# =====================================================
elif menu == "🚔 Delegacia" and submenu_delegacia == "Entrada de Veículo":
    st.subheader("Registro de Entrada de Veículo - Delegacia")

    with st.form("entrada_delegacia", clear_on_submit=True):
        numero_grv = st.text_input("Número da GRV")
        placa = st.text_input("Placa/Chassi/Nr do motor")
        marca = st.text_input("Marca")
        modelo = st.text_input("Modelo")
        cor = st.text_input("Cor")
        tipo = st.selectbox("Tipo", ["AUTOMÓVEL", "MOTOCICLETA", "CAMINHÃO", "OUTRO"], key="tipo_delegacia")
        procedencia = st.text_input("Procedência / Delegacia de Origem / Observações")

        data_entrada = st.text_input(
            "Data da Entrada",
            value="",
            key="data_entrada_del",
            placeholder="Ex: 23/03/2026 ou 23032026",
            help="Aceita: 23/03/2026, 23-03-2026, 23032026, 230326"
        )
        hora_entrada = st.text_input(
            "Hora da Entrada",
            value="",
            key="hora_entrada_del",
            placeholder="Ex: 14:00 ou 1400",
            help="Aceita: 14:00, 1400, 930"
        )


        agente = st.text_input("Agente Responsável", value=st.session_state['nome_usuario'])

        if st.form_submit_button("Registrar Entrada - Delegacia"):
            data_ok, data_formatada = validar_data_manual(data_entrada)
            hora_ok, hora_formatada = validar_hora_manual(hora_entrada)

            if not numero_grv or not placa or not marca or not modelo or not cor or not procedencia or not agente:
                st.warning("Preencha todos os campos obrigatórios.")
            elif not data_ok:
                st.error("Data inválida. Use DD/MM/AAAA ou 23032026.")
            elif not hora_ok:
                st.error("Hora inválida. Use HH:MM ou 1400.")
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
                st.success("✅ Veículo da delegacia registrado com sucesso!")


# =====================================================
# DELEGACIA - SAÍDA DE VEÍCULO
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
            with st.form("form_saida_delegacia", clear_on_submit=True):
                veiculo = st.selectbox(
                    "Selecione o veículo da delegacia",
                    df_ativos["id"].astype(str) + " - GRV " + df_ativos["numero_grv"].astype(str) + " - " + df_ativos["placa"].astype(str) + " - " + df_ativos["procedencia"].astype(str)
                )

                data_saida = st.text_input(
                    "Data da Saída",
                    value="",
                    key="data_saida_del",
                    placeholder="Ex: 23/03/2026 ou 23032026",
                    help="Aceita: 23/03/2026, 23-03-2026, 23032026, 230326"
                )
                hora_saida = st.text_input(
                    "Hora da Saída",
                    value="",
                    key="hora_saida_del",
                    placeholder="Ex: 14:00 ou 1400",
                    help="Aceita: 14:00, 1400, 930"
                )


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
                        st.error("Data inválida. Use DD/MM/AAAA ou 23032026.")
                    elif not hora_ok:
                        st.error("Hora inválida. Use HH:MM ou 1400.")
                    else:
                        id_veiculo = int(veiculo.split(" - ")[0])

                        registrar_saida_delegacia(
                            id_veiculo=id_veiculo,
                            data_saida=data_formatada,
                            hora_saida=hora_formatada,
                            agente_saida=agente_saida.strip(),
                            observacoes=obs.strip()
                        )

                        st.success("✅ Saída de veículo da delegacia registrada com sucesso!")


# =====================================================
# DELEGACIA - CONSULTA DE VEÍCULOS
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
# RELATÓRIOS
# =====================================================
elif menu == "🖨️ Relatórios":
    st.subheader("Relatórios de Veículos")

    tab1, tab2 = st.tabs(["Relatório de Veículo", "Relatório Geral de Logs"])

    with tab1:
        tipo_origem = st.radio("Origem do Veículo", ["DEPÓSITO", "DELEGACIA"], horizontal=True)

        if tipo_origem == "DEPÓSITO":
            df_base = carregar_dados()
        else:
            df_base = carregar_dados_delegacia()

        df_base = preparar_dataframe(df_base)
        df_ret = carregar_retiradas()

        if df_base.empty:
            st.info("Nenhum veículo encontrado para gerar relatório.")
        else:
            filtro_tipo = st.radio("Localizar por", ["Placa", "GRV", "ID"], horizontal=True)

            valor_busca = ""
            df_filtrado = pd.DataFrame()

            if filtro_tipo == "Placa":
                valor_busca = st.text_input("Informe a placa")
                if valor_busca:
                    df_filtrado = df_base[df_base["placa"].astype(str).str.upper() == valor_busca.strip().upper()]

            elif filtro_tipo == "GRV":
                valor_busca = st.text_input("Informe o número da GRV")
                if valor_busca:
                    df_filtrado = df_base[df_base["numero_grv"].astype(str).str.upper() == valor_busca.strip().upper()]

            else:
                valor_busca = st.text_input("Informe o ID")
                if valor_busca:
                    df_filtrado = df_base[df_base["id"].astype(str) == valor_busca.strip()]

            if not df_filtrado.empty:
                veiculo_sel = df_filtrado.iloc[0]
                id_veiculo = veiculo_sel.get("id", "")
                placa_veiculo = veiculo_sel.get("placa", "")
                grv_veiculo = veiculo_sel.get("numero_grv", "")

                if not df_ret.empty and "id_veiculo" in df_ret.columns:
                    df_ret_filtrado = df_ret[df_ret["id_veiculo"].astype(str) == str(id_veiculo)]
                else:
                    df_ret_filtrado = pd.DataFrame()

                relatorio_txt = montar_relatorio_veiculo(
                    df_veiculo=df_filtrado,
                    df_retiradas=df_ret_filtrado,
                    origem=tipo_origem
                )

                st.text_area("Pré-visualização do Relatório", relatorio_txt, height=500)

                pdf_bytes = gerar_pdf_texto(
                    titulo=f"RELATÓRIO DO VEÍCULO - {tipo_origem}",
                    conteudo=relatorio_txt,
                    usuario_emissor=st.session_state['nome_usuario']
                )

                nome_arquivo = f"relatorio_{tipo_origem.lower()}_{obter_nome_arquivo_seguro(placa_veiculo or grv_veiculo or id_veiculo)}.pdf"

                if st.download_button(
                    label="📥 Baixar Relatório do Veículo em PDF",
                    data=pdf_bytes,
                    file_name=nome_arquivo,
                    mime="application/pdf"
                ):
                    registrar_log_impressao(
                        usuario=st.session_state['nome_usuario'],
                        tipo_relatorio=f"RELATORIO_VEICULO_{tipo_origem}",
                        referencia=f"ID {id_veiculo} | GRV {grv_veiculo} | PLACA {placa_veiculo}"
                    )
            elif valor_busca:
                st.warning("Nenhum veículo encontrado com esse critério.")

    with tab2:
        if st.session_state['tipo_usuario'] not in ['admin', 'gestor']:
            st.warning("Apenas admin e gestor podem acessar o relatório geral de logs.")
        else:
            df_logs = carregar_logs()

            c1, c2, c3 = st.columns(3)
            filtro_usuario = c1.text_input("Filtrar por usuário", key="rel_filtro_usuario")
            filtro_acao = c2.text_input("Filtrar por ação", key="rel_filtro_acao")
            filtro_data = c3.text_input("Filtrar por data (dd/mm/aaaa)", key="rel_filtro_data")

            if not df_logs.empty:
                if filtro_usuario and "usuario" in df_logs.columns:
                    df_logs = df_logs[df_logs["usuario"].astype(str).str.contains(filtro_usuario, case=False, na=False)]

                if filtro_acao and "acao" in df_logs.columns:
                    df_logs = df_logs[df_logs["acao"].astype(str).str.contains(filtro_acao, case=False, na=False)]

                if filtro_data and "data" in df_logs.columns:
                    df_logs = df_logs[df_logs["data"].astype(str) == filtro_data]

            relatorio_logs_txt = montar_relatorio_logs(df_logs)
            st.text_area("Pré-visualização do Relatório de Logs", relatorio_logs_txt, height=500)

            pdf_logs = gerar_pdf_texto(
                titulo="RELATÓRIO COMPLETO DE LOGS DO SISTEMA",
                conteudo=relatorio_logs_txt,
                usuario_emissor=st.session_state['nome_usuario']
            )

            nome_arquivo_logs = f"relatorio_logs_{datetime.now(TZ).strftime('%Y%m%d_%H%M%S')}.pdf"

            if st.download_button(
                label="📥 Baixar Relatório Completo de Logs em PDF",
                data=pdf_logs,
                file_name=nome_arquivo_logs,
                mime="application/pdf"
            ):
                registrar_log_impressao(
                    usuario=st.session_state['nome_usuario'],
                    tipo_relatorio="RELATORIO_GERAL_LOGS",
                    referencia="LOG COMPLETO DO SISTEMA"
                )


# =====================================================
# CONSULTA / INVENTÁRIO
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
# LOG DE AUDITORIA
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