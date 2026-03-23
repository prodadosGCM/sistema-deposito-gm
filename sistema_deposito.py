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