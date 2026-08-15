import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
import yaml

PROJECT_ROOT = Path(__file__).parents[2]
TEST_REVISION = "a" * 40
pytestmark = pytest.mark.skipif(
    os.name == "nt",
    reason="POSIX deployment script execution is validated on the Linux CI runner",
)


def _release(root: Path, release_id: str) -> Path:
    release = root / "releases" / release_id
    release.mkdir(parents=True)
    for name in (
        "compose.yaml",
        "compose.production.yaml",
        "compose.selfhost.yaml",
        "compose.monitoring.yaml",
        "compose.monitoring.production.yaml",
        ".env",
    ):
        (release / name).write_text("name: test\n", encoding="utf-8")
    return release


def test_deploy_script_activates_and_rolls_back_releases(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_docker = fake_bin / "docker"
    fake_docker.write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\n"
        "if [[ ${1:-} == info ]]; then printf '%s\\n' \"$DOCKER_ROOT\"; exit 0; fi\n"
        'printf \'%s\\n\' "$*" >> "$DOCKER_LOG"\n',
        encoding="utf-8",
    )
    fake_docker.chmod(0o755)
    deploy_root = tmp_path / "deploy"
    first = _release(deploy_root, "release-1")
    second = _release(deploy_root, "release-2")
    docker_log = tmp_path / "docker.log"
    env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "DOCKER_LOG": str(docker_log),
        "DOCKER_ROOT": str(tmp_path),
        "MIN_FREE_DISK_MB": "1",
    }
    script = PROJECT_ROOT / "scripts" / "deploy_production.sh"

    subprocess.run(  # noqa: S603
        [str(script), "deploy", str(deploy_root), "release-1"],
        check=True,
        env=env,
    )
    assert (deploy_root / "current").resolve() == first

    subprocess.run(  # noqa: S603
        [str(script), "deploy", str(deploy_root), "release-2"],
        check=True,
        env=env,
    )
    assert (deploy_root / "current").resolve() == second
    assert (deploy_root / ".previous-release").read_text(encoding="utf-8").strip() == str(first)

    subprocess.run(  # noqa: S603
        [str(script), "rollback", str(deploy_root)], check=True, env=env
    )
    assert (deploy_root / "current").resolve() == first
    log = docker_log.read_text(encoding="utf-8")
    assert "compose -f compose.yaml -f compose.production.yaml" in log
    assert "compose.monitoring.production.yaml pull" in log
    assert "compose.monitoring.production.yaml up -d --no-build" in log
    assert log.count("exec -T grafana sh -ceu") == 3
    assert log.count("exec -T prometheus promtool check config") == 3
    assert log.count("kill -s SIGHUP prometheus") == 3
    assert log.index("image prune -f") < log.index("compose.monitoring.production.yaml pull")


def test_deploy_script_rejects_release_when_disk_preflight_fails(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_docker = fake_bin / "docker"
    fake_docker.write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\n"
        "if [[ ${1:-} == info ]]; then printf '%s\\n' \"$DOCKER_ROOT\"; exit 0; fi\n"
        'printf \'%s\\n\' "$*" >> "$DOCKER_LOG"\n',
        encoding="utf-8",
    )
    fake_docker.chmod(0o755)
    deploy_root = tmp_path / "deploy"
    _release(deploy_root, "release-1")
    docker_log = tmp_path / "docker.log"
    env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "DOCKER_LOG": str(docker_log),
        "DOCKER_ROOT": str(tmp_path),
        "MIN_FREE_DISK_MB": "999999999",
    }

    result = subprocess.run(  # noqa: S603
        [
            str(PROJECT_ROOT / "scripts" / "deploy_production.sh"),
            "deploy",
            str(deploy_root),
            "release-1",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode != 0
    assert "Insufficient disk space" in result.stderr
    assert "image prune -f" in docker_log.read_text(encoding="utf-8")
    assert "compose.monitoring.production.yaml pull" not in docker_log.read_text(encoding="utf-8")
    assert not (deploy_root / "current").exists()


def test_deploy_script_uses_self_hosted_overlay_and_checks_docker_disk(
    tmp_path: Path,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_docker = fake_bin / "docker"
    fake_docker.write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\n"
        "if [[ ${1:-} == info ]]; then printf '%s\\n' \"$DOCKER_ROOT\"; exit 0; fi\n"
        'printf \'%s\\n\' "$*" >> "$DOCKER_LOG"\n',
        encoding="utf-8",
    )
    fake_docker.chmod(0o755)
    deploy_root = tmp_path / "deploy"
    release = _release(deploy_root, "release-1")
    docker_log = tmp_path / "docker.log"
    env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "DOCKER_LOG": str(docker_log),
        "DOCKER_ROOT": str(tmp_path),
        "MIN_FREE_DISK_MB": "1",
        "MIN_DOCKER_FREE_DISK_MB": "999999999",
    }

    result = subprocess.run(  # noqa: S603
        [
            str(PROJECT_ROOT / "scripts" / "deploy_production.sh"),
            "deploy",
            str(deploy_root),
            "release-1",
            "self-hosted",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode != 0
    assert "Insufficient disk space" in result.stderr
    assert (release / ".deployment-mode").read_text(encoding="utf-8").strip() == "self-hosted"
    log = docker_log.read_text(encoding="utf-8")
    assert "compose.selfhost.yaml config -q" in log
    assert "compose.selfhost.yaml pull" not in log


def test_failed_initial_deploy_stops_partial_stack(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_docker = fake_bin / "docker"
    fake_docker.write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\n"
        "if [[ ${1:-} == info ]]; then printf '%s\\n' \"$DOCKER_ROOT\"; exit 0; fi\n"
        'printf \'%s\\n\' "$*" >> "$DOCKER_LOG"\n'
        "if [[ $* == *'exec -T api'* ]]; then exit 1; fi\n",
        encoding="utf-8",
    )
    fake_docker.chmod(0o755)
    deploy_root = tmp_path / "deploy"
    _release(deploy_root, "release-1")
    docker_log = tmp_path / "docker.log"
    env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "DOCKER_LOG": str(docker_log),
        "DOCKER_ROOT": str(tmp_path),
        "MIN_FREE_DISK_MB": "1",
        "HEALTHCHECK_ATTEMPTS": "1",
        "HEALTHCHECK_INTERVAL_SECONDS": "0",
    }

    result = subprocess.run(  # noqa: S603
        [
            str(PROJECT_ROOT / "scripts" / "deploy_production.sh"),
            "deploy",
            str(deploy_root),
            "release-1",
            "self-hosted",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode != 0
    assert "failed internal health checks" in result.stderr
    assert "stopping the failed stack" in result.stderr
    assert "compose.selfhost.yaml down --remove-orphans" in docker_log.read_text(encoding="utf-8")
    assert not (deploy_root / "current").exists()


def test_failed_grafana_credential_sync_stops_initial_stack(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_docker = fake_bin / "docker"
    fake_docker.write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\n"
        "if [[ ${1:-} == info ]]; then printf '%s\\n' \"$DOCKER_ROOT\"; exit 0; fi\n"
        'printf \'%s\\n\' "$*" >> "$DOCKER_LOG"\n'
        "if [[ $* == *'exec -T grafana'* ]]; then exit 1; fi\n",
        encoding="utf-8",
    )
    fake_docker.chmod(0o755)
    deploy_root = tmp_path / "deploy"
    _release(deploy_root, "release-1")
    docker_log = tmp_path / "docker.log"
    env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "DOCKER_LOG": str(docker_log),
        "DOCKER_ROOT": str(tmp_path),
        "MIN_FREE_DISK_MB": "1",
        "GRAFANA_CREDENTIAL_ATTEMPTS": "1",
        "GRAFANA_CREDENTIAL_INTERVAL_SECONDS": "0",
    }

    result = subprocess.run(  # noqa: S603
        [
            str(PROJECT_ROOT / "scripts" / "deploy_production.sh"),
            "deploy",
            str(deploy_root),
            "release-1",
            "self-hosted",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode != 0
    assert "failed to synchronize Grafana credentials" in result.stderr
    assert "stopping the failed stack" in result.stderr
    assert "compose.selfhost.yaml down --remove-orphans" in docker_log.read_text(encoding="utf-8")
    assert not (deploy_root / "current").exists()


def test_deploy_rejects_prometheus_tsdb_corruption_after_readiness(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_docker = fake_bin / "docker"
    fake_docker.write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\n"
        'printf \'%s\\n\' "$*" >> "$DOCKER_LOG"\n'
        "if [[ ${1:-} == info ]]; then printf '%s\\n' \"$DOCKER_ROOT\"; exit 0; fi\n"
        "if [[ $* == *' ps -q prometheus'* ]]; then\n"
        "  [[ -f \"$DOCKER_STATE\" ]] && printf 'prometheus-container\\n'\n"
        "  exit 0\n"
        "fi\n"
        "if [[ $* == *' up -d --no-build --remove-orphans'* ]]; then\n"
        '  touch "$DOCKER_STATE"\n'
        "  exit 0\n"
        "fi\n"
        "if [[ ${1:-} == inspect && $* == *'.State.StartedAt'* ]]; then\n"
        "  printf '2026-07-24T17:15:16.000000000Z\\n'\n"
        "  exit 0\n"
        "fi\n"
        "if [[ ${1:-} == logs ]]; then\n"
        "  printf 'Loading on-disk chunks failed\\n' >&2\n"
        "  exit 0\n"
        "fi\n",
        encoding="utf-8",
    )
    fake_docker.chmod(0o755)
    deploy_root = tmp_path / "deploy"
    _release(deploy_root, "release-1")
    docker_log = tmp_path / "docker.log"
    env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "DOCKER_LOG": str(docker_log),
        "DOCKER_ROOT": str(tmp_path),
        "DOCKER_STATE": str(tmp_path / "docker.state"),
        "MIN_FREE_DISK_MB": "1",
        "HEALTHCHECK_ATTEMPTS": "1",
        "HEALTHCHECK_INTERVAL_SECONDS": "0",
    }

    result = subprocess.run(  # noqa: S603
        [
            str(PROJECT_ROOT / "scripts" / "deploy_production.sh"),
            "deploy",
            str(deploy_root),
            "release-1",
            "self-hosted",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode != 0
    assert "failed Prometheus TSDB startup checks" in result.stderr
    assert not (deploy_root / "current").exists()
    log = docker_log.read_text(encoding="utf-8")
    assert log.index("exec -T api") < log.index("logs --since")
    assert "compose.selfhost.yaml down --remove-orphans" in log


def test_failed_rollback_restores_the_active_release(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_docker = fake_bin / "docker"
    fake_docker.write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\n"
        'printf \'%s %s\\n\' "$PWD" "$*" >> "$DOCKER_LOG"\n'
        "if [[ $PWD == */release-1 && $* == *'exec -T api'* ]]; then exit 1; fi\n",
        encoding="utf-8",
    )
    fake_docker.chmod(0o755)
    deploy_root = tmp_path / "deploy"
    previous = _release(deploy_root, "release-1")
    current = _release(deploy_root, "release-2")
    (previous / ".deployment-mode").write_text("self-hosted\n", encoding="utf-8")
    (current / ".deployment-mode").write_text("self-hosted\n", encoding="utf-8")
    (deploy_root / "current").symlink_to(current)
    (deploy_root / ".previous-release").write_text(str(previous), encoding="utf-8")
    docker_log = tmp_path / "docker.log"
    env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "DOCKER_LOG": str(docker_log),
        "HEALTHCHECK_ATTEMPTS": "1",
        "HEALTHCHECK_INTERVAL_SECONDS": "0",
    }

    result = subprocess.run(  # noqa: S603
        [
            str(PROJECT_ROOT / "scripts" / "deploy_production.sh"),
            "rollback",
            str(deploy_root),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode != 0
    assert "Rollback target failed internal health checks" in result.stderr
    assert (deploy_root / "current").resolve() == current
    log = docker_log.read_text(encoding="utf-8")
    assert f"{previous} compose" in log
    assert f"{current} compose" in log
    assert (deploy_root / ".previous-release").exists()


def test_abort_stops_failed_initial_release(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_docker = fake_bin / "docker"
    fake_docker.write_text(
        '#!/usr/bin/env bash\nset -euo pipefail\nprintf \'%s\\n\' "$*" >> "$DOCKER_LOG"\n',
        encoding="utf-8",
    )
    fake_docker.chmod(0o755)
    deploy_root = tmp_path / "deploy"
    release = _release(deploy_root, "release-1")
    (release / ".deployment-mode").write_text("self-hosted\n", encoding="utf-8")
    (deploy_root / "current").symlink_to(release)
    docker_log = tmp_path / "docker.log"
    env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "DOCKER_LOG": str(docker_log),
    }

    subprocess.run(  # noqa: S603
        [
            str(PROJECT_ROOT / "scripts" / "deploy_production.sh"),
            "abort",
            str(deploy_root),
        ],
        check=True,
        env=env,
    )

    assert not (deploy_root / "current").exists()
    assert "compose.selfhost.yaml down --remove-orphans" in docker_log.read_text(encoding="utf-8")


def test_release_cleanup_preserves_rollback_and_scopes_image_pruning(
    tmp_path: Path,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_docker = fake_bin / "docker"
    fake_docker.write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\n"
        "if [[ ${1:-} == image && ${2:-} == ls ]]; then\n"
        "  printf '%s\\n' \"$DOCKER_IMAGES\"\n"
        "  exit 0\n"
        "fi\n"
        "if [[ ${1:-} == container && ${2:-} == ls ]]; then\n"
        "  printf '%s\\n' \"${DOCKER_CONTAINER_IMAGES:-}\"\n"
        "  exit 0\n"
        "fi\n"
        'printf \'%s\\n\' "$*" >> "$DOCKER_LOG"\n',
        encoding="utf-8",
    )
    fake_docker.chmod(0o755)
    deploy_root = tmp_path / "deploy"
    releases: list[Path] = []
    image_refs: list[list[str]] = []
    for index in range(7):
        release = _release(deploy_root, f"release-{index}")
        sha = f"{index:040x}"
        refs = [
            f"ghcr.io/example/jobradarvn-{component}:{sha}"
            for component in ("backend", "ml", "web")
        ]
        (release / ".env").write_text(
            "\n".join(
                (
                    f"BACKEND_IMAGE={refs[0]}",
                    f"ML_IMAGE={refs[1]}",
                    f"WEB_IMAGE={refs[2]}",
                )
            )
            + "\n",
            encoding="utf-8",
        )
        timestamp = 1_700_000_000 + index
        os.utime(release, (timestamp, timestamp))
        releases.append(release)
        image_refs.append(refs)

    (deploy_root / "current").symlink_to(releases[0])
    (deploy_root / ".previous-release").write_text(f"{releases[1]}\n", encoding="utf-8")
    unrelated = "ghcr.io/example/unrelated:latest"
    other_owner = f"ghcr.io/other/jobradarvn-backend:{'f' * 40}"
    in_use = image_refs[2][0]
    docker_log = tmp_path / "docker.log"
    env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "DOCKER_IMAGES": "\n".join(
            [ref for refs in image_refs for ref in refs] + [unrelated, other_owner]
        ),
        "DOCKER_CONTAINER_IMAGES": in_use,
        "DOCKER_LOG": str(docker_log),
    }

    subprocess.run(  # noqa: S603
        [
            str(PROJECT_ROOT / "scripts" / "prune_production_releases.sh"),
            str(deploy_root),
            "3",
        ],
        check=True,
        env=env,
    )

    for index in (0, 1, 4, 5, 6):
        assert releases[index].is_dir()
    for index in (2, 3):
        assert not releases[index].exists()

    log = docker_log.read_text(encoding="utf-8")
    for index in (2, 3):
        for ref in image_refs[index]:
            if ref == in_use:
                assert f"image rm {ref}" not in log
            else:
                assert f"image rm {ref}" in log
    for index in (0, 1, 4, 5, 6):
        for ref in image_refs[index]:
            assert f"image rm {ref}" not in log
    assert unrelated not in log
    assert other_owner not in log
    assert "image prune -f" in log


def test_release_cleanup_aborts_before_deletion_on_unsafe_metadata(
    tmp_path: Path,
) -> None:
    deploy_root = tmp_path / "deploy"
    stale = _release(deploy_root, "release-stale")
    current = _release(deploy_root, "release-current")
    (current / ".env").write_text(
        "BACKEND_IMAGE=ubuntu:latest\n"
        f"ML_IMAGE=ghcr.io/example/jobradarvn-ml:{'a' * 40}\n"
        f"WEB_IMAGE=ghcr.io/example/jobradarvn-web:{'b' * 40}\n",
        encoding="utf-8",
    )
    os.utime(stale, (1_700_000_000, 1_700_000_000))
    os.utime(current, (1_700_000_001, 1_700_000_001))
    (deploy_root / "current").symlink_to(current)

    result = subprocess.run(  # noqa: S603
        [
            str(PROJECT_ROOT / "scripts" / "prune_production_releases.sh"),
            str(deploy_root),
            "1",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "Unsafe production image reference" in result.stderr
    assert current.is_dir()
    assert stale.is_dir()


def test_deploy_workflow_propagates_every_scraper_flag() -> None:
    workflow = (PROJECT_ROOT / ".github/workflows/deploy.yml").read_text(encoding="utf-8")

    assert "SCRAPER_CONTACT_EMAIL: ${{ vars.SCRAPER_CONTACT_EMAIL" in workflow
    assert "printf 'SCRAPER_CONTACT_EMAIL=%s\\n' \"$SCRAPER_CONTACT_EMAIL\"" in workflow

    for flag in (
        "ENABLE_ITVIEC_SCRAPER",
        "ENABLE_TOPCV_SCRAPER",
        "ENABLE_VIETNAMWORKS_SCRAPER",
    ):
        assert f"{flag}: ${{{{ vars.{flag} || 'false' }}}}" in workflow
        assert f'[[ "${flag}" =~ ^(true|false)$ ]]' in workflow
        assert f"printf '{flag}=%s\\n' \"${flag}\"" in workflow

    assert "scripts/prune_production_releases.sh" in workflow
    assert (
        'bash "$DEPLOY_ROOT/current/scripts/prune_production_releases.sh" "$DEPLOY_ROOT" 5'
    ) in workflow

    ci_workflow = (PROJECT_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert (
        "docker://rhysd/actionlint@sha256:"
        "b1934ee5f1c509618f2508e6eb47ee0d3520686341fec936f3b79331f9315667"
    ) in ci_workflow


def test_release_and_deploy_are_separate_chained_gates() -> None:
    release = (PROJECT_ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    deploy = (PROJECT_ROOT / ".github/workflows/deploy.yml").read_text(encoding="utf-8")

    assert "workflows: [CI]" in release
    assert "push: true" in release
    assert "\n  deploy:" not in release
    assert "workflows: [Release]" in deploy
    assert "github.event.workflow_run.conclusion == 'success'" in deploy
    assert "packages: read" in deploy
    assert "Verify private HTTPS production routes" in deploy
    assert "Roll back or stop failed release" in deploy
    assert "if: failure() && steps.smoke.outcome == 'failure'" in deploy
    assert 'deploy_production.sh" abort "$DEPLOY_ROOT"' in deploy
    assert "steps.deploy.outcome == 'failure'" not in deploy
    assert "continue-on-error:" not in deploy


def test_deploy_temporarily_authorizes_only_the_hosted_runner() -> None:
    deploy = (PROJECT_ROOT / ".github/workflows/deploy-hcloud.yml").read_text(encoding="utf-8")

    assert "HCLOUD_TOKEN: ${{ secrets.HCLOUD_TOKEN }}" in deploy
    assert "HCLOUD_FIREWALL_NAME: ${{ vars.HCLOUD_FIREWALL_NAME" in deploy
    assert '"${HCLOUD_TOKEN:?HCLOUD_TOKEN is required}"' in deploy
    assert "manage_deploy_firewall.py authorize" in deploy
    assert 'echo "cidr=$cidr" >> "$GITHUB_OUTPUT"' in deploy
    assert "if: always() && steps.release.outcome == 'success'" in deploy
    assert "manage_deploy_firewall.py revoke" in deploy
    assert "workflow_dispatch:" in deploy
    assert "workflow_run:" not in deploy


def test_primary_deploy_uses_private_self_hosted_ingress() -> None:
    deploy = (PROJECT_ROOT / ".github/workflows/deploy.yml").read_text(encoding="utf-8")
    ci = (PROJECT_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    overlay = (PROJECT_ROOT / "compose.selfhost.yaml").read_text(encoding="utf-8")
    monitoring = (PROJECT_ROOT / "compose.monitoring.production.yaml").read_text(encoding="utf-8")
    actionlint = (PROJECT_ROOT / ".github/actionlint.yaml").read_text(encoding="utf-8")

    assert "runs-on: [self-hosted, linux, x64, jobradar-production]" in deploy
    assert "DOMAIN: ${{ vars.DOMAIN }}" in deploy
    assert "DOMAIN: ${{ secrets.DOMAIN }}" not in deploy
    assert "tailscale status --json" in deploy
    assert "self-hosted" in deploy
    assert "HCLOUD_TOKEN" not in deploy
    assert "PRODUCTION_SSH_KEY" not in deploy
    assert '"127.0.0.1:3000:3000"' in overlay
    assert "profiles: [public-ingress]" in overlay
    assert "driver: local" in overlay
    assert 'max-size: "10m"' in overlay
    assert 'user: "${BACKUP_UID:-1000}:${BACKUP_GID:-1000}"' in (
        PROJECT_ROOT / "compose.production.yaml"
    ).read_text(encoding="utf-8")
    assert "Validate private self-hosted ingress" in ci
    assert '(.services.backup.user == "1000:1000")' in ci
    assert '.services.backup.depends_on.migrate.condition == "service_completed_successfully"' in ci
    assert '.services.prometheus.depends_on["prometheus-config"].condition' in ci
    assert 'select(.target == "/etc/prometheus") | .type' in ci
    assert "prometheus_config:/etc/prometheus:ro" in monitoring
    assert "condition: service_completed_successfully" in monitoring
    assert '(.services | has("caddy") | not)' in ci
    assert 'all(. == "local")' in ci
    assert "jobradar-production" in actionlint


def test_deploy_keeps_runtime_config_readable_with_a_restrictive_runner_umask() -> None:
    workflow = (PROJECT_ROOT / ".github/workflows/deploy.yml").read_text(encoding="utf-8")

    assert 'find "$release_dir/infra" -type d -exec chmod 755 {} +' in workflow
    assert 'find "$release_dir/infra" -type f -exec chmod 644 {} +' in workflow
    assert 'chmod 644 "$release_dir/scripts/backup_loop.sh"' in workflow
    assert 'chmod 600 "$release_dir/.env"' in workflow
    assert "printf 'BACKUP_UID=%s\\n' \"$(id -u)\"" in workflow
    assert "printf 'BACKUP_GID=%s\\n' \"$(id -g)\"" in workflow


def test_deploy_synchronizes_and_verifies_grafana_admin_credentials() -> None:
    script = (PROJECT_ROOT / "scripts/deploy_production.sh").read_text(encoding="utf-8")

    assert "grafana cli admin reset-admin-password --password-from-stdin" in script
    assert "http://127.0.0.1:3000/api/user" in script
    assert script.count("sync_grafana_admin_credentials") == 4
    assert "promtool check config /etc/prometheus/prometheus.yml" in script
    assert script.count("reload_prometheus_configuration") == 4
    assert ".State.StartedAt" in script
    assert "Loading on-disk chunks failed" in script


def test_release_images_preserve_source_revision() -> None:
    workflow = (PROJECT_ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")

    assert "build-args: SOURCE_REVISION=${{ env.RELEASE_SHA }}" in workflow
    for dockerfile in ("Dockerfile", "Dockerfile.ml", "web/Dockerfile"):
        contents = (PROJECT_ROOT / dockerfile).read_text(encoding="utf-8")
        assert "ARG SOURCE_REVISION=local" in contents
        assert "SOURCE_REVISION=$SOURCE_REVISION" in contents
        assert "org.opencontainers.image.revision=$SOURCE_REVISION" in contents


def test_dependency_and_release_image_security_gates_are_enforced() -> None:
    ci = (PROJECT_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    release = (PROJECT_ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    compose = (PROJECT_ROOT / "compose.yaml").read_text(encoding="utf-8")

    assert "uv run python scripts/audit_python_dependencies.py" in ci
    assert "Scan immutable release image" in release
    assert "aquasec/trivy@sha256:" in release
    assert "--format json" in release
    assert "--severity HIGH,CRITICAL" in release
    assert "--scanners vuln,secret" in release
    assert "scripts/enforce_container_security_report.py" in release
    assert '--expected-image "$IMAGE"' in release
    assert "container-security-${{ matrix.image }}" in release
    assert "--ignore-unfixed" not in release
    assert "continue-on-error:" not in release
    assert "MLFLOW_TRACKING_URI: sqlite:///artifacts/release-mlflow.db" in release
    assert "MLFLOW_ALLOW_FILE_STORE" not in release
    assert 'MLFLOW_SERVER_ENABLE_JOB_EXECUTION: "false"' in compose
    assert 'UV_VERSION: "0.12.5"' in ci
    assert 'UV_VERSION: "0.12.5"' in release
    for dockerfile in ("Dockerfile", "Dockerfile.ml"):
        contents = (PROJECT_ROOT / dockerfile).read_text(encoding="utf-8")
        assert "ARG UV_VERSION=0.12.5" in contents
        assert "pip uninstall --yes uv" in contents
    web_dockerfile = (PROJECT_ROOT / "web/Dockerfile").read_text(encoding="utf-8")
    assert web_dockerfile.count("FROM node:24-alpine") == 3
    assert "apk upgrade --no-cache" in web_dockerfile
    assert "rm -rf /usr/local/lib/node_modules/npm" in web_dockerfile


def test_release_builds_and_installs_a_revision_bound_salary_model() -> None:
    workflow = (PROJECT_ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    compose = (PROJECT_ROOT / "compose.yaml").read_text(encoding="utf-8")
    production = (PROJECT_ROOT / "compose.production.yaml").read_text(encoding="utf-8")
    deploy = (PROJECT_ROOT / "scripts/deploy_production.sh").read_text(encoding="utf-8")

    assert "uv run python scripts/train_salary_release.py" in workflow
    assert "name: salary-model-${{ env.RELEASE_SHA }}" in workflow
    assert "path: ml/model_seed/current" in workflow
    assert "needs: model" in workflow
    assert "scripts/install_salary_model.py ml/model_seed/current" in compose
    assert "condition: service_completed_successfully" in compose
    assert 'REQUIRE_SALARY_MODEL: "true"' in production
    assert "SALARY_MODEL_ARTIFACT_DIR" in production
    assert "['model_available'] is True" in deploy


def test_web_image_supports_apps_without_public_assets() -> None:
    dockerfile = (PROJECT_ROOT / "web" / "Dockerfile").read_text(encoding="utf-8")

    create_public = dockerfile.index("RUN mkdir -p public")
    build_application = dockerfile.index("RUN npm run build")
    copy_public = dockerfile.index("COPY --from=builder /app/public ./public")

    assert create_public < build_application < copy_public


def test_e2e_api_does_not_hold_the_uv_cache_lock_during_cleanup() -> None:
    workflow = (PROJECT_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    e2e_job = workflow.split("  e2e:", maxsplit=1)[1].split("\n  ml-contract:", maxsplit=1)[0]

    assert "enable-cache: false" in e2e_job
    assert ".venv/bin/uvicorn api.main:app" in e2e_job
    assert "uv run uvicorn" not in e2e_job


def test_test_jobs_fetch_history_for_evidence_provenance() -> None:
    workflow = (PROJECT_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    backend_job = workflow.split("  backend:", maxsplit=1)[1].split("\n  frontend:", maxsplit=1)[0]
    contract_job = workflow.split("  ml-contract:", maxsplit=1)[1].split(
        "\n  ml-publication:", maxsplit=1
    )[0]

    assert "fetch-depth: 0" in backend_job
    assert "fetch-depth: 0" in contract_job


def test_collector_overlay_restarts_only_long_running_services() -> None:
    overlay = yaml.safe_load((PROJECT_ROOT / "compose.collector.yaml").read_text(encoding="utf-8"))

    assert set(overlay["services"]) == {
        "db",
        "redis",
        "api",
        "worker",
        "ml-worker",
        "ml-api",
        "mlflow",
        "beat",
        "web",
    }
    assert all(service["restart"] == "unless-stopped" for service in overlay["services"].values())


class _SmokeHandler(BaseHTTPRequestHandler):
    paths: list[str] = []

    def do_GET(self) -> None:  # noqa: N802
        self.paths.append(self.path)
        if self.path == "/health/ready":
            body = b'{"status":"ready"}'
        elif self.path == "/version":
            body = f'{{"source_revision":"{TEST_REVISION}"}}'.encode()
        else:
            body = b"{}"
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        return


def test_production_smoke_checks_public_routes() -> None:
    _SmokeHandler.paths = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _SmokeHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        subprocess.run(  # noqa: S603
            [
                str(PROJECT_ROOT / "scripts" / "production_smoke.sh"),
                f"http://127.0.0.1:{server.server_port}",
                TEST_REVISION,
            ],
            check=True,
        )
    finally:
        server.shutdown()
        thread.join()
        server.server_close()

    assert _SmokeHandler.paths == [
        "/health/ready",
        "/version",
        "/",
        "/api/jobs?limit=1",
        "/api/salary/bands",
    ]

    next_config = (PROJECT_ROOT / "web" / "next.config.mjs").read_text(encoding="utf-8")
    assert '{source: "/version", destination: `${apiBase}/version`}' in next_config


def test_backup_loop_writes_complete_restricted_dump(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_pg_dump = fake_bin / "pg_dump"
    fake_pg_dump.write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\n"
        'for argument in "$@"; do\n'
        "  case $argument in --file=*) printf 'postgres-dump' > \"${argument#--file=}\";; esac\n"
        "done\n",
        encoding="utf-8",
    )
    fake_pg_dump.chmod(0o755)
    backup_dir = tmp_path / "backups"
    env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "BACKUP_DIR": str(backup_dir),
        "BACKUP_RUN_ONCE": "true",
    }

    subprocess.run(  # noqa: S603
        [str(PROJECT_ROOT / "scripts" / "backup_loop.sh")], check=True, env=env
    )

    dumps = list(backup_dir.glob("jobradarvn-*.dump"))
    assert len(dumps) == 1
    assert dumps[0].read_text(encoding="utf-8") == "postgres-dump"
    assert dumps[0].stat().st_mode & 0o777 == 0o600
    assert not list(backup_dir.glob("*.partial"))
