# HACS default store submission

Checklist for [including this repo in HACS default](https://www.hacs.xyz/docs/publish/include/):

## Repository (done in this repo)

- [x] Public GitHub repository: `ZL1LAC/homeassistant-fnb58`
- [x] Structure: `custom_components/fnb58/`
- [x] `hacs.json` at repository root
- [x] `manifest.json` with `documentation`, `issue_tracker`, `codeowners`, `version`
- [x] `icon.png` in the integration directory
- [x] README and MIT `LICENSE`
- [x] GitHub Actions: Hassfest + HACS validation (`.github/workflows/`)
- [x] GitHub release published (use latest tag)

## GitHub repository settings (you)

- [ ] Repository **description** set (e.g. “Home Assistant integration for FNIRSI FNB58 USB Fast Charge Tester (BLE)”)
- [ ] **Issues** enabled
- [ ] **Topics**: `home-assistant`, `homeassistant`, `hacs`, `hacs-integration`, `fnirsi`, `fnb58`, `bluetooth`

## Pull request to `hacs/default`

1. Fork https://github.com/hacs/default (branch from `master`, not `main`).
2. Edit `integration` and add this line **in alphabetical order** (after `yunusp01/auto_utility_meter`, before `ZacheryThomas/homeassistant-smartrent`):

   ```json
   "ZL1LAC/homeassistant-fnb58",
   ```

3. Open a PR from your fork with a short description and link to this repo.
4. Ensure **Hassfest** and **HACS** actions pass on `homeassistant-fnb58` before or when the PR is reviewed.

After merge, the integration appears in HACS default on the next scheduled scan (can take several hours).
