import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError
import streamlit as st
from datetime import datetime, timedelta
import threading

load_dotenv()

EXTERNAL_TABLE_NAME = os.getenv('EXTERNAL_TABLE_NAME', 'vw_pqrs_registro_telefonico')

# Cache mejorado para múltiples usuarios
_cache = {
    'last_check': None,
    'personas_cache': [],
    'cache_duration': 10,  # Reducido para múltiples usuarios
    'lock': threading.Lock()  # Lock para evitar condiciones de carrera
}

def get_db_engine():
    """Engine para BD principal con conexión persistente"""
    if 'main_engine' not in st.session_state:
        try:
            database_url = f"mysql+mysqlconnector://{os.getenv('DB_USER', 'root')}:{os.getenv('DB_PASSWORD', '')}@{os.getenv('DB_HOST', 'localhost')}:{os.getenv('DB_PORT', '3306')}/{os.getenv('DB_NAME', 'analitica_fondos')}"
            st.session_state.main_engine = create_engine(
                database_url, 
                pool_pre_ping=True, 
                pool_recycle=3600,
                pool_size=10,  # Aumentado para múltiples usuarios
                max_overflow=20
            )
        except SQLAlchemyError as e:
            print(f"❌ Error creando engine principal: {e}")
            return None
    return st.session_state.main_engine

def get_external_db_engine():
    """Engine para BD externa con conexión persistente"""
    if 'external_engine' not in st.session_state:
        try:
            external_db_config = {
                'host': os.getenv('EXTERNAL_DB_HOST', 'localhost'),
                'database': os.getenv('EXTERNAL_DB_NAME', 'convocatoria_sapiencia'),
                'user': os.getenv('EXTERNAL_DB_USER', 'root'),
                'password': os.getenv('EXTERNAL_DB_PASSWORD', ''),
                'port': os.getenv('EXTERNAL_DB_PORT', '3306')
            }
            database_url = f"mysql+mysqlconnector://{external_db_config['user']}:{external_db_config['password']}@{external_db_config['host']}:{external_db_config['port']}/{external_db_config['database']}"
            st.session_state.external_engine = create_engine(
                database_url, 
                pool_pre_ping=True, 
                pool_recycle=3600,
                pool_size=10,
                max_overflow=20
            )
        except SQLAlchemyError as e:
            print(f"❌ Error creando engine externo: {e}")
            return None
    return st.session_state.external_engine

def obtener_personas_sin_turno():
    """Obtiene personas con cache thread-safe - Detecta reingresos legítimos"""
    with _cache['lock']:
        now = datetime.now()
        
        if (_cache['last_check'] and 
            (now - _cache['last_check']).seconds < _cache['cache_duration'] and
            _cache['personas_cache']):
            return _cache['personas_cache']
        
        engine = get_external_db_engine()
        if not engine:
            return []
        
        try:
            with engine.connect() as conn:
                # Contar apariciones por cédula en la vista externa HOY
                query_count = text(f"""
                SELECT documento, COUNT(*) as apariciones
                FROM {EXTERNAL_TABLE_NAME}
                WHERE DATE(fecha) = CURDATE()
                AND tema_de_solicitud = 'Inscripción convocatoria'
                GROUP BY documento
                """)
                
                result_count = conn.execute(query_count)
                conteo_apariciones = {row[0]: row[1] for row in result_count}
                
                # Obtener todas las personas
                query_personas = text(f"""
                SELECT 
                    nombre1, nombre2, apellido1, apellido2, documento, tema_de_solicitud
                FROM {EXTERNAL_TABLE_NAME}
                WHERE DATE(fecha) = CURDATE()
                AND tema_de_solicitud = 'Inscripción convocatoria'
                LIMIT 100
                """)
                
                result_personas = conn.execute(query_personas)
                todas_personas = result_personas.fetchall()
                
                # FILTRAR con lógica de reingreso
                engine_main = get_db_engine()
                personas_filtradas = []
                
                if engine_main:
                    with engine_main.connect() as conn_main:
                        for persona in todas_personas:
                            documento = persona[4]
                            if not documento:
                                continue
                            
                            # SOLO USAR NOMBRE1 Y APELLIDO1
                            nombre1 = persona[0].strip() if persona[0] else ''
                            apellido1 = persona[2].strip() if persona[2] else ''
                            
                            # Crear nueva tupla con solo los datos necesarios
                            persona_simple = (
                                nombre1, '', apellido1, '',  # Solo nombre1 y apellido1, los demás vacíos
                                documento, persona[5]
                            )
                                
                            # Verificar en nuestra base de datos
                            result_turnos = conn_main.execute(
                                text("""
                                SELECT COUNT(*) as turnos_hoy 
                                FROM turnos 
                                WHERE cedula_usuario = :cedula 
                                AND DATE(fecha_creacion) = CURDATE()
                                """),
                                {"cedula": documento}
                            )
                            turnos_existentes = result_turnos.fetchone()[0]
                            
                            apariciones_externas = conteo_apariciones.get(documento, 0)
                            
                            # LÓGICA DE REINGRESO:
                            if turnos_existentes == 0:
                                # Nuevo ingreso - asignar siempre
                                personas_filtradas.append(persona_simple)
                                print(f"✅ NUEVO: {documento} - Primer turno del día")
                                
                            elif apariciones_externas > turnos_existentes:
                                # Reingreso legítimo - necesita nuevo turno
                                personas_filtradas.append(persona_simple)
                                print(f"✅ REINGRESO: {documento} - Apariciones: {apariciones_externas} vs Turnos: {turnos_existentes}")
                                
                            else:
                                # Posible duplicado - no asignar
                                print(f"⏭️ DUPLICADO: {documento} - Ya tiene {turnos_existentes} turno(s), apariciones: {apariciones_externas}")
                
                _cache['last_check'] = now
                _cache['personas_cache'] = personas_filtradas
                
                print(f"👥 Filtrado: {len(todas_personas)} → {len(personas_filtradas)} personas para asignar")
                return personas_filtradas
                
        except SQLAlchemyError as e:
            print(f"❌ Error obteniendo personas: {e}")
            return []

def ya_tiene_turno_pendiente(cedula):
    """Verificación optimizada con cache por sesión"""
    if 'turnos_pendientes' not in st.session_state:
        st.session_state.turnos_pendientes = {}
    
    # Cache de corta duración por sesión
    cache_key = f"{cedula}_{datetime.now().strftime('%H%M')}"  # Cache por minuto
    
    if cache_key in st.session_state.turnos_pendientes:
        return st.session_state.turnos_pendientes[cache_key]
    
    engine = get_db_engine()
    if not engine:
        return False
    
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text("SELECT COUNT(*) FROM turnos WHERE cedula_usuario = :cedula AND estado != 'atendido'"),
                {"cedula": cedula}
            )
            count = result.fetchone()[0]
            tiene_turno = count > 0
            
            st.session_state.turnos_pendientes[cache_key] = tiene_turno
            return tiene_turno
            
    except SQLAlchemyError as e:
        print(f"❌ Error verificando turno: {e}")
        return False

def obtener_siguiente_turno_lote(modulo):
    """Obtiene números de turno con manejo de concurrencia"""
    engine = get_db_engine()
    if not engine:
        return 1
    
    try:
        with engine.connect() as conn:
            # Usar transacción para evitar condiciones de carrera
            with conn.begin():
                result = conn.execute(
                    text("SELECT MAX(CAST(numero_turno AS UNSIGNED)) FROM turnos WHERE modulo = :modulo"),
                    {"modulo": modulo}
                )
                resultado = result.fetchone()
                return resultado[0] + 1 if resultado[0] is not None else 1
                
    except SQLAlchemyError as e:
        print(f"Error obteniendo turno: {e}")
        return 1

def asignar_turnos_automaticos_silencioso():
    """Versión silenciosa para asignación automática en background"""
    # Limpiar cache al inicio
    limpiar_cache_personas()
    
    personas = obtener_personas_sin_turno()
    if not personas:
        return 0
    
    turnos_asignados = 0
    
    for persona in personas:
        if hasattr(persona, '_mapping'):
            persona_dict = dict(persona._mapping)
        else:
            persona_dict = {
                'nombre1': persona[0], 'nombre2': persona[1],
                'apellido1': persona[2], 'apellido2': persona[3],
                'documento': persona[4], 'tema_de_solicitud': persona[5]
            }
        
        # SOLO GUARDAR NOMBRE1 Y APELLIDO1
        nombre1 = persona_dict.get('nombre1', '').strip()
        apellido1 = persona_dict.get('apellido1', '').strip()
        
        # Construir nombre simple: nombre1 + apellido1
        nombre_simple = f"{nombre1} {apellido1}".strip()
        
        cedula = persona_dict.get('documento', '')
        tipo_solicitud = persona_dict.get('tema_de_solicitud', 'Inscripción convocatoria')
        
        if not cedula:
            continue
        
        # SOLO evitar si tiene turnos PENDIENTES HOY (espera o llamando)
        if ya_tiene_turno_pendiente_robusto(cedula):
            continue
        
        modulo = 'A'
        siguiente_numero = obtener_siguiente_turno_lote(modulo)
        turno_formateado = f"{siguiente_numero:03d}"
        
        engine = get_db_engine()
        if engine:
            try:
                with engine.connect() as conn:
                    # Verificación final en transacción - solo HOY
                    result = conn.execute(
                        text("""
                        SELECT COUNT(*) FROM turnos 
                        WHERE cedula_usuario = :cedula 
                        AND estado IN ('espera', 'llamando')
                        AND DATE(fecha_creacion) = CURDATE()
                        """),
                        {"cedula": cedula}
                    )
                    if result.fetchone()[0] > 0:
                        continue
                    
                    conn.execute(
                        text("""
                        INSERT INTO turnos 
                        (modulo, numero_turno, estado, nombre_usuario, cedula_usuario, tipo_tramite) 
                        VALUES (:modulo, :numero_turno, 'espera', :nombre, :cedula, :tramite)
                        """),
                        {
                            "modulo": modulo, "numero_turno": turno_formateado,
                            "nombre": nombre_simple, "cedula": cedula, "tramite": tipo_solicitud
                        }
                    )
                    conn.commit()
                    turnos_asignados += 1
                    print(f"✅ Turno automático: {modulo}{turno_formateado} para {cedula}")
                    
            except SQLAlchemyError as e:
                if "Duplicate" not in str(e):
                    print(f"❌ Error asignando turno: {e}")
    
    return turnos_asignados

# En la función obtener_turnos_en_espera, cambiamos la consulta:
def obtener_turnos_por_estado():
    """Obtiene todos los turnos agrupados por estado"""
    engine = get_db_engine()
    if engine:
        try:
            with engine.connect() as conn:
                query = text("""
                SELECT 
                    id, modulo, numero_turno, nombre_usuario, cedula_usuario, 
                    tipo_tramite, estado, taquilla_asignada, fecha_llamado
                FROM turnos 
                WHERE estado IN ('espera', 'llamando')
                ORDER BY 
                    CASE 
                        WHEN estado = 'llamando' THEN 1
                        WHEN estado = 'espera' THEN 2
                    END,
                    fecha_creacion
                """)
                result = conn.execute(query)
                turnos = result.fetchall()
                return turnos
        except SQLAlchemyError as e:
            print(f"❌ Error obteniendo turnos por estado: {e}")
            return []
    return []

# Agregar estas funciones al database.py

def taquilla_tiene_turno_activo(taquilla):
    """Verifica si una taquilla ya tiene un turno en estado 'llamando'"""
    engine = get_db_engine()
    if not engine:
        return False
    
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text("""
                SELECT COUNT(*) FROM turnos 
                WHERE taquilla_asignada = :taquilla 
                AND estado = 'llamando'
                """),
                {"taquilla": taquilla}
            )
            count = result.fetchone()[0]
            return count > 0
    except SQLAlchemyError as e:
        print(f"❌ Error verificando taquilla activa: {e}")
        return False

def obtener_turno_activo_taquilla(taquilla):
    """Obtiene el turno activo de una taquilla específica"""
    engine = get_db_engine()
    if not engine:
        return None
    
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text("""
                SELECT id, modulo, numero_turno, nombre_usuario, tipo_tramite, fecha_llamado
                FROM turnos 
                WHERE taquilla_asignada = :taquilla 
                AND estado = 'llamando'
                LIMIT 1
                """),
                {"taquilla": taquilla}
            )
            return result.fetchone()
    except SQLAlchemyError as e:
        print(f"❌ Error obteniendo turno activo: {e}")
        return None
    
def limpiar_cache_personas():
    """Limpia el cache de personas sin turno"""
    with _cache['lock']:
        _cache['last_check'] = None
        _cache['personas_cache'] = []
    print("🧹 Cache de personas limpiado")

def ya_tiene_turno_pendiente_robusto(cedula):
    """SOLO evita tener múltiples turnos PENDIENTES simultáneamente"""
    engine = get_db_engine()
    if not engine:
        return False
    
    try:
        with engine.connect() as conn:
            # Solo verificar turnos que aún NO han sido atendidos
            result = conn.execute(
                text("""
                SELECT COUNT(*) FROM turnos 
                WHERE cedula_usuario = :cedula 
                AND estado IN ('espera', 'llamando')
                AND DATE(fecha_creacion) = CURDATE()  # ← AGREGAR ESTO
                """),
                {"cedula": cedula}
            )
            count = result.fetchone()[0]
            return count > 0
            
    except SQLAlchemyError as e:
        print(f"❌ Error verificando turno (robusto): {e}")
        return False
    
def limpiar_cache_turnos_pendientes(cedula=None):
    """Limpia el cache de turnos pendientes - importante después de marcar como atendido"""
    if 'turnos_pendientes' in st.session_state:
        if cedula:
            # Limpiar solo para una cédula específica
            keys_a_eliminar = [key for key in st.session_state.turnos_pendientes.keys() if key.startswith(cedula)]
            for key in keys_a_eliminar:
                del st.session_state.turnos_pendientes[key]
            print(f"🧹 Cache limpiado para cédula: {cedula}")
        else:
            # Limpiar todo el cache
            st.session_state.turnos_pendientes = {}
            print("🧹 Cache de turnos pendientes limpiado completamente")

def init_database():
    """
    Inicializa la tabla de turnos en analitica_fondos
    """
    engine = get_db_engine()
    if engine:
        try:
            with engine.connect() as conn:
                create_table_query = text("""
                CREATE TABLE IF NOT EXISTS turnos (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    modulo VARCHAR(10) NOT NULL,
                    numero_turno VARCHAR(10) NOT NULL,
                    estado ENUM('espera', 'llamando', 'atendido') DEFAULT 'espera',
                    taquilla_asignada VARCHAR(50),
                    nombre_usuario VARCHAR(100),
                    cedula_usuario VARCHAR(20),
                    tipo_tramite VARCHAR(50),
                    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    fecha_llamado TIMESTAMP NULL,
                    INDEX idx_estado (estado),
                    INDEX idx_modulo (modulo),
                    INDEX idx_fecha_creacion (fecha_creacion)
                )
                """)
                conn.execute(create_table_query)
                conn.commit()
                print("✅ Tabla 'turnos' creada/verificada correctamente en analitica_fondos")
                
        except SQLAlchemyError as e:
            print(f"❌ Error inicializando base de datos: {e}")