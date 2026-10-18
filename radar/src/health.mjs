// Bounded and credential-free diagnostics for GitHub Actions.
// This cannot detect a permanently stopped scheduler on its own; it flags gaps when Cron resumes.
export function safeDiagnosticError(error){
  const raw=String(error?.message||'');
  // Only two fixed spreadsheet labels, HTTP codes and allowlisted Google
  // API reasons may reach public workflow logs. Reject arbitrary text.
  const statusPattern=/^(?:OK|(?:HTTP[45][0-9]{2}|FAILED):(?:PERMISSION_DENIED|UNAUTHENTICATED|RESOURCE_EXHAUSTED|NOT_FOUND|ACCESS_TOKEN_SCOPE_INSUFFICIENT|insufficientPermissions|rateLimitExceeded|accessNotConfigured|forbidden|UNCLASSIFIED))$/;
  const structured=/^Radar Sheets preflight failed register=(\S+) radar=(\S+)$/.exec(raw);
  if(structured&&statusPattern.test(structured[1])&&statusPattern.test(structured[2]))
    return raw.slice(0,210);
  if(/^Google OAuth HTTP [45]\d\d$/.test(raw) ||
     /^Sheets (read|update|clear) HTTP [45]\d\d$/.test(raw) ||
     /^Public API HTTP [45]\d\d$/.test(raw) ||
     /^(Missing required Worker bindings or secrets|Missing required bindings or secrets|Missing Google Sheets service account secret|Invalid candidate limit|Invalid Google OAuth scope|Radar is not in a read-only transition state|Radar State baseline unavailable|Duplicate identity in Radar history|Duplicate source ID in live register|No active registered source pair|Invalid radar review state|Invalid or duplicate review observation|Duplicate review official URL|Conflicting radar identity in durable state|Conflicting radar review replay|Radar review state capacity reached|Spreadsheet header mismatch: stop before dedupe or writes|No active ATS\+employer source pairs|Source exceeds safe job limit|Source payload too large|Unexpected public jobs payload|Unexpected ATS job host: source contract changed)$/.test(raw))
    return raw.slice(0,110);
  if(/^Public API fetch (?:timeout_or_network|malformed_result|response_too_large|rate_limited|upstream_transient|blocked_or_auth_required|other_technical_failure|http_error)$/.test(raw) ||
     (['Public API contract mismatch','Public API adapter internal failure'].includes(raw) ||
      /^Public API contract (?:schema|job_url|job_url_malformed|job_url_uk_apex|job_url_untrusted_host|normalized_role|other)$/.test(raw)))
    return raw;
  // These are fixed internal discovery status labels; never print provider bodies.
  if(['Public discovery adapter failed','Unexpected public discovery payload',
      'Radar discovery source metadata unavailable','Invalid live discovery policy',
      'Invalid live discovery source class','Invalid bounded discovery scope',
      'Invalid public discovery source contract',
      'Missing approved public discovery adapters'].includes(raw))
    return raw;
  return 'Unexpected runtime failure';
}
