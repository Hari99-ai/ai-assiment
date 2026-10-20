output "registry" { value = aws_ecr_repository.app.repository_url }
output "cluster" { value = aws_eks_cluster.main.name }
output "database_endpoint" { value = aws_db_instance.postgres.endpoint }
output "redis_endpoint" { value = aws_elasticache_replication_group.redis.primary_endpoint_address }
output "application_secret_arn" { value = aws_secretsmanager_secret.app.arn }
