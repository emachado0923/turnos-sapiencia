import streamlit as st
import pandas as pd
from config.database import (
    get_db_engine, obtener_turnos_por_estado, 
    obtener_personas_sin_turno, asignar_turnos_automaticos_silencioso,
    taquilla_tiene_turno_activo, obtener_turno_activo_taquilla,
    ya_tiene_turno_pendiente, obtener_siguiente_turno_lote,
    ya_tiene_turno_pendiente_robusto, limpiar_cache_personas  # ← AGREGAR ESTOS
)
from utils.helpers import setup_page_config
from sqlalchemy import text
from datetime import datetime

setup_page_config("Interfaz de Taquillas", "wide")

def asignar_turnos_rapido():
    """Función rápida para asignar turnos - SOLO evita turnos pendientes simultáneos"""
    from config.database import limpiar_cache_personas
    
    # LIMPIAR CACHE ANTES DE ASIGNAR
    limpiar_cache_personas()
    
    personas = obtener_personas_sin_turno()
    if not personas:
        print("🔍 No hay personas nuevas para asignar turnos")
        return 0
    
    turnos_asignados = 0
    engine = get_db_engine()
    
    print(f"🔍 Procesando {len(personas)} personas de la lista externa")
    
    for persona in personas:
        if hasattr(persona, '_mapping'):
            persona_dict = dict(persona._mapping)
        else:
            persona_dict = {
                'nombre1': persona[0], 'nombre2': persona[1],
                'apellido1': persona[2], 'apellido2': persona[3],
                'documento': persona[4], 'tema_de_solicitud': persona[5]
            }
        
        cedula = persona_dict.get('documento', '')
        
        # SOLO GUARDAR NOMBRE1 Y APELLIDO1
        nombre1 = persona_dict.get('nombre1', '').strip()
        apellido1 = persona_dict.get('apellido1', '').strip()
        
        # Construir nombre simple: nombre1 + apellido1
        nombre_simple = f"{nombre1} {apellido1}".strip()
        
        if not cedula:
            print(f"⚠️ Persona sin cédula: {nombre_simple}")
            continue
        
        print(f"🔍 Verificando cédula: {cedula} - {nombre_simple}")
        
        # VERIFICACIÓN DETALLADA
        engine_check = get_db_engine()
        if engine_check:
            try:
                with engine_check.connect() as conn:
                    # Consulta COMPLETA de todos los turnos de hoy para esta cédula
                    result = conn.execute(
                        text("""
                        SELECT id, modulo, numero_turno, estado, fecha_creacion 
                        FROM turnos 
                        WHERE cedula_usuario = :cedula 
                        AND DATE(fecha_creacion) = CURDATE()
                        ORDER BY fecha_creacion DESC
                        """),
                        {"cedula": cedula}
                    )
                    turnos_existentes = result.fetchall()
                    
                    if turnos_existentes:
                        print(f"📋 Turnos existentes para {cedula}:")
                        for turno in turnos_existentes:
                            print(f"   - {turno[1]}{turno[2]} | Estado: {turno[3]} | Fecha: {turno[4]}")
                        
                        # Verificar si hay algún turno NO atendido
                        turnos_pendientes = [t for t in turnos_existentes if t[3] in ('espera', 'llamando')]
                        if turnos_pendientes:
                            print(f"⏭️ Saltando {cedula} - tiene {len(turnos_pendientes)} turno(s) pendiente(s)")
                            continue
                        else:
                            print(f"✅ {cedula} - Todos los turnos están atendidos, puede recibir nuevo turno")
                    else:
                        print(f"✅ {cedula} - No tiene turnos hoy, puede recibir primer turno")
                        
            except Exception as e:
                print(f"❌ Error verificando turnos para {cedula}: {e}")
                continue
        
        # Si llegamos aquí, puede asignar turno
        modulo = 'A'
        siguiente_numero = obtener_siguiente_turno_lote(modulo)
        turno_formateado = f"{siguiente_numero:03d}"
        
        if engine:
            try:
                with engine.connect() as conn:
                    # VERIFICACIÓN FINAL EN TRANSACCIÓN
                    result = conn.execute(
                        text("""
                        SELECT COUNT(*) FROM turnos 
                        WHERE cedula_usuario = :cedula 
                        AND estado IN ('espera', 'llamando')
                        AND DATE(fecha_creacion) = CURDATE()
                        """),
                        {"cedula": cedula}
                    )
                    count_pendientes = result.fetchone()[0]
                    
                    if count_pendientes > 0:
                        print(f"🚫 TRANSACCIÓN BLOQUEADA: {cedula} tiene {count_pendientes} turno(s) pendiente(s)")
                        continue
                    
                    print(f"🎫 ASIGNANDO NUEVO TURNO: {modulo}{turno_formateado} para {cedula}")
                    
                    conn.execute(
                        text("""
                        INSERT INTO turnos 
                        (modulo, numero_turno, estado, nombre_usuario, cedula_usuario, tipo_tramite) 
                        VALUES (:modulo, :numero_turno, 'espera', :nombre, :cedula, :tramite)
                        """),
                        {
                            "modulo": modulo, 
                            "numero_turno": turno_formateado,
                            "nombre": nombre_simple,  # ← SOLO NOMBRE1 Y APELLIDO1
                            "cedula": cedula, 
                            "tramite": "Inscripción convocatoria"
                        }
                    )
                    conn.commit()
                    turnos_asignados += 1
                    print(f"✅✅✅ TURNO ASIGNADO EXITOSAMENTE: {modulo}{turno_formateado} para {cedula}")
                    
            except Exception as e:
                if "Duplicate" not in str(e):
                    print(f"❌ Error asignando turno para {cedula}: {e}")
    
    print(f"📊 RESUMEN: {turnos_asignados} turnos asignados en esta ejecución")
    return turnos_asignados

def llamar_siguiente_turno_con_actualizacion(taquilla):
    """Función que actualiza la lista automáticamente antes de llamar el siguiente turno"""
    
    # Primero actualizar la lista de turnos
    with st.spinner("🔄 Actualizando lista de turnos..."):
        turnos_asignados = asignar_turnos_rapido()
        if turnos_asignados > 0:
            st.toast(f'✅ {turnos_asignados} nuevos turnos asignados', icon='✅')
    
    # Luego proceder a llamar el siguiente turno
    if taquilla_tiene_turno_activo(taquilla):
        return None, None, "❌ Ya tienes un turno en atención. Termina el actual primero."
    
    engine = get_db_engine()
    if not engine:
        return None, None, "❌ Error de conexión a la base de datos"
    
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text("""
                SELECT id, modulo, numero_turno, nombre_usuario, tipo_tramite 
                FROM turnos 
                WHERE estado = 'espera' 
                ORDER BY fecha_creacion 
                LIMIT 1
                """)
            )
            turno = result.fetchone()
            
            if turno:
                conn.execute(
                    text("""
                    UPDATE turnos 
                    SET estado = 'llamando', taquilla_asignada = :taquilla, fecha_llamado = NOW() 
                    WHERE id = :id
                    """),
                    {"taquilla": taquilla.strip(), "id": turno[0]}
                )
                conn.commit()
                
                turno_info = f"{turno[1]}{turno[2]}"
                print(f"📢 Taquilla {taquilla} llamando turno: {turno_info}")
                return turno_info, turno[0], f"✅ Turno {turno_info} asignado a {taquilla}"
            else:
                print(f"ℹ️ Taquilla {taquilla}: No hay turnos en espera")
                return None, None, "ℹ️ No hay turnos en espera"
                
    except Exception as e:
        print(f"❌ Error al llamar turno en taquilla {taquilla}: {e}")
        return None, None, f"❌ Error al llamar turno: {e}"

def marcar_como_atendido(turno_id):
    """Función optimizada"""
    engine = get_db_engine()
    if not engine:
        return False
    
    try:
        with engine.connect() as conn:
            # Obtener información del turno antes de marcarlo como atendido
            result = conn.execute(
                text("SELECT modulo, numero_turno, taquilla_asignada, cedula_usuario FROM turnos WHERE id = :id"),
                {"id": int(turno_id)}
            )
            turno_info = result.fetchone()
            
            conn.execute(
                text("UPDATE turnos SET estado = 'atendido' WHERE id = :id"),
                {"id": int(turno_id)}
            )
            conn.commit()
            
            if turno_info:
                print(f"✅ Turno {turno_info[0]}{turno_info[1]} marcado como atendido en {turno_info[2]}")
                # LIMPIAR CACHE DE LA CÉDULA PARA EVITAR DUPLICADOS
                from config.database import limpiar_cache_turnos_pendientes
                if turno_info[3]:  # cedula_usuario
                    limpiar_cache_turnos_pendientes(turno_info[3])
            return True
    except Exception as e:
        st.error(f"❌ Error al marcar como atendido: {e}")
        return False

def obtener_turnos_activos(taquilla):
    """Función optimizada"""
    engine = get_db_engine()
    if not engine:
        return pd.DataFrame()
    
    try:
        with engine.connect() as conn:
            query = text("""
            SELECT id, modulo, numero_turno, estado, nombre_usuario, tipo_tramite, fecha_llamado
            FROM turnos 
            WHERE taquilla_asignada = :taquilla AND estado != 'atendido' 
            ORDER BY fecha_llamado DESC
            """)
            
            df = pd.read_sql(query, conn, params={"taquilla": taquilla})
            
            if not df.empty and 'fecha_llamado' in df.columns:
                df['hora_llamado'] = pd.to_datetime(df['fecha_llamado']).dt.strftime('%H:%M:%S')
            else:
                df['hora_llamado'] = '--:--:--'
                
            return df
            
    except Exception as e:
        st.error(f"❌ Error al obtener turnos activos: {e}")
        return pd.DataFrame()

# INTERFAZ PRINCIPAL MEJORADA
st.title("🖥️ Gestión por Taquilla")

# EJECUCIÓN AUTOMÁTICA AL CARGAR LA PÁGINA (solo primera vez) - MEJORADA
if 'auto_assigned' not in st.session_state:
    # Mostrar progreso mientras se asignan turnos
    with st.status("🔄 Inicializando sistema de turnos...", expanded=True) as status:
        st.write("📋 Verificando conexión a base de datos...")
        engine = get_db_engine()
        if engine:
            st.write("✅ Conexión establecida")
        else:
            st.error("❌ Error de conexión")
        
        st.write("👥 Consultando personas sin turno...")
        personas = obtener_personas_sin_turno()
        st.write(f"📊 {len(personas)} personas encontradas en la lista")
        
        st.write("🎫 Asignando turnos automáticamente...")
        turnos_iniciales = asignar_turnos_rapido()
        
        if turnos_iniciales > 0:
            status.update(label=f"✅ {turnos_iniciales} turnos asignados automáticamente", state="complete")
            st.toast(f'✅ {turnos_iniciales} turnos asignados automáticamente', icon='✅')
        else:
            status.update(label="✅ Sistema listo - No hay nuevos turnos para asignar", state="complete")
    
    st.session_state.auto_assigned = True

st.markdown("---")

# Selección de taquilla
taquilla = st.selectbox(
    "Selecciona tu taquilla",
    ["Taquilla 1", "Taquilla 2", "Taquilla 3", "Taquilla 4", "Taquilla 5", "Taquilla 6", "Taquilla 7", "Taquilla 8"]
)

st.markdown("---")

# SECCIÓN: Estado Actual de la Taquilla
st.subheader(f"📊 Estado de {taquilla}")

# Verificar estado de la taquilla
taquilla_ocupada = taquilla_tiene_turno_activo(taquilla)
turno_activo = obtener_turno_activo_taquilla(taquilla)

col1, col2 = st.columns(2)

with col1:
    if taquilla_ocupada and turno_activo:
        st.error(f"**⛔ OCUPADA**")
    else:
        st.success(f"**✅ DISPONIBLE**")
        st.info("Puedes llamar al siguiente turno")

with col2:
    if taquilla_ocupada and turno_activo:
        # Mostrar tiempo transcurrido
        if turno_activo[5]:  # fecha_llamado
            tiempo_transcurrido = datetime.now() - turno_activo[5]
            minutos = int(tiempo_transcurrido.total_seconds() / 60)
            st.metric("⏱️ Tiempo en atención", f"{minutos} min")

st.markdown("---")

# Obtener estado actual de turnos
personas_sin_turno = obtener_personas_sin_turno()
turnos_por_estado = obtener_turnos_por_estado()

# Separar turnos por estado
turnos_llamando = [t for t in turnos_por_estado if t[6] == 'llamando']
turnos_espera = [t for t in turnos_por_estado if t[6] == 'espera']

# Mostrar estadísticas rápidas
col_stat1, col_stat2, col_stat3 = st.columns(3)
with col_stat1:
    st.metric("⏳ Turnos en espera", len(turnos_espera))
with col_stat2:
    st.metric("📢 Turnos llamados", len(turnos_llamando))
    

st.markdown("---")

# SECCIÓN: Turnos en Atención (LLAMANDO)
if turnos_llamando:
    st.subheader("🧑‍💻 Turnos actualmente en atención (todas las taquillas)")
    
    for turno in turnos_llamando:
        col1, col2, col3, col4, col5 = st.columns([1, 3, 3, 2, 2])
        with col1:
            # Resaltar el turno de esta taquilla
            if turno[7] == taquilla:
                st.success(f"**{turno[1]}{turno[2]}** ⭐")
            else:
                st.write(f"**{turno[1]}{turno[2]}**")
        with col2:
            st.write(f"**{turno[3]}**")
        with col3:
            st.write(turno[5])  # trámite
        with col4:
            if turno[7] == taquilla:
                st.success(f"**{turno[7]}**")
            else:
                st.info(f"**{turno[7]}**")  # taquilla asignada
        with col5:
            # Mostrar hora de llamado si está disponible
            if turno[8]:
                hora_llamado = turno[8].strftime('%H:%M:%S') if hasattr(turno[8], 'strftime') else turno[8]
                st.caption(f"Llamado: {hora_llamado}")
else:
    st.info("ℹ️ No hay turnos en atención actualmente")

st.markdown("---")

# SECCIÓN: Turnos en Espera
if turnos_espera:
    st.subheader("⏳ Turnos en Espera")
    
    # Mostrar máximo 10 turnos en espera
    for i, turno in enumerate(turnos_espera[:10]):
        col1, col2, col3 = st.columns([1, 3, 3])
        with col1:
            st.write(f"**{turno[1]}{turno[2]}**")
        with col2:
            st.write(turno[3])  # nombre
        with col3:
            st.write(turno[5])  # trámite
    
    if len(turnos_espera) > 10:
        st.info(f"... y {len(turnos_espera) - 10} turnos más en espera")
else:
    st.info("ℹ️ No hay turnos en espera")

st.markdown("---")

# SECCIÓN: Acciones de Taquilla
st.subheader("🎛️ Acciones de Taquilla")

if taquilla_ocupada:
    # TAQUILLA OCUPADA - Mostrar acciones para terminar el turno actual
    st.warning("**⚠️ Tienes un turno en atención. Si vas a llamar a otro, debes marcar el actual como atendido.**")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if turno_activo:
            st.info(f"**Turno actual:** {turno_activo[1]}{turno_activo[2]}")
    
    with col2:
        if st.button("✅ Finalizar Atención Actual", width='stretch', type="primary"):
            if turno_activo:
                if marcar_como_atendido(turno_activo[0]):
                    st.success(f"✅ Turno **{turno_activo[1]}{turno_activo[2]}** marcado como atendido")
                    st.toast('✅ Turno finalizado correctamente', icon='✅')
                    st.rerun()
                else:
                    st.error("❌ No se pudo marcar el turno como atendido")
        
        if st.button("🔄 Verificar Estado", width='stretch', type="secondary"):
            st.rerun()

else:
    # TAQUILLA LIBRE - Mostrar acciones para llamar turno
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("📢 Llamar Siguiente Turno", width='stretch', type="primary"):
            # Esta función ahora incluye actualización automática
            turno_llamado, turno_id, mensaje = llamar_siguiente_turno_con_actualizacion(taquilla)
            
            if turno_llamado:
                st.success(mensaje)
                st.toast('✅ Turno asignado correctamente', icon='✅')
                
                # Mostrar información del usuario llamado
                engine = get_db_engine()
                if engine:
                    try:
                        with engine.connect() as conn:
                            result = conn.execute(
                                text("SELECT nombre_usuario, tipo_tramite FROM turnos WHERE id = :id"),
                                {"id": turno_id}
                            )
                            usuario_info = result.fetchone()
                            if usuario_info:
                                st.info(f"**Usuario:** {usuario_info[0]} | **Trámite:** {usuario_info[1]}")
                    except Exception as e:
                        st.error(f"Error obteniendo información: {e}")
                
                # Actualizar inmediatamente
                st.rerun()
            else:
                st.info(mensaje)
    
    with col2:
        if st.button("🔄 Actualizar Estado", width='stretch', type="secondary"):
            st.rerun()

# ASIGNACIÓN MANUAL (opcional - para casos específicos)
st.subheader("🔄 Forzar actualización de listado")

col1, col2 = st.columns(2)
with col1:
    if st.button("🔄 Actualizar Lista de Turnos", type="secondary", use_container_width=True):
        with st.spinner("Actualizando lista de turnos..."):
            turnos_asignados = asignar_turnos_rapido()
            if turnos_asignados > 0:
                st.success(f"✅ {turnos_asignados} nuevos turnos asignados")
            else:
                st.info("ℹ️ No hay nuevos turnos para asignar")
            st.rerun()

# Información adicional
st.markdown("---")
st.caption("💡 **Sistema de taquilla única**: Cada taquilla solo puede atender un turno a la vez. Debes finalizar la atención actual antes de llamar al siguiente turno.")
st.caption("🔄 **Actualización automática**: La lista de turnos se actualiza automáticamente al llamar un nuevo turno.")