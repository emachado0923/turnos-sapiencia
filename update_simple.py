from config.database import init_database

if __name__ == "__main__":
    print("🔄 Inicializando base de datos simplificada...")
    init_database()
    print("✅ Base de datos lista! Solo tabla 'turnos'")