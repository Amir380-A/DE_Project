provider "aws" {
  region = "us-east-1"
}

resource "random_id" "suffix" {
  byte_length = 4
}

# S3 Buckets
resource "aws_s3_bucket" "raw" {
  bucket        = "data-raw-${random_id.suffix.hex}"
  force_destroy = true
}

resource "aws_s3_bucket" "processed" {
  bucket        = "data-processed-${random_id.suffix.hex}"
  force_destroy = true
}
resource "aws_s3_bucket" "validation" {
  bucket        = "data-validation-${random_id.suffix.hex}"
  force_destroy = true
}
# IAM Role for Glue
resource "aws_iam_role" "glue_role" {
  name = "glue-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Action = "sts:AssumeRole",
      Effect = "Allow",
      Principal = {
        Service = "glue.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_policy" "glue_s3_policy" {
  name = "glue-s3-policy"
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Effect = "Allow",
      Action = ["s3:*"],
      Resource = [
        "arn:aws:s3:::${aws_s3_bucket.raw.bucket}",
        "arn:aws:s3:::${aws_s3_bucket.raw.bucket}/*",
        "arn:aws:s3:::${aws_s3_bucket.processed.bucket}",
        "arn:aws:s3:::${aws_s3_bucket.processed.bucket}/*",
        "arn:aws:s3:::${aws_s3_bucket.validation.bucket}",
        "arn:aws:s3:::${aws_s3_bucket.validation.bucket}/*"
        
      ]
    }]
  })
}

resource "aws_iam_role_policy_attachment" "attach_glue_policy" {
  role       = aws_iam_role.glue_role.name
  policy_arn = aws_iam_policy.glue_s3_policy.arn
}

# Glue Catalog Database
resource "aws_glue_catalog_database" "processed_db" {
  name = "processed_db"
}



# IAM Role for Redshift COPY/UNLOAD
resource "aws_iam_role" "redshift_copy_role" {
  name = "redshift-copy-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Effect = "Allow",
      Principal = {
        Service = "redshift-serverless.amazonaws.com"
      },
      Action = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_policy" "redshift_s3_full_policy" {
  name = "redshift-s3-full-access"
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Effect = "Allow",
      Action = ["s3:*"],
      Resource = [
        "arn:aws:s3:::${aws_s3_bucket.raw.bucket}",
        "arn:aws:s3:::${aws_s3_bucket.raw.bucket}/*",
        "arn:aws:s3:::${aws_s3_bucket.processed.bucket}",
        "arn:aws:s3:::${aws_s3_bucket.processed.bucket}/*",
        "arn:aws:s3:::${aws_s3_bucket.validation.bucket}",
        "arn:aws:s3:::${aws_s3_bucket.validation.bucket}/*"
      ]
    }]
  })
}

resource "aws_iam_role_policy_attachment" "attach_redshift_policy" {
  role       = aws_iam_role.redshift_copy_role.name
  policy_arn = aws_iam_policy.redshift_s3_full_policy.arn
}

# Redshift Serverless Namespace
resource "aws_redshiftserverless_namespace" "main" {
  namespace_name      = "analytics"
  admin_username      = "admin"
  admin_user_password = "StrongPassword123!"

  iam_roles = [aws_iam_role.redshift_copy_role.arn]
}

# Redshift Serverless Workgroup
resource "aws_redshiftserverless_workgroup" "main" {
  workgroup_name      = "analytics-workgroup"
  namespace_name      = aws_redshiftserverless_namespace.main.namespace_name
  publicly_accessible = true
}
resource "null_resource" "create_redshift_schema" {
  provisioner "local-exec" {
    command = <<EOT
aws redshift-data execute-statement \
  --workgroup-name ${aws_redshiftserverless_workgroup.main.workgroup_name} \
  --database ${aws_redshiftserverless_namespace.main.namespace_name} \
  --sql "CREATE SCHEMA IF NOT EXISTS dwh;" \
  --region us-east-1
EOT
  }

  depends_on = [aws_redshiftserverless_workgroup.main]
}



# IAM User with Admin Access
resource "aws_iam_user" "admin_user" {
  name           = "super-admin"
  force_destroy  = true
  tags = {
    Purpose = "Full admin access with console and API access"
  }
}

resource "aws_iam_user_policy_attachment" "admin_access" {
  user       = aws_iam_user.admin_user.name
  policy_arn = "arn:aws:iam::aws:policy/AdministratorAccess"
}

resource "aws_iam_access_key" "admin_key" {
  user = aws_iam_user.admin_user.name
}

# Let AWS generate console password (no manual password allowed)
resource "aws_iam_user_login_profile" "admin_login" {
  user = aws_iam_user.admin_user.name
}

# IAM Role for Lambda Function
resource "aws_iam_role" "lambda_role" {
  name = "lambda-execution-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Action = "sts:AssumeRole",
      Effect = "Allow",
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
  })
}

# IAM Policy for Lambda to Access S3 Buckets
resource "aws_iam_policy" "lambda_s3_policy" {
  name = "lambda-s3-access"
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:ListBucket"
        ],
        Resource = [
          "arn:aws:s3:::${aws_s3_bucket.raw.bucket}",
          "arn:aws:s3:::${aws_s3_bucket.raw.bucket}/*",
          "arn:aws:s3:::${aws_s3_bucket.processed.bucket}",
          "arn:aws:s3:::${aws_s3_bucket.processed.bucket}/*",
          "arn:aws:s3:::${aws_s3_bucket.validation.bucket}",
          "arn:aws:s3:::${aws_s3_bucket.validation.bucket}/*"
        ]
      }
    ]
  })
}

# Attach Policy to Lambda Role
resource "aws_iam_role_policy_attachment" "lambda_policy_attachment" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = aws_iam_policy.lambda_s3_policy.arn
}

