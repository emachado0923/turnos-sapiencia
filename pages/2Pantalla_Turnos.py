import streamlit as st
import pandas as pd
import time
from config.database import get_db_engine
from utils.helpers import setup_page_config
from sqlalchemy import text

# Configuración especial para pantalla TV
st.set_page_config(
    page_title="Pantalla de Turnos - TV",
    layout="wide",
    initial_sidebar_state="collapsed"
)

def obtener_turnos_llamando():
    """Obtiene los últimos 10 turnos llamados (incluye atendidos recientemente)"""
    engine = get_db_engine()
    if engine:
        try:
            with engine.connect() as conn:
                query = text("""
                SELECT modulo, numero_turno, taquilla_asignada, fecha_llamado, estado, nombre_usuario
                FROM turnos 
                WHERE estado IN ('llamando', 'atendido')
                AND fecha_llamado IS NOT NULL
                ORDER BY fecha_llamado DESC 
                LIMIT 10
                """)
                result = conn.execute(query)
                turnos = result.fetchall()
                
                # Convertir a DataFrame para manejo más fácil
                if turnos:
                    df = pd.DataFrame(turnos, columns=['modulo', 'numero_turno', 'taquilla_asignada', 'fecha_llamado', 'estado', 'nombre_usuario'])
                    return df
                else:
                    return pd.DataFrame()
                    
        except Exception as e:
            print(f"Error al obtener turnos llamando: {e}")
            return pd.DataFrame()
    return pd.DataFrame()

def obtener_turno_actual():
    """Obtiene el turno más reciente que fue llamado (aunque ya esté atendido)"""
    engine = get_db_engine()
    if engine:
        try:
            with engine.connect() as conn:
                query = text("""
                SELECT modulo, numero_turno, taquilla_asignada, fecha_llamado, estado, nombre_usuario
                FROM turnos 
                WHERE fecha_llamado IS NOT NULL
                ORDER BY fecha_llamado DESC 
                LIMIT 1
                """)
                result = conn.execute(query)
                turno = result.fetchone()
                
                if turno:
                    return {
                        'modulo': turno[0],
                        'numero_turno': turno[1],
                        'taquilla_asignada': turno[2],
                        'fecha_llamado': turno[3],
                        'estado': turno[4],
                        'nombre_usuario': turno[5]
                    }
                else:
                    return None
                    
        except Exception as e:
            print(f"Error al obtener turno actual: {e}")
            return None
    return None

def obtener_historial_turnos():
    """Obtiene el historial de turnos (excluyendo el actual) - máximo 4"""
    engine = get_db_engine()
    if engine:
        try:
            with engine.connect() as conn:
                query = text("""
                SELECT modulo, numero_turno, taquilla_asignada, fecha_llamado, estado, nombre_usuario
                FROM turnos 
                WHERE fecha_llamado IS NOT NULL
                AND estado IN ('llamando', 'atendido')
                ORDER BY fecha_llamado DESC 
                LIMIT 1, 4  -- Salta el más reciente (actual) y toma los siguientes 4
                """)
                result = conn.execute(query)
                turnos = result.fetchall()
                
                # Convertir a DataFrame
                if turnos:
                    df = pd.DataFrame(turnos, columns=['modulo', 'numero_turno', 'taquilla_asignada', 'fecha_llamado', 'estado', 'nombre_usuario'])
                    return df
                else:
                    return pd.DataFrame()
                    
        except Exception as e:
            print(f"Error al obtener historial: {e}")
            return pd.DataFrame()
    return pd.DataFrame()

# CSS personalizado mejorado - estilo más formal
st.markdown("""
<style>
    /* Ocultar elementos de Streamlit */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    .main-header {
        font-size: 4rem;
        text-align: center;
        color: #1E3A8A;
        margin-bottom: 1rem;
        font-weight: bold;
        text-transform: uppercase;
        text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
    }
    
    .section-title {
        font-size: 2.5rem;
        text-align: center;
        color: #1E3A8A;
        margin-bottom: 2rem;
        font-weight: bold;
    }
    
    .current-turno {
        font-size: 7rem;
        text-align: center;
        background: linear-gradient(135deg, #FF6B6B, #FFE66D);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        font-weight: bold;
        margin: 1rem 0;
        animation: pulse 2s infinite;
    }
    
    .taquilla-info {
        font-size: 3rem;
        text-align: center;
        color: #1E3A8A;
        font-weight: bold;
        margin: 1rem 0;
        background: rgba(255, 230, 109, 0.2);
        padding: 1rem;
        border-radius: 15px;
        border: 3px solid #FFE66D;
    }
    
    /* HORA FORMAL - estilo similar al turno actual */
    .hora-llamada {
        font-size: 2.2rem;
        text-align: center;
        color: #1E3A8A;
        font-weight: bold;
        margin: 2rem 0;
        background: rgba(30, 58, 138, 0.1);
        padding: 1.2rem;
        border-radius: 15px;
        border: 3px solid #1E3A8A;
    }
    
    .hora-label {
        font-size: 1.5rem;
        color: #1E3A8A;
        font-weight: normal;
        margin-bottom: 0.5rem;
        opacity: 0.9;
    }
    
    .hora-valor {
        font-size: 2.5rem;
        color: #1E3A8A;
        font-weight: bold;
    }
    
    .historial-item {
        background: rgba(30, 58, 138, 0.1);
        padding: 1.5rem;
        border-radius: 10px;
        border-left: 5px solid #1E3A8A;
        margin: 0.5rem 0;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    
    .turno-con-nombre-historial {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1E3A8A;
    }
    
    .taquilla-number {
        font-size: 1.8rem;
        color: #1E3A8A;
        background: rgba(255, 230, 109, 0.3);
        padding: 0.5rem 1rem;
        border-radius: 8px;
        margin-top: 0.5rem;
    }
    
    .time-stamp {
        font-size: 1.4rem;
        color: #1E3A8A;
        font-weight: bold;
        text-align: right;
        background: rgba(30, 58, 138, 0.1);
        padding: 0.5rem 1rem;
        border-radius: 8px;
        border: 2px solid #1E3A8A;
    }
    
    .empty-state {
        font-size: 2rem;
        text-align: center;
        color: #666;
        font-style: italic;
        margin: 2rem 0;
    }
    
    @keyframes pulse {
        0% { transform: scale(1); }
        50% { transform: scale(1.05); }
        100% { transform: scale(1); }
    }
    
    /* Fondo general */
    .stApp {
        background: linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%);
    }
</style>
""", unsafe_allow_html=True)

def format_hora(fecha_llamado):
    """Formatea la hora del llamado"""
    if pd.isna(fecha_llamado) or fecha_llamado is None:
        return "--:--:--"
    try:
        return pd.to_datetime(fecha_llamado).strftime('%H:%M:%S')
    except:
        return "--:--:--"

# Contenedor principal
main_placeholder = st.empty()

# Bucle de actualización automática
while True:
    with main_placeholder.container():
        # Encabezado principal
        st.markdown('<div class="main-header">TURNOS MEJORES BACHILLERES</div>', unsafe_allow_html=True)
        
        # Obtener datos
        turno_actual = obtener_turno_actual()
        historial_df = obtener_historial_turnos()
        
        # Crear layout dividido con columnas de Streamlit
        col_left, col_right = st.columns([1, 1], gap="large")
        
        with col_left:
            # SECCIÓN IZQUIERDA - TURNO ACTUAL
            st.markdown('<div class="section-title">TURNO ACTUAL</div>', unsafe_allow_html=True)
            
            if turno_actual:
                # MOSTRAR TURNO CON NOMBRE DIRECTAMENTE EN LA PARTE AMARILLA PRINCIPAL
                nombre_usuario = turno_actual.get("nombre_usuario", "")
                if nombre_usuario:
                    # El turno principal en amarillo muestra "A002 - SUSANA LOPEZ"
                    turno_con_nombre = f"{turno_actual['modulo']}{turno_actual['numero_turno']} - {nombre_usuario}"
                    st.markdown(f'<div class="current-turno">{turno_con_nombre}</div>', unsafe_allow_html=True)
                else:
                    st.markdown(f'<div class="current-turno">{turno_actual["modulo"]}{turno_actual["numero_turno"]}</div>', unsafe_allow_html=True)
                
                # Mostrar taquilla
                st.markdown(f'<div class="taquilla-info">{turno_actual["taquilla_asignada"]}</div>', unsafe_allow_html=True)
                
                # HORA DE LLAMADA
                hora_llamado = format_hora(turno_actual["fecha_llamado"])
                st.markdown(f'''
                <div class="hora-llamada">
                    <div class="hora-label">Hora de llamado</div>
                    <div class="hora-valor">{hora_llamado}</div>
                </div>
                ''', unsafe_allow_html=True)
                
            else:
                st.markdown('<div class="current-turno">---</div>', unsafe_allow_html=True)
                st.markdown('<div class="taquilla-info">ESPERANDO TURNOS</div>', unsafe_allow_html=True)
                
                # Mostrar hora actual cuando no hay turnos
                hora_actual = time.strftime('%H:%M:%S')
                st.markdown(f'''
                <div class="hora-llamada">
                    <div class="hora-label">Hora actual</div>
                    <div class="hora-valor">{hora_actual}</div>
                </div>
                ''', unsafe_allow_html=True)
        
        with col_right:
            # SECCIÓN DERECHA - HISTORIAL
            st.markdown('<div class="section-title">TURNOS ANTERIORES</div>', unsafe_allow_html=True)
            
            if not historial_df.empty:
                # Mostrar historial (máximo 4 turnos)
                for i, turno in historial_df.iterrows():
                    hora_llamado = format_hora(turno["fecha_llamado"])
                    nombre_usuario = turno.get("nombre_usuario", "")
                    
                    # TURNO CON NOMBRE CONCATENADO PARA HISTORIAL
                    turno_con_nombre = f"{turno['modulo']}{turno['numero_turno']} - {nombre_usuario}" if nombre_usuario else f"{turno['modulo']}{turno['numero_turno']}"
                    
                    st.markdown(f"""
                    <div class="historial-item">
                        <div>
                            <div class="turno-con-nombre-historial">{turno_con_nombre}</div>
                            <div class="taquilla-number">{turno["taquilla_asignada"]}</div>
                        </div>
                        <div class="time-stamp">{hora_llamado}</div>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.markdown('<div class="empty-state">No hay turnos en el historial</div>', unsafe_allow_html=True)
    
    time.sleep(3)  # Actualizar cada 3 segundos