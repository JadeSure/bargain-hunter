output "lambda_function_name" {
  description = "Name of the deployed Lambda. Invoke manually with: aws lambda invoke --function-name <name> /dev/stdout"
  value       = aws_lambda_function.hunt.function_name
}

output "lambda_function_arn" {
  value = aws_lambda_function.hunt.arn
}

output "state_bucket" {
  description = "S3 bucket holding pipeline state. Seed it from the daily git snapshot before first real run."
  value       = aws_s3_bucket.state.bucket
}

output "state_prefix" {
  value = var.state_prefix
}

output "schedule_name" {
  value = aws_scheduler_schedule.hunt.name
}

output "schedule_enabled" {
  description = "Whether the 5-minute failover schedule is currently active."
  value       = var.schedule_enabled
}

output "log_group" {
  value = aws_cloudwatch_log_group.lambda.name
}
