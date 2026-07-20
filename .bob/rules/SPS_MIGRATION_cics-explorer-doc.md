# IBM Cloud SPS Migration Guide - CICS Explorer Documentation

## Overview

This document describes the migration from Jenkins to IBM Cloud Secure Pipeline Service (SPS) for the CICS Explorer Documentation build pipeline.

## Important Lessons Learned

### 1. Image Selection
- **Always use `pipeline-base-ubi:latest`** for standard builds (not `csso-image-sign`)
- Only use `csso-image-sign` image when artifact signing is explicitly required
- This project does NOT require signing (verified in build.gradle and original Jenkinsfile)

### 2. Variable Naming Conventions
- Use **`goals`** instead of `tasks` for Gradle build commands
- This matches the standard convention used across CICS projects (e.g., cics-cm-plugin)

### 3. Pipeline Detection
- Use `get_env pipeline_namespace` to detect CI vs PR pipelines
- CI pipelines have namespace containing "ci"
- Use `get_env branch` to get the current branch name

### 4. Build Behavior
- **Original Jenkins**: Both main and explorer55 published to Artifactory
- **SPS Migration**: Must maintain same behavior - both branches publish to Artifactory
- PR builds: Only build locally, no Artifactory publish

### 5. Java Version
- DITA-OT requires Java 8
- Use IBM Semeru OpenJDK 8 (same as cics-exec-utility-library)
- Download and configure in setup.sh before running Gradle

### 6. Secrets Management
- Use `get_env` function to fetch secrets (not CLI scripts)
- Export as `ORG_GRADLE_PROJECT_*` environment variables
- Maps to Gradle properties: `artifactory_user` and `artifactory_password`

## Migration Summary

### Previous Setup (Jenkins)
- **Build System**: Jenkins hosted at `zsystems-zeus-jenkins.swg-devops.com`
- **Build Tool**: Gradle with DITA-OT plugins
- **Artifact Repository**: Artifactory (`eu.artifactory.swg-devops.com`)
- **Notifications**: Slack (#cics-explorer-monitoring)
- **Secrets Management**: IBM Secrets Manager via CLI script

### New Setup (IBM Cloud SPS)
- **Build System**: IBM Cloud Secure Pipeline Service
- **Build Tool**: Gradle (unchanged)
- **Artifact Repository**: Artifactory (unchanged)
- **Notifications**: Integrated via SPS
- **Secrets Management**: IBM Secrets Manager via `get_env` function

## Files Created

### 1. `.pipeline-config-ci.yaml`
Main CI/CD pipeline configuration for builds on `main` and `explorer55` branches.

**Key Features:**
- Runs detect-secrets scan for security
- Builds and publishes documentation to Artifactory
- Uses CISO artifact signing
- Runs on protected branches (main, explorer55)

### 2. `.pipeline-config-pr.yaml`
Pull request pipeline configuration for validation builds.

**Key Features:**
- Runs detect-secrets scan
- Builds documentation without publishing
- Validates changes before merge
- Faster feedback for developers

### 3. `.pipeline-scan-config.yaml`
Security and compliance scanning pipeline configuration.

**Key Features:**
- Runs detect-secrets scan for security
- Performs static code analysis
- Executes compliance checks
- Can be triggered on-demand or scheduled
- Does not build artifacts (scan-only pipeline)

### 4. `scripts/setup.sh`
Environment setup script that:
- Fetches Artifactory credentials from IBM Secrets Manager
- Configures Gradle properties
- Validates Java environment

### 5. `scripts/build.sh`
Build execution script that:
- Accepts build type parameter (`build` or `publish`)
- Runs appropriate Gradle tasks
- Provides clear logging

## Configuration Requirements

### IBM Cloud SPS Toolchain Setup

1. **Create SPS Toolchain** in IBM Cloud
   - Navigate to IBM Cloud DevOps
   - Create new toolchain with SPS template
   - Connect to GitHub repository: `github.ibm.com/CICS/cics-explorer-docs`

2. **Configure Repository Integration**
   - Add GitHub Enterprise integration
   - Set repository URL: `https://github.ibm.com/CICS/cics-explorer-docs.git`
   - Configure webhook for automatic triggers

3. **Configure Secrets in IBM Secrets Manager**
   
   Required secrets:
   - `artif_user_value`: Artifactory username
   - `artif_token_value`: Artifactory password/token
   
   The secret ID `bdec0030-aeb4-a040-72ec-1ff118675fe7` should contain:
   ```json
   {
     "user": "<artifactory-username>",
     "token": "<artifactory-token>"
   }
   ```

4. **Configure Pipeline Triggers**
   - **CI Pipeline** (`.pipeline-config-ci.yaml`):
     - Trigger on push to `main` branch
     - Trigger on push to `explorer55` branch
   
   - **PR Pipeline** (`.pipeline-config-pr.yaml`):
     - Trigger on pull request creation
     - Trigger on pull request updates

### Environment Variables

The following environment variables are automatically available in SPS:

| Variable | Description | Source |
|----------|-------------|--------|
| `WORKSPACE` | Build workspace directory | SPS |
| `APP_REPO_FOLDER` | Repository folder name | SPS |
| `GIT_BRANCH` | Current branch name | SPS |
| `GIT_COMMIT` | Current commit SHA | SPS |
| `artif_user_value` | Artifactory username | Secrets Manager |
| `artif_token_value` | Artifactory token | Secrets Manager |

### Gradle Properties

The setup script exports these Gradle properties:
- `ORG_GRADLE_PROJECT_artifactory_user`: Artifactory username
- `ORG_GRADLE_PROJECT_artifactory_password`: Artifactory password

These map to the `artifactory_user` and `artifactory_password` properties used in `build.gradle`.

## Build Process

### CI Build (main/explorer55 branches)
1. **Code Checks**: Detect secrets scan
2. **Setup**: Configure environment and fetch secrets
3. **Build**: Run Gradle build with artifact signing
4. **Publish**: Push artifacts to Artifactory
5. **Notify**: Send status to Slack (if configured)

### PR Build
1. **Code Checks**: Detect secrets scan
2. **Setup**: Configure environment and fetch secrets
3. **Build**: Run Gradle build (no publish)
4. **Validate**: Ensure build succeeds

## Differences from Jenkins

### What Changed
1. **Pipeline Definition**: YAML-based instead of Jenkinsfile
2. **Secrets Access**: Using `get_env` function instead of CLI script (`/home/jenkins/secretsmanagercli.sh`)
3. **Build Scripts**: Separated into `setup.sh` and `build.sh` for modularity
4. **Java Setup**: Automated Java 8 download and configuration in setup.sh
5. **Security Scanning**: Built-in detect-secrets, static-scan, and compliance-checks
6. **Pipeline Detection**: Uses `pipeline_namespace` instead of branch-based logic

### What Stayed the Same
1. **Build Tool**: Gradle with same goals (clean publishToMavenLocal artifactoryPublish)
2. **Artifact Repository**: Same Artifactory instance (eu.artifactory.swg-devops.com)
3. **Build Output**: Same documentation artifacts (com.ibm.cics.core.help)
4. **Branch Strategy**: Same protected branches (main, explorer55) both publish to Artifactory
5. **No Signing**: Original Jenkins had no signing, SPS also has no signing

## Testing the Migration

### Before Going Live

1. **Test PR Pipeline**:
   ```bash
   # Create a test branch
   git checkout -b test/sps-migration
   
   # Make a small change
   echo "# Test" >> test.md
   git add test.md
   git commit -m "Test SPS pipeline"
   git push origin test/sps-migration
   
   # Create PR and verify build runs
   ```

2. **Verify Secrets Access**:
   - Check that Artifactory credentials are fetched correctly
   - Verify build can authenticate to Artifactory

3. **Test Build Output**:
   - Verify documentation is built correctly
   - Check artifact structure matches previous builds

### After Migration

1. **Monitor First Builds**:
   - Watch CI builds on main/explorer55
   - Verify artifacts are published to Artifactory
   - Check Slack notifications (if configured)

2. **Validate PR Builds**:
   - Ensure PR builds run on every PR
   - Verify build feedback is timely

## Rollback Plan

If issues occur, you can temporarily revert to Jenkins:

1. Keep the Jenkinsfile in the repository
2. Re-enable Jenkins webhook in GitHub
3. Disable SPS triggers
4. Investigate and fix SPS issues
5. Re-enable SPS when ready

## Slack Notifications

To enable Slack notifications in SPS:

1. Configure Slack integration in SPS toolchain
2. Add Slack webhook URL to toolchain
3. Configure notification rules in SPS UI
4. Test notifications with a build

## Support and Resources

- **IBM Cloud SPS Documentation**: https://cloud.ibm.com/docs/devsecops
- **CICS Explorer Team**: #cics-explorer-monitoring (Slack)
- **Aqua Release Train**: https://ibm.box.com/s/ch49vm90n29upxqw7l42oj8u7dni0scm

## Troubleshooting

### Build Fails with "get_env: command not found"
- Ensure you're using the correct SPS base image
- Verify the image includes the SPS helper functions

### Artifactory Authentication Fails
- Check Secrets Manager configuration
- Verify secret ID is correct
- Ensure credentials have proper permissions

### Build Succeeds but Artifacts Not Published
- Verify branch name matches `main` or `explorer55`
- Check Artifactory repository permissions
- Review build logs for publish step

### Detect-Secrets Scan Fails
- Review the secrets baseline file
- Update `.secrets.baseline` if needed
- Ensure no actual secrets are committed

## Next Steps

1. ✅ Create pipeline configuration files
2. ✅ Create build scripts
3. ⏳ Configure SPS toolchain in IBM Cloud
4. ⏳ Test PR pipeline
5. ⏳ Test CI pipeline on test branch
6. ⏳ Enable for main/explorer55 branches
7. ⏳ Disable Jenkins webhook
8. ⏳ Monitor first production builds

## Reference Implementations

This migration follows patterns from multiple CICS repositories:

1. **cics-exec-utility-library** (`/Users/anushka/git/cics-exec-utility-library`)
   - Java 8 setup in setup.sh
   - Pipeline namespace detection
   - Secrets management with get_env

2. **cics-cm-plugin** (`/Users/anushka/git/cics-cm-plugin`)
   - Use of "goals" variable naming convention
   - Pipeline-aware build logic

## Key Decisions Made During Migration

1. **No Artifact Signing**: Verified that original Jenkins setup had no signing, and build.gradle has no signing configuration. Therefore, removed CISO signing from SPS pipeline.

2. **Both Branches Publish**: Original Jenkins published both main and explorer55 to Artifactory. Maintained this behavior in SPS (not just main).

3. **Image Selection**: Changed from `csso-image-sign` to `pipeline-base-ubi` since no signing is needed.

4. **Variable Naming**: Changed from "tasks" to "goals" to match CICS project conventions.

5. **Java Version**: Java 8 required for DITA-OT compatibility. Using IBM Semeru OpenJDK 8u322-b06.

## Common Pitfalls to Avoid

1. ❌ Don't use `csso-image-sign` unless signing is actually needed
2. ❌ Don't use nested if statements when AND operators are clearer
3. ❌ Don't use version-specific image tags (e.g., 3.61) - use `latest`
4. ❌ Don't assume branch-specific behavior without checking original Jenkins
5. ❌ Don't use `GIT_BRANCH` - use `get_env branch` instead
6. ❌ Don't forget to make scripts executable with `chmod +x`