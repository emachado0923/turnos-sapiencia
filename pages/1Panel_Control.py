import streamlit as st
import pandas as pd
from config.database import get_db_engine, obtener_siguiente_turno_lote, resetear_contadores_turnos, inicializar_contadores_turnos, desbloquear_contadores_turnos
from utils.helpers import setup_page_config
from sqlalchemy import text

setup_page_config("Panel de Control - Registro", "wide")

# Configuración de módulos SOLO para clasificación
# Configuración de módulos SOLO para clasificación
MODULOS_CONFIG = {
    "A": "Inscripción Convocatoria",
    "P": "Legalización Fondo",  # Actualizado
    "L": "Libranzas", 
    "C": "Consultas",
    "S": "Soporte Técnico"
}

def obtener_estadisticas():
    """
    Obtiene estadísticas desde la tabla de turnos
    """
    engine = get_db_engine()
    if engine:
        try:
            with engine.connect() as conn:
                # Turnos en espera por módulo
                query_espera = text("""
                SELECT modulo, COUNT(*) as cantidad 
                FROM turnos 
                WHERE estado = 'espera' 
                GROUP BY modulo
                ORDER BY modulo
                """)
                df_espera = pd.read_sql(query_espera, conn)
                
                # Próximos turnos
                query_proximos = text("""
                SELECT modulo, numero_turno, nombre_usuario, tipo_tramite
                FROM turnos 
                WHERE estado = 'espera' 
                ORDER BY fecha_creacion 
                LIMIT 5
                """)
                df_proximos = pd.read_sql(query_proximos, conn)
                
                # Total de turnos hoy
                query_hoy = text("""
                SELECT COUNT(*) as total_hoy 
                FROM turnos 
                WHERE DATE(fecha_creacion) = CURDATE()
                """)
                result = conn.execute(query_hoy)
                total_hoy = result.fetchone()[0]
                
                return df_espera, df_proximos, total_hoy
                
        except Exception as e:
            st.error(f"❌ Error obteniendo estadísticas: {e}")
            return pd.DataFrame(), pd.DataFrame(), 0
    return pd.DataFrame(), pd.DataFrame(), 0

# INTERFAZ PRINCIPAL
st.title("🏠 Panel de control - sistema de turnos")
st.markdown("---")

# Estadísticas en tiempo real
st.subheader("📊 Estado Actual del Sistema")

df_espera, df_proximos, total_hoy = obtener_estadisticas()

# Métricas principales
col1, col2 = st.columns(2)
with col1:
    st.metric("Total de Turnos Hoy", total_hoy)
with col2:
    total_espera = df_espera['cantidad'].sum() if not df_espera.empty else 0
    st.metric("En Espera", total_espera)

# Turnos en espera por módulo
st.markdown("#### 📈 Turnos en Espera por Tipo")
if not df_espera.empty:
    cols = st.columns(len(df_espera))
    for idx, (_, row) in enumerate(df_espera.iterrows()):
        with cols[idx]:
            nombre_modulo = MODULOS_CONFIG.get(row['modulo'], "General")
            st.metric(f"{row['modulo']}", row['cantidad'])
            st.caption(nombre_modulo)
else:
    st.info("No hay turnos en espera")

# Próximos turnos
st.markdown("#### 🔜 Próximos Turnos")
if not df_proximos.empty:
    for _, turno in df_proximos.iterrows():
        turno_completo = f"{turno['modulo']}{turno['numero_turno']}"
        st.write(f"**{turno_completo}** - {turno['nombre_usuario']}")
else:
    st.info("No hay turnos pendientes")

# Últimos turnos registrados
st.markdown("---")
st.subheader("🕒 Últimos Turnos Registrados")

engine = get_db_engine()
if engine:
    try:
        with engine.connect() as conn:
            # Consulta simplificada - que pandas maneje el formato de fecha
            query = text("""
            SELECT modulo, numero_turno, nombre_usuario, tipo_tramite, taquilla_asignada,
                   fecha_creacion, estado
            FROM turnos 
            ORDER BY fecha_creacion DESC 
            LIMIT 8
            """)
            ultimos_turnos = pd.read_sql(query, conn)
            
            if not ultimos_turnos.empty:
                # Formatear la hora con pandas
                ultimos_turnos['hora'] = pd.to_datetime(ultimos_turnos['fecha_creacion']).dt.strftime('%H:%M:%S')
                
                ultimos_turnos['Turno'] = ultimos_turnos['modulo'] + ultimos_turnos['numero_turno']
                ultimos_turnos['Estado'] = ultimos_turnos['estado'].map({
                    'espera': '⏳ Espera',
                    'llamando': '📢 Llamando', 
                    'atendido': '✅ Atendido'
                })
                
                # Mostrar taquilla solo si está asignada
                ultimos_turnos['Taquilla'] = ultimos_turnos['taquilla_asignada'].fillna('Pendiente')
                
                # Rellenar valores None
                ultimos_turnos['nombre_usuario'] = ultimos_turnos['nombre_usuario'].fillna('No registrado')
                ultimos_turnos['tipo_tramite'] = ultimos_turnos['tipo_tramite'].fillna('No especificado')
                
                ultimos_display = ultimos_turnos[['Turno', 'nombre_usuario', 'tipo_tramite', 'Taquilla', 'Estado', 'hora']]
                ultimos_display.columns = ['Turno', 'Usuario', 'Trámite', 'Taquilla', 'Estado', 'Hora ingreso']
                
                st.dataframe(ultimos_display, width='stretch', hide_index=True)
            else:
                st.info("No hay turnos registrados aún")
                
    except Exception as e:
        st.error(f"Error cargando últimos turnos: {e}")
        # Mostrar error detallado para debugging
        st.error(f"Detalle del error: {str(e)}")

# ============================================================================
# SECCIÓN DE ADMINISTRACIÓN Y RESETEO
# ============================================================================

st.markdown("---")
st.subheader("⚙️ Administración")

# Crear expandible para no saturar la pantalla
with st.expander("🔧 Herramientas de mantenimiento", expanded=False):
    
    st.info("🔄 **Resetear contadores** - Inicia numeración desde 001")
    st.subheader("📊 Contadores actuales:", divider=True)

    # Mostrar estado actual de los contadores SIN sincronizar automáticamente
    engine = get_db_engine()
    if engine:
        try:
            with engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT modulo, ultimo_turno, fecha_reseteo
                    FROM contadores_turnos
                    ORDER BY modulo
                """))
                contadores = result.fetchall()
                
                # Mostrar en columnas
                cols_contador = st.columns(len(contadores))
                for idx, (modulo, ultimo_turno, fecha_reseteo) in enumerate(contadores):
                    with cols_contador[idx]:
                        proximo = ultimo_turno + 1
                        st.metric(f"Módulo {modulo}", f"{proximo:03d}")
                        st.caption(f"Último: {ultimo_turno:03d}")
        except Exception as e:
            st.error(f"Error cargando contadores: {e}")
    
    st.divider()

    confirmacion = st.checkbox(
        "✅ Confirmar reseteo de contadores a CERO",
        key="confirm_reset"
    )

    if confirmacion:
        if st.button("🚀 Resetear contadores", key="btn_reset", type="secondary"):
            if resetear_contadores_turnos():
                st.success("✅ ✅ CONTADORES RESETEADOS A CERO")
                st.info("💡 Los próximos turnos asignados serán 001, 002, 003...")
                st.info("📋 Todos los registros de turnos se conservaron en el histórico")
                st.balloons()
                
                # Recargar estadísticas
                st.rerun()
            else:
                st.error("❌ Error durante el reseteo")

    st.divider()