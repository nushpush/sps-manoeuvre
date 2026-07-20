# IBM Cloud SPS Build Configuration

This repository uses IBM Cloud Secure Pipeline Service (SPS) for CI/CD builds.

## Quick Reference

### Pipeline Files
- [`.pipeline-config-ci.yaml`](.pipeline-config-ci.yaml) - CI builds for `main` and `explorer55` branches
- [`.pipeline-config-pr.yaml`](.pipeline-config-pr.yaml) - PR validation builds
- [`.pipeline-scan-config.yaml`](.pipeline-scan-config.yaml) - Security and compliance scanning pipeline
- [`scripts/setup.sh`](scripts/setup.sh) - Environment setup and secrets fetching
- [`scripts/build.sh`](scripts/build.sh) - Build execution script

### Build Behavior

| Branch | Pipeline | Actions |
|--------|----------|---------|
| `main` | CI | Build + Publish to Artifactory |
| `explorer55` | CI | Build + Publish to Artifactory |
| PR branches | PR | Build only (no publish) |

**Note**: Both main and explorer55 branches publish to Artifactory, matching the original Jenkins behavior.

### Required Secrets

Configure these in IBM Secrets Manager (Secret ID: `bdec0030-aeb4-a040-72ec-1ff118675fe7`):

| Secret Key | Description | Used By |
|------------|-------------|---------|
| `artif_user_value` | Artifactory username | [`setup.sh`](scripts/setup.sh:14) |
| `artif_token_value` | Artifactory token/password | [`setup.sh`](scripts/setup.sh:15) |

### Environment Variables

SPS automatically provides:

| Variable | Description | Example |
|----------|-------------|---------|
| `WORKSPACE` | Build workspace directory | `/workspace` |
| `APP_REPO_FOLDER` | Repository folder name | `cics-explorer-docs` |
| `GIT_BRANCH` | Current branch | `main` |
| `GIT_COMMIT` | Current commit SHA | `abc123...` |

### Build Commands

The build process uses Gradle with pipeline-aware logic:

```bash
# The build script automatically detects pipeline type
source scripts/build.sh

# Internally it runs:
# - PR builds: ./gradlew clean publishToMavenLocal --info
# - CI builds: ./gradlew clean publishToMavenLocal artifactoryPublish --info
```

**Pipeline Detection**: Uses `get_env pipeline_namespace` to detect CI vs PR pipelines.

### Artifactory Configuration

Artifacts are published to:
- **Repository**: `zeus-rc-local`
- **URL**: `https://eu.artifactory.swg-devops.com/artifactory`
- **Artifact**: `com.ibm.cics.core.help:help:jar` (version from [`build.gradle`](build.gradle:13))

### Local Testing

To test the build scripts locally:

```bash
# Set up environment (requires IBM Cloud credentials)
export artif_user_value="your-username"
export artif_token_value="your-token"

# Run setup
source scripts/setup.sh

# Run build (without publish)
source scripts/build.sh build

# Run build with publish (for testing)
source scripts/build.sh publish
```

### Migration Notes

This repository was migrated from Jenkins to IBM Cloud SPS. For detailed migration information, see the Bob rules directory: `/Users/anushka/.bob/rules/SPS_MIGRATION_cics-explorer-doc.md`

### Important Notes

1. **No Artifact Signing**: This project does not use artifact signing (verified in build.gradle and original Jenkins setup)
2. **Java 8 Required**: DITA-OT requires Java 8 - automatically downloaded in setup.sh
3. **Variable Convention**: Uses "goals" instead of "tasks" for Gradle commands (CICS standard)
4. **Image Selection**: Uses `pipeline-base-ubi:latest` (not csso-image-sign) since no signing is needed

### Support

- **Team Channel**: #cics-explorer-monitoring (Slack)
- **SPS Documentation**: https://cloud.ibm.com/docs/devsecops
- **Aqua Release Train**: https://ibm.box.com/s/ch49vm90n29upxqw7l42oj8u7dni0scm