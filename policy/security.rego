package security

deny[msg] {
    input.metadata.vulnerabilities.critical > 0
    msg := sprintf("Blocked: %d CRITICAL vulnerabilities found", [input.metadata.vulnerabilities.critical])
}

default allow = false

allow {
    count(deny) == 0
}
