# Security Policy

Eclipse Ditto follows the [Eclipse Vulnerability Reporting Policy](https://www.eclipse.org/security/policy/).  
Vulnerabilities are tracked by the Eclipse security team, in cooperation with the Ditto project leads.
Fixing vulnerabilities is taken care of by the Ditto project committers, with assistance and guidance of the security team.

## How To Report a Vulnerability

If you think you have found a vulnerability in this repository, please report it to us through coordinated disclosure.

**Please do not report security vulnerabilities through public issues, discussions, or change requests.**

Instead, report it using one of the following ways:

* Create a [confidential issue](https://gitlab.eclipse.org/security/vulnerability-reports/-/issues/new?issuable_template=new_vulnerability) in the Eclipse Foundation Vulnerability Reporting Tracker

You can find more information about reporting and disclosure at the [Eclipse Foundation Security page](https://www.eclipse.org/security/).

Please include as much of the information listed below as you can to help us better understand and resolve the issue:

* The type of issue (e.g., credential leakage, token handling, or command injection)
* Affected version(s)
* Impact of the issue, including how an attacker might exploit the issue
* Step-by-step instructions to reproduce the issue
* The location of the affected source code (tag/branch/commit or direct URL)
* Full paths of source file(s) related to the manifestation of the issue
* Configuration required to reproduce the issue
* Log files that are related to this issue (if possible)
* Proof-of-concept or exploit code (if possible)

This information will help us triage your report more quickly.

## Supported Versions

dittoctl is in early development. Until 1.0, only the latest release receives security updates.

| Version          | Supported          |
|------------------|--------------------|
| latest 0.x       | :white_check_mark: |
| older 0.x        | :x:                |
