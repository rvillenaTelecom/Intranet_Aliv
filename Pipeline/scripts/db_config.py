# Módulo de compatibilidad — re-exporta desde Carga_SQL_to_Render para que
# todos los scripts que hacen "from db_config import ..." sigan funcionando.
from Carga_SQL_to_Render import get_engine, upload_to_sql, upload_incremental_to_sql
