import streamlit as st
import base64

def autoplay_audio(file_path: str):
    """
    Reproduce un archivo de audio automáticamente
    """
    try:
        with open(file_path, "rb") as f:
            data = f.read()
            b64 = base64.b64encode(data).decode()
            md = f"""
                <audio autoplay>
                <source src="data:audio/mp3;base64,{b64}" type="audio/mp3">
                </audio>
                """
            st.markdown(md, unsafe_allow_html=True)
    except Exception as e:
        st.error(f"Error reproduciendo audio: {e}")

def play_notification_sound():
    """
    Reproduce sonido de notificación general
    """
    autoplay_audio("sounds/notification.mp3")

def play_call_turn_sound():
    """
    Reproduce sonido específico para llamado de turnos
    """
    autoplay_audio("sounds/call_turn.mp3")