output "worker_name" {
  value       = cloudflare_workers_script.feedback.script_name
  description = "Set FEEDBACK_BASE_URL to https://<worker_name>.<your-subdomain>.workers.dev"
}
