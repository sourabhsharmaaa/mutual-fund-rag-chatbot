import streamlit as st 
import asyncio

# IMPORTANT WARNING:
# Streamlit Community Cloud ONLY hosts Streamlit UIs. It CANNOT host a FastAPI backend
# that your Vercel React frontend can communicate with. 
# If you want your Vercel frontend to work, deploy `backend/main.py` to Render, Railway, or Koyeb.
# This file is provided just in case you decide to use Streamlit for your frontend instead.

from backend.services.generator import get_generator

st.set_page_config(page_title="PPFAS RAG Support", page_icon="📈")

st.title("Ask INDy (Streamlit Fallback)")
st.caption("Warning: If you meant to deploy a backend for Vercel, Streamlit is the wrong platform. Use Render or Railway.")

if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

prompt = st.chat_input("Ask about Parag Parikh Mutual Funds...")
if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                gen = get_generator()
                result = gen.generate(prompt)
                st.markdown(result.answer)
                st.session_state.messages.append({"role": "assistant", "content": result.answer})
            except Exception as e:
                st.error(f"Error: {e}")
