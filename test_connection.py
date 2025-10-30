import mysql.connector
from mysql.connector import Error
import os
from dotenv import load_dotenv

load_dotenv()

def test_connection():
    try:
        connection = mysql.connector.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            database=os.getenv('DB_NAME', 'analitica_fondos'),
            user=os.getenv('DB_USER', 'root'),
            password=os.getenv('DB_PASSWORD', ''),
            port=os.getenv('DB_PORT', '3306')
        )
        
        if connection.is_connected():
            print("✅ Conexión exitosa a MySQL")
            
            # Probar una consulta simple
            cursor = connection.cursor()
            cursor.execute("SELECT VERSION()")
            version = cursor.fetchone()
            print(f"✅ Versión de MySQL: {version[0]}")
            
            # Verificar si la base de datos existe
            cursor.execute("SHOW DATABASES LIKE 'analitica_fondos'")
            result = cursor.fetchone()
            if result:
                print("✅ Base de datos 'analitica_fondos' encontrada")
            else:
                print("⚠️ Base de datos 'analitica_fondos' no existe")
                
            cursor.close()
            connection.close()
            
    except Error as e:
        print(f"❌ Error de conexión: {e}")

if __name__ == "__main__":
    test_connection()