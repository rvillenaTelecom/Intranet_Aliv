# Módulo de compatibilidad — re-exporta desde Carga_SQL para que
# todos los scripts que hacen "from db_config import ..." sigan funcionando.
from Carga_SQL import get_engine, upload_to_sql, upload_incremental_to_sql
