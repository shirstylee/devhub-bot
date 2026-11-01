from importlib import metadata
from pathlib import Path
import re
import unittest


BASE_DIR = Path(__file__).resolve().parent.parent
PIN = re.compile(r"([A-Za-z0-9_.-]+)(?:\[[^\]]+\])?==([0-9]+(?:\.[0-9]+)*)")


def canonical_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def read_pins(filename: str) -> dict[str, str]:
    pins = {}
    for line in (BASE_DIR / filename).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith(("#", "-c ")):
            continue
        match = PIN.fullmatch(line)
        if match is None:
            raise ValueError(f"Expected an exact stable version in {filename}: {line}")
        name, version = match.groups()
        name = canonical_name(name)
        if name in pins:
            raise ValueError(f"Duplicate package in {filename}: {name}")
        pins[name] = version
    return pins


class DependencySecurityTests(unittest.TestCase):
    def test_both_installation_manifests_apply_transitive_constraints(self) -> None:
        for filename in ("requirements.txt", "requirements-tools.txt"):
            with self.subTest(filename=filename):
                lines = (BASE_DIR / filename).read_text(encoding="utf-8").splitlines()
                self.assertIn("-c constraints.txt", lines)

    def test_declared_versions_match_the_verified_snapshot(self) -> None:
        constraints = read_pins("constraints.txt")
        for filename in ("requirements.txt", "requirements-tools.txt"):
            for name, version in read_pins(filename).items():
                with self.subTest(filename=filename, package=name):
                    self.assertEqual(constraints.get(name), version)

    def test_known_vulnerable_versions_cannot_be_reintroduced(self) -> None:
        floors = {
            "pillow": "13.0.0",
            "aiohttp": "3.14.4",
            "brotli": "1.2.1",
            "certifi": "2026.10.19",
            "multidict": "6.9.1",
            "setuptools": "84.1.0",
        }
        constraints = read_pins("constraints.txt")
        for name, minimum in floors.items():
            with self.subTest(package=name):
                actual = tuple(map(int, constraints[name].split(".")))
                expected = tuple(map(int, minimum.split(".")))
                self.assertGreaterEqual(actual, expected)

    def test_installed_runtime_matches_declared_versions(self) -> None:
        for name, version in read_pins("requirements.txt").items():
            with self.subTest(package=name):
                self.assertEqual(metadata.version(name), version,
                                 "Update this environment with python -m pip install -r requirements.txt")

    def test_installed_transitive_and_optional_packages_match_snapshot(self) -> None:
        for name, version in read_pins("constraints.txt").items():
            try:
                installed = metadata.version(name)
            except metadata.PackageNotFoundError:
                # Optional tools/platform-specific packages need not be present.
                continue
            with self.subTest(package=name):
                self.assertEqual(installed, version,
                                 "Reinstall dependencies from the checked-in requirements files")
