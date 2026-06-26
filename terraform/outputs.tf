output "worker_name" {
  value       = cloudflare_workers_script.feedback.script_name
  description = "Set FEEDBACK_BASE_URL to https://<worker_name>.<your-subdomain>.workers.dev"
}

output "portal_worker_url" {
  value       = "https://${var.portal_worker_name}.${var.cloudflare_account_id}.workers.dev"
  description = "Portal API base URL. Set as NEXT_PUBLIC_API_URL in the frontend."
}

output "portal_kv_namespace_id" {
  value       = cloudflare_workers_kv_namespace.portal_sessions.id
  description = "KV namespace ID — paste into portal-worker/wrangler.jsonc."
}

output "pages_url" {
  value       = "https://${var.pages_project_name}.pages.dev"
  description = "Cloudflare Pages production URL. Set as TF_VAR_frontend_url in CI."
}
