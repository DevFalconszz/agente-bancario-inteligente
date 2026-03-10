"""
Aplicação Streamlit - Orquestrador de Agentes com Acúmulo de Respostas
"""

import streamlit as st
import sys
import os
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
load_dotenv()

from agentes import AgenteTriagem, AgenteCredito, AgenteEntrevista, AgenteCambio
from langchain_core.messages import HumanMessage, AIMessage

st.set_page_config(page_title="Banco Digital", page_icon="🏦", layout="centered")
st.markdown("<style>#MainMenu, footer, header {visibility: hidden;}</style>", unsafe_allow_html=True)

st.title("🏦 Banco Digital")
st.markdown("---")

def log_troca(de, para):
    print(f"\033[95m[LOG]\033[0m \033[93m{de}\033[0m -> \033[92m{para}\033[0m")

if "messages" not in st.session_state: st.session_state["messages"] = []
if "historico_langchain" not in st.session_state: st.session_state["historico_langchain"] = []
if "agente_atual" not in st.session_state:
    api_key = os.getenv("GROQ_API_KEY", "")
    if api_key:
        st.session_state["agente_instancia"] = AgenteTriagem(api_key=api_key)
        st.session_state["agente_atual"] = "triagem"
    else: st.stop()

for msg in st.session_state["messages"]:
    with st.chat_message(msg["role"]): st.markdown(msg["content"])

if st.session_state.get("atendimento_encerrado"):
    st.info("🔒 Atendimento encerrado."); st.stop()

if prompt := st.chat_input("Digite sua mensagem..."):
    st.session_state["messages"].append({"role": "user", "content": prompt})
    with st.chat_message("user"): st.markdown(prompt)
    
    # ENCERRAMENTO UNIVERSAL
    if any(p in prompt.lower() for p in ["encerrar", "finalizar", "sair", "tchau", "obrigado"]):
        st.session_state["atendimento_encerrado"] = True
        with st.chat_message("assistant"): st.markdown("Atendimento encerrado. O Banco Digital agradece!")
        st.session_state["messages"].append({"role": "assistant", "content": "Atendimento encerrado. O Banco Digital agradece!"})
        st.rerun()

    with st.chat_message("assistant"):
        with st.spinner("..."):
            try:
                respostas_geradas = []
                agente = st.session_state["agente_instancia"]
                
                # 1. Processamento Inicial
                res, hist = agente.processar_mensagem(prompt, st.session_state["historico_langchain"])
                if res: respostas_geradas.append(res)
                
                # 2. Loop de Troca de Agentes (Garante fluidez)
                while hasattr(agente, "proximo_agente") and agente.proximo_agente:
                    api_key = os.getenv("GROQ_API_KEY", "")
                    target = agente.proximo_agente
                    cliente = getattr(agente, "cliente", {})
                    
                    st.session_state["historico_langchain"] = [] # Reset contexto ao trocar
                    
                    de_agente = st.session_state["agente_atual"]
                    if target == "AgenteCredito":
                        veio = (st.session_state["agente_atual"] == "entrevista")
                        st.session_state["agente_instancia"] = AgenteCredito(api_key, cliente, veio)
                        st.session_state["agente_atual"] = "credito"
                    elif target == "AgenteEntrevista":
                        st.session_state["agente_instancia"] = AgenteEntrevista(api_key, cliente)
                        st.session_state["agente_atual"] = "entrevista"
                    elif target == "AgenteCambio":
                        st.session_state["agente_instancia"] = AgenteCambio(api_key, cliente)
                        st.session_state["agente_atual"] = "cambio"
                    elif target == "AgenteTriagem":
                        st.session_state["agente_instancia"] = AgenteTriagem(api_key)
                        st.session_state["agente_instancia"].cliente = cliente
                        st.session_state["agente_atual"] = "triagem"
                    
                    log_troca(de_agente, st.session_state["agente_atual"])
                    agente = st.session_state["agente_instancia"]
                    
                    # Reprocessa imediatamente para obter a resposta do novo agente
                    # Se for retorno para triagem ou crédito, envia vazio para ativar saudação/menu
                    res_next, hist = agente.processar_mensagem("", [])
                    if res_next: respostas_geradas.append(res_next)

                # Exibir todas as respostas acumuladas
                st.session_state["historico_langchain"] = hist
                if respostas_geradas:
                    full_res = "\n\n---\n\n".join(respostas_geradas)
                    st.markdown(full_res)
                    st.session_state["messages"].append({"role": "assistant", "content": full_res})
                
                if hasattr(agente, "etapa_atual") and agente.etapa_atual == "encerrado":
                    st.session_state["atendimento_encerrado"] = True; st.rerun()
                
            except Exception as e: 
                st.error(f"Erro no processamento: {str(e)}")

st.markdown("---")
