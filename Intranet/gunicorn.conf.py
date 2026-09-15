import threading


def post_worker_init(worker):
    """Se ejecuta justo despues de que un worker arranca, antes de recibir
    trafico real. Dispara el precalentado de la conexion a la BD en un hilo
    aparte, SIN esperarlo -- asi el worker queda listo para aceptar
    conexiones (incluyendo /healthz) de inmediato, sin importar cuanto tarde
    o si se cuelga el primer connect() a la BD (que en produccion a veces se
    queda colgado, ver el comentario de _serializar_conexiones en
    db_config.py). Bloquear el arranque aca fue un error: si el connect()
    se cuelga, NINGUN worker queda listo para nada, ni para el health check
    -- eso es peor que antes de este hook.
    """
    def _precalentar():
        try:
            import db_config
            import sqlalchemy as sa
            with db_config.get_engine().connect() as conn:
                conn.execute(sa.text("SELECT 1"))
            worker.log.info("Conexion a BD precalentada OK")
        except Exception as e:
            worker.log.warning(f"Precalentar conexion a BD fallo (se reintentara en la primera peticion real): {e}")

    threading.Thread(target=_precalentar, daemon=True).start()
