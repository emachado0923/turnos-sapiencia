"""
Script para resetear los contadores de turnos a cero
Uso: python reset_turnos.py
Nota: Solo resetea el contador, NO elimina registros de turnos
Los contadores quedan en cero y continúan desde ahí (001, 002, 003...)
"""

from config.database import get_db_engine, resetear_contadores_turnos, inicializar_contadores_turnos, Session, ContadorTurnos
from sqlalchemy import text
from datetime import datetime

def visualizar_estado_actual():
    """Muestra el estado actual de los contadores"""
    try:
        session = Session()
        contadores = session.query(ContadorTurnos).all()

        print("\n📊 ESTADO ACTUAL DE LOS CONTADORES:")
        print("-" * 40)

        if not contadores:
            print("❌ No hay contadores inicializados")
            return False

        for contador in contadores:
            print(f"📋 Módulo {contador.modulo}: {contador.ultimo_turno:03d}")

        return True

    except Exception as e:
        print(f"❌ Error al visualizar estado: {e}")
        return False
    finally:
        session.close()

if __name__ == "__main__":
    print("\n" + "="*70)
    print("🔄 HERRAMIENTA DE RESETEO DE CONTADORES DE TURNOS")
    print("="*70)
    print("\n✅ Resetea contadores a CERO")
    print("✅ NO elimina registros de turnos")
    print("✅ Los contadores continúan desde cero (001, 002, 003...)")
    print("✅ Histórico completo preservado\n")

    # Mostrar estado actual
    if not visualizar_estado_actual():
        print("🔄 Inicializando contadores...")
        inicializar_contadores_turnos()
        visualizar_estado_actual()

    print("\nOpciones:")
    print("1 - Resetear TODOS los contadores")
    print("2 - Salir sin hacer cambios")

    opcion = input("\nElige una opción (1/2): ").strip()

    if opcion == "1":
        respuesta = input("\n⚠️  ¿Estás seguro? Los contadores empezarán desde 001 (sí/no): ").lower().strip()

        if respuesta in ['sí', 'si', 'yes', 's']:
            if resetear_contadores_turnos():
                print("\n✅ ✅ CONTADORES RESETEADOS A CERO")
                print("\n📊 Nuevo estado:")
                visualizar_estado_actual()
                print("\n💡 Tip: Los próximos turnos asignados serán 001, 002, 003...")
                print("💡 El histórico completo se conservó\n")
            else:
                print("\n❌ Hubo un error al resetear los contadores")
        else:
            print("❌ Operación cancelada")
    elif opcion == "2":
        print("❌ Saliendo sin cambios...")
    else:
        print("❌ Opción inválida")