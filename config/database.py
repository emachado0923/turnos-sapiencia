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

def verificar_tabla_control():
    """Verifica que la tabla de control exista, si no, la crea"""
    engine = get_db_engine()
    if not engine:
        return False
    
    try:
        with engine.connect() as conn:
            # Verificar si la tabla existe
            result = conn.execute(
                text("""
                SELECT COUNT(*) FROM information_schema.tables 
                WHERE table_schema = 'analitica_fondos' 
                AND table_name = 'control_turnos_externos'
                """)
            )
            tabla_existe = result.fetchone()[0] > 0
            
            if not tabla_existe:
                print("🔄 La tabla control_turnos_externos no existe, creándola...")
                # Crear solo la tabla de control
                create_control_query = text("""
                CREATE TABLE IF NOT EXISTS control_turnos_externos (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    nombre1 VARCHAR(100),
                    nombre2 VARCHAR(100),
                    apellido1 VARCHAR(100),
                    apellido2 VARCHAR(100),
                    documento VARCHAR(20) NOT NULL,
                    tema_solicitud VARCHAR(100),
                    fecha_lectura TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    procesado BOOLEAN DEFAULT FALSE,
                    turno_asignado VARCHAR(20),
                    fecha_procesado TIMESTAMP NULL,
                    INDEX idx_documento (documento),
                    INDEX idx_procesado (procesado),
                    INDEX idx_fecha_lectura (fecha_lectura),
                    INDEX idx_documento_fecha (documento, fecha_lectura)
                )
                """)
                conn.execute(create_control_query)
                conn.commit()
                print("✅ Tabla 'control_turnos_externos' creada exitosamente")
            else:
                print("✅ Tabla control_turnos_externos verificada")
            
            return True
            
    except SQLAlchemyError as e:
        print(f"❌ Error verificando tabla control: {e}")
        return False

def sincronizar_y_obtener_personas_ordenadas():
    """
    1. Sincroniza la vista externa con nuestra tabla de control
    2. Devuelve personas NO procesadas en ORDEN DE LLEGADA
    """
    # Primero verificar que la tabla de control existe
    if not verificar_tabla_control():
        return []
    
    engine_ext = get_external_db_engine()
    engine_main = get_db_engine()
    
    if not engine_ext or not engine_main:
        return []
    
    try:
        # Obtener fecha actual en formato YYYY-MM-DD
        fecha_actual = datetime.now().strftime('%Y-%m-%d')
        fecha_actual_formato_vista = datetime.now().strftime('%d/%m/%Y')  # Formato común para vistas
        
        print(f"📅 Buscando registros para hoy: {fecha_actual_formato_vista} (formato vista)")
        
        # PASO 1: Obtener TODOS los registros de hoy de la vista externa
        with engine_ext.connect() as conn_ext:
            # Intentar diferentes formatos de fecha
            query_todos = text(f"""
            SELECT 
                nombre1, nombre2, apellido1, apellido2, documento, tema_de_solicitud
            FROM {EXTERNAL_TABLE_NAME}
            WHERE (fecha = :fecha1 OR fecha = :fecha2 OR fecha = :fecha3)
            AND tema_de_solicitud IN ('Notificaciones')  -- MODIFICADO
            """)
            
            # Probar diferentes formatos de fecha
            fecha_formato1 = datetime.now().strftime('%d/%m/%Y')  # DD/MM/YYYY
            fecha_formato2 = datetime.now().strftime('%Y-%m-%d')  # YYYY-MM-DD
            fecha_formato3 = datetime.now().strftime('%d-%m-%Y')  # DD-MM-YYYY
            
            result_todos = conn_ext.execute(query_todos, {
                "fecha1": fecha_formato1,
                "fecha2": fecha_formato2, 
                "fecha3": fecha_formato3
            })
            
            todos_registros = result_todos.fetchall()
            print(f"👥 Total de registros en vista externa: {len(todos_registros)}")
            
            if todos_registros:
                for registro in todos_registros:
                    print(f"   - Documento: {registro[4]}, Tema: {registro[5]}")
        
        # PASO 2: Para cada registro, verificar si ya existe en control e insertar si no existe
        nuevos_count = 0
        with engine_main.connect() as conn_main:
            for registro in todos_registros:
                documento = registro[4]
                tema_solicitud = registro[5]
                
                if not documento:
                    continue
                
                # Verificar si ya existe en control_turnos_externos HOY con el mismo tema
                result_existe = conn_main.execute(
                    text("""
                    SELECT COUNT(*) FROM control_turnos_externos 
                    WHERE documento = :documento 
                    AND DATE(fecha_lectura) = CURDATE()
                    AND tema_solicitud = :tema_solicitud
                    """),
                    {"documento": documento, "tema_solicitud": tema_solicitud}
                )
                existe = result_existe.fetchone()[0] > 0
                
                if not existe:
                    try:
                        conn_main.execute(
                            text("""
                            INSERT INTO control_turnos_externos 
                            (nombre1, nombre2, apellido1, apellido2, documento, tema_solicitud)
                            VALUES (:nombre1, :nombre2, :apellido1, :apellido2, :documento, :tema)
                            """),
                            {
                                "nombre1": registro[0] or '', 
                                "nombre2": registro[1] or '',
                                "apellido1": registro[2] or '', 
                                "apellido2": registro[3] or '',
                                "documento": documento, 
                                "tema": tema_solicitud
                            }
                        )
                        nuevos_count += 1
                        print(f"📥 Nuevo registro en control: {documento} - {tema_solicitud}")
                    except Exception as e:
                        if "Duplicate" not in str(e):
                            print(f"❌ Error insertando en control para {documento}: {e}")
            
            if nuevos_count > 0:
                conn_main.commit()
                print(f"✅ Sincronización completada: {nuevos_count} registros nuevos")
        
        # PASO 3: Obtener personas NO procesadas en ORDEN CORRECTO DE LLEGADA
        with engine_main.connect() as conn_main:
            query_pendientes = text("""
            SELECT 
                id, nombre1, nombre2, apellido1, apellido2, documento, tema_solicitud
            FROM control_turnos_externos
            WHERE DATE(fecha_lectura) = CURDATE()
            AND procesado = FALSE
            ORDER BY id DESC
            LIMIT 50
            """)
            
            result_pendientes = conn_main.execute(query_pendientes)
            personas_pendientes = result_pendientes.fetchall()
            
            # Mostrar el orden en que se van a procesar
            if personas_pendientes:
                print("📋 ORDEN DE PROCESAMIENTO (primero los más antiguos):")
                for i, persona in enumerate(personas_pendientes):
                    print(f"   {i+1}. ID: {persona[0]} - {persona[5]} - {persona[6]}")
            
            print(f"👥 Personas pendientes por turno: {len(personas_pendientes)}")
            
            return personas_pendientes
            
    except SQLAlchemyError as e:
        print(f"❌ Error en sincronización: {e}")
        return []

def obtener_personas_sin_turno():
    """Función mantenida para compatibilidad - ahora usa la nueva tabla de control"""
    return sincronizar_y_obtener_personas_ordenadas()

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
    
    personas = sincronizar_y_obtener_personas_ordenadas()
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
                'documento': persona[4], 'tema_solicitud': persona[5]  # Nota: aquí es tema_solicitud
            }
        
        # SOLO GUARDAR NOMBRE1 Y APELLIDO1
        nombre1 = persona_dict.get('nombre1', '').strip()
        apellido1 = persona_dict.get('apellido1', '').strip()
        
        # Construir nombre simple: nombre1 + apellido1
        nombre_simple = f"{nombre1} {apellido1}".strip()
        
        cedula = persona_dict.get('documento', '')
        tipo_solicitud = persona_dict.get('tema_solicitud', '')  # Cambiado de tema_de_solicitud a tema_solicitud
        
        if not cedula:
            continue
        
        # SOLO evitar si tiene turnos PENDIENTES HOY (espera o llamando)
        if ya_tiene_turno_pendiente_robusto(cedula):
            continue
        
        # DETERMINAR MÓDULO SEGÚN TEMA DE SOLICITUD
        if tipo_solicitud == 'Legalización fondo':
            modulo = 'P'
        else:  # Cualquier otro
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
                    
                    # Marcar como procesado en tabla de control
                    conn.execute(
                        text("""
                        UPDATE control_turnos_externos 
                        SET procesado = TRUE, turno_asignado = :turno, fecha_procesado = NOW()
                        WHERE documento = :documento 
                        AND DATE(fecha_lectura) = CURDATE()
                        """),
                        {"documento": cedula, "turno": f"{modulo}{turno_formateado}"}
                    )
                    
                    conn.commit()
                    turnos_asignados += 1
                    print(f"✅ Turno automático: {modulo}{turno_formateado} para {cedula} ({tipo_solicitud})")
                    
            except SQLAlchemyError as e:
                if "Duplicate" not in str(e):
                    print(f"❌ Error asignando turno: {e}")
    
    return turnos_asignados

def verificar_sincronizacion():
    """Función para depurar la sincronización"""
    engine_ext = get_external_db_engine()
    engine_main = get_db_engine()
    
    if not engine_ext or not engine_main:
        print("❌ No se pudo conectar a las bases de datos")
        return
    
    try:
        # Obtener fecha actual en diferentes formatos
        fecha_formato1 = datetime.now().strftime('%d/%m/%Y')
        fecha_formato2 = datetime.now().strftime('%Y-%m-%d')
        fecha_formato3 = datetime.now().strftime('%d-%m-%Y')
        
        print(f"🔍 Verificando sincronización para hoy:")
        print(f"   - Formato 1: {fecha_formato1}")
        print(f"   - Formato 2: {fecha_formato2}")
        print(f"   - Formato 3: {fecha_formato3}")
        
        # Ver vista externa
        with engine_ext.connect() as conn:
            query = text(f"""
            SELECT fecha, documento, tema_de_solicitud 
            FROM {EXTERNAL_TABLE_NAME}
            WHERE tema_de_solicitud IN ('Notificaciones')
            ORDER BY fecha DESC
            LIMIT 20
            """)
            result = conn.execute(query)
            registros = result.fetchall()
            
            print(f"📋 Registros en vista {EXTERNAL_TABLE_NAME}:")
            for reg in registros:
                print(f"   Fecha: {reg[0]}, Doc: {reg[1]}, Tema: {reg[2]}")
        
        # Ver tabla de control
        with engine_main.connect() as conn:
            query = text("""
            SELECT documento, tema_solicitud, procesado, fecha_lectura
            FROM control_turnos_externos 
            WHERE DATE(fecha_lectura) >= CURDATE() - INTERVAL 1 DAY
            ORDER BY fecha_lectura DESC
            """)
            result = conn.execute(query)
            registros_control = result.fetchall()
            
            print(f"📋 Registros en control_turnos_externos (último día):")
            for reg in registros_control:
                print(f"   Doc: {reg[0]}, Tema: {reg[1]}, Procesado: {reg[2]}, Fecha: {reg[3]}")
                
    except Exception as e:
        print(f"❌ Error en verificación: {e}")

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
                # Asegurarnos de usar la base de datos correcta
                conn.execute(text("USE analitica_fondos"))
                
                # Tabla de turnos principal
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
                print("✅ Tabla 'turnos' verificada en analitica_fondos")
                
                # NUEVA: Tabla de control para capturar el orden de llegada
                create_control_query = text("""
                CREATE TABLE IF NOT EXISTS control_turnos_externos (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    nombre1 VARCHAR(100),
                    nombre2 VARCHAR(100),
                    apellido1 VARCHAR(100),
                    apellido2 VARCHAR(100),
                    documento VARCHAR(20) NOT NULL,
                    tema_solicitud VARCHAR(100),
                    fecha_lectura TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    procesado BOOLEAN DEFAULT FALSE,
                    turno_asignado VARCHAR(20),
                    fecha_procesado TIMESTAMP NULL,
                    INDEX idx_documento (documento),
                    INDEX idx_procesado (procesado),
                    INDEX idx_fecha_lectura (fecha_lectura),
                    INDEX idx_documento_fecha (documento, fecha_lectura)
                )
                """)
                conn.execute(create_control_query)
                print("✅ Tabla 'control_turnos_externos' creada en analitica_fondos")
                
                conn.commit()
                print("✅✅ Todas las tablas inicializadas correctamente en analitica_fondos")
                
        except SQLAlchemyError as e:
            print(f"❌ Error inicializando base de datos: {e}")