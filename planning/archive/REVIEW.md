# Change Review

## Findings

### [P1] Do not publish a quick start that cannot run — `README.md:18`

The documented first command fails because `.env.example` is not present, and the next command fails because there is no `scripts/` directory or `start_mac.sh`/`start_windows.ps1`. The repository also has no `Dockerfile` or application source from which the claimed container could be built. As a result, a user following the primary setup path cannot start the project at all. Either add the referenced runnable artifacts in the same change or describe this repository as a specification/scaffold and remove the quick-start claims until they are implemented.

### [P2] Make the project layout match the repository — `README.md:41`

The layout documents `frontend/` and `scripts/`, but neither path exists; the tracked placeholder is named `fontend/`. Likewise, `backend/` and `test/` contain only `.gitkeep`, so describing them as a FastAPI app and Playwright suite is misleading. Update the README to reflect the current scaffold (and call out the `fontend/` typo), or rename/populate the directories before documenting them as implemented components.

### [P2] Remove test commands for test suites that do not exist — `README.md:49`

There is no Python project/test configuration, frontend package, or `test/docker-compose.test.yml` in the repository, so none of the three advertised test workflows can be executed. This gives contributors no valid verification path and makes the implementation status appear further along than it is. Document only checks that exist, or explicitly label these as planned testing approaches and point readers to `planning/PLAN.md`.
