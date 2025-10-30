import streamlit as st
from config.database import init_database
from sqlalchemy import text

# Inicializar base de datos al iniciar la app
init_database()

# Configurar página principal
st.set_page_config(
    page_title="Sistema de Gestión de Turnos",
    page_icon="🎫",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Título principal
st.title("🎫 Sistema de Gestión de Turnos Virtuales")
st.markdown("---")

# Descripción del sistema
st.markdown("""
### 📋 Módulos Disponibles:

1. **🏠 Panel de Control** - Asignar nuevos turnos y ver estadísticas
2. **📺 Pantalla de Turnos** - Mostrar turnos en pantalla grande (para TV)
3. **🏦 Interfaz de Taquillas** - Llamar y atender turnos

### 🚀 Instrucciones Rápidas:

1. **Asignar turnos**: Ve al Panel de Control
2. **Mostrar en TV**: Abre Pantalla de Turnos en pantalla completa
3. **Atender usuarios**: Usa Interfaz de Taquillas

### 📊 Estado del Sistema:
""")

# Verificar conexión a base de datos
from config.database import get_db_engine
engine = get_db_engine()
if engine:
    st.success("✅ **Base de datos:** Conectada correctamente")
    
    # Mostrar estadísticas rápidas
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT COUNT(*) FROM turnos WHERE estado = 'espera'"))
            en_espera = result.fetchone()[0]
            
            result = conn.execute(text("SELECT COUNT(*) FROM turnos WHERE estado = 'llamando'"))
            llamando = result.fetchone()[0]
            
            result = conn.execute(text("SELECT COUNT(*) FROM turnos WHERE estado = 'atendido'"))
            atendidos = result.fetchone()[0]
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("⏳ En Espera", en_espera)
            with col2:
                st.metric("📢 Llamando", llamando)
            with col3:
                st.metric("✅ Atendidos", atendidos)
                
    except Exception as e:
        st.error(f"Error obteniendo estadísticas: {e}")
else:
    st.error("❌ **Base de datos:** No conectada")

st.markdown("---")
st.info("💡 **Tip:** Usa el menú lateral para navegar entre los diferentes módulos")