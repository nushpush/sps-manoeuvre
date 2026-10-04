# SPS Commons Internals Reference

This document maps every `/opt/commons/` script call you see in `.pipeline-config.yaml` files to its actual source in the IBM One Pipeline compliance repositories, explains what it does, what `get_env` properties control it, and what secrets it needs.

**Source repositories:**
- Scripts: [github.ibm.com/one-pipeline/compliance-commons-internal](https://github.ibm.com/one-pipeline/compliance-commons-internal)
- Pipeline definitions: [github.ibm.com/one-pipeline/compliance-pipelines](https://github.ibm.com/one-pipeline/compliance-pipelines)

---

## How it all connects

When SPS builds a pipeline image, it clones specific folders from `compliance-commons-internal` (and the public `compliance-commons`) into `/opt/commons/` inside the image. The `defaults/defaults.yaml` in `compliance-pipelines` defines exactly which folders are cloned for each stage and at which commit SHA.

```
.pipeline-config.yaml (your repo)
    │
    │  script: /opt/commons/detect-secrets/run_scan.sh
    │
    ▼
/opt/commons/                          ← cloned at image build time
├── detect-secrets/run_scan.sh         ← from compliance-commons (public)
├── static-scan/run.sh                 ← from compliance-commons-internal
├── mend/mend-sca.sh                   ← from compliance-commons-internal
├── scan-artifact/scan.sh              ← from compliance-commons-internal
├── ciso/sign_artifacts.sh             ← from compliance-commons-internal
├── ciso/sign_icr.sh                   ← from compliance-commons-internal
├── verify-artifact/verify_artifact_sign.sh  ← from compliance-commons-internal
└── compliance-checks/run.sh           ← from compliance-commons-internal
```

The SPS helper variable `COMMONS_PATH` always points to `/opt/commons`. Scripts reference each other as `${COMMONS_PATH}/mend/mend-sca.sh` etc.

`ONE_PIPELINE_PATH` points to the core SPS pipeline tools (pipelinectl, `get_env`, `get_secret`, `load_repo`, `save_artifact`, etc.).

---

## Stage → script mapping

| `.pipeline-config.yaml` script call | Source file in compliance-commons-internal | Stage it belongs to |
|---|---|---|
| `/opt/commons/detect-secrets/run_scan.sh` | `detect-secrets/run_scan.sh` (public commons) | `code-checks` / `pr-code-checks` |
| `/opt/commons/static-scan/run.sh` | `static-scan/run.sh` | `code-checks` / `pr-code-checks` |
| `/opt/commons/compliance-checks/run.sh` | `compliance-checks/run.sh` | `code-checks` / `pr-code-checks` |
| `/opt/commons/scan-artifact/scan.sh` | `scan-artifact/scan.sh` | `scan-artifact` |
| `/opt/commons/ciso/sign_artifacts.sh` | `ciso/sign_artifacts.sh` | `deploy-checks` (signing step) |
| `/opt/commons/ciso/sign_icr.sh` | `ciso/sign_icr.sh` | `deploy-checks` (image signing) |
| `/opt/commons/ciso/sign_artifactory.sh` | `ciso/sign_artifactory.sh` | `deploy-checks` (Artifactory image signing) |
| `/opt/commons/verify-artifact/verify_artifact_sign.sh` | `verify-artifact/verify_artifact_sign.sh` | `deploy-checks` (verification) |
| `/opt/commons/verify-artifact/verify_icr_sign.sh` | `verify-artifact/verify_icr_sign.sh` | `deploy-checks` (ICR verification) |
| `/opt/commons/mend/mend-sca.sh` | `mend/mend-sca.sh` | `compliance-checks` (opt-in) |
| `/opt/commons/static-scan/run.sh` (with opt-in-sonar) | `static-scan/run.sh` → `sonarqube/sonarqube_run.sh` | `static-scan` |
| `/opt/commons/zap-dast/run_scan.sh` | `zap-dast/run_scan.sh` | `dynamic-scan` (opt-in) |

---

## detect-secrets

**Script:** `detect-secrets/run_scan.sh`  
**Called as:** `/opt/commons/detect-secrets/run_scan.sh`  
**Purpose:** Scans the repository for accidentally committed secrets using the `detect-secrets` tool. Compares against `.secrets.baseline` for known false positives.

**No `get_env` properties required for basic operation.** The `.secrets.baseline` file in the repo controls what is whitelisted.

**Common issue:** If `.secrets.baseline` is missing or stale, the scan fails. Regenerate with:
```bash
detect-secrets scan > .secrets.baseline
```

---

## static-scan

**Script:** `static-scan/run.sh`  
**Called as:** `/opt/commons/static-scan/run.sh`  
**Purpose:** Dispatcher — runs whichever static analysis tools are opted in. By default does nothing unless you set opt-in properties.

**`get_env` properties (all optional — enable the tool you need):**

| Property | Tool enabled |
|---|---|
| `opt-in-sonar` | SonarQube scan |
| `opt-in-gosec` | GoSec (Go security scanner) |
| `opt-in-terraform-fmt-validate` | Terraform format + validate |
| `opt-in-tflint` | TFLint |
| `opt-in-fips-scan` | FIPS 140-2 compliance scan |
| `opt-in-mend-sast` | Mend SAST |

**`get_secret` secrets:**

| Secret | Required for |
|---|---|
| `ibmcloud-api-key` | All tools |
| `ciso-ibmcloud-api-key` | Overrides `ibmcloud-api-key` for container registry interactions |

---

## compliance-checks (Mend SCA)

**Script:** `compliance-checks/run.sh` → internally calls `mend/mend-sca.sh`  
**Called as:** `/opt/commons/compliance-checks/run.sh`  
**Purpose:** Runs Mend SCA (Software Composition Analysis) — dependency vulnerability scanning. Replaces the deprecated CRA (Code Risk Analyzer).

**To enable Mend SCA**, the `opt-in-mend-sca` property must be set to `1` in the pipeline or config. Without it, the compliance-checks step runs but skips Mend.

**`get_env` properties:**

| Property | Description |
|---|---|
| `opt-in-mend-sca` | Set to `1` to enable Mend CLI SCA scan (required) |
| `mend-user-email` | Service user email associated with your product in Mend |
| `mend-product-name` | Product name returned by Mend onboarding |
| `mend-product-token` | Product token from Mend onboarding |
| `mend-server-url` | Mend server base URL |
| `mend-custom-script-path` | Path to a repo script that installs build dependencies before scanning |
| `mend-sca-exclude-dev-dependencies` | `1` to exclude dev dependencies |
| `mend-sca-disabled-pkg-mgr-resolvers` | Comma-separated list of package managers to skip (e.g. `maven,gradle`) |

**`get_secret` secrets:**

| Secret | Description |
|---|---|
| `mend-org-token` | Org token from Mend onboarding |
| `mend-user-key` | Product service user key from Mend onboarding |
| `ibmcloud-api-key` | IBM Cloud API key |

**Evidence collected:**  
tool type: `mend` · evidence type: `com.ibm.code_vulnerability_scan` · asset type: `repo`

---

## scan-artifact

**Script:** `scan-artifact/scan.sh`  
**Called as:** `/opt/commons/scan-artifact/scan.sh`  
**Purpose:** Scans container image artifacts for CVEs. Can invoke Container Image Multi-Scanner (CIMS), Vulnerability Advisor (VA), Sysdig, or JFrog Xray depending on opt-in properties.

**`get_env` properties:**

| Property | Description |
|---|---|
| `opt-in-multiscan` | Enable Container Image Multi-Scanner |
| `sysdig-scan` | `1` to enable Sysdig scan |
| `xray-opt-in` | Any value to enable JFrog Xray scan |
| `xray-api-url` | Artifactory base URL for Xray |
| `xray-watch-name` | Your Xray watch name |

**`get_secret` secrets:**

| Secret | Description |
|---|---|
| `ibmcloud-api-key` | IBM Cloud API key |

---

## ciso/sign_artifacts.sh — Non-image artifact signing (JAR, tar, zip)

**Script:** `ciso/sign_artifacts.sh`  
**Called as:** `/opt/commons/ciso/sign_artifacts.sh`  
**Purpose:** Signs non-image artifacts (tar, zip, JAR files) using GaraSign. Uses GPG client by default; CoSign if `gara-cosign=1`.

**Requires `csso-image-sign:latest` image** — this is the only image that has GaraSign tooling pre-installed.

**`get_env` properties:**

| Property | Description |
|---|---|
| `gara-cosign` | `1` to use CoSign instead of GPG |
| `product-type` | GaraSign product registration type (`prd` for `PRDXXXXX`, `eal` for `EAL-XXX`) |
| `print-code-signing-certificate` | `1` to print GPG public key to console |
| `skip-sign-artifact-type` | Semicolon-separated artifact types to skip signing |

**`get_secret` secrets:**

| Secret | Description |
|---|---|
| `gara-signing-key` | Base64-encoded GaraSign certificate (`client_auth_XXX.pfx`) |
| `gara-signing-credential` | P12 password from the GaraSign credentials bundle |
| `GPGCERTIFICATE` | Only for self-signing — base64-encoded private key |

**Evidence collected:**  
tool type: `ciso-code-signing` · evidence type: `com.ibm.cloud.image_signing` · asset type: `artifact`

---

## ciso/sign_icr.sh — ICR image signing

**Script:** `ciso/sign_icr.sh`  
**Called as:** `/opt/commons/ciso/sign_icr.sh`  
**Purpose:** Signs container images hosted on IBM Container Registry (ICR) using GaraSign via Skopeo (default) or Cosign.

**Requires `csso-image-sign:latest` image.**

**Signing flow:**
1. Loads GaraSign certificate from `gara-signing-key` secret
2. Sets P12 password from `gara-signing-credential`
3. Downloads GPG key and gets fingerprint
4. Signs image using Skopeo + GaraSign PKCS11 library
5. Collects evidence

**`get_env` properties:**

| Property | Description |
|---|---|
| `gara-cosign` | `1` to use CoSign instead of Skopeo |
| `signing-dockerconfigjson` | Docker auth config for multi-registry support |
| `product-type` | GaraSign product registration type |

**`get_secret` secrets:**

| Secret | Description |
|---|---|
| `gara-signing-key` | Base64-encoded GaraSign certificate |
| `gara-signing-credential` | P12 password |

---

## ciso/sign_artifactory.sh — Artifactory image signing

**Script:** `ciso/sign_artifactory.sh`  
**Called as:** `/opt/commons/ciso/sign_artifactory.sh`  
**Purpose:** Signs images hosted on TaaS Artifactory using GaraSign + Skopeo. Creates `/etc/containers/registries.d/artifactory.yaml` for sigstore configuration.

**Requires `csso-image-sign:latest` image.**

Same secrets as `sign_icr.sh`. Additional property:

| Property | Description |
|---|---|
| `artifactory-dockerconfigjson` | Docker auth config for Artifactory registry |

---

## ciso/sign_jar_jarsigner.sh — JAR signing

**Script:** `ciso/sign_jar_jarsigner.sh`  
**Called as:** `/opt/commons/ciso/sign_jar_jarsigner.sh`  
**Purpose:** Signs JAR files using GaraSign + `jarsigner`. Installs OpenJDK 17 if not present. Configures GaraSign PKCS11 library for jarsigner.

**Requires `csso-image-sign:latest` image.**

Same secrets as `sign_artifacts.sh`.

---

## verify-artifact/verify_artifact_sign.sh — Artifact signature verification

**Script:** `verify-artifact/verify_artifact_sign.sh`  
**Called as:** `/opt/commons/verify-artifact/verify_artifact_sign.sh`  
**Purpose:** Verifies signatures of artifacts hosted on TaaS Artifactory. Downloads Private certificate and GPG public key from the evidence locker. Creates `/etc/containers/policy.json` and uses Skopeo to verify.

**`get_env` properties:**

| Property | Description |
|---|---|
| `ibm-certificate-chain` | IBM certificate chain for verification (required) |

---

## verify-artifact/verify_icr_sign.sh — ICR image verification

**Script:** `verify-artifact/verify_icr_sign.sh`  
**Called as:** `/opt/commons/verify-artifact/verify_icr_sign.sh`  
**Purpose:** Verifies signatures of images on IBM Container Registry. Downloads certificate and GPG public key from evidence locker. Creates `/etc/containers/policy.json` and uses Skopeo for verification.

**`get_env` properties:**

| Property | Description |
|---|---|
| `ibm-certificate-chain` | IBM certificate chain for verification (required) |

---

## Where these scripts live at runtime

The `defaults/defaults.yaml` in `compliance-pipelines` specifies the exact commit SHAs at which each folder is cloned. This means the scripts are **pinned to a specific version** when the image is built. When One Pipeline releases a new version, the SHAs are bumped and a new image is built.

This is why the `/opt/commons/` path is stable — the scripts are baked into the image, not fetched at pipeline runtime.

```yaml
# From compliance-pipelines/defaults/defaults.yaml
defaults:
  scan-artifact:
    image: icr.io/continuous-delivery/pipeline/pipeline-base-ubi:3.83
    sources:
      - repo: https://github.ibm.com/one-pipeline/compliance-commons-internal.git
        sha: c52b1d771d44715bc7fd4ea5f9a68276e4517314
        path: scan-artifact
```

---

## Key environment variables available in every SPS step

| Variable | Source | Description |
|---|---|---|
| `COMMONS_PATH` | SPS | Always `/opt/commons` — prefix for all commons script calls |
| `ONE_PIPELINE_PATH` | SPS | Path to pipelinectl and SPS tooling |
| `WORKSPACE` | SPS | Network-mounted PVC — slower, persistent across stages |
| `STAGE_WORKSPACE` | SPS | Local disk — ~3× faster, use for build I/O within a stage |
| `APP_REPO_FOLDER` | SPS | The checked-out repository folder name inside `$WORKSPACE` |
| `STAGE` | SPS | Name of the current stage (e.g. `code-checks`, `deploy-checks`) |
| `PIPELINE_DEBUG` | User-set | Set to `1` to enable `set -x` in all commons scripts |

---

## pipelinectl helpers used by commons scripts

These are the SPS pipeline control functions available in any step using `pipeline-base-ubi` or `csso-image-sign`:

| Function | Description |
|---|---|
| `get_env <key> [default]` | Read a pipeline property (non-secret) |
| `get_secret <key>` | Read a secret from the linked Secrets Manager |
| `set_env <key> <value>` | Write a pipeline property for use in later steps |
| `load_repo <name> <property>` | Get a property of a saved repo (e.g. `load_repo app-repo path`) |
| `save_artifact <name> type=<type> ...` | Register an artifact for scanning/signing |
| `load_artifact <name> <property>` | Get a property of a saved artifact |
| `save_file <name> <file>` | Store a file in the pipeline for later steps |
| `load_file <name>` | Retrieve a stored file |

> **Breaking change (deadline 31 Aug 2026):** `get_env` will stop working for secrets. Migrate all secret access to `get_secret <key>`.

---

## Common misconfiguration patterns

| What you see in the config | What it means | Common mistake |
|---|---|---|
| `abort_on_failure: false` on static-scan | Scan runs but failures don't block the pipeline | Often set this way intentionally during onboarding — change to `true` once scan is stable |
| `when: 'false'` on a step | Step is completely disabled | Travis migrants often disable unused steps here rather than removing them — that's fine |
| `include: [dind]` on a task | Docker-in-Docker enabled for the whole task | Required for any step that pulls or runs Docker images (scans, signing) |
| `include: [docker-socket]` on a step | Mounts the Docker socket | Required for steps that need Docker but don't need full DinD |
| `runtimeClassName: large` | Requests a larger Tekton pod | Needed for heavy steps (compliance-checks, scan-artifact, build) |
| Calling `sign_artifacts.sh` with `pipeline-base-ubi` | Signing will fail — GaraSign not present | Must use `csso-image-sign:latest` for any signing step |
| Missing `opt-in-mend-sca: 1` | Mend SCA silently skipped | compliance-checks step runs but does no scanning |
