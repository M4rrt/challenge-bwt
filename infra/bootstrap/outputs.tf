output "state_bucket" {
  description = "Name of the S3 bucket holding the main infra/ Terraform state."
  value       = aws_s3_bucket.terraform_state.id
}

output "lock_table" {
  description = "Name of the DynamoDB table used for state locking."
  value       = aws_dynamodb_table.terraform_lock.name
}
