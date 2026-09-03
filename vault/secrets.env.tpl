{{- with secret "secret/data/horragor/api" -}}
JWT_SECRET_KEY={{ .Data.data.jwt_secret_key }}
GROQ_API_KEY={{ .Data.data.groq_api_key }}
SUPABASE_DB_URL={{ .Data.data.supabase_db_url }}
{{ end -}}
{{- with secret "secret/data/horragor/langfuse" -}}
SALT={{ .Data.data.salt }}
ENCRYPTION_KEY={{ .Data.data.encryption_key }}
NEXTAUTH_SECRET={{ .Data.data.nextauth_secret }}
CLICKHOUSE_PASSWORD={{ .Data.data.clickhouse_password }}
REDIS_AUTH={{ .Data.data.redis_auth }}
MINIO_ROOT_PASSWORD={{ .Data.data.minio_root_password }}
LANGFUSE_S3_EVENT_UPLOAD_SECRET_ACCESS_KEY={{ .Data.data.minio_root_password }}
LANGFUSE_S3_MEDIA_UPLOAD_SECRET_ACCESS_KEY={{ .Data.data.minio_root_password }}
{{ end -}}
{{- with secret "secret/data/horragor/monitoring" -}}
GF_SECURITY_ADMIN_PASSWORD={{ .Data.data.grafana_admin_password }}
{{ end -}}
