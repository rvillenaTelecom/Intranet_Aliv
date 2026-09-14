def post_worker_init(worker):
    """Se ejecuta justo despues de que un worker arranca, antes de recibir
    trafico real. Abre la conexion a la BD de una vez en vez de esperar a
    la primera peticion -- asi el primer usuario que entra justo despues
    de un deploy (o de un reciclado por --max-requests) no paga el costo
    de establecer la conexion desde cero, que en produccion a veces se
    queda colgado (ver el comentario de _serializar_conexiones en
    db_config.py). Si falla, no bloquea el arranque: la conexion se
    intentara de nuevo en la primera peticion real, como antes.
    """
    try:
        import db_config
        import sqlalchemy as sa
        with db_config.get_engine().connect() as conn:
            conn.execute(sa.text("SELECT 1"))
        worker.log.info("Conexion a BD precalentada OK")
    except Exception as e:
        worker.log.warning(f"Precalentar conexion a BD fallo (se reintentara en la primera peticion): {e}")
