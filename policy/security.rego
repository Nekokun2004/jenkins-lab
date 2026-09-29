package security

import rego.v1

deny contains msg if {
    input.metadata.vulnerabilities.critical > 0
    msg := sprintf("Blocked: %d CRITICAL vulnerabilities found", [input.metadata.vulnerabilities.critical])
}

default allow := false

allow if {
    count(deny) == 0
}
