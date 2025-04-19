# Outputs
output "raw_bucket_name" {
  value = aws_s3_bucket.raw.bucket
}

output "processed_bucket_name" {
  value = aws_s3_bucket.processed.bucket
}
output "validation_bucket_name" {
  value = aws_s3_bucket.validation.bucket
}


output "glue_database_name" {
  value = aws_glue_catalog_database.processed_db.name
}

output "redshift_copy_role_arn" {
  value = aws_iam_role.redshift_copy_role.arn
}

output "admin_user_name" {
  value = aws_iam_user.admin_user.name
}

output "admin_access_key" {
  value     = aws_iam_access_key.admin_key.id
  sensitive = true
}

output "admin_secret_key" {
  value     = aws_iam_access_key.admin_key.secret
  sensitive = true
}

output "admin_password" {
  value     = aws_iam_user_login_profile.admin_login.encrypted_password
  sensitive = true
}

output "redshift_endpoint" {
  value = aws_redshiftserverless_workgroup.main.endpoint
}

output "redshift_admin_username" {
  value = aws_redshiftserverless_namespace.main.admin_username
  sensitive = true
}

output "redshift_admin_password" {
  value     = aws_redshiftserverless_namespace.main.admin_user_password
  sensitive = true
}

