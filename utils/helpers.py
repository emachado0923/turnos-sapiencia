import streamlit as st
from datetime import datetime

def format_turno(modulo, numero_turno):
    """
    Formatea el turno para mostrar
    """
    return f"{modulo} {numero_turno}"

def get_taquillas_disponibles():
    """
    Retorna lista de taquillas disponibles
    """
    return [f"Taquilla {i}" for i in range(1, 6)]

def get_modulos_disponibles():
    """
    Retorna lista de módulos disponibles
    """
    return ["A", "L", "P", "C", "S"]

def setup_page_config(title, layout="centered"):
    """
    Configuración básica de la página
    """
    st.set_page_config(
        page_title=title,
        page_icon="🎫",
        layout=layout,
        initial_sidebar_state="collapsed" if "Pantalla" in title else "auto"
    )