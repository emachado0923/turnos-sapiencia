import os
from dotenv import load_dotenv
import mysql.connector
from mysql.connector import Error

load_dotenv()

def test_connections():
    print("🔍 DIAGNÓSTICO DE CONEXIONES")
    
    # Configuración BD principal
    main_config = {
        'host': os.getenv('DB_HOST', 'localhost'),
        'database': os.getenv('DB_NAME', 'analitica_fondos'),
        'user': os.getenv('DB_USER', 'root'),
        'password': os.getenv('DB_PASSWORD', ''),
        'port': os.getenv('DB_PORT', '3306')
    }
    
    # Configuración BD externa
    ext_config = {
        'host': os.getenv('EXTERNAL_DB_HOST', 'localhost'),
        'database': os.getenv('EXTERNAL_DB_NAME', 'convocatoria_sapiencia'),
        'user': os.getenv('EXTERNAL_DB_USER', 'root'),
        'password': os.getenv('EXTERNAL_DB_PASSWORD', ''),
        'port': os.getenv('EXTERNAL_DB_PORT', '3306')
    }
    
    print(f"\n1. Probando BD principal:")
    print(f"   Host: {main_config['host']}:{main_config['port']}")
    print(f"   Database: {main_config['database']}")
    print(f"   User: {main_config['user']}")
    
    try:
        conn = mysql.connector.connect(**main_config)
        print("   ✅ CONEXIÓN EXITOSA")
        conn.close()
    except Error as e:
        print(f"   ❌ ERROR: {e}")
    
    print(f"\n2. Probando BD externa:")
    print(f"   Host: {ext_config['host']}:{ext_config['port']}")
    print(f"   Database: {ext_config['database']}")
    print(f"   User: {ext_config['user']}")
    
    try:
        conn = mysql.connector.connect(**ext_config)
        print("   ✅ CONEXIÓN EXITOSA")
        conn.close()
    except Error as e:
        print(f"   ❌ ERROR: {e}")

if __name__ == "__main__":
    test_connections()