"""What this build is, so a deployed instance can say what it is running.

Offline installations receive versioned, prebuilt images. Every update takes
a full backup before startup migrations. Bump RELEASE for each delivery and
SCHEMA_REVISION when the schema or data migration sequence changes.
"""

RELEASE = "2.11.1"

# Raised whenever models.py gains a table, column or index, or a migration
# step is added. Health checks report it alongside the applied migrations.
SCHEMA_REVISION = 14

# A short diagnostic note for the health endpoint.
RELEASE_NOTE = "Кадровые действия, сроки контрактов, звания, поощрения и расчёт стажа"
